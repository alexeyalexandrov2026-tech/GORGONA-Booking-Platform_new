"""R4b (package R, RENT-01): the rental agreement as the frozen accepted quote, and its versions.

docs/plan/PACKAGE_R4B_DESIGN_2026-11-06.md. Version 1 freezes the quote of the card in force when
the booking was made, with the chosen extras, the source, who accepted and when; a change is the
next insert-only version with a reason over the same card and period.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import UniqueViolation
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import (
    RentalValueInvalidError,
    Strict,
    fingerprint,
    require_rental,
)
from gorgona_booking.business.rental_bookings import (
    BookingView,
    RentalBookingCancelledError,
    load_booking,
)
from gorgona_booking.business.rental_rates import (
    QuoteExtraInput,
    QuoteView,
    RateCardView,
    in_force,
    load_card,
    priced,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError


class RentalAgreementExistsError(ConflictError):
    """R4b decision 1: a booking has at most one agreement."""

    code = "RENTAL_AGREEMENT_EXISTS"


def _text(value: str) -> str:
    if not value.strip():
        raise ValueError("text that is not only blanks")
    return value


Name = Annotated[str, AfterValidator(_text), Field(min_length=1, max_length=200)]
Reason = Annotated[str, AfterValidator(_text), Field(min_length=1, max_length=500)]


class AcceptInput(Strict):
    schema_version: Literal[1]
    # Platform responses are reserved for a customer acting through a grant (R-09).
    source: Literal["paper", "email"]
    accepted_by: Name
    accepted_at: AwareDatetime
    extras: Annotated[list[QuoteExtraInput], Field(default_factory=list, max_length=50)]

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        codes = [e.code for e in self.extras]
        if len(codes) != len(set(codes)):
            raise ValueError("every extra is chosen once")
        return self


class ChangeInput(AcceptInput):
    reason: Reason


class AgreementExtraView(BaseModel):
    code: str
    name: str
    price: int
    unit: str
    quantity: int
    amount: int


class VersionView(BaseModel):
    version: int
    rate_card_id: UUID
    card_version: int
    currency: str
    starts_at: datetime
    ends_at: datetime
    counts: dict[str, int]
    rental: int
    rental_days: int
    extras: list[AgreementExtraView]
    total: int
    source: str
    accepted_by: str
    accepted_at: datetime
    reason: str | None
    created_at: datetime


class AgreementView(BaseModel):
    agreement_id: UUID
    booking_id: UUID
    current_version: int
    versions: list[VersionView]


async def _versions(conn: RuntimeConnection, agreement_id: UUID) -> list[VersionView]:
    rows = await (
        await conn.execute(
            "select v.version, v.rate_card_id, r.version, r.currency, v.starts_at, v.ends_at, "
            "v.month_count, v.week_count, v.day_count, v.hour_count, v.rental_amount, "
            "v.rental_days, v.total, v.source, v.accepted_by, v.accepted_at, v.reason, "
            "v.created_at "
            "from gba.rental_agreement_versions v join gba.rental_rate_cards r "
            "on r.tenant_id = v.tenant_id and r.id = v.rate_card_id "
            "where v.agreement_id = %s order by v.version",
            (agreement_id,),
        )
    ).fetchall()
    lines = await (
        await conn.execute(
            "select version, code, name, price, unit, quantity, amount "
            "from gba.rental_agreement_version_extras where agreement_id = %s "
            "order by version, code",
            (agreement_id,),
        )
    ).fetchall()
    extras: dict[int, list[AgreementExtraView]] = {}
    for line in lines:
        extras.setdefault(line[0], []).append(
            AgreementExtraView(
                code=line[1],
                name=line[2],
                price=line[3],
                unit=line[4],
                quantity=line[5],
                amount=line[6],
            )
        )
    return [
        VersionView(
            version=row[0],
            rate_card_id=row[1],
            card_version=row[2],
            currency=row[3],
            starts_at=row[4].astimezone(UTC),
            ends_at=row[5].astimezone(UTC),
            counts={"month": row[6], "week": row[7], "day": row[8], "hour": row[9]},
            rental=row[10],
            rental_days=row[11],
            extras=extras.get(row[0], []),
            total=row[12],
            source=row[13],
            accepted_by=row[14],
            accepted_at=row[15].astimezone(UTC),
            reason=row[16],
            created_at=row[17].astimezone(UTC),
        )
        for row in rows
    ]


async def _agreement_id(conn: RuntimeConnection, booking_id: UUID) -> UUID | None:
    row = await (
        await conn.execute(
            "select id from gba.rental_agreements where booking_id = %s", (booking_id,)
        )
    ).fetchone()
    return None if row is None else UUID(str(row[0]))


async def load_agreement(conn: RuntimeConnection, booking_id: UUID) -> AgreementView:
    agreement_id = await _agreement_id(conn, booking_id)
    if agreement_id is None:
        raise NotFoundError("Agreement not found", booking_id=str(booking_id))
    versions = await _versions(conn, agreement_id)
    return AgreementView(
        agreement_id=agreement_id,
        booking_id=booking_id,
        current_version=versions[-1].version,
        versions=versions,
    )


async def open_booking(conn: RuntimeConnection, booking_id: UUID) -> BookingView:
    booking = await load_booking(conn, booking_id)
    if booking is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    if booking.cancellation is not None:
        raise RentalBookingCancelledError("A cancelled booking takes no agreement")
    return booking


async def check_time(conn: RuntimeConnection, accepted_at: datetime) -> None:
    clock = await (await conn.execute("select now()")).fetchone()
    if accepted_at > (clock[0] if clock else datetime.now(UTC)):
        raise RentalValueInvalidError("An acceptance is not in the future")


async def record_version(
    conn: RuntimeConnection,
    business: UUID,
    agreement_id: UUID,
    version: int,
    card: RateCardView,
    quote: QuoteView,
    body: AcceptInput,
    reason: str | None,
    user_id: UUID,
) -> None:
    offered = {e.code: e for e in card.extras}
    counts = quote.counts
    await conn.execute(
        "insert into gba.rental_agreement_versions (tenant_id, agreement_id, version, "
        "rate_card_id, starts_at, ends_at, month_count, week_count, day_count, hour_count, "
        "rental_amount, rental_days, total, source, accepted_by, accepted_at, reason, recorded_by) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            business,
            agreement_id,
            version,
            card.rate_card_id,
            quote.starts_at,
            quote.ends_at,
            counts["month"],
            counts["week"],
            counts["day"],
            counts["hour"],
            quote.rental,
            quote.rental_days,
            quote.total,
            body.source,
            body.accepted_by,
            body.accepted_at,
            reason,
            user_id,
        ),
    )
    for line in quote.extras:
        extra = offered[line.code]
        await conn.execute(
            "insert into gba.rental_agreement_version_extras (tenant_id, agreement_id, version, "
            "code, name, price, unit, quantity, amount) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                agreement_id,
                version,
                extra.code,
                extra.name,
                extra.price,
                extra.unit,
                line.quantity,
                line.amount,
            ),
        )


async def accept(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AcceptInput,
) -> AgreementView:
    """Freeze the booking's quote as version 1 of its agreement (decisions 1-2)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.agreement", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_agreement(conn, booking_id)
    booking = await open_booking(conn, booking_id)
    if await _agreement_id(conn, booking_id) is not None:
        raise RentalAgreementExistsError("The booking already has an agreement")
    await check_time(conn, body.accepted_at)
    card = await in_force(conn, booking.class_id, booking.pickup_location_id, booking.booked_at)
    quote = priced(card, booking.starts_at, booking.ends_at, body.extras)
    agreement_id = uuid7()
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_agreements (tenant_id, id, booking_id, created_by) "
                "values (%s, %s, %s, %s)",
                (business, agreement_id, booking_id, user_id),
            )
            await record_version(conn, business, agreement_id, 1, card, quote, body, None, user_id)
    except UniqueViolation as exc:
        raise RentalAgreementExistsError("The booking already has an agreement") from exc
    await idempotency.complete(conn, scope, 200, {"agreement_id": str(agreement_id)})
    return await load_agreement(conn, booking_id)


async def change(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ChangeInput,
) -> AgreementView:
    """Record the next version over the same card and period with new extras (decision 3)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.agreement_version", key)
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
    quote = priced(card, latest.starts_at, latest.ends_at, body.extras)
    async with module_writes(RENTAL_MODULE), conn.transaction():
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
    await idempotency.complete(conn, scope, 200, {"agreement_id": str(current.agreement_id)})
    return await load_agreement(conn, booking_id)
