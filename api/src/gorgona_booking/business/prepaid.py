"""L6: prepaid packages and gift certificates (package L, BEAUTY-01).

Design docs/plan/PACKAGE_L6_DESIGN_2026-10-22.md. A balance is sold by a FIN-03 invoice line on a
prepayment liability and is usable once its sale invoice is fully paid. A redemption is a FIN-03
credit note of the visit invoice, issued at once, whose lines name the prepayment account: the
liability becomes revenue exactly when the service is delivered.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import credit_notes, financial_documents, ledger, settlements
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditIssueInput,
    CreditLineInput,
    CreditNoteView,
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.visit_billing import load_visit_invoice, priced_lines
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

_AMOUNT = r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,3})?$"
REASON = "Prepaid redemption"


class PrepaidAccountError(DomainError):
    code = "PREPAYMENT_ACCOUNT_NOT_LIABILITY"


class PrepaidAmountError(DomainError):
    code = "PREPAID_AMOUNT_INVALID"


class PrepaidNotPaidError(ConflictError):
    code = "PREPAID_NOT_PAID"


class PrepaidExhaustedError(ConflictError):
    code = "PREPAID_EXHAUSTED"


class PrepaidAlreadyUsedError(ConflictError):
    code = "PREPAID_ALREADY_USED"


class PrepaidOtherCustomerError(ConflictError):
    code = "PREPAID_OTHER_CUSTOMER"


class PrepaidCurrencyError(ConflictError):
    code = "PREPAID_CURRENCY_MISMATCH"


class PrepaidCurrencyMismatchError(DomainError):
    code = "PREPAID_CURRENCY_MISMATCH"


class PrepaidUnitExceedsLineError(ConflictError):
    code = "PREPAID_UNIT_EXCEEDS_LINE"


class PrepaidNoMatchingServiceError(ConflictError):
    code = "PREPAID_NO_MATCHING_SERVICE"


class VisitNotInvoicedError(ConflictError):
    code = "VISIT_NOT_INVOICED"


class VisitNothingUnpaidError(ConflictError):
    code = "VISIT_NOTHING_UNPAID"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SaleInput(_Strict):
    kind: Literal["package", "certificate"]
    counterparty_id: UUID
    variant_id: UUID | None = None
    units: int | None = Field(default=None, ge=1, le=1000)
    price: str = Field(pattern=_AMOUNT)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    book_id: UUID
    control_account_id: UUID
    prepayment_account_id: UUID
    invoice_date: date
    due_date: date | None = None
    number: str = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def shape(self) -> Self:
        package = self.kind == "package"
        if package != (self.variant_id is not None and self.units is not None):
            raise ValueError("A package names a service and its units; a certificate neither")
        return self


class RedeemInput(_Strict):
    prepaid_id: UUID
    credit_date: date
    number: str = Field(min_length=1, max_length=64)


class PrepaidView(BaseModel):
    prepaid_id: UUID
    kind: str
    counterparty_id: UUID
    variant_id: UUID | None
    units: int | None
    remaining_units: int | None
    value: str
    remaining_value: str
    currency: str
    # Usable once the sale invoice is issued and fully paid (decision 34).
    usable: bool
    sale: InvoiceDocumentView


class RedemptionView(BaseModel):
    booking_id: UUID
    prepaid_id: UUID
    units: int
    amount: str
    credit: CreditNoteView
    prepaid: PrepaidView


def _money(minor: int, units: int) -> str:
    whole, fraction = divmod(minor, 10**units)
    return str(whole) if units == 0 else f"{whole}.{fraction:0{units}d}"


def _minor(text: str, units: int) -> int:
    whole, _, fraction = text.partition(".")
    if len(fraction) > units:
        raise PrepaidAmountError(f"At most {units} decimal places are accepted here")
    scale: int = 10**units
    return int(whole) * scale + int(fraction.ljust(units, "0") or "0")


async def _units(conn: RuntimeConnection, currency: str) -> int:
    row = await (
        await conn.execute("select minor_units from gba.currencies where code = %s", (currency,))
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    return int(row[0])


async def _party_revision(conn: RuntimeConnection, party: UUID) -> int:
    row = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions where counterparty_id = %s",
            (party,),
        )
    ).fetchone()
    if row is None or row[0] is None:
        raise InvalidReferenceError("Unknown counterparty", field="counterparty_id")
    return int(row[0])


_BALANCE = (
    "select id, kind, counterparty_id, variant_id, units, price_minor, currency, book_id, "
    "sale_document_id, prepayment_account_id, used_units, used_minor from gba.prepaid_balances "
    "where id = %s"
)


async def _row(conn: RuntimeConnection, prepaid_id: UUID, *, lock: bool = False) -> Any:
    query = _BALANCE + (" for update" if lock else "")
    return await (await conn.execute(query, (prepaid_id,))).fetchone()


async def load_prepaid(
    conn: RuntimeConnection, tenant_id: UUID, prepaid_id: UUID
) -> PrepaidView | None:
    row = await _row(conn, prepaid_id)
    if row is None:
        return None
    units = await _units(conn, row[6])
    sale = await financial_documents.load_invoice(conn, tenant_id, row[7], row[8])
    if sale is None:
        raise NotFoundError("Sale invoice not found", document_id=str(row[8]))
    usable = False
    if sale.obligation_id is not None:
        owed = await settlements.load_obligation(conn, tenant_id, row[7], sale.obligation_id)
        usable = owed is not None and all(
            Decimal(value) == 0 for value in (owed.available, owed.reserved, owed.credited)
        )
    return PrepaidView(
        prepaid_id=row[0],
        kind=row[1],
        counterparty_id=row[2],
        variant_id=row[3],
        units=row[4],
        remaining_units=None if row[4] is None else int(row[4]) - int(row[10]),
        value=_money(int(row[5]), units),
        remaining_value=_money(int(row[5]) - int(row[11]), units),
        currency=row[6],
        usable=usable,
        sale=sale,
    )


class PrepaidList(BaseModel):
    items: list[PrepaidView]
    next_cursor: UUID | None


async def list_prepaid(
    conn: RuntimeConnection,
    tenant_id: UUID,
    *,
    counterparty_id: UUID | None,
    after: UUID | None,
    limit: int,
) -> PrepaidList:
    """L7 decision 46: balances in creation order (time-ordered ids), one page after a cursor."""
    rows = await (
        await conn.execute(
            "select id from gba.prepaid_balances "
            "where (%(party)s::uuid is null or counterparty_id = %(party)s::uuid) "
            "and (%(after)s::uuid is null or id > %(after)s::uuid) "
            "order by id limit %(limit)s",
            {"party": counterparty_id, "after": after, "limit": limit + 1},
        )
    ).fetchall()
    items: list[PrepaidView] = []
    for (prepaid_id,) in rows[:limit]:
        view = await load_prepaid(conn, tenant_id, prepaid_id)
        if view is None:
            raise NotFoundError("Prepaid balance not found", prepaid_id=str(prepaid_id))
        items.append(view)
    more = len(rows) > limit
    return PrepaidList(items=items, next_cursor=items[-1].prepaid_id if more else None)


def _fingerprint(subject: str, body: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            {"subject": subject, "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


async def sell(
    conn: RuntimeConnection,
    tenant_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: SaleInput,
) -> PrepaidView:
    """Save the sale invoice draft (one line on the prepayment liability) and the balance."""
    scope = IdempotencyScope(tenant_id, actor, "prepaid.sell", key)
    fingerprint = _fingerprint("sale", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_prepaid(conn, tenant_id, UUID(str(stored.body["prepaid_id"])))
        if view is None:
            raise NotFoundError("Prepaid balance not found")
        return view
    account = await ledger.load_account(conn, tenant_id, body.book_id, body.prepayment_account_id)
    if account is None or account.type != "liability":
        raise PrepaidAccountError("A prepaid balance is held on a liability account")
    units = await _units(conn, body.currency)
    price = _minor(body.price, units)
    if price <= 0 or (body.units is not None and price < body.units):
        raise PrepaidAmountError("Every unit needs a value of at least one minor unit")
    description = "Gift certificate"
    if body.variant_id is not None:
        variant = await (
            await conn.execute(
                "select name, currency from gba.service_variants where id = %s",
                (body.variant_id,),
            )
        ).fetchone()
        if variant is None:
            raise InvalidReferenceError("Unknown service", field="variant_id")
        if variant[1] != body.currency:
            # L8 decision 67: a package in another currency could never be redeemed.
            raise PrepaidCurrencyMismatchError(
                "A package is sold in its service's currency", currency=variant[1]
            )
        description = f"Prepaid package: {body.units} x {variant[0]}"
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
            counterparty_revision=await _party_revision(conn, body.counterparty_id),
            currency=body.currency,
            invoice_date=body.invoice_date,
            due_date=body.due_date,
            control_account_id=body.control_account_id,
            title=description,
            number=body.number,
            lines=(
                InvoiceLineInput(
                    line_id=uuid7(),
                    counter_account_id=body.prepayment_account_id,
                    description=description,
                    amount=_money(price, units),
                ),
            ),
        ),
    )
    prepaid = uuid7()
    await conn.execute(
        "insert into gba.prepaid_balances (tenant_id, id, kind, counterparty_id, variant_id, "
        "units, price_minor, currency, book_id, sale_document_id, prepayment_account_id, "
        "created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            tenant_id,
            prepaid,
            body.kind,
            body.counterparty_id,
            body.variant_id,
            body.units,
            price,
            body.currency,
            body.book_id,
            document,
            body.prepayment_account_id,
            user_id,
        ),
    )
    view = await load_prepaid(conn, tenant_id, prepaid)
    assert view is not None  # noqa: S101 - inserted above
    await idempotency.complete(conn, scope, 200, {"prepaid_id": str(prepaid)})
    return view


async def load_redemption(
    conn: RuntimeConnection, tenant_id: UUID, prepaid_id: UUID, booking_id: UUID
) -> RedemptionView | None:
    row = await (
        await conn.execute(
            "select units, amount_minor, book_id, credit_document_id from gba.prepaid_redemptions "
            "where prepaid_id = %s and booking_id = %s",
            (prepaid_id, booking_id),
        )
    ).fetchone()
    if row is None:
        return None
    prepaid = await load_prepaid(conn, tenant_id, prepaid_id)
    credit = await credit_notes.load_credit(conn, tenant_id, row[2], row[3])
    if prepaid is None or credit is None:
        raise NotFoundError("Redemption not found")
    units = await _units(conn, prepaid.currency)
    return RedemptionView(
        booking_id=booking_id,
        prepaid_id=prepaid_id,
        units=int(row[0]),
        amount=_money(int(row[1]), units),
        credit=credit,
        prepaid=prepaid,
    )


def _credits(
    row: Any, invoice: InvoiceDocumentView, quote: dict[str, Any], status: str, available: int
) -> tuple[int, list[tuple[UUID, int]]]:
    """Units used and (invoice line, amount) pairs a redemption credits (decisions 35-36)."""
    units = invoice.minor_units
    remaining = int(row[5]) - int(row[11])
    if row[1] == "package":
        left = int(row[4]) - int(row[10])
        if left <= 0 or remaining <= 0:
            raise PrepaidExhaustedError("This package has no unit left")
        # L8 decision 57: the service's invoice line is its priced quote line (the invoice holds
        # the priced quote lines in order, then the fees) and must still say what the quote says.
        priced = priced_lines(quote, units) if status == "CONFIRMED" else []
        index = next(
            (
                i
                for i, (line, _) in enumerate(priced)
                if line.get("kind") == "variant" and str(line.get("id")) == str(row[3])
            ),
            None,
        )
        if index is None or index >= len(invoice.lines):
            raise PrepaidNoMatchingServiceError("The visit has no service of this package")
        quoted, price = priced[index]
        line = invoice.lines[index]
        if line.description != str(quoted["name"]) or _minor(line.amount, units) != price:
            raise PrepaidNoMatchingServiceError("The visit has no service of this package")
        # A unit is worth price / units; the last one takes the remainder.
        worth = remaining if left == 1 else int(row[5]) // int(row[4])
        if worth > price or worth > available:
            # L8 decision 58: a unit is spent only for its whole worth; the liability ends at zero.
            raise PrepaidUnitExceedsLineError(
                "This unit is worth more than the visit's open line; settle it by hand",
                worth=worth,
            )
        return 1, [(line.line_id, worth)]
    if remaining <= 0:
        raise PrepaidExhaustedError("This certificate has no value left")
    pairs: list[tuple[UUID, int]] = []
    budget = min(remaining, available)
    for line in invoice.lines:
        if budget <= 0:
            break
        amount = min(_minor(line.amount, units), budget)
        if amount > 0:
            pairs.append((line.line_id, amount))
            budget -= amount
    return 0, pairs


async def redeem(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RedeemInput,
) -> RedemptionView:
    """Credit the visit invoice from a prepaid balance, once per visit (decisions 36-37)."""
    scope = IdempotencyScope(tenant_id, actor, "prepaid.redeem", key)
    fingerprint = _fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_redemption(conn, tenant_id, body.prepaid_id, booking_id)
        if view is None:
            raise NotFoundError("Redemption not found")
        return view
    row = await _row(conn, body.prepaid_id, lock=True)
    if row is None:
        raise NotFoundError("Prepaid balance not found", prepaid_id=str(body.prepaid_id))
    if await load_redemption(conn, tenant_id, body.prepaid_id, booking_id) is not None:
        raise PrepaidAlreadyUsedError("This balance was already used for this visit")
    balance = await load_prepaid(conn, tenant_id, body.prepaid_id)
    if balance is None or not balance.usable:
        raise PrepaidNotPaidError("The prepaid balance is not paid yet")
    quote = await (
        await conn.execute(
            "select quote, status from gba.bookings where id = %s for update", (booking_id,)
        )
    ).fetchone()
    if quote is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    billed = await load_visit_invoice(conn, tenant_id, booking_id)
    if billed is None or billed.obligation is None:
        raise VisitNotInvoicedError("The visit invoice is not issued yet")
    invoice, owed = billed.invoice, billed.obligation
    if invoice.counterparty_id != row[2]:
        raise PrepaidOtherCustomerError("The balance belongs to another customer")
    if invoice.currency != row[6]:
        raise PrepaidCurrencyError("The balance and the visit use different currencies")
    available = _minor(owed.available, invoice.minor_units)
    if available <= 0:
        raise VisitNothingUnpaidError("Nothing of the visit invoice is unpaid")
    used_units, pairs = _credits(row, invoice, quote[0], quote[1], available)
    if not pairs:
        raise VisitNothingUnpaidError("Nothing of the visit invoice is left to credit")
    document = uuid7()
    await credit_notes.save_draft(
        conn,
        business_id=tenant_id,
        book_id=billed.book_id,
        document_id=document,
        user_id=user_id,
        actor=actor,
        key=key,
        body=CreditDraftInput(
            expected_revision=0,
            credited_obligation_id=owed.obligation_id,
            counterparty_revision=await _party_revision(conn, row[2]),
            credit_date=body.credit_date,
            title=REASON,
            number=body.number,
            lines=tuple(
                CreditLineInput(
                    line_id=uuid7(),
                    credited_line_id=line,
                    counter_account_id=row[9],
                    description=REASON,
                    amount=_money(amount, invoice.minor_units),
                    reason=REASON,
                )
                for line, amount in pairs
            ),
        ),
    )
    await credit_notes.issue_credit(
        conn,
        business_id=tenant_id,
        book_id=billed.book_id,
        document_id=document,
        user_id=user_id,
        actor=actor,
        key=key,
        body=CreditIssueInput(
            expected_revision=1,
            entry_date=body.credit_date,
            attestation="confirmed_account_treatment",
        ),
    )
    total = sum(amount for _, amount in pairs)
    await conn.execute(
        "insert into gba.prepaid_redemptions (tenant_id, prepaid_id, booking_id, units, "
        "amount_minor, book_id, credit_document_id, created_by) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            tenant_id,
            body.prepaid_id,
            booking_id,
            used_units,
            total,
            billed.book_id,
            document,
            user_id,
        ),
    )
    await conn.execute(
        "update gba.prepaid_balances set used_units = used_units + %s, "
        "used_minor = used_minor + %s where id = %s",
        (used_units, total, body.prepaid_id),
    )
    view = await load_redemption(conn, tenant_id, body.prepaid_id, booking_id)
    assert view is not None  # noqa: S101 - recorded above
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return view
