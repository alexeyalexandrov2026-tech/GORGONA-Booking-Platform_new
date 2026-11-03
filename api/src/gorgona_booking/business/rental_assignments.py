"""R3a (package R, RENT-01): assigning a rental unit to a booking on the shared occupancy.

docs/plan/PACKAGE_R3A_DESIGN_2026-11-03.md. An assignment holds the unit's own resource for the
booking period through one confirmed allocation, so the exclusion constraint makes a double issue
impossible. A new assignment releases the booking's current one; a cancellation releases it too.
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, ExclusionViolation
from pydantic import BaseModel

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import Strict, fingerprint, require_rental
from gorgona_booking.business.rental_bookings import (
    RentalBookingCancelledError,
    load_booking,
    release_current,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError


class RentalUnitBusyError(ConflictError):
    code = "RENTAL_UNIT_BUSY"


class AssignmentInput(Strict):
    schema_version: Literal[1]
    unit_id: UUID


class ReleaseView(BaseModel):
    reason: str
    released_at: datetime


class AssignmentView(BaseModel):
    assignment_id: UUID
    booking_id: UUID
    unit_id: UUID
    starts_at: datetime
    ends_at: datetime
    assigned_at: datetime
    release: ReleaseView | None


class AssignmentList(BaseModel):
    items: list[AssignmentView]


_SELECT = (
    "select a.id, a.booking_id, a.unit_id, a.starts_at, a.ends_at, a.assigned_at, l.reason, "
    "l.released_at from gba.rental_assignments a "
    "left join gba.rental_assignment_releases l "
    "on l.tenant_id = a.tenant_id and l.assignment_id = a.id "
)


def _view(row: Any) -> AssignmentView:
    return AssignmentView(
        assignment_id=row[0],
        booking_id=row[1],
        unit_id=row[2],
        starts_at=row[3].astimezone(UTC),
        ends_at=row[4].astimezone(UTC),
        assigned_at=row[5].astimezone(UTC),
        release=None
        if row[6] is None
        else ReleaseView(reason=row[6], released_at=row[7].astimezone(UTC)),
    )


async def list_assignments(conn: RuntimeConnection, booking_id: UUID) -> AssignmentList:
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    rows = await (
        await conn.execute(
            _SELECT + "where a.booking_id = %s order by a.assigned_at", (booking_id,)
        )
    ).fetchall()
    return AssignmentList(items=[_view(row) for row in rows])


async def _load(conn: RuntimeConnection, assignment_id: UUID) -> AssignmentView | None:
    row = await (await conn.execute(_SELECT + "where a.id = %s", (assignment_id,))).fetchone()
    return None if row is None else _view(row)


async def assign_unit(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AssignmentInput,
) -> AssignmentView:
    """Hold a suitable unit for the booking period, replacing the current one (decisions 2-3)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.assignment", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await _load(conn, UUID(str(stored.body["assignment_id"])))
        if view is None:
            raise NotFoundError("Assignment not found")
        return view
    booking = await load_booking(conn, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    if booking.cancellation is not None:
        raise RentalBookingCancelledError("The booking is cancelled")
    unit = await (
        await conn.execute(
            "select class_id, location_id, state, resource_id from gba.rental_units "
            "where id = %s for update",
            (body.unit_id,),
        )
    ).fetchone()
    if (
        unit is None
        or unit[0] != booking.class_id
        or unit[1] != booking.pickup_location_id
        or unit[2] != "active"
    ):
        raise InvalidReferenceError(
            "The unit is not an active unit of the booked class at the pickup branch",
            field="unit_id",
        )
    assignment_id = uuid7()
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await release_current(conn, business, booking_id, user_id, "replaced")
            await conn.execute(
                "insert into gba.rental_assignments (tenant_id, id, booking_id, unit_id, "
                "starts_at, ends_at, assigned_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    assignment_id,
                    booking_id,
                    body.unit_id,
                    booking.starts_at,
                    booking.ends_at,
                    user_id,
                ),
            )
            await conn.execute(
                "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
                "source_id, during, state) values (%s, %s, 'rental_assignment', %s, "
                "tstzrange(%s, %s, '[)'), 'confirmed')",
                (business, unit[3], assignment_id, booking.starts_at, booking.ends_at),
            )
            await conn.execute(
                "set constraints gba.rental_assignments_hold, "
                "gba.rental_assignment_releases_hold immediate"
            )
    except ExclusionViolation as exc:
        raise RentalUnitBusyError(
            "The unit is already held for an overlapping booking", unit_id=str(body.unit_id)
        ) from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "rental_assignments_booking_check":
            raise InvalidReferenceError(
                "The unit is not suitable for the booking", field="unit_id"
            ) from exc
        raise
    view = await _load(conn, assignment_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"assignment_id": str(assignment_id)})
    return view
