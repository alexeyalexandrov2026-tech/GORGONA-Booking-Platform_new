"""R7c (package R, RENT-01): the reconciliation per rental agreement, derived on read.

docs/plan/PACKAGE_R7C_DESIGN_2026-11-08.md. The R7a settlement and the R7b damage charges with the
FIN-03 state and balance of their invoices, the R7b refunds with their credit note and the refund
obligation FIN-03 made at its issue, the R5a security figures and the totals. Nothing is stored and
no rule is added.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.business.rental_security import load_security
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import NotFoundError


class DocumentRow(BaseModel):
    kind: Literal["settlement", "damage_charge"]
    number: int | None
    amount_minor: int
    book_id: UUID
    document_id: UUID
    state: Literal["draft", "issued"]
    principal_minor: int
    paid_minor: int
    credited_minor: int
    open_minor: int


class RefundRow(BaseModel):
    number: int
    method: Literal["credit", "external"]
    amount_minor: int
    state: Literal["recorded", "draft", "issued"]
    credit_document_id: UUID | None
    refund_obligation_minor: int | None
    refund_paid_minor: int | None


class SecurityFigures(BaseModel):
    state: str
    amount: int
    held: int
    captured: int
    released: int
    expired: int
    remaining: int


class Totals(BaseModel):
    charged_minor: int
    invoiced_minor: int
    paid_minor: int
    credited_minor: int
    open_minor: int
    refunded_external_minor: int
    refund_owed_minor: int


class ReconciliationView(BaseModel):
    booking_id: UUID
    currency: str
    documents: list[DocumentRow]
    refunds: list[RefundRow]
    security: SecurityFigures | None
    totals: Totals


async def _balance(
    conn: RuntimeConnection, business: UUID, book: UUID, source_kind: str, source: UUID
) -> tuple[int, int, int, int] | None:
    """Principal, paid, credited and reserved of the obligation FIN-03 made for a document."""
    row = await (
        await conn.execute(
            "select b.principal_minor, b.paid_minor, b.credited_minor, b.reserved_minor "
            "from gba.financial_obligations o, gba.obligation_balance(%s, o.book_id, o.id) b "
            "where o.book_id = %s and o.source_kind = %s and o.source_id = %s",
            (business, book, source_kind, source),
        )
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])


async def _document(
    conn: RuntimeConnection,
    business: UUID,
    kind: Literal["settlement", "damage_charge"],
    number: int | None,
    amount: int,
    book: UUID,
    document: UUID,
) -> DocumentRow:
    balance = await _balance(conn, business, book, "invoice", document)
    if balance is None:
        return DocumentRow(
            kind=kind,
            number=number,
            amount_minor=amount,
            book_id=book,
            document_id=document,
            state="draft",
            principal_minor=0,
            paid_minor=0,
            credited_minor=0,
            open_minor=0,
        )
    principal, paid, credited, reserved = balance
    return DocumentRow(
        kind=kind,
        number=number,
        amount_minor=amount,
        book_id=book,
        document_id=document,
        state="issued",
        principal_minor=principal,
        paid_minor=paid,
        credited_minor=credited,
        open_minor=principal - paid - credited - reserved,
    )


async def load_reconciliation(
    conn: RuntimeConnection, business: UUID, booking_id: UUID
) -> ReconciliationView:
    """Decisions 1-5: everything charged, paid, credited, refunded and secured for the booking."""
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    settled = await (
        await conn.execute(
            "select s.total_minor, s.book_id, s.invoice_document_id, v.currency "
            "from gba.rental_settlements s join gba.financial_document_versions v "
            "on v.tenant_id = s.tenant_id and v.book_id = s.book_id "
            "and v.document_id = s.invoice_document_id and v.revision = 1 "
            "where s.booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if settled is None:
        raise NotFoundError("Settlement not found", booking_id=str(booking_id))
    documents = [
        await _document(conn, business, "settlement", None, int(settled[0]), settled[1], settled[2])
    ]
    for number, amount, book, document in await (
        await conn.execute(
            "select number, amount_minor, book_id, invoice_document_id "
            "from gba.rental_damage_charges where booking_id = %s order by number",
            (booking_id,),
        )
    ).fetchall():
        documents.append(
            await _document(conn, business, "damage_charge", number, int(amount), book, document)
        )
    refunds: list[RefundRow] = []
    for number, method, amount, book, note in await (
        await conn.execute(
            "select number, method, amount_minor, book_id, credit_document_id "
            "from gba.rental_refunds where booking_id = %s order by number",
            (booking_id,),
        )
    ).fetchall():
        if method == "external":
            refunds.append(
                RefundRow(
                    number=number,
                    method="external",
                    amount_minor=int(amount),
                    state="recorded",
                    credit_document_id=None,
                    refund_obligation_minor=None,
                    refund_paid_minor=None,
                )
            )
            continue
        state = await (
            await conn.execute(
                "select state from gba.financial_document_versions where book_id = %s "
                "and document_id = %s order by revision desc limit 1",
                (book, note),
            )
        ).fetchone()
        issued = state is not None and state[0] == "issued"
        owed = await _balance(conn, business, book, "credit_refund", note) if issued else None
        refunds.append(
            RefundRow(
                number=number,
                method="credit",
                amount_minor=int(amount),
                state="issued" if issued else "draft",
                credit_document_id=note,
                refund_obligation_minor=(owed[0] if owed else 0) if issued else None,
                refund_paid_minor=(owed[1] if owed else 0) if issued else None,
            )
        )
    try:
        held = await load_security(conn, booking_id)
    except NotFoundError:
        security = None
    else:
        security = SecurityFigures(
            state=held.state,
            amount=held.amount,
            held=held.held,
            captured=held.captured,
            released=held.released,
            expired=held.expired,
            remaining=held.remaining,
        )
    return ReconciliationView(
        booking_id=booking_id,
        currency=settled[3],
        documents=documents,
        refunds=refunds,
        security=security,
        totals=Totals(
            charged_minor=sum(d.amount_minor for d in documents),
            invoiced_minor=sum(d.principal_minor for d in documents),
            paid_minor=sum(d.paid_minor for d in documents),
            credited_minor=sum(d.credited_minor for d in documents),
            open_minor=sum(d.open_minor for d in documents),
            refunded_external_minor=sum(r.amount_minor for r in refunds if r.method == "external"),
            refund_owed_minor=sum(
                (r.refund_obligation_minor or 0) - (r.refund_paid_minor or 0) for r in refunds
            ),
        ),
    )
