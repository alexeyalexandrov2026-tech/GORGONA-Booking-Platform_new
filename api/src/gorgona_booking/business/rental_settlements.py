"""R7a (package R, RENT-01): the final settlement invoice of a rental agreement.

docs/plan/PACKAGE_R7A_DESIGN_2026-11-07.md. After the return, one FIN-03 receivable invoice draft
for the booking's customer: the latest agreement version's total, the R6b meter excess and the late
return priced by the frozen card's hour or day rate. The database recomputes every figure and checks
the document; issuing and paying the invoice stay FIN-03's own flows.
"""

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import financial_documents
from gorgona_booking.business.financial_contracts import InvoiceDraftInput, InvoiceLineInput
from gorgona_booking.business.ledger_contracts import from_minor
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import OneLine, Strict, fingerprint, require_rental
from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.business.rental_usage import load_usage
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError


class RentalSettlementStateError(ConflictError):
    """R7a decision 1: no agreement or return, a cancelled booking, or already settled."""

    code = "RENTAL_SETTLEMENT_STATE"


class RentalSettlementUnpricedError(ConflictError):
    """R7a decision 2: an overdue return on a card without an hour or a day rate."""

    code = "RENTAL_SETTLEMENT_UNPRICED"


class SettlementInput(Strict):
    schema_version: Literal[1]
    book_id: UUID
    receivable_account_id: UUID
    revenue_account_id: UUID
    invoice_date: date
    due_date: date | None = None
    number: Annotated[OneLine, Field(min_length=1, max_length=62)]
    title: Annotated[OneLine, Field(min_length=1, max_length=200)] = "Rental settlement"

    @model_validator(mode="after")
    def _due_after_invoice(self) -> Self:
        if self.due_date is not None and self.due_date < self.invoice_date:
            raise ValueError("The due date is before the invoice date")
        return self


class SettlementView(BaseModel):
    booking_id: UUID
    agreement_version: int
    currency: str
    rental_minor: int
    excess_minor: int
    late_minor: int
    late_units: int
    total_minor: int
    book_id: UUID
    invoice_document_id: UUID
    settled_by: UUID
    settled_at: datetime


async def load_settlement(conn: RuntimeConnection, booking_id: UUID) -> SettlementView:
    """The booking's settlement; not found outside the caller's scope or before it exists."""
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    row = await (
        await conn.execute(
            "select s.agreement_version, v.currency, s.rental_minor, s.excess_minor, "
            "s.late_minor, s.late_units, s.total_minor, s.book_id, s.invoice_document_id, "
            "s.settled_by, s.settled_at from gba.rental_settlements s "
            "join gba.financial_document_versions v on v.tenant_id = s.tenant_id "
            "and v.book_id = s.book_id and v.document_id = s.invoice_document_id "
            "and v.revision = 1 where s.booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Settlement not found", booking_id=str(booking_id))
    return SettlementView(
        booking_id=booking_id,
        agreement_version=row[0],
        currency=row[1],
        rental_minor=row[2],
        excess_minor=row[3],
        late_minor=row[4],
        late_units=row[5],
        total_minor=row[6],
        book_id=row[7],
        invoice_document_id=row[8],
        settled_by=row[9],
        settled_at=row[10],
    )


async def _terms(
    conn: RuntimeConnection, booking_id: UUID
) -> tuple[int, int, int | None, int | None]:
    """The latest agreement version, its total and the card's hour and day rates."""
    cancelled = await (
        await conn.execute(
            "select 1 from gba.rental_booking_cancellations where booking_id = %s", (booking_id,)
        )
    ).fetchone()
    settled = await (
        await conn.execute(
            "select 1 from gba.rental_settlements where booking_id = %s", (booking_id,)
        )
    ).fetchone()
    if cancelled is not None or settled is not None:
        raise RentalSettlementStateError("The booking is cancelled or already settled")
    row = await (
        await conn.execute(
            "select v.version, v.total, r.hour_rate, r.day_rate from gba.rental_agreements a "
            "join gba.rental_agreement_versions v on v.tenant_id = a.tenant_id "
            "and v.agreement_id = a.id "
            "join gba.rental_rate_cards r on r.tenant_id = v.tenant_id and r.id = v.rate_card_id "
            "where a.booking_id = %s order by v.version desc limit 1",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        raise RentalSettlementStateError("The booking has no agreement")
    return int(row[0]), int(row[1]), row[2], row[3]


def _late(seconds: int, hour_rate: int | None, day_rate: int | None) -> tuple[int, int]:
    """Decision 2(c): started hours at the hour rate, else started days at the day rate."""
    if seconds <= 0:
        return 0, 0
    if hour_rate is not None:
        units = -(-seconds // 3600)
        return units, units * hour_rate
    if day_rate is not None:
        units = -(-seconds // 86400)
        return units, units * day_rate
    raise RentalSettlementUnpricedError("An overdue return needs an hour or a day rate")


async def _customer(conn: RuntimeConnection, booking_id: UUID) -> tuple[UUID, int]:
    row = await (
        await conn.execute(
            "select b.customer_id, (select max(v.revision) from gba.counterparty_versions v "
            "where v.counterparty_id = b.customer_id) from gba.rental_bookings b where b.id = %s",
            (booking_id,),
        )
    ).fetchone()
    if row is None or row[1] is None:
        raise InvalidReferenceError("Unknown customer", field="customer_id")
    return row[0], int(row[1])


async def settle(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: SettlementInput,
) -> SettlementView:
    """Settle the returned booking into one FIN-03 receivable invoice draft (decisions 1-5)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.settlement", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_settlement(conn, booking_id)
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    version, rental, hour_rate, day_rate = await _terms(conn, booking_id)
    usage = await load_usage(conn, booking_id)
    if usage.state != "returned":
        raise RentalSettlementStateError("A settlement follows the return")
    units, late = _late(usage.overdue_seconds, hour_rate, day_rate)
    excess = usage.excess_amount or 0
    customer, revision = await _customer(conn, booking_id)
    minor = await (
        await conn.execute(
            "select minor_units from gba.currencies where code = %s", (usage.currency,)
        )
    ).fetchone()
    if minor is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    places = int(minor[0])
    lines = tuple(
        InvoiceLineInput(
            line_id=uuid7(),
            counter_account_id=body.revenue_account_id,
            description=text,
            amount=from_minor(amount, places),
        )
        for text, amount in (
            (f"Rental of {usage.rental_days} days and extras", rental),
            ("Meter use over the allowance", excess),
            (f"Late return, {units} started units", late),
        )
        if amount > 0
    )
    document = uuid7()
    await financial_documents.save_draft(
        conn,
        business_id=business,
        book_id=body.book_id,
        document_id=document,
        user_id=user_id,
        actor=actor,
        key=key,
        body=InvoiceDraftInput(
            expected_revision=0,
            direction="receivable",
            counterparty_id=customer,
            counterparty_revision=revision,
            currency=usage.currency,
            invoice_date=body.invoice_date,
            due_date=body.due_date,
            control_account_id=body.receivable_account_id,
            title=body.title,
            number=body.number,
            lines=lines,
        ),
    )
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_settlements (tenant_id, booking_id, agreement_version, "
                "rental_minor, excess_minor, late_minor, late_units, total_minor, book_id, "
                "invoice_document_id, settled_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    booking_id,
                    version,
                    rental,
                    excess,
                    late,
                    units,
                    rental + excess + late,
                    body.book_id,
                    document,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise RentalSettlementStateError("The booking is already settled") from exc
    except CheckViolation as exc:
        name = exc.diag.constraint_name or ""
        if name == "rental_settlements_unpriced_check":
            raise RentalSettlementUnpricedError("An overdue return needs a rate") from exc
        if name.startswith("rental_settlements_"):
            raise RentalSettlementStateError("The settlement does not follow the booking") from exc
        raise
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_settlement(conn, booking_id)
