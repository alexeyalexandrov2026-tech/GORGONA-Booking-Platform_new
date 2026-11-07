"""R6a (package R, RENT-01): handover and return inspections of a rental booking.

docs/plan/PACKAGE_R6A_DESIGN_2026-11-07.md. One handover and one return per booking, of its current
unit assignment, with the class meter reading, a level, a note and damage marks that may cite a
photo. Insert-only; the database checks the order, the meter and the marks. Nothing here changes
an assignment, agreement, security or payment.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import BaseModel, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import OneLine, Strict, fingerprint, require_rental
from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError

Kind = Literal["handover", "return"]
Severity = Literal["minor", "major"]

# Constraint names of the 0105 guards: the booking, assignment or order is wrong (a state), or
# the meter or a mark breaks a rule (invalid).
_STATE = (
    "rental_inspections_booking_check",
    "rental_inspections_assignment_check",
    "rental_inspections_order_check",
)


class RentalInspectionStateError(ConflictError):
    """R6a decision 1: no agreement or current assignment, a cancelled booking, a return before the
    handover, or a second handover or return."""

    code = "RENTAL_INSPECTION_STATE"


class RentalInspectionInvalidError(ConflictError):
    """R6a decisions 2-3: the meter does not follow the class or goes back, or a mark breaks
    a rule."""

    code = "RENTAL_INSPECTION_INVALID"


class PhotoInput(Strict):
    document_id: UUID
    revision: int = Field(ge=1, le=1_000_000)


class MarkInput(Strict):
    area: Annotated[OneLine, Field(min_length=1, max_length=100)]
    severity: Severity
    note: Annotated[str, Field(min_length=1, max_length=500)] | None = None
    new: bool = False
    photo: PhotoInput | None = None


class InspectionInput(Strict):
    schema_version: Literal[1]
    kind: Kind
    meter: Annotated[int, Field(ge=0, le=10_000_000)] | None = None
    level: Annotated[int, Field(ge=0, le=100)] | None = None
    note: Annotated[str, Field(min_length=1, max_length=1000)] | None = None
    marks: Annotated[tuple[MarkInput, ...], Field(max_length=50)] = ()


class PhotoView(BaseModel):
    document_id: UUID
    revision: int


class MarkView(BaseModel):
    position: int
    area: str
    severity: Severity
    note: str | None
    new: bool
    photo: PhotoView | None


class InspectionView(BaseModel):
    inspection_id: UUID
    kind: Kind
    assignment_id: UUID
    unit_id: UUID
    meter: int | None
    level: int | None
    note: str | None
    inspected_by: UUID
    inspected_at: datetime
    marks: list[MarkView]


class InspectionsView(BaseModel):
    booking_id: UUID
    inspections: list[InspectionView]


async def load_inspections(conn: RuntimeConnection, booking_id: UUID) -> InspectionsView:
    """The booking's handover and return in that order; not found outside the caller's scope."""
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    rows = await (
        await conn.execute(
            "select i.id, i.kind, i.assignment_id, a.unit_id, i.meter, i.level, i.note, "
            "i.inspected_by, i.inspected_at from gba.rental_inspections i "
            "join gba.rental_assignments a on a.tenant_id = i.tenant_id and a.id = i.assignment_id "
            "where i.booking_id = %s order by i.kind = 'return', i.inspected_at",
            (booking_id,),
        )
    ).fetchall()
    marks = await (
        await conn.execute(
            "select m.inspection_id, m.position, m.area, m.severity, m.note, m.new, "
            "m.document_id, m.document_revision from gba.rental_inspection_marks m "
            "join gba.rental_inspections i on i.tenant_id = m.tenant_id and i.id = m.inspection_id "
            "where i.booking_id = %s order by m.position",
            (booking_id,),
        )
    ).fetchall()
    return InspectionsView(
        booking_id=booking_id,
        inspections=[
            InspectionView(
                inspection_id=r[0],
                kind=r[1],
                assignment_id=r[2],
                unit_id=r[3],
                meter=r[4],
                level=r[5],
                note=r[6],
                inspected_by=r[7],
                inspected_at=r[8],
                marks=[
                    MarkView(
                        position=m[1],
                        area=m[2],
                        severity=m[3],
                        note=m[4],
                        new=m[5],
                        photo=None if m[6] is None else PhotoView(document_id=m[6], revision=m[7]),
                    )
                    for m in marks
                    if m[0] == r[0]
                ],
            )
            for r in rows
        ],
    )


async def _current_assignment(conn: RuntimeConnection, booking_id: UUID) -> UUID:
    cancelled = await (
        await conn.execute(
            "select 1 from gba.rental_booking_cancellations where booking_id = %s", (booking_id,)
        )
    ).fetchone()
    if cancelled is not None:
        raise RentalInspectionStateError("The booking is cancelled")
    row = await (
        await conn.execute(
            "select a.id from gba.rental_assignments a where a.booking_id = %s "
            "and not exists (select 1 from gba.rental_assignment_releases r "
            "where r.tenant_id = a.tenant_id and r.assignment_id = a.id) "
            "order by a.assigned_at desc limit 1",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        raise RentalInspectionStateError("The booking has no unit assigned")
    assignment: UUID = row[0]
    return assignment


async def record_inspection(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: InspectionInput,
) -> InspectionsView:
    """Record the handover or the return of the booking's current assignment (decisions 1-5)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.inspection", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_inspections(conn, booking_id)
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    assignment = await _current_assignment(conn, booking_id)
    inspection = uuid7()
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_inspections (tenant_id, id, booking_id, assignment_id, "
                "kind, meter, level, note, inspected_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    inspection,
                    booking_id,
                    assignment,
                    body.kind,
                    body.meter,
                    body.level,
                    body.note,
                    user_id,
                ),
            )
            for position, mark in enumerate(body.marks, start=1):
                photo = mark.photo
                await conn.execute(
                    "insert into gba.rental_inspection_marks (tenant_id, inspection_id, position, "
                    "area, severity, note, new, document_id, document_revision) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        inspection,
                        position,
                        mark.area,
                        mark.severity,
                        mark.note,
                        mark.new,
                        None if photo is None else photo.document_id,
                        None if photo is None else photo.revision,
                    ),
                )
    except UniqueViolation as exc:
        raise RentalInspectionStateError(f"The booking already has its {body.kind}") from exc
    except CheckViolation as exc:
        name = exc.diag.constraint_name or ""
        if name in _STATE:
            raise RentalInspectionStateError("The inspection does not follow the booking") from exc
        if name.startswith("rental_inspection"):
            raise RentalInspectionInvalidError("The meter or a mark breaks a rule") from exc
        raise
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_inspections(conn, booking_id)
