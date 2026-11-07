"""R4c (package R, RENT-01): extensions and shortened periods on the shared occupancy.

docs/plan/PACKAGE_R4C_DESIGN_2026-11-06.md. A period change is an insert-only row with the next
agreement version priced from the frozen card; availability counts the current period; a booking
holding a unit keeps the same unit, whose hold moves by releasing and assigning it again.
"""

from datetime import timedelta
from typing import Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, ExclusionViolation
from pydantic import AwareDatetime, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import fingerprint, require_rental
from gorgona_booking.business.rental_agreements import (
    AgreementView,
    ChangeInput,
    check_time,
    load_agreement,
    open_booking,
    record_version,
)
from gorgona_booking.business.rental_assignments import RentalUnitBusyError
from gorgona_booking.business.rental_bookings import RentalUnavailableError, release_current
from gorgona_booking.business.rental_rates import load_card, priced
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import NotFoundError

LONGEST = timedelta(days=366)


class PeriodInput(ChangeInput):
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def _period(self) -> Self:
        if self.ends_at <= self.starts_at or self.ends_at - self.starts_at > LONGEST:
            raise ValueError("a period ends after it starts and lasts at most 366 days")
        return self


async def change_period(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: PeriodInput,
) -> AgreementView:
    """Move the booking period with the next agreement version and the hold (decisions 1-3)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.period", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_agreement(conn, booking_id)
    await open_booking(conn, booking_id)
    current = await load_agreement(conn, booking_id)
    await check_time(conn, body.accepted_at)
    latest = current.versions[-1]
    card = await load_card(conn, latest.rate_card_id)
    if card is None:
        raise NotFoundError("Rate card not found", rate_card_id=str(latest.rate_card_id))
    quote = priced(card, body.starts_at, body.ends_at, body.extras)
    numbered = await (
        await conn.execute(
            "select coalesce(max(sequence), 1) + 1 from gba.rental_booking_periods "
            "where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    sequence = int(numbered[0]) if numbered else 2
    held = await (
        await conn.execute(
            "select a.unit_id, u.resource_id from gba.rental_assignments a "
            "join gba.rental_units u on u.tenant_id = a.tenant_id and u.id = a.unit_id "
            "where a.booking_id = %s and not exists (select 1 "
            "from gba.rental_assignment_releases l "
            "where l.tenant_id = a.tenant_id and l.assignment_id = a.id)",
            (booking_id,),
        )
    ).fetchone()
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_booking_periods (tenant_id, booking_id, sequence, "
                "starts_at, ends_at, recorded_by) values (%s, %s, %s, %s, %s, %s)",
                (business, booking_id, sequence, body.starts_at, body.ends_at, user_id),
            )
            if held is not None:
                await release_current(conn, business, booking_id, user_id, "replaced")
                assignment_id = uuid7()
                await conn.execute(
                    "insert into gba.rental_assignments (tenant_id, id, booking_id, unit_id, "
                    "starts_at, ends_at, assigned_by) values (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        assignment_id,
                        booking_id,
                        held[0],
                        body.starts_at,
                        body.ends_at,
                        user_id,
                    ),
                )
                await conn.execute(
                    "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
                    "source_id, during, state) values (%s, %s, 'rental_assignment', %s, "
                    "tstzrange(%s, %s, '[)'), 'confirmed')",
                    (business, held[1], assignment_id, body.starts_at, body.ends_at),
                )
            await record_version(
                conn,
                business,
                current.agreement_id,
                latest.version + 1,
                card,
                quote,
                body,
                body.reason,
                user_id,
            )
            await conn.execute("set constraints all immediate")
    except ExclusionViolation as exc:
        unit = str(held[0]) if held is not None else ""
        raise RentalUnitBusyError(
            "The unit is held for an overlapping assignment or block", unit_id=unit
        ) from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "rental_booking_periods_availability_check":
            raise RentalUnavailableError(
                "The change would leave a booking of the class without a unit"
            ) from exc
        raise
    await idempotency.complete(conn, scope, 200, {"agreement_id": str(current.agreement_id)})
    return await load_agreement(conn, booking_id)
