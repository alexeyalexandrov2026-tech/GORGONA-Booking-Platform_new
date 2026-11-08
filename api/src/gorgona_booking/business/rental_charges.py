"""R7b (package R, RENT-01): damage charges and refunds of a rental agreement.

docs/plan/PACKAGE_R7B_DESIGN_2026-11-08.md. After the settlement, a damage charge cites new marks of
the return inspection and is its own FIN-03 receivable invoice draft; a refund is a FIN-03 credit
note draft against an issued obligation of the booking's settlement or charges, or a recorded
external refund. Neither edits the settlement, the security or another charge; the database
rechecks the basis, the numbering, the ceiling and the documents.
"""

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import credit_notes, financial_documents
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditLineInput,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.ledger_contracts import from_minor
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import OneLine, Strict, fingerprint, require_rental
from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

Amount = Annotated[int, Field(ge=1, le=999_999_999_999)]
Reason = Annotated[OneLine, Field(min_length=1, max_length=500)]
Number = Annotated[OneLine, Field(min_length=1, max_length=62)]
Position = Annotated[int, Field(ge=1, le=50)]


class RentalChargeStateError(ConflictError):
    """R7b decisions 1-2: not settled, a basis mark that is not new or already charged, or an
    invoice that is not the booking's or not issued."""

    code = "RENTAL_CHARGE_STATE"


class RentalRefundExceedsError(ConflictError):
    """R7b decision 2: refunds never exceed the settlement total plus the damage charged."""

    code = "RENTAL_REFUND_EXCEEDS"


class DamageChargeInput(Strict):
    schema_version: Literal[1]
    marks: Annotated[tuple[Position, ...], Field(min_length=1, max_length=50)]
    amount: Amount
    reason: Reason
    book_id: UUID
    receivable_account_id: UUID
    revenue_account_id: UUID
    invoice_date: date
    due_date: date | None = None
    number: Number
    title: Annotated[OneLine, Field(min_length=1, max_length=200)] = "Damage charge"


class RefundInput(Strict):
    schema_version: Literal[1]
    amount: Amount
    reason: Reason
    method: Literal["credit", "external"]
    invoice_document_id: UUID | None = None
    credit_date: date | None = None
    number: Number | None = None
    reference: Annotated[OneLine, Field(min_length=1, max_length=200)] | None = None
    refunded_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _fields_follow_the_method(self) -> Self:
        credit = (self.invoice_document_id, self.credit_date, self.number)
        external = (self.reference, self.refunded_at)
        if self.method == "credit" and (None in credit or any(x is not None for x in external)):
            raise ValueError("A credit refund names the invoice, the credit date and a number")
        if self.method == "external" and (None in external or any(x is not None for x in credit)):
            raise ValueError("An external refund names its reference and time")
        return self


class DamageChargeView(BaseModel):
    number: int
    marks: list[int]
    amount_minor: int
    reason: str
    book_id: UUID
    invoice_document_id: UUID
    charged_by: UUID
    charged_at: datetime


class RefundView(BaseModel):
    number: int
    method: Literal["credit", "external"]
    amount_minor: int
    reason: str
    reference: str | None
    refunded_at: datetime | None
    book_id: UUID | None
    credit_document_id: UUID | None
    recorded_by: UUID
    recorded_at: datetime


class ChargesView(BaseModel):
    booking_id: UUID
    damage_charges: list[DamageChargeView]
    refunds: list[RefundView]


async def load_charges(conn: RuntimeConnection, booking_id: UUID) -> ChargesView:
    """The booking's damage charges and refunds in order; not found outside the caller's scope."""
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    charges = await (
        await conn.execute(
            "select c.number, coalesce(array_agg(m.position order by m.position) "
            "filter (where m.position is not null), '{}'), c.amount_minor, c.reason, c.book_id, "
            "c.invoice_document_id, c.charged_by, c.charged_at "
            "from gba.rental_damage_charges c left join gba.rental_damage_charge_marks m "
            "on m.tenant_id = c.tenant_id and m.booking_id = c.booking_id and m.number = c.number "
            "where c.booking_id = %s group by c.tenant_id, c.booking_id, c.number "
            "order by c.number",
            (booking_id,),
        )
    ).fetchall()
    refunds = await (
        await conn.execute(
            "select number, method, amount_minor, reason, reference, refunded_at, book_id, "
            "credit_document_id, recorded_by, recorded_at from gba.rental_refunds "
            "where booking_id = %s order by number",
            (booking_id,),
        )
    ).fetchall()
    return ChargesView(
        booking_id=booking_id,
        damage_charges=[
            DamageChargeView(
                number=r[0],
                marks=list(r[1]),
                amount_minor=r[2],
                reason=r[3],
                book_id=r[4],
                invoice_document_id=r[5],
                charged_by=r[6],
                charged_at=r[7],
            )
            for r in charges
        ],
        refunds=[
            RefundView(
                number=r[0],
                method=r[1],
                amount_minor=r[2],
                reason=r[3],
                reference=r[4],
                refunded_at=r[5],
                book_id=r[6],
                credit_document_id=r[7],
                recorded_by=r[8],
                recorded_at=r[9],
            )
            for r in refunds
        ],
    )


class _Settled(BaseModel):
    customer: UUID
    revision: int
    currency: str
    places: int
    total: int
    book: UUID
    invoice: UUID


async def _settled(conn: RuntimeConnection, booking_id: UUID) -> _Settled:
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    row = await (
        await conn.execute(
            "select b.customer_id, (select max(p.revision) from gba.counterparty_versions p "
            "where p.counterparty_id = b.customer_id), v.currency, c.minor_units, s.total_minor, "
            "s.book_id, s.invoice_document_id from gba.rental_settlements s "
            "join gba.rental_bookings b on b.tenant_id = s.tenant_id and b.id = s.booking_id "
            "join gba.financial_document_versions v on v.tenant_id = s.tenant_id "
            "and v.book_id = s.book_id and v.document_id = s.invoice_document_id "
            "and v.revision = 1 join gba.currencies c on c.code = v.currency "
            "where s.booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        raise RentalChargeStateError("The booking is not settled")
    if row[1] is None:
        raise InvalidReferenceError("Unknown customer", field="customer_id")
    return _Settled(
        customer=row[0],
        revision=int(row[1]),
        currency=row[2],
        places=int(row[3]),
        total=int(row[4]),
        book=row[5],
        invoice=row[6],
    )


async def _next_charge(conn: RuntimeConnection, booking_id: UUID) -> int:
    row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.rental_damage_charges "
            "where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    return int(row[0]) if row else 1


async def _next_refund(conn: RuntimeConnection, booking_id: UUID) -> int:
    row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.rental_refunds where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    return int(row[0]) if row else 1


async def record_damage_charge(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: DamageChargeInput,
) -> ChargesView:
    """A damage charge on new return marks with its own receivable draft (decision 1)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.damage_charge", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_charges(conn, booking_id)
    settled = await _settled(conn, booking_id)
    if len(set(body.marks)) != len(body.marks):
        raise RentalChargeStateError("A mark is cited twice")
    eligible = {
        row[0]
        for row in await (
            await conn.execute(
                "select m.position from gba.rental_inspections i "
                "join gba.rental_inspection_marks m on m.tenant_id = i.tenant_id "
                "and m.inspection_id = i.id where i.booking_id = %s and i.kind = 'return' "
                "and m.new and not exists (select 1 from gba.rental_damage_charge_marks c "
                "where c.tenant_id = i.tenant_id and c.booking_id = i.booking_id "
                "and c.position = m.position)",
                (booking_id,),
            )
        ).fetchall()
    }
    if not set(body.marks) <= eligible:
        raise RentalChargeStateError("Each basis mark is new on the return and charged once")
    number = await _next_charge(conn, booking_id)
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
            counterparty_id=settled.customer,
            counterparty_revision=settled.revision,
            currency=settled.currency,
            invoice_date=body.invoice_date,
            due_date=body.due_date,
            control_account_id=body.receivable_account_id,
            title=body.title,
            number=body.number,
            lines=(
                InvoiceLineInput(
                    line_id=uuid7(),
                    counter_account_id=body.revenue_account_id,
                    description=f"Damage charge {number}: {body.reason}",
                    amount=from_minor(body.amount, settled.places),
                ),
            ),
        ),
    )
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_damage_charges (tenant_id, booking_id, number, "
                "amount_minor, reason, book_id, invoice_document_id, charged_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    booking_id,
                    number,
                    body.amount,
                    body.reason,
                    body.book_id,
                    document,
                    user_id,
                ),
            )
            for position in body.marks:
                await conn.execute(
                    "insert into gba.rental_damage_charge_marks (tenant_id, booking_id, number, "
                    "position) values (%s, %s, %s, %s)",
                    (business, booking_id, number, position),
                )
            await conn.execute("set constraints gba.rental_damage_charges_basis immediate")
    except UniqueViolation as exc:
        raise RentalChargeStateError("A charge or a mark is already recorded") from exc
    except CheckViolation as exc:
        if (exc.diag.constraint_name or "").startswith("rental_damage_charge"):
            raise RentalChargeStateError("The charge does not follow the booking") from exc
        raise
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_charges(conn, booking_id)


async def _credit_lines(
    conn: RuntimeConnection, settled: _Settled, booking_id: UUID, invoice: UUID, amount: int
) -> tuple[UUID, UUID, tuple[CreditLineInput, ...]]:
    """The book, the issued obligation and the credit lines that reduce the invoice in order."""
    if invoice == settled.invoice:
        book: UUID = settled.book
    else:
        found = await (
            await conn.execute(
                "select book_id from gba.rental_damage_charges "
                "where booking_id = %s and invoice_document_id = %s",
                (booking_id, invoice),
            )
        ).fetchone()
        if found is None:
            raise RentalChargeStateError("The invoice is not the booking's settlement or charge")
        book = found[0]
    obligation = await (
        await conn.execute(
            "select o.id, o.source_revision from gba.financial_obligations o where o.book_id = %s "
            "and o.source_kind = 'invoice' and o.source_id = %s",
            (book, invoice),
        )
    ).fetchone()
    if obligation is None:
        raise RentalChargeStateError("The invoice is not issued yet")
    lines = await (
        await conn.execute(
            "select l.line_id, l.counter_account_id, l.amount_minor - coalesce(("
            "select sum(x.amount_minor) from gba.financial_document_lines x "
            "join gba.rental_refunds r on r.tenant_id = x.tenant_id and r.book_id = x.book_id "
            "and r.credit_document_id = x.document_id where x.credited_line_id = l.line_id), 0) "
            "from gba.financial_document_lines l where l.book_id = %s and l.document_id = %s "
            "and l.revision = %s order by l.line_no",
            (book, invoice, obligation[1]),
        )
    ).fetchall()
    left = amount
    credited: list[CreditLineInput] = []
    for line_id, account, open_minor in lines:
        take = min(left, int(open_minor))
        if take > 0:
            credited.append(
                CreditLineInput(
                    line_id=uuid7(),
                    credited_line_id=line_id,
                    counter_account_id=account,
                    description="Rental refund",
                    amount=from_minor(take, settled.places),
                )
            )
            left -= take
    if left > 0:
        raise RentalRefundExceedsError("The refund exceeds what the invoice still carries")
    return book, obligation[0], tuple(credited)


async def record_refund(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RefundInput,
) -> ChargesView:
    """A credit-note or an external refund within the ceiling (decision 2)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.refund", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_charges(conn, booking_id)
    settled = await _settled(conn, booking_id)
    totals = await (
        await conn.execute(
            "select coalesce((select sum(amount_minor) from gba.rental_damage_charges "
            "where booking_id = %s), 0), coalesce((select sum(amount_minor) "
            "from gba.rental_refunds where booking_id = %s), 0)",
            (booking_id, booking_id),
        )
    ).fetchone()
    charged, refunded = (int(totals[0]), int(totals[1])) if totals else (0, 0)
    if refunded + body.amount > settled.total + charged:
        raise RentalRefundExceedsError("Refunds exceed the settlement total plus the damage")
    number = await _next_refund(conn, booking_id)
    book: UUID | None = None
    document: UUID | None = None
    if body.method == "credit":
        if body.invoice_document_id is None or body.credit_date is None or body.number is None:
            raise RentalChargeStateError("A credit refund names its invoice, date and number")
        book, obligation, lines = await _credit_lines(
            conn, settled, booking_id, body.invoice_document_id, body.amount
        )
        document = uuid7()
        await credit_notes.save_draft(
            conn,
            business_id=business,
            book_id=book,
            document_id=document,
            user_id=user_id,
            actor=actor,
            key=key,
            body=CreditDraftInput(
                expected_revision=0,
                credited_obligation_id=obligation,
                counterparty_revision=settled.revision,
                credit_date=body.credit_date,
                title=f"Rental refund {number}",
                number=body.number,
                lines=lines,
            ),
        )
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_refunds (tenant_id, booking_id, number, amount_minor, "
                "reason, method, reference, refunded_at, book_id, credit_document_id, "
                "recorded_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    booking_id,
                    number,
                    body.amount,
                    body.reason,
                    body.method,
                    body.reference,
                    body.refunded_at,
                    book,
                    document,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise RentalChargeStateError("The refund is already recorded") from exc
    except CheckViolation as exc:
        name = exc.diag.constraint_name or ""
        if name == "rental_refunds_ceiling_check":
            raise RentalRefundExceedsError("Refunds exceed the ceiling") from exc
        if name.startswith("rental_refunds_"):
            raise RentalChargeStateError("The refund does not follow the booking") from exc
        raise
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_charges(conn, booking_id)
