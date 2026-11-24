"""R4a (package R, RENT-01): rental rate cards and quotes.

docs/plan/PACKAGE_R4A_DESIGN_2026-11-04.md. A rate card is an insert-only version per class and
branch; the card in force at an instant is the one with the latest effective_from at or before it.
A quote is computed from the card in force (rental_quote); a booking is quoted from the card in
force when it was made.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import (
    RentalValueInvalidError,
    Strict,
    caller_branch,
    fingerprint,
    require_rental,
)
from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.business.rental_quote import Extra, Quote, Rates, quote
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError

Amount = Annotated[int, Field(gt=0, le=1_000_000_000_000)]
Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")]


class RentalNoRateError(ConflictError):
    """R4a decision 3: no rate card is in force for the class at the branch."""

    code = "RENTAL_NO_RATE"


class RatesInput(Strict):
    hour: Amount | None = None
    day: Amount | None = None
    week: Amount | None = None
    month: Amount | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        if all(r is None for r in (self.hour, self.day, self.week, self.month)):
            raise ValueError("a rate card has at least one rate")
        return self


class ExtraInput(Strict):
    code: Code
    name: Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
    price: Annotated[int, Field(ge=0, le=1_000_000_000_000)]
    unit: Literal["per_day", "per_rental"]


class RateCardInput(Strict):
    schema_version: Literal[1]
    location_id: UUID
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    effective_from: AwareDatetime | None = None
    rates: RatesInput
    meter_allowance_per_day: Annotated[int, Field(ge=0, le=1_000_000)] | None = None
    excess_rate: Annotated[int, Field(ge=0, le=1_000_000_000_000)] | None = None
    extras: Annotated[list[ExtraInput], Field(default_factory=list, max_length=50)]

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        codes = [e.code for e in self.extras]
        if len(codes) != len(set(codes)):
            raise ValueError("every extra of a card has its own code")
        return self


class QuoteExtraInput(Strict):
    code: Code
    quantity: Annotated[int, Field(gt=0, le=100)]


class QuoteInput(Strict):
    schema_version: Literal[1]
    class_id: UUID
    location_id: UUID
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    extras: Annotated[list[QuoteExtraInput], Field(default_factory=list, max_length=50)]


class RatesView(BaseModel):
    hour: int | None
    day: int | None
    week: int | None
    month: int | None


class ExtraView(BaseModel):
    code: str
    name: str
    price: int
    unit: str


class RateCardView(BaseModel):
    rate_card_id: UUID
    class_id: UUID
    location_id: UUID
    version: int
    currency: str
    effective_from: datetime
    rates: RatesView
    meter_allowance_per_day: int | None
    excess_rate: int | None
    extras: list[ExtraView]
    created_at: datetime


class RateCardList(BaseModel):
    items: list[RateCardView]


class QuoteLineView(BaseModel):
    code: str
    quantity: int
    amount: int


class QuoteView(BaseModel):
    rate_card_id: UUID
    version: int
    currency: str
    starts_at: datetime
    ends_at: datetime
    counts: dict[str, int]
    rental: int
    rental_days: int
    extras: list[QuoteLineView]
    total: int
    booking_id: UUID | None = None


_CARD = (
    "select id, class_id, location_id, version, currency, effective_from, hour_rate, day_rate, "
    "week_rate, month_rate, meter_allowance_per_day, excess_rate, created_at "
    "from gba.rental_rate_cards "
)


async def _view(conn: RuntimeConnection, row: Any) -> RateCardView:
    extras = await (
        await conn.execute(
            "select code, name, price, unit from gba.rental_rate_card_extras "
            "where card_id = %s order by code",
            (row[0],),
        )
    ).fetchall()
    return RateCardView(
        rate_card_id=row[0],
        class_id=row[1],
        location_id=row[2],
        version=row[3],
        currency=row[4],
        effective_from=row[5].astimezone(UTC),
        rates=RatesView(hour=row[6], day=row[7], week=row[8], month=row[9]),
        meter_allowance_per_day=row[10],
        excess_rate=row[11],
        extras=[ExtraView(code=e[0], name=e[1], price=e[2], unit=e[3]) for e in extras],
        created_at=row[12].astimezone(UTC),
    )


async def load_card(conn: RuntimeConnection, card_id: UUID) -> RateCardView | None:
    row = await (await conn.execute(_CARD + "where id = %s", (card_id,))).fetchone()
    return None if row is None else await _view(conn, row)


async def _known(conn: RuntimeConnection, class_id: UUID, location_id: UUID) -> None:
    found = await (
        await conn.execute("select 1 from gba.rental_classes where id = %s", (class_id,))
    ).fetchone()
    if found is None:
        raise NotFoundError("Class not found", class_id=str(class_id))
    branch = await caller_branch(conn)
    place = await (
        await conn.execute("select 1 from gba.locations where id = %s", (location_id,))
    ).fetchone()
    if place is None or (branch is not None and branch != location_id):
        raise NotFoundError("Branch not found", location_id=str(location_id))


async def list_cards(
    conn: RuntimeConnection, class_id: UUID, location_id: UUID | None
) -> RateCardList:
    found = await (
        await conn.execute("select 1 from gba.rental_classes where id = %s", (class_id,))
    ).fetchone()
    if found is None:
        raise NotFoundError("Class not found", class_id=str(class_id))
    rows = await (
        await conn.execute(
            _CARD + "where class_id = %s and (%s::uuid is null or location_id = %s) "
            "order by location_id, version",
            (class_id, location_id, location_id),
        )
    ).fetchall()
    return RateCardList(items=[await _view(conn, row) for row in rows])


async def create_card(
    conn: RuntimeConnection,
    business: UUID,
    class_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RateCardInput,
) -> RateCardView:
    """Record the next version of a class's rate card at a branch (decisions 1-2)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.rate_card", key)
    request = fingerprint(str(class_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_card(conn, UUID(str(stored.body["rate_card_id"])))
        if view is None:
            raise NotFoundError("Rate card not found")
        return view
    await _known(conn, class_id, body.location_id)
    await conn.execute("select 1 from gba.rental_classes where id = %s for update", (class_id,))
    clock = await (await conn.execute("select now()")).fetchone()
    now = clock[0] if clock else datetime.now(UTC)
    effective = body.effective_from or now
    if effective < now:
        raise RentalValueInvalidError("A rate card takes effect no earlier than it is recorded")
    latest = await (
        await conn.execute(
            "select coalesce(max(version), 0) from gba.rental_rate_cards "
            "where class_id = %s and location_id = %s",
            (class_id, body.location_id),
        )
    ).fetchone()
    version = (int(latest[0]) if latest else 0) + 1
    card_id = uuid7()
    rates = body.rates
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_rate_cards (tenant_id, id, class_id, location_id, version, "
                "currency, effective_from, hour_rate, day_rate, week_rate, month_rate, "
                "meter_allowance_per_day, excess_rate, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    card_id,
                    class_id,
                    body.location_id,
                    version,
                    body.currency,
                    effective,
                    rates.hour,
                    rates.day,
                    rates.week,
                    rates.month,
                    body.meter_allowance_per_day,
                    body.excess_rate,
                    user_id,
                ),
            )
            for extra in body.extras:
                await conn.execute(
                    "insert into gba.rental_rate_card_extras (tenant_id, card_id, code, name, "
                    "price, unit) values (%s, %s, %s, %s, %s, %s)",
                    (business, card_id, extra.code, extra.name, extra.price, extra.unit),
                )
    except CheckViolation as exc:
        if exc.diag.constraint_name == "rental_rate_cards_effective_check":
            raise RentalValueInvalidError(
                "A rate card takes effect no earlier than it is recorded"
            ) from exc
        raise
    view = await load_card(conn, card_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"rate_card_id": str(card_id)})
    return view


async def in_force(
    conn: RuntimeConnection, class_id: UUID, location_id: UUID, moment: datetime
) -> RateCardView:
    row = await (
        await conn.execute(
            _CARD + "where class_id = %s and location_id = %s and effective_from <= %s "
            "order by effective_from desc, version desc limit 1",
            (class_id, location_id, moment),
        )
    ).fetchone()
    if row is None:
        raise RentalNoRateError(
            "No rate card is in force for the class at the branch",
            class_id=str(class_id),
            location_id=str(location_id),
        )
    return await _view(conn, row)


def priced(
    card: RateCardView,
    starts: datetime,
    ends: datetime,
    wanted: list[QuoteExtraInput],
) -> QuoteView:
    offered = {e.code: e for e in card.extras}
    lines: list[tuple[Extra, int]] = []
    for item in wanted:
        extra = offered.get(item.code)
        if extra is None:
            raise RentalValueInvalidError("The rate card has no such extra", code=item.code)
        unit: Literal["per_day", "per_rental"] = (
            "per_day" if extra.unit == "per_day" else "per_rental"
        )
        lines.append((Extra(extra.code, extra.name, extra.price, unit), item.quantity))
    r = card.rates
    try:
        computed: Quote = quote(Rates(r.hour, r.day, r.week, r.month), starts, ends, lines)
    except ValueError as exc:
        raise RentalValueInvalidError(str(exc)) from exc
    return QuoteView(
        rate_card_id=card.rate_card_id,
        version=card.version,
        currency=card.currency,
        starts_at=starts.astimezone(UTC),
        ends_at=ends.astimezone(UTC),
        counts=computed.counts,
        rental=computed.rental,
        rental_days=computed.rental_days,
        extras=[QuoteLineView(code=c, quantity=q, amount=a) for c, q, a in computed.extras],
        total=computed.total,
    )


async def quote_period(conn: RuntimeConnection, body: QuoteInput) -> QuoteView:
    """Quote a class at a branch for a period from the card in force now (decision 3)."""
    await _known(conn, body.class_id, body.location_id)
    clock = await (await conn.execute("select now()")).fetchone()
    now = clock[0] if clock else datetime.now(UTC)
    card = await in_force(conn, body.class_id, body.location_id, now)
    return priced(card, body.starts_at, body.ends_at, body.extras)


async def quote_booking(conn: RuntimeConnection, booking_id: UUID) -> QuoteView:
    """Quote a booking from the card in force when it was made (decision 4)."""
    booking = await load_booking(conn, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    card = await in_force(conn, booking.class_id, booking.pickup_location_id, booking.booked_at)
    view = priced(card, booking.starts_at, booking.ends_at, [])
    return view.model_copy(update={"booking_id": booking_id})
