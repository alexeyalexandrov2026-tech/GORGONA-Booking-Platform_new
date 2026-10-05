"""Company-owned counterparties: append-only cards, decisions and booking links (ADR-0020).

Callers hold the per-business `counterparties` lock before the membership share lock.
Every command claims its key, replays a stored receipt (references only) for the same
body, checks the module, writes, audits without personal data and stores its receipt in
one transaction. Nothing is updated or deleted.
"""

from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.counterparty_contracts import (
    BookingLinkHistory,
    BookingLinkReceipt,
    BookingLinkResult,
    BookingLinkView,
    ContactView,
    CounterpartyHistory,
    CounterpartyInput,
    CounterpartyList,
    CounterpartyReceipt,
    CounterpartyRevision,
    CounterpartyState,
    CounterpartySummary,
    CounterpartyView,
    DistinctInput,
    LinkBookingsInput,
    LinkedBooking,
    LinkedBookingList,
    MatchDecisionList,
    MatchDecisionReceipt,
    MatchDecisionView,
    MergeInput,
    SeparateInput,
    UnlinkBookingInput,
)
from gorgona_booking.business.counterparty_matching import (
    basis_of,
    booking_matches,
    booking_summary,
)
from gorgona_booking.business.module_gate import (
    COUNTERPARTIES_MODULE,
    module_writes,
    require_module,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError


class CounterpartyStateError(ConflictError):
    code = "COUNTERPARTY_STATE_INVALID"


class MergeNotAllowedError(ConflictError):
    code = "MERGE_NOT_ALLOWED"


class BookingAlreadyLinkedError(ConflictError):
    code = "BOOKING_ALREADY_LINKED"


class BookingNotACandidateError(ConflictError):
    code = "BOOKING_NOT_A_CANDIDATE"


_SAVE = "business.counterparty.save"
_DECIDE = "business.counterparty.match_decision"
_LINK = "business.counterparty.booking_link"
_TARGET = "counterparty"


def _not_found() -> NotFoundError:
    return NotFoundError("Counterparty not found")


async def load_counterparty(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    revision: int | None = None,
) -> CounterpartyView | None:
    row = await (
        await conn.execute(
            "select c.kind, v.revision, v.display_name, v.legal_name, v.tax_id, "
            "v.registration_number, v.email, v.phone, v.roles, v.state, v.merged_into, "
            "v.created_at "
            "from gba.counterparties c join gba.counterparty_versions v "
            "on v.tenant_id = c.tenant_id and v.counterparty_id = c.id "
            "where c.tenant_id = %s and c.id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (business_id, counterparty_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    contacts = await (
        await conn.execute(
            "select position, name, job_title, email, phone "
            "from gba.counterparty_version_contacts "
            "where tenant_id = %s and counterparty_id = %s and revision = %s "
            "order by position",
            (business_id, counterparty_id, row[1]),
        )
    ).fetchall()
    return CounterpartyView(
        business_id=business_id,
        counterparty_id=counterparty_id,
        kind=row[0],
        revision=row[1],
        display_name=row[2],
        legal_name=row[3],
        tax_id=row[4],
        registration_number=row[5],
        email=row[6],
        phone=row[7],
        roles=tuple(row[8]),
        state=row[9],
        merged_into=row[10],
        contacts=tuple(
            ContactView(position=c[0], name=c[1], job_title=c[2], email=c[3], phone=c[4])
            for c in contacts
        ),
        created_at=row[11],
    )


async def _require(
    conn: RuntimeConnection, business_id: UUID, counterparty_id: UUID
) -> CounterpartyView:
    current = await load_counterparty(conn, business_id, counterparty_id)
    if current is None:
        raise _not_found()
    return current


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_counterparties(
    conn: RuntimeConnection,
    business_id: UUID,
    *,
    query: str | None,
    state: CounterpartyState | None,
    after: UUID | None,
    limit: int,
) -> CounterpartyList:
    """Alphabetical by normalized name; without a state, merged records are left out."""
    digits = "".join(ch for ch in query if ch.isdigit()) if query else ""
    rows = await (
        await conn.execute(
            "with latest as (select distinct on (v.counterparty_id) v.counterparty_id, "
            "v.revision, v.display_name, v.legal_name, v.email, v.phone_digits, v.name_key, "
            "v.roles, v.state, v.merged_into from gba.counterparty_versions v "
            "where v.tenant_id = %(business)s order by v.counterparty_id, v.revision desc) "
            "select l.counterparty_id, c.kind, l.revision, l.display_name, l.roles, l.state, "
            "l.merged_into from latest l join gba.counterparties c "
            "on c.tenant_id = %(business)s and c.id = l.counterparty_id "
            "where (case when %(state)s::text is null then l.state <> 'merged' "
            "else l.state = %(state)s end) "
            "and (%(pattern)s::text is null or l.display_name ilike %(pattern)s "
            "or l.legal_name ilike %(pattern)s or l.email ilike %(pattern)s "
            "or (%(digits)s::text is not null and l.phone_digits like %(digits)s)) "
            "and (%(after)s::uuid is null or (l.name_key, l.counterparty_id) > "
            "(select a.name_key, a.counterparty_id from latest a "
            "where a.counterparty_id = %(after)s)) "
            "order by l.name_key, l.counterparty_id limit %(limit)s",
            {
                "business": business_id,
                "state": state,
                "pattern": _like(query) if query else None,
                "digits": f"%{digits}%" if len(digits) >= 3 else None,
                "after": after,
                "limit": limit + 1,
            },
        )
    ).fetchall()
    items = tuple(
        CounterpartySummary(
            counterparty_id=row[0],
            kind=row[1],
            revision=row[2],
            display_name=row[3],
            roles=tuple(row[4]),
            state=row[5],
            merged_into=row[6],
        )
        for row in rows[:limit]
    )
    return CounterpartyList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].counterparty_id if len(rows) > limit else None,
    )


async def counterparty_history(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    before: int | None,
    limit: int,
) -> CounterpartyHistory:
    await _require(conn, business_id, counterparty_id)
    rows = await (
        await conn.execute(
            "select revision, state, display_name, created_at from gba.counterparty_versions "
            "where tenant_id = %s and counterparty_id = %s "
            "and (%s::integer is null or revision < %s) order by revision desc limit %s",
            (business_id, counterparty_id, before, before, limit + 1),
        )
    ).fetchall()
    items = tuple(
        CounterpartyRevision(revision=r[0], state=r[1], display_name=r[2], created_at=r[3])
        for r in rows[:limit]
    )
    return CounterpartyHistory(
        business_id=business_id,
        counterparty_id=counterparty_id,
        items=items,
        next_cursor=items[-1].revision if len(rows) > limit else None,
    )


async def merged_counterparties(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> CounterpartyList:
    """Current relationships are separate from immutable revision content."""
    await _require(conn, business_id, counterparty_id)
    rows = await (
        await conn.execute(
            "with latest as (select distinct on (v.counterparty_id) v.* "
            "from gba.counterparty_versions v where v.tenant_id = %s "
            "order by v.counterparty_id, v.revision desc) "
            "select v.counterparty_id, c.kind, v.revision, v.display_name, v.roles, "
            "v.state, v.merged_into from latest v join gba.counterparties c "
            "on c.tenant_id = v.tenant_id and c.id = v.counterparty_id "
            "where v.state = 'merged' and v.merged_into = %s "
            "and (%s::uuid is null or v.counterparty_id > %s) "
            "order by v.counterparty_id limit %s",
            (business_id, counterparty_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        CounterpartySummary(
            counterparty_id=r[0],
            kind=r[1],
            revision=r[2],
            display_name=r[3],
            roles=tuple(r[4]),
            state=r[5],
            merged_into=r[6],
        )
        for r in rows[:limit]
    )
    return CounterpartyList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].counterparty_id if len(rows) > limit else None,
    )


async def _insert_version(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    revision: int,
    body: CounterpartyInput,
    user_id: UUID,
) -> None:
    await conn.execute(
        "insert into gba.counterparty_versions (tenant_id, counterparty_id, revision, "
        "display_name, legal_name, tax_id, registration_number, email, phone, roles, state, "
        "created_by) values (%s, %s, %s, %s, %s, %s, %s, lower(btrim(%s)), %s, %s, %s, %s)",
        (
            business_id,
            counterparty_id,
            revision,
            body.display_name,
            body.legal_name,
            body.tax_id,
            body.registration_number,
            body.email,
            body.phone,
            list(body.roles),
            "archived" if body.archived else "active",
            user_id,
        ),
    )
    for position, contact in enumerate(body.contacts, start=1):
        await conn.execute(
            "insert into gba.counterparty_version_contacts (tenant_id, counterparty_id, "
            "revision, position, name, job_title, email, phone) "
            "values (%s, %s, %s, %s, %s, %s, lower(btrim(%s)), %s)",
            (
                business_id,
                counterparty_id,
                revision,
                position,
                contact.name,
                contact.job_title,
                contact.email,
                contact.phone,
            ),
        )


async def _copy_version(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    revision: int,
    *,
    state: CounterpartyState,
    merged_into: UUID | None,
    user_id: UUID,
) -> int:
    """A new revision with the same content as `revision` and a new state."""
    new_revision = revision + 1
    await conn.execute(
        "insert into gba.counterparty_versions (tenant_id, counterparty_id, revision, "
        "display_name, legal_name, tax_id, registration_number, email, phone, roles, state, "
        "merged_into, created_by) select tenant_id, counterparty_id, %s, display_name, "
        "legal_name, tax_id, registration_number, email, phone, roles, %s, %s, %s "
        "from gba.counterparty_versions "
        "where tenant_id = %s and counterparty_id = %s and revision = %s",
        (new_revision, state, merged_into, user_id, business_id, counterparty_id, revision),
    )
    await conn.execute(
        "insert into gba.counterparty_version_contacts (tenant_id, counterparty_id, "
        "revision, position, name, job_title, email, phone) select tenant_id, "
        "counterparty_id, %s, position, name, job_title, email, phone "
        "from gba.counterparty_version_contacts "
        "where tenant_id = %s and counterparty_id = %s and revision = %s",
        (new_revision, business_id, counterparty_id, revision),
    )
    return new_revision


async def save_counterparty(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    counterparty_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: CounterpartyInput,
) -> CounterpartyView:
    scope = IdempotencyScope(business_id, actor, _SAVE, key)
    request_hash = commands.fingerprint(
        {"counterparty_id": str(counterparty_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, CounterpartyReceipt)
    if receipt is not None:
        return await _version(conn, business_id, receipt.counterparty_id, receipt.revision)

    await require_module(conn, business_id, COUNTERPARTIES_MODULE)
    current = await load_counterparty(conn, business_id, counterparty_id)
    revision = current.revision if current else 0
    if body.expected_revision != revision:
        raise ConflictError(
            "This counterparty changed. Reload it before saving.", revision=revision
        )
    if current is not None and current.kind != body.kind:
        raise InvalidReferenceError("The kind of a counterparty cannot change", field="kind")
    if current is not None and current.state == "merged":
        raise CounterpartyStateError(
            "This record is merged into another one. Separate it before editing."
        )
    revision += 1
    async with module_writes(COUNTERPARTIES_MODULE):
        if current is None:
            await conn.execute(
                "insert into gba.counterparties (tenant_id, id, kind, created_by) "
                "values (%s, %s, %s, %s)",
                (business_id, counterparty_id, body.kind, user_id),
            )
        await _insert_version(conn, business_id, counterparty_id, revision, body, user_id)
    await commands.audit(
        conn,
        business_id,
        actor,
        "counterparty.saved",
        _TARGET,
        str(counterparty_id),
        {
            "revision": revision,
            "kind": body.kind,
            "state": "archived" if body.archived else "active",
            "roles": list(body.roles),
            "contacts": len(body.contacts),
        },
    )
    await commands.complete(
        conn, scope, CounterpartyReceipt(counterparty_id=counterparty_id, revision=revision)
    )
    return await _version(conn, business_id, counterparty_id, revision)


async def _version(
    conn: RuntimeConnection, business_id: UUID, counterparty_id: UUID, revision: int
) -> CounterpartyView:
    result = await load_counterparty(conn, business_id, counterparty_id, revision=revision)
    if result is None:
        raise RuntimeError("A stored counterparty version is missing")
    return result


_DECISION_COLUMNS = (
    "d.id, d.kind, d.counterparty_id, d.other_counterparty_id, d.reverses_decision_id, "
    "d.decided_at, exists (select 1 from gba.counterparty_match_decisions r "
    "where r.tenant_id = d.tenant_id and r.reverses_decision_id = d.id), d.counterparty_revision"
)


def _decision(
    business_id: UUID, row: tuple[Any, ...], revision: int | None = None
) -> MatchDecisionView:
    return MatchDecisionView(
        business_id=business_id,
        decision_id=row[0],
        kind=row[1],
        counterparty_id=row[2],
        other_counterparty_id=row[3],
        reverses_decision_id=row[4],
        decided_at=row[5],
        reversed=row[6],
        counterparty_revision=row[7] if revision is None else revision,
    )


async def list_match_decisions(
    conn: RuntimeConnection, business_id: UUID, counterparty_id: UUID
) -> MatchDecisionList:
    await _require(conn, business_id, counterparty_id)
    rows = await (
        await conn.execute(
            f"select {_DECISION_COLUMNS} from gba.counterparty_match_decisions d "  # noqa: S608
            "where d.tenant_id = %s and (d.counterparty_id = %s or d.other_counterparty_id = %s) "
            "order by d.id desc limit 100",
            (business_id, counterparty_id, counterparty_id),
        )
    ).fetchall()
    return MatchDecisionList(
        business_id=business_id,
        counterparty_id=counterparty_id,
        items=tuple(_decision(business_id, row) for row in rows),
    )


async def _record_decision(
    conn: RuntimeConnection,
    business_id: UUID,
    kind: str,
    counterparty_id: UUID,
    other_id: UUID,
    reverses: UUID | None,
    user_id: UUID,
    revision: int | None = None,
) -> tuple[Any, ...]:
    row = await (
        await conn.execute(
            "insert into gba.counterparty_match_decisions (tenant_id, kind, counterparty_id, "
            "other_counterparty_id, reverses_decision_id, decided_by, counterparty_revision) "
            "values (%s, %s, %s, %s, %s, %s, %s) returning id, kind, counterparty_id, "
            "other_counterparty_id, reverses_decision_id, decided_at, false, counterparty_revision",
            (business_id, kind, counterparty_id, other_id, reverses, user_id, revision),
        )
    ).fetchone()
    if row is None:
        raise RuntimeError("Decision insert returned nothing")
    return tuple(row)


async def decide_match(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    counterparty_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: MergeInput | DistinctInput | SeparateInput,
) -> MatchDecisionView:
    scope = IdempotencyScope(business_id, actor, _DECIDE, key)
    request_hash = commands.fingerprint(
        {"counterparty_id": str(counterparty_id), **body.model_dump(mode="json")}
    )
    previous = await commands.claim(conn, scope, request_hash, MatchDecisionReceipt)
    if previous is not None:
        stored = await (
            await conn.execute(
                "select id, kind, counterparty_id, other_counterparty_id, "
                "reverses_decision_id, decided_at, false, counterparty_revision "
                "from gba.counterparty_match_decisions where tenant_id = %s and id = %s",
                (business_id, previous.decision_id),
            )
        ).fetchone()
        if stored is None:
            raise RuntimeError("A stored match decision is missing")
        return _decision(business_id, tuple(stored), previous.counterparty_revision)

    await require_module(conn, business_id, COUNTERPARTIES_MODULE)
    current = await _require(conn, business_id, counterparty_id)
    async with module_writes(COUNTERPARTIES_MODULE):
        if isinstance(body, MergeInput):
            result = await _merge(conn, business_id, current, body, user_id)
            action, details = "counterparty.merged", {"other_id": str(body.into_id)}
        elif isinstance(body, DistinctInput):
            result = await _distinct(conn, business_id, current, body, user_id)
            action, details = "counterparty.marked_distinct", {"other_id": str(body.other_id)}
        else:
            result = await _separate(conn, business_id, current, body, user_id)
            action = "counterparty.separated"
            details = {
                "other_id": str(result.other_counterparty_id),
                "reverses_decision_id": str(body.decision_id),
            }
    await commands.audit(
        conn,
        business_id,
        actor,
        action,
        _TARGET,
        str(counterparty_id),
        {
            **details,
            "decision_id": str(result.decision_id),
            "revision": result.counterparty_revision,
        },
    )
    await commands.complete(
        conn,
        scope,
        MatchDecisionReceipt(
            decision_id=result.decision_id,
            counterparty_revision=result.counterparty_revision,
        ),
    )
    return result


async def _merge(
    conn: RuntimeConnection,
    business_id: UUID,
    current: CounterpartyView,
    body: MergeInput,
    user_id: UUID,
) -> MatchDecisionView:
    if body.into_id == current.counterparty_id:
        raise InvalidReferenceError("A record cannot be merged into itself", field="into_id")
    target = await load_counterparty(conn, business_id, body.into_id)
    if target is None:
        raise InvalidReferenceError("Unknown counterparty", field="into_id")
    if body.expected_revision != current.revision:
        raise ConflictError("This counterparty changed. Reload it.", revision=current.revision)
    if body.into_expected_revision != target.revision:
        raise ConflictError(
            "The other counterparty changed. Reload it.", into_revision=target.revision
        )
    if current.state == "merged":
        raise MergeNotAllowedError("This record is already merged into another one")
    if target.state == "merged":
        raise MergeNotAllowedError("A record cannot be merged into a merged record")
    children = await merged_counterparties(
        conn, business_id, current.counterparty_id, after=None, limit=1
    )
    if children.items:
        raise MergeNotAllowedError("Other records are merged into this one. Separate them first.")
    row = await _record_decision(
        conn,
        business_id,
        "merged",
        current.counterparty_id,
        target.counterparty_id,
        None,
        user_id,
        current.revision + 1,
    )
    revision = await _copy_version(
        conn,
        business_id,
        current.counterparty_id,
        current.revision,
        state="merged",
        merged_into=target.counterparty_id,
        user_id=user_id,
    )
    return _decision(business_id, row, revision)


async def _distinct(
    conn: RuntimeConnection,
    business_id: UUID,
    current: CounterpartyView,
    body: DistinctInput,
    user_id: UUID,
) -> MatchDecisionView:
    if body.other_id == current.counterparty_id:
        raise InvalidReferenceError("Choose another record", field="other_id")
    if await load_counterparty(conn, business_id, body.other_id) is None:
        raise InvalidReferenceError("Unknown counterparty", field="other_id")
    try:
        async with conn.transaction():
            row = await _record_decision(
                conn,
                business_id,
                "distinct",
                current.counterparty_id,
                body.other_id,
                None,
                user_id,
            )
    except UniqueViolation as exc:
        if exc.diag.constraint_name != "counterparty_match_decisions_one_distinct_pair":
            raise
        raise ConflictError("These records are already marked as different") from exc
    return _decision(business_id, row)


async def _separate(
    conn: RuntimeConnection,
    business_id: UUID,
    current: CounterpartyView,
    body: SeparateInput,
    user_id: UUID,
) -> MatchDecisionView:
    merge = await (
        await conn.execute(
            f"select {_DECISION_COLUMNS} from gba.counterparty_match_decisions d "  # noqa: S608
            "where d.tenant_id = %s and d.id = %s",
            (business_id, body.decision_id),
        )
    ).fetchone()
    if merge is None or merge[1] != "merged" or merge[2] != current.counterparty_id:
        raise InvalidReferenceError("Unknown merge of this record", field="decision_id")
    if merge[6]:
        raise CounterpartyStateError("This merge was already reversed")
    if body.expected_revision != current.revision:
        raise ConflictError("This counterparty changed. Reload it.", revision=current.revision)
    if current.state != "merged" or current.merged_into != merge[3]:
        raise CounterpartyStateError("This record is not merged by that decision")
    before = await (
        await conn.execute(
            "select state from gba.counterparty_versions "
            "where tenant_id = %s and counterparty_id = %s and revision = %s",
            (business_id, current.counterparty_id, current.revision - 1),
        )
    ).fetchone()
    restored: CounterpartyState = "archived" if before and before[0] == "archived" else "active"
    row = await _record_decision(
        conn,
        business_id,
        "separated",
        current.counterparty_id,
        merge[3],
        body.decision_id,
        user_id,
        current.revision + 1,
    )
    revision = await _copy_version(
        conn,
        business_id,
        current.counterparty_id,
        current.revision,
        state=restored,
        merged_into=None,
        user_id=user_id,
    )
    return _decision(business_id, row, revision)


_LINK_COLUMNS = "id, booking_id, sequence, action, counterparty_id, basis, decided_at"


def _link(row: tuple[Any, ...]) -> BookingLinkView:
    return BookingLinkView(
        link_id=row[0],
        booking_id=row[1],
        sequence=row[2],
        action=row[3],
        counterparty_id=row[4],
        basis=tuple(row[5]),
        decided_at=row[6],
    )


async def _links(
    conn: RuntimeConnection, business_id: UUID, link_ids: tuple[UUID, ...]
) -> tuple[BookingLinkView, ...]:
    rows = await (
        await conn.execute(
            f"select {_LINK_COLUMNS} from gba.counterparty_booking_links "  # noqa: S608
            "where tenant_id = %s and id = any(%s) order by booking_id, sequence",
            (business_id, list(link_ids)),
        )
    ).fetchall()
    return tuple(_link(row) for row in rows)


async def change_booking_links(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    counterparty_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: LinkBookingsInput | UnlinkBookingInput,
) -> BookingLinkResult:
    scope = IdempotencyScope(business_id, actor, _LINK, key)
    request_hash = commands.fingerprint(
        {"counterparty_id": str(counterparty_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, BookingLinkReceipt)
    if receipt is not None:
        return BookingLinkResult(
            business_id=business_id,
            counterparty_id=receipt.counterparty_id,
            links=await _links(conn, business_id, receipt.link_ids),
        )

    await require_module(conn, business_id, COUNTERPARTIES_MODULE)
    current = await _require(conn, business_id, counterparty_id)
    async with module_writes(COUNTERPARTIES_MODULE):
        if isinstance(body, LinkBookingsInput):
            created = await _link_bookings(conn, business_id, current, body, user_id)
        else:
            created = await _unlink_booking(conn, business_id, current, body, user_id)
    for link in created:
        await commands.audit(
            conn,
            business_id,
            actor,
            f"counterparty.booking_{link.action}",
            "booking",
            str(link.booking_id),
            {
                "counterparty_id": str(counterparty_id),
                "sequence": link.sequence,
                "basis": list(link.basis),
            },
        )
    link_ids = tuple(link.link_id for link in created)
    await commands.complete(
        conn, scope, BookingLinkReceipt(counterparty_id=counterparty_id, link_ids=link_ids)
    )
    return BookingLinkResult(
        business_id=business_id,
        counterparty_id=counterparty_id,
        links=await _links(conn, business_id, link_ids),
    )


async def _insert_link(
    conn: RuntimeConnection,
    business_id: UUID,
    booking_id: UUID,
    sequence: int,
    action: str,
    counterparty_id: UUID,
    basis: tuple[str, ...],
    user_id: UUID,
) -> BookingLinkView:
    row = await (
        await conn.execute(
            "insert into gba.counterparty_booking_links (tenant_id, booking_id, sequence, "
            "action, counterparty_id, basis, decided_by) values (%s, %s, %s, %s, %s, %s, %s) "
            "returning id, booking_id, sequence, action, counterparty_id, basis, decided_at",
            (business_id, booking_id, sequence, action, counterparty_id, list(basis), user_id),
        )
    ).fetchone()
    if row is None:
        raise RuntimeError("Link insert returned nothing")
    return _link(tuple(row))


async def _link_bookings(
    conn: RuntimeConnection,
    business_id: UUID,
    current: CounterpartyView,
    body: LinkBookingsInput,
    user_id: UUID,
) -> list[BookingLinkView]:
    if current.state != "active":
        raise CounterpartyStateError("Only an active record can be linked to bookings")
    # Re-checked under the counterparties lock: each booking still matches and is free.
    rows = await booking_matches(
        conn,
        business_id,
        current.counterparty_id,
        booking_ids=body.booking_ids,
        limit=len(body.booking_ids),
    )
    found = {row[0]: row for row in rows}
    created = []
    for booking_id in body.booking_ids:
        row = found.get(booking_id)
        if row is None:
            raise BookingNotACandidateError(
                "This booking's customer details no longer match the record",
                booking_id=str(booking_id),
            )
        if row[9] == "linked":
            raise BookingAlreadyLinkedError(
                "This booking is already linked to a record", booking_id=str(booking_id)
            )
        created.append(
            await _insert_link(
                conn,
                business_id,
                booking_id,
                (row[8] or 0) + 1,
                "linked",
                current.counterparty_id,
                basis_of(row[6], row[7]),
                user_id,
            )
        )
    return created


async def _unlink_booking(
    conn: RuntimeConnection,
    business_id: UUID,
    current: CounterpartyView,
    body: UnlinkBookingInput,
    user_id: UUID,
) -> list[BookingLinkView]:
    latest = await (
        await conn.execute(
            "select sequence, action, counterparty_id from gba.counterparty_booking_links "
            "where tenant_id = %s and booking_id = %s order by sequence desc limit 1",
            (business_id, body.booking_id),
        )
    ).fetchone()
    if latest is None or latest[1] != "linked" or latest[2] != current.counterparty_id:
        raise InvalidReferenceError("This booking is not linked to this record", field="booking_id")
    if latest[0] != body.expected_sequence:
        raise ConflictError("This link changed. Reload it.", sequence=latest[0])
    return [
        await _insert_link(
            conn,
            business_id,
            body.booking_id,
            latest[0] + 1,
            "unlinked",
            current.counterparty_id,
            (),
            user_id,
        )
    ]


async def linked_bookings(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> LinkedBookingList:
    """Bookings linked to the record or to a duplicate merged into it."""
    await _require(conn, business_id, counterparty_id)
    rows = await (
        await conn.execute(
            "with family as (select %(record)s::uuid as id union "
            "select v.counterparty_id from gba.counterparty_versions v "
            "where v.tenant_id = %(business)s and v.merged_into = %(record)s "
            "and v.revision = (select max(x.revision) from gba.counterparty_versions x "
            "where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)), "
            "latest_links as (select distinct on (l.booking_id) l.* "
            "from gba.counterparty_booking_links l where l.tenant_id = %(business)s "
            "order by l.booking_id, l.sequence desc), "
            "keys as (select v.counterparty_id, array(select x from (select v.email union "
            "select c.email from gba.counterparty_version_contacts c "
            "where c.tenant_id = v.tenant_id and c.counterparty_id = v.counterparty_id "
            "and c.revision = v.revision) s(x) where x is not null) as emails, "
            "array(select x from (select v.phone_digits union "
            "select c.phone_digits from gba.counterparty_version_contacts c "
            "where c.tenant_id = v.tenant_id and c.counterparty_id = v.counterparty_id "
            "and c.revision = v.revision) s(x) where x is not null) as phones "
            "from gba.counterparty_versions v where v.tenant_id = %(business)s "
            "and v.counterparty_id in (select id from family) "
            "and v.revision = (select max(x.revision) from gba.counterparty_versions x "
            "where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)) "
            "select bc.booking_id, b.starts_at, b.status, bc.customer_name, bc.email, bc.phone, "
            "ll.id, ll.counterparty_id, ll.sequence, ll.basis, ll.decided_at, "
            "(('email' = any(ll.basis) and lower(btrim(bc.email)) = any(k.emails)) or "
            "('phone' = any(ll.basis) and "
            "nullif(regexp_replace(bc.phone, '[^0-9]', '', 'g'), '') = any(k.phones))) "
            "from latest_links ll join family f on f.id = ll.counterparty_id "
            "join keys k on k.counterparty_id = ll.counterparty_id "
            "join gba.booking_customers bc on bc.tenant_id = %(business)s "
            "and bc.booking_id = ll.booking_id "
            "join gba.bookings b on b.tenant_id = bc.tenant_id and b.id = bc.booking_id "
            "where ll.action = 'linked' and (%(after)s::uuid is null or ll.id < %(after)s) "
            "order by ll.id desc limit %(limit)s",
            {
                "business": business_id,
                "record": counterparty_id,
                "after": after,
                "limit": limit + 1,
            },
        )
    ).fetchall()
    items = tuple(
        LinkedBooking(
            booking=booking_summary(row),
            counterparty_id=row[7],
            sequence=row[8],
            basis=tuple(row[9]),
            decided_at=row[10],
            still_matches=bool(row[11]),
        )
        for row in rows[:limit]
    )
    return LinkedBookingList(
        business_id=business_id,
        counterparty_id=counterparty_id,
        items=items,
        next_cursor=rows[limit - 1][6] if len(rows) > limit else None,
    )


async def booking_link_history(
    conn: RuntimeConnection,
    business_id: UUID,
    counterparty_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> BookingLinkHistory:
    await _require(conn, business_id, counterparty_id)
    rows = await (
        await conn.execute(
            f"select {_LINK_COLUMNS} from gba.counterparty_booking_links "  # noqa: S608
            "where tenant_id = %s and counterparty_id = %s "
            "and (%s::uuid is null or id < %s) order by id desc limit %s",
            (business_id, counterparty_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_link(row) for row in rows[:limit])
    return BookingLinkHistory(
        business_id=business_id,
        counterparty_id=counterparty_id,
        items=items,
        next_cursor=items[-1].link_id if len(rows) > limit else None,
    )
