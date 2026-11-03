"""R2 (package R, RENT-01): rental class bookings and availability.

docs/plan/PACKAGE_R2_DESIGN_2026-11-03.md. A booking holds a class, never a unit, for a period from
a pickup branch; it is accepted only while the active units of the class at that branch cover the
peak of overlapping bookings. Bookings and their one cancellation are insert-only. The service and
the database both check under the class lock, so two racing bookings for the last unit leave one.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import Strict, caller_branch, fingerprint, require_rental
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

PAGE = 50
LONGEST = timedelta(days=366)


class RentalUnavailableError(ConflictError):
    code = "RENTAL_UNAVAILABLE"


class RentalBookingCancelledError(ConflictError):
    code = "RENTAL_BOOKING_CANCELLED"


def _text(value: str) -> str:
    if not value.strip():
        raise ValueError("text that is not only blanks")
    return value


Text = Annotated[str, AfterValidator(_text)]


class BookingInput(Strict):
    schema_version: Literal[1]
    class_id: UUID
    customer_id: UUID
    pickup_location_id: UUID
    return_location_id: UUID
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    note: Annotated[Text, Field(min_length=1, max_length=1000)] | None = None

    @model_validator(mode="after")
    def _period(self) -> Self:
        if self.ends_at <= self.starts_at or self.ends_at - self.starts_at > LONGEST:
            raise ValueError("a period ends after it starts and lasts at most 366 days")
        return self


class CancellationInput(Strict):
    schema_version: Literal[1]
    reason: Annotated[Text, Field(min_length=1, max_length=500)]


class CancellationView(BaseModel):
    reason: str
    cancelled_at: datetime


class BookingView(BaseModel):
    booking_id: UUID
    number: int
    class_id: UUID
    customer_id: UUID
    pickup_location_id: UUID
    return_location_id: UUID
    starts_at: datetime
    ends_at: datetime
    note: str | None
    booked_at: datetime
    cancellation: CancellationView | None


class BookingList(BaseModel):
    items: list[BookingView]
    next_cursor: UUID | None = None


class AvailabilityView(BaseModel):
    class_id: UUID
    location_id: UUID
    starts_at: datetime
    ends_at: datetime
    units: int
    booked: int
    available: int


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


async def load_booking(conn: RuntimeConnection, booking_id: UUID) -> BookingView | None:
    row = await (
        await conn.execute(
            "select b.number, b.class_id, b.customer_id, b.pickup_location_id, "
            "b.return_location_id, b.starts_at, b.ends_at, b.note, b.booked_at, c.reason, "
            "c.cancelled_at from gba.rental_bookings b "
            "left join gba.rental_booking_cancellations c "
            "on c.tenant_id = b.tenant_id and c.booking_id = b.id where b.id = %s",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        return None
    return BookingView(
        booking_id=booking_id,
        number=row[0],
        class_id=row[1],
        customer_id=row[2],
        pickup_location_id=row[3],
        return_location_id=row[4],
        starts_at=_utc(row[5]),
        ends_at=_utc(row[6]),
        note=row[7],
        booked_at=_utc(row[8]),
        cancellation=None
        if row[9] is None
        else CancellationView(reason=row[9], cancelled_at=_utc(row[10])),
    )


async def list_bookings(
    conn: RuntimeConnection, after: UUID | None = None, class_id: UUID | None = None
) -> BookingList:
    rows = await (
        await conn.execute(
            "select id from gba.rental_bookings where (%s::uuid is null or id > %s) "
            "and (%s::uuid is null or class_id = %s) order by id limit %s",
            (after, after, class_id, class_id, PAGE + 1),
        )
    ).fetchall()
    views = [v for v in [await load_booking(conn, r[0]) for r in rows[:PAGE]] if v is not None]
    more = len(rows) > PAGE and bool(views)
    return BookingList(items=views, next_cursor=views[-1].booking_id if more else None)


async def _units(conn: RuntimeConnection, class_id: UUID, location_id: UUID) -> int:
    row = await (
        await conn.execute(
            "select count(*) from gba.rental_units where class_id = %s and location_id = %s "
            "and state = 'active'",
            (class_id, location_id),
        )
    ).fetchone()
    return int(row[0]) if row else 0


async def _peak(
    conn: RuntimeConnection,
    business: UUID,
    class_id: UUID,
    location_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> int:
    row = await (
        await conn.execute(
            "select gba.rental_booking_peak(%s, %s, %s, %s, %s)",
            (business, class_id, location_id, starts_at, ends_at),
        )
    ).fetchone()
    return int(row[0]) if row else 0


async def availability(
    conn: RuntimeConnection,
    business: UUID,
    class_id: UUID,
    location_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
) -> AvailabilityView:
    """Units of the class at the branch, the peak of overlapping bookings and what is left."""
    units = await _units(conn, class_id, location_id)
    booked = await _peak(conn, business, class_id, location_id, starts_at, ends_at)
    return AvailabilityView(
        class_id=class_id,
        location_id=location_id,
        starts_at=_utc(starts_at),
        ends_at=_utc(ends_at),
        units=units,
        booked=booked,
        available=units - booked,
    )


async def _known_location(conn: RuntimeConnection, location_id: UUID) -> bool:
    found = await (
        await conn.execute("select 1 from gba.locations where id = %s", (location_id,))
    ).fetchone()
    return found is not None


async def _active_customer(conn: RuntimeConnection, customer_id: UUID) -> bool:
    row = await (
        await conn.execute(
            "select 1 from gba.counterparty_versions v where v.counterparty_id = %s "
            "and v.state = 'active' and 'customer' = any(v.roles) and v.revision = ("
            "select max(x.revision) from gba.counterparty_versions x "
            "where x.counterparty_id = v.counterparty_id)",
            (customer_id,),
        )
    ).fetchone()
    return row is not None


async def create_booking(
    conn: RuntimeConnection,
    business: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: BookingInput,
) -> BookingView:
    """Book a class for a period while its units at the pickup branch cover it (decisions 1-3)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.booking", key)
    request = fingerprint("booking", body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_booking(conn, UUID(str(stored.body["booking_id"])))
        if view is None:
            raise NotFoundError("Booking not found")
        return view
    for field in ("pickup_location_id", "return_location_id"):
        if not await _known_location(conn, getattr(body, field)):
            raise InvalidReferenceError("Unknown branch", field=field)
    branch = await caller_branch(conn)
    if branch is not None and body.pickup_location_id != branch:
        raise InvalidReferenceError("Unknown branch", field="pickup_location_id")
    locked = await (
        await conn.execute(
            "select 1 from gba.rental_classes where id = %s for update", (body.class_id,)
        )
    ).fetchone()
    if locked is None:
        raise InvalidReferenceError("Unknown class", field="class_id")
    if not await _active_customer(conn, body.customer_id):
        raise InvalidReferenceError("A booking names an active customer", field="customer_id")
    units = await _units(conn, body.class_id, body.pickup_location_id)
    peak = await _peak(
        conn, business, body.class_id, body.pickup_location_id, body.starts_at, body.ends_at
    )
    if peak + 1 > units:
        raise RentalUnavailableError(
            "No unit of the class is free at the pickup branch for the whole period",
            units=units,
            booked=peak,
        )
    row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.rental_bookings "
            "where pickup_location_id = %s",
            (body.pickup_location_id,),
        )
    ).fetchone()
    number = int(row[0]) if row else 1
    booking_id = uuid7()
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_bookings (tenant_id, id, number, class_id, customer_id, "
                "pickup_location_id, return_location_id, starts_at, ends_at, note, booked_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    booking_id,
                    number,
                    body.class_id,
                    body.customer_id,
                    body.pickup_location_id,
                    body.return_location_id,
                    body.starts_at,
                    body.ends_at,
                    body.note,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown reference", field="customer_id") from exc
    except CheckViolation as exc:
        name = exc.diag.constraint_name or ""
        if name == "rental_bookings_availability_check":
            raise RentalUnavailableError("No unit of the class is free") from exc
        if name == "rental_bookings_customer_check":
            raise InvalidReferenceError(
                "A booking names an active customer", field="customer_id"
            ) from exc
        raise
    view = await load_booking(conn, booking_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return view


async def cancel_booking(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CancellationInput,
) -> BookingView:
    """Cancel a booking once, with its reason; the class is free again (decision 1)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.cancellation", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_booking(conn, booking_id)
        if view is None:
            raise NotFoundError("Booking not found", booking_id=str(booking_id))
        return view
    current = await load_booking(conn, booking_id)
    if current is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    await conn.execute(
        "select 1 from gba.rental_classes where id = %s for update", (current.class_id,)
    )
    if current.cancellation is not None:
        raise RentalBookingCancelledError("The booking is already cancelled")
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_booking_cancellations (tenant_id, booking_id, reason, "
                "cancelled_by) values (%s, %s, %s, %s)",
                (business, booking_id, body.reason, user_id),
            )
    except UniqueViolation as exc:
        raise RentalBookingCancelledError("The booking is already cancelled") from exc
    view = await load_booking(conn, booking_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return view
