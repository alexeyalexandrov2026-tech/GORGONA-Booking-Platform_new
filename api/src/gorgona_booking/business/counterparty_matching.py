"""Duplicate and booking-customer suggestions for counterparties (ADR-0020, §12.4).

Normalization happens in SQL with the same expressions on both sides, so a suggestion
never depends on Python and PostgreSQL agreeing about case or whitespace. Equal
e-mail, phone digits, tax identifier or registration number is a strong reason; an
equal name is only a weak one. Nothing here writes: a person decides.
"""

from typing import Any
from uuid import UUID

from gorgona_booking.business.counterparty_contracts import (
    STRONG_REASONS,
    BookingCandidate,
    BookingCandidateList,
    BookingSummary,
    LinkBasis,
    MatchCandidate,
    MatchCheckInput,
    MatchList,
    MatchReason,
)
from gorgona_booking.db.pool import RuntimeConnection

# Latest version of every record of the business with its normalized match keys.
_KEYS = """
latest as (
    select distinct on (v.counterparty_id) v.*
    from gba.counterparty_versions v
    where v.tenant_id = %(business)s
    order by v.counterparty_id, v.revision desc
),
keys as (
    select l.counterparty_id, l.display_name, l.state, l.name_key,
        nullif(upper(regexp_replace(l.tax_id, '[^A-Za-z0-9]', '', 'g')), '') as tax_key,
        nullif(upper(regexp_replace(l.registration_number, '[^A-Za-z0-9]', '', 'g')), '')
            as registration_key,
        array(
            select x from (
                select l.email union
                select c.email from gba.counterparty_version_contacts c
                where c.tenant_id = l.tenant_id and c.counterparty_id = l.counterparty_id
                  and c.revision = l.revision
            ) s(x) where x is not null
        ) as emails,
        array(
            select x from (
                select l.phone_digits union
                select c.phone_digits from gba.counterparty_version_contacts c
                where c.tenant_id = l.tenant_id and c.counterparty_id = l.counterparty_id
                  and c.revision = l.revision
            ) s(x) where x is not null
        ) as phones
    from latest l
)"""

_PROBE_FROM_INPUT = """
probe as (
    select
        array(select distinct lower(btrim(e)) from unnest(%(emails)s::text[]) e) as emails,
        array(
            select distinct d from (
                select nullif(regexp_replace(p, '[^0-9]', '', 'g'), '') as d
                from unnest(%(phones)s::text[]) p
            ) s where d is not null
        ) as phones,
        lower(regexp_replace(btrim(%(name)s::text), '[[:space:]]+', ' ', 'g')) as name_key,
        nullif(upper(regexp_replace(%(tax)s::text, '[^A-Za-z0-9]', '', 'g')), '') as tax_key,
        nullif(upper(regexp_replace(%(registration)s::text, '[^A-Za-z0-9]', '', 'g')), '')
            as registration_key
)"""

_PROBE_FROM_RECORD = """
probe as (
    select emails, phones, name_key, tax_key, registration_key
    from keys where counterparty_id = %(exclude)s
)"""

_CANDIDATES = """
select k.counterparty_id, c.kind, k.display_name, k.state,
    k.emails && p.emails, k.phones && p.phones,
    coalesce(k.tax_key = p.tax_key, false),
    coalesce(k.registration_key = p.registration_key, false),
    coalesce(k.name_key = p.name_key, false)
from keys k
cross join probe p
join gba.counterparties c on c.tenant_id = %(business)s and c.id = k.counterparty_id
where k.state <> 'merged'
  and k.counterparty_id is distinct from %(exclude)s
  and (k.emails && p.emails or k.phones && p.phones or k.tax_key = p.tax_key
       or k.registration_key = p.registration_key or k.name_key = p.name_key)
  and not exists (
      select 1 from gba.counterparty_match_decisions d
      where d.tenant_id = %(business)s and d.kind = 'distinct'
        and least(d.counterparty_id, d.other_counterparty_id)
            = least(k.counterparty_id, %(exclude)s)
        and greatest(d.counterparty_id, d.other_counterparty_id)
            = greatest(k.counterparty_id, %(exclude)s)
  )
order by (k.emails && p.emails or k.phones && p.phones or k.tax_key = p.tax_key
          or k.registration_key = p.registration_key) desc,
         k.name_key, k.counterparty_id
limit 50
"""

_REASONS: tuple[MatchReason, ...] = ("email", "phone", "tax_id", "registration_number", "name")


def _match_list(business_id: UUID, rows: list[tuple[Any, ...]]) -> MatchList:
    items = []
    for row in rows:
        reasons = tuple(reason for reason, hit in zip(_REASONS, row[4:9], strict=True) if hit)
        items.append(
            MatchCandidate(
                counterparty_id=row[0],
                kind=row[1],
                display_name=row[2],
                state=row[3],
                reasons=reasons,
                strength="strong" if STRONG_REASONS & set(reasons) else "weak",
            )
        )
    return MatchList(business_id=business_id, items=tuple(items))


async def check_matches(
    conn: RuntimeConnection, business_id: UUID, probe: MatchCheckInput
) -> MatchList:
    rows = await (
        await conn.execute(
            f"with {_KEYS}, {_PROBE_FROM_INPUT} {_CANDIDATES}",
            {
                "business": business_id,
                "emails": list(probe.emails),
                "phones": list(probe.phones),
                "name": probe.display_name,
                "tax": probe.tax_id,
                "registration": probe.registration_number,
                "exclude": probe.exclude_id,
            },
        )
    ).fetchall()
    return _match_list(business_id, rows)


async def find_duplicates(
    conn: RuntimeConnection, business_id: UUID, counterparty_id: UUID
) -> MatchList:
    rows = await (
        await conn.execute(
            f"with {_KEYS}, {_PROBE_FROM_RECORD} {_CANDIDATES}",
            {"business": business_id, "exclude": counterparty_id},
        )
    ).fetchall()
    return _match_list(business_id, rows)


# Latest link of every booking; a booking is free when it has none or it was unlinked.
_LATEST_LINKS = """
latest_links as (
    select distinct on (l.booking_id) l.booking_id, l.sequence, l.action, l.counterparty_id
    from gba.counterparty_booking_links l
    where l.tenant_id = %(business)s
    order by l.booking_id, l.sequence desc
)"""

_BOOKING_MATCH = """
    lower(btrim(bc.email)) = any(s.emails),
    nullif(regexp_replace(bc.phone, '[^0-9]', '', 'g'), '') = any(s.phones)
"""

_BOOKING_CANDIDATES = f"""
with {_KEYS}, {_LATEST_LINKS}
select bc.booking_id, b.starts_at, b.status, bc.customer_name, bc.email, bc.phone,
    {_BOOKING_MATCH}, ll.sequence, ll.action
from gba.booking_customers bc
join gba.bookings b on b.tenant_id = bc.tenant_id and b.id = bc.booking_id
join keys s on s.counterparty_id = %(subject)s
left join latest_links ll on ll.booking_id = bc.booking_id
where bc.tenant_id = %(business)s and bc.email is not null
  and (%(bookings)s::uuid[] is null or bc.booking_id = any(%(bookings)s::uuid[]))
  and (%(bookings)s::uuid[] is not null or ll.action is distinct from 'linked')
  and (lower(btrim(bc.email)) = any(s.emails)
       or nullif(regexp_replace(bc.phone, '[^0-9]', '', 'g'), '') = any(s.phones))
order by b.starts_at desc, bc.booking_id
limit %(limit)s
"""  # noqa: S608 - fixed fragments


def basis_of(by_email: bool, by_phone: bool) -> tuple[LinkBasis, ...]:
    basis: list[LinkBasis] = []
    if by_email:
        basis.append("email")
    if by_phone:
        basis.append("phone")
    return tuple(basis)


def booking_summary(row: tuple[Any, ...]) -> BookingSummary:
    return BookingSummary(
        booking_id=row[0],
        starts_at=row[1],
        status=row[2],
        customer_name=row[3],
        email=row[4],
        phone=row[5],
    )


async def booking_matches(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    booking_ids: tuple[UUID, ...] | None,
    limit: int,
) -> list[tuple[Any, ...]]:
    """Bookings whose customer details match the record: (summary..., by_email, by_phone,
    latest link sequence, latest link action). Without explicit ids, linked bookings are
    left out."""
    return await (
        await conn.execute(
            _BOOKING_CANDIDATES,
            {
                "business": business_id,
                "subject": counterparty_id,
                "bookings": list(booking_ids) if booking_ids is not None else None,
                "limit": limit,
            },
        )
    ).fetchall()


async def booking_candidates(
    conn: RuntimeConnection, business_id: UUID, counterparty_id: UUID
) -> BookingCandidateList:
    rows = await booking_matches(conn, business_id, counterparty_id, booking_ids=None, limit=100)
    items = tuple(
        BookingCandidate(booking=booking_summary(row), basis=basis_of(row[6], row[7]))
        for row in rows
    )
    return BookingCandidateList(
        business_id=business_id, counterparty_id=counterparty_id, items=items
    )
