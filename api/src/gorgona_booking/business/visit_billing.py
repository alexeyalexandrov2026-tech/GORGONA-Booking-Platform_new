"""L4: visit billing through FIN-03 (package L, BEAUTY-01).

Design docs/plan/PACKAGE_L4_DESIGN_2026-10-22.md. The visit invoice is a FIN-03 receivable draft
built from the visit's quote lines plus fee lines, linked to the visit once; issuing it and paying
it (a deposit and the rest) are FIN-03's own routes.
"""

import hashlib
import json
from datetime import date
from typing import Any
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import financial_documents, settlements
from gorgona_booking.business.financial_contracts import (
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.settlement_contracts import ObligationView
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)

_AMOUNT = r"^(0|[1-9][0-9]{0,17})(\.[0-9]{1,3})?$"


class VisitNotBillableError(ConflictError):
    code = "VISIT_NOT_BILLABLE"


class VisitAlreadyInvoicedError(ConflictError):
    code = "VISIT_ALREADY_INVOICED"


class VisitPriceNotExactError(DomainError):
    code = "VISIT_PRICE_NOT_EXACT"


def catalog_minor(price_cents: int, units: int) -> int:
    """A catalog price (hundredths of the main unit) in the currency's minor units, exactly.

    L8 decision 55: never rounded; a price that is not exact in the currency is refused.
    """
    scaled: int = price_cents * pow(10, units)
    if scaled % 100:
        raise VisitPriceNotExactError(
            "The price cannot be written exactly in this currency", price_cents=price_cents
        )
    return scaled // 100


def priced_lines(quote: dict[str, Any], units: int) -> list[tuple[dict[str, Any], int]]:
    """The quote lines a visit invoice bills, in quote order, with their minor amounts.

    A free line gets no invoice line (L8 decision 56); prepaid maps a quote line to its invoice line
    through this same list (decision 57).
    """
    pairs = [
        (line, catalog_minor(int(line["price_cents"]), units)) for line in quote.get("lines") or []
    ]
    return [(line, minor) for line, minor in pairs if minor > 0]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeeLine(_Strict):
    """A cancellation, no-show or other fee, named by a finance user (decision 26)."""

    description: str = Field(min_length=1, max_length=500)
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT)
    account_id: UUID


class VisitInvoiceInput(_Strict):
    book_id: UUID
    counterparty_id: UUID
    control_account_id: UUID
    revenue_account_id: UUID
    invoice_date: date
    due_date: date | None = None
    number: str = Field(min_length=1, max_length=64)
    title: str = Field(default="Visit", min_length=1, max_length=200)
    fee_lines: list[FeeLine] = Field(default_factory=list, max_length=20)


class VisitInvoiceView(BaseModel):
    booking_id: UUID
    book_id: UUID
    document_id: UUID
    invoice: InvoiceDocumentView
    # Once the invoice is issued: its obligation with paid and available amounts (decision 25).
    obligation: ObligationView | None


def _money(minor: int, units: int) -> str:
    whole, fraction = divmod(minor, 10**units)
    return str(whole) if units == 0 else f"{whole}.{fraction:0{units}d}"


async def load_visit_invoice(
    conn: RuntimeConnection, tenant_id: UUID, booking_id: UUID
) -> VisitInvoiceView | None:
    link = await (
        await conn.execute(
            "select book_id, document_id from gba.visit_invoices where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if link is None:
        return None
    invoice = await financial_documents.load_invoice(conn, tenant_id, link[0], link[1])
    if invoice is None:
        raise NotFoundError("Invoice not found", document_id=str(link[1]))
    obligation = (
        await settlements.load_obligation(conn, tenant_id, link[0], invoice.obligation_id)
        if invoice.obligation_id is not None
        else None
    )
    return VisitInvoiceView(
        booking_id=booking_id,
        book_id=link[0],
        document_id=link[1],
        invoice=invoice,
        obligation=obligation,
    )


async def _lines(
    conn: RuntimeConnection, status: str, quote: dict[str, Any], body: VisitInvoiceInput
) -> tuple[str, list[InvoiceLineInput]]:
    """The quote lines of a confirmed visit, then the fee lines (decisions 22 and 24)."""
    currency = str(quote.get("currency", ""))
    row = await (
        await conn.execute("select minor_units from gba.currencies where code = %s", (currency,))
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown currency of the visit", field="currency")
    units = int(row[0])
    lines: list[InvoiceLineInput] = []
    if status == "CONFIRMED":
        lines.extend(
            InvoiceLineInput(
                line_id=uuid7(),
                counter_account_id=body.revenue_account_id,
                description=str(line["name"]),
                amount=_money(minor, units),
            )
            for line, minor in priced_lines(quote, units)
        )
    elif status != "CANCELLED" or not body.fee_lines:
        raise VisitNotBillableError(
            "Only a confirmed visit, or a cancelled one with a fee, is billed", status=status
        )
    lines.extend(
        InvoiceLineInput(
            line_id=uuid7(),
            counter_account_id=fee.account_id,
            description=fee.description,
            amount=fee.amount,
        )
        for fee in body.fee_lines
    )
    return currency, lines


async def bill_visit(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: VisitInvoiceInput,
) -> VisitInvoiceView:
    """Save the visit's FIN-03 draft invoice and link it to the visit, once (decision 23)."""
    scope = IdempotencyScope(tenant_id, actor, "visit.invoice", key)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"booking_id": str(booking_id), "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_visit_invoice(conn, tenant_id, booking_id)
        if view is None:
            raise NotFoundError("Invoice not found", booking_id=str(booking_id))
        return view
    booking = await (
        await conn.execute(
            "select status, quote from gba.bookings where id = %s for update", (booking_id,)
        )
    ).fetchone()
    if booking is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    if await load_visit_invoice(conn, tenant_id, booking_id) is not None:
        raise VisitAlreadyInvoicedError("This visit already has its invoice")
    currency, lines = await _lines(conn, str(booking[0]), booking[1], body)
    party = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions where counterparty_id = %s",
            (body.counterparty_id,),
        )
    ).fetchone()
    if party is None or party[0] is None:
        raise InvalidReferenceError("Unknown counterparty", field="counterparty_id")
    document = uuid7()
    await financial_documents.save_draft(
        conn,
        business_id=tenant_id,
        book_id=body.book_id,
        document_id=document,
        user_id=user_id,
        actor=actor,
        key=key,
        body=InvoiceDraftInput(
            expected_revision=0,
            direction="receivable",
            counterparty_id=body.counterparty_id,
            counterparty_revision=int(party[0]),
            currency=currency,
            invoice_date=body.invoice_date,
            due_date=body.due_date,
            control_account_id=body.control_account_id,
            title=body.title,
            number=body.number,
            lines=tuple(lines),
        ),
    )
    await conn.execute(
        "insert into gba.visit_invoices (tenant_id, booking_id, book_id, document_id, "
        "created_by) values (%s, %s, %s, %s, %s)",
        (tenant_id, booking_id, body.book_id, document, user_id),
    )
    view = await load_visit_invoice(conn, tenant_id, booking_id)
    assert view is not None  # noqa: S101 - linked above
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return view
