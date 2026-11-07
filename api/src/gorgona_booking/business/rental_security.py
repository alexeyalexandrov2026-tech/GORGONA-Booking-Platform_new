"""R5a (package R, RENT-01): recorded security of payment for a rental booking.

docs/plan/PACKAGE_R5A_DESIGN_2026-11-07.md. One security per booking with an agreement, in the
agreement currency; states and figures are derived from insert-only events that the database
checks (held, captured, released, expired). Nothing here touches charges or payments.
"""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import Strict, fingerprint, require_rental
from gorgona_booking.business.rental_agreements import check_time, load_agreement, open_booking
from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError

LIMIT = 1_000_000_000_000
Kind = Literal["held", "captured", "released", "expired"]
KINDS: tuple[Kind, ...] = ("held", "captured", "released", "expired")
State = Literal["requested", "held", "released", "expired"]


class RentalSecurityExistsError(ConflictError):
    """R5a decision 1: a booking has at most one security."""

    code = "RENTAL_SECURITY_EXISTS"


class RentalSecurityStateError(ConflictError):
    """R5a decision 2: an event that does not follow the security's states and amounts."""

    code = "RENTAL_SECURITY_STATE"


def _text(value: str) -> str:
    if not value.strip():
        raise ValueError("text that is not only blanks")
    return value


Reference = Annotated[str, AfterValidator(_text), Field(min_length=1, max_length=200)]
Basis = Annotated[str, AfterValidator(_text), Field(min_length=1, max_length=500)]


class SecurityInput(Strict):
    schema_version: Literal[1]
    amount: Annotated[int, Field(gt=0, lt=LIMIT, strict=True)]
    method: Literal["card_hold", "cash", "bank_transfer", "other"]


class SecurityEventInput(Strict):
    schema_version: Literal[1]
    kind: Kind
    amount: Annotated[int, Field(ge=0, lt=LIMIT, strict=True)]
    occurred_at: AwareDatetime
    reference: Reference | None = None
    hold_expires_at: AwareDatetime | None = None
    basis: Basis | None = None

    @model_validator(mode="after")
    def _fields(self) -> Self:
        if (self.kind == "held") != (self.reference is not None):
            raise ValueError("a hold, and only a hold, has an external reference")
        if self.kind != "held" and self.hold_expires_at is not None:
            raise ValueError("only a hold has an expiry")
        if (self.kind == "captured") != (self.basis is not None):
            raise ValueError("a capture, and only a capture, has a basis")
        return self


class SecurityEventView(BaseModel):
    sequence: int
    kind: Kind
    amount: int
    reference: str | None
    hold_expires_at: datetime | None
    basis: str | None
    occurred_at: datetime
    recorded_by: UUID


class SecurityView(BaseModel):
    security_id: UUID
    booking_id: UUID
    amount: int
    currency: str
    method: str
    state: State
    held: int
    captured: int
    released: int
    expired: int
    remaining: int
    events: list[SecurityEventView]


async def load_security(conn: RuntimeConnection, booking_id: UUID) -> SecurityView:
    row = await (
        await conn.execute(
            "select id, amount, currency, method from gba.rental_securities where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Security not found", booking_id=str(booking_id))
    rows = await (
        await conn.execute(
            "select sequence, kind, amount, reference, hold_expires_at, basis, occurred_at, "
            "recorded_by from gba.rental_security_events where security_id = %s order by sequence",
            (row[0],),
        )
    ).fetchall()
    events = [
        SecurityEventView(
            sequence=r[0],
            kind=r[1],
            amount=r[2],
            reference=r[3],
            hold_expires_at=r[4],
            basis=r[5],
            occurred_at=r[6],
            recorded_by=r[7],
        )
        for r in rows
    ]
    total = {kind: sum(e.amount for e in events if e.kind == kind) for kind in KINDS}
    state: State = "requested"
    for e in events:
        if e.kind != "captured":
            state = e.kind
    return SecurityView(
        security_id=row[0],
        booking_id=booking_id,
        amount=row[1],
        currency=row[2],
        method=row[3],
        state=state,
        held=total["held"],
        captured=total["captured"],
        released=total["released"],
        expired=total["expired"],
        remaining=total["held"] - total["captured"] - total["released"] - total["expired"],
        events=events,
    )


async def request_security(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: SecurityInput,
) -> SecurityView:
    """Request the booking's security in its agreement currency (decision 1)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.security", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_security(conn, booking_id)
    await open_booking(conn, booking_id)
    await load_agreement(conn, booking_id)
    currency = await (
        await conn.execute(
            "select r.currency from gba.rental_agreements a "
            "join gba.rental_agreement_versions v on v.tenant_id = a.tenant_id "
            "and v.agreement_id = a.id "
            "join gba.rental_rate_cards r on r.tenant_id = v.tenant_id and r.id = v.rate_card_id "
            "where a.booking_id = %s order by v.version desc limit 1",
            (booking_id,),
        )
    ).fetchone()
    if currency is None:
        raise NotFoundError("Agreement not found", booking_id=str(booking_id))
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_securities (tenant_id, id, booking_id, amount, currency, "
                "method, requested_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (business, uuid7(), booking_id, body.amount, currency[0], body.method, user_id),
            )
    except UniqueViolation as exc:
        raise RentalSecurityExistsError("The booking already has a security") from exc
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_security(conn, booking_id)


async def record_event(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: SecurityEventInput,
) -> SecurityView:
    """Record the next event of the booking's security; the database checks it (decision 2)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.security_event", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_security(conn, booking_id)
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    current = await load_security(conn, booking_id)
    await check_time(conn, body.occurred_at)
    sequence = current.events[-1].sequence + 1 if current.events else 1
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_security_events (tenant_id, security_id, sequence, kind, "
                "amount, reference, hold_expires_at, basis, occurred_at, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    current.security_id,
                    sequence,
                    body.kind,
                    body.amount,
                    body.reference,
                    body.hold_expires_at,
                    body.basis,
                    body.occurred_at,
                    user_id,
                ),
            )
    except CheckViolation as exc:
        name = exc.diag.constraint_name or ""
        if name.startswith("rental_security_events_"):
            raise RentalSecurityStateError(
                "The event does not follow the security's states and amounts", reason=name
            ) from exc
        raise
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_security(conn, booking_id)
