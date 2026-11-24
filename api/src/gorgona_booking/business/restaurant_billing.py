"""REST-01 Slice 4 (ADR-0037): split billing, FIN-03 invoices and coordinated refunds."""

from datetime import date
from typing import Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, credit_notes, financial_documents, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditLineInput,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.ledger_contracts import from_minor
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.restaurant_floor import (
    RESTAURANT_MODULE,
    RestaurantNotReadyError,
    RestaurantStateError,
    _clean_single_line,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

SplitMode = Literal["by_items", "by_amounts"]
RefundMethod = Literal["credit", "external"]

_MAX_MONEY = 999_999_999_999


class RestaurantRefundExceedsError(ConflictError):
    code = "RESTAURANT_REFUND_EXCEEDS_BILLED"


class SplitShareInput(Strict):
    label: str
    counterparty_id: UUID | None = None
    amount_minor: StrictInt | None = Field(default=None, ge=1, le=_MAX_MONEY)
    line_ids: list[UUID] = Field(default_factory=list, max_length=500)

    @field_validator("label")
    @classmethod
    def valid_label(cls, value: str) -> str:
        return _clean_single_line(value, 120)


class SplitCheckInput(Versioned):
    split_mode: SplitMode
    shares: list[SplitShareInput] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_shares(self) -> Self:
        if self.split_mode == "by_amounts":
            for sh in self.shares:
                if sh.amount_minor is None:
                    raise ValueError("by_amounts split requires amount_minor on every share")
                if sh.line_ids:
                    raise ValueError("by_amounts split cannot assign line_ids")
        else:
            seen: set[UUID] = set()
            for sh in self.shares:
                if sh.amount_minor is not None:
                    raise ValueError("by_items split computes share amounts from assigned lines")
                if not sh.line_ids:
                    raise ValueError("by_items split requires at least one line_id per share")
                for lid in sh.line_ids:
                    if lid in seen:
                        raise ValueError("A check line can only be assigned to one share")
                    seen.add(lid)
        return self


class BillShareInput(Versioned):
    book_id: UUID
    counterparty_id: UUID
    receivable_account_id: UUID
    revenue_account_id: UUID
    invoice_date: date
    due_date: date
    title: str
    number: str

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 120)

    @field_validator("number")
    @classmethod
    def valid_number(cls, value: str) -> str:
        return _clean_single_line(value, 64)

    @model_validator(mode="after")
    def valid_dates(self) -> Self:
        if self.due_date < self.invoice_date:
            raise ValueError("due_date cannot precede invoice_date")
        return self


class RefundCheckInput(Versioned):
    share_no: StrictInt = Field(ge=1, le=20)
    amount_minor: StrictInt = Field(ge=1, le=_MAX_MONEY)
    method: RefundMethod
    reason: str
    returned_line_id: UUID | None = None
    credit_date: date | None = None
    number: str | None = None
    reference: str | None = None
    refunded_at: AwareDatetime | None = None

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        return _clean_single_line(value, 500)

    @field_validator("number")
    @classmethod
    def valid_number(cls, value: str | None) -> str | None:
        return None if value is None else _clean_single_line(value, 64)

    @field_validator("reference")
    @classmethod
    def valid_reference(cls, value: str | None) -> str | None:
        return None if value is None else _clean_single_line(value, 120)

    @model_validator(mode="after")
    def valid_method_fields(self) -> Self:
        if self.method == "credit":
            if self.credit_date is None or self.number is None:
                raise ValueError("credit refund requires credit_date and number")
            if self.reference is not None or self.refunded_at is not None:
                raise ValueError("credit refund must not set external reference or refunded_at")
        else:
            if self.reference is None or self.refunded_at is None:
                raise ValueError("external refund requires reference and refunded_at")
            if self.credit_date is not None or self.number is not None:
                raise ValueError("external refund must not set credit_date or number")
        return self


class SplitShareView(Strict):
    share_no: int
    label: str
    counterparty_id: UUID | None
    amount_minor: int
    line_ids: list[UUID] = Field(default_factory=list)
    billed: bool = False
    book_id: UUID | None = None
    invoice_document_id: UUID | None = None
    billed_counterparty_id: UUID | None = None
    billed_at: AwareDatetime | None = None


class CheckSplitView(Strict):
    schema_version: Literal[1] = 1
    check_id: UUID
    location_id: UUID
    split_mode: SplitMode
    share_count: int
    total_minor: int
    recorded_by: UUID
    recorded_at: AwareDatetime
    shares: list[SplitShareView]


class CheckBillView(Strict):
    schema_version: Literal[1] = 1
    check_id: UUID
    share_no: int
    location_id: UUID
    counterparty_id: UUID
    amount_minor: int
    book_id: UUID
    invoice_document_id: UUID
    billed_by: UUID
    billed_at: AwareDatetime


class CheckRefundView(Strict):
    schema_version: Literal[1] = 1
    check_id: UUID
    number: int
    share_no: int
    location_id: UUID
    returned_line_id: UUID | None
    amount_minor: int
    method: RefundMethod
    reason: str
    reference: str | None
    refunded_at: AwareDatetime | None
    book_id: UUID | None
    credit_document_id: UUID | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class ReconciledShareView(Strict):
    share_no: int
    label: str
    amount_minor: int
    line_ids: list[UUID]
    book_id: UUID | None
    invoice_document_id: UUID | None
    invoice_state: Literal["unbilled", "draft", "issued"]
    principal_minor: int
    paid_minor: int
    credited_minor: int
    open_minor: int


class ReconciledRefundView(Strict):
    number: int
    share_no: int
    returned_line_id: UUID | None
    method: RefundMethod
    amount_minor: int
    state: Literal["recorded", "draft", "issued", "voided"]
    credit_document_id: UUID | None
    refund_obligation_minor: int | None
    refund_paid_minor: int | None


class CheckReconciliationTotals(Strict):
    check_subtotal_minor: int
    split_total_minor: int
    billed_total_minor: int
    invoiced_issued_minor: int
    paid_minor: int
    credited_minor: int
    open_minor: int
    refunded_external_minor: int
    refund_owed_minor: int
    balanced: bool


class CheckReconciliationView(Strict):
    schema_version: Literal[1] = 1
    check_id: UUID
    location_id: UUID
    currency: str
    status: str
    consumption_posted: bool
    stock_document_id: UUID | None
    split_mode: SplitMode | None
    shares: list[ReconciledShareView]
    refunds: list[ReconciledRefundView]
    totals: CheckReconciliationTotals


class _SplitReceipt(Strict):
    check_id: UUID


class _BillReceipt(Strict):
    check_id: UUID
    share_no: int


class _RefundReceipt(Strict):
    check_id: UUID
    number: int


def _check_ready() -> None:
    if not modules.MODULES_BY_ID[RESTAURANT_MODULE].enableable:
        raise RestaurantNotReadyError("The restaurant module is not enabled for use")


async def get_check_split(
    conn: RuntimeConnection, business: UUID, check_id: UUID
) -> CheckSplitView:
    await require_module(conn, business, RESTAURANT_MODULE)
    head = await (
        await conn.execute(
            "select check_id, location_id, split_mode, share_count, total_minor, "
            "recorded_by, recorded_at from gba.restaurant_check_splits "
            "where tenant_id = %s and check_id = %s",
            (business, check_id),
        )
    ).fetchone()
    if head is None:
        raise NotFoundError("Restaurant check split not found")
    share_rows = await (
        await conn.execute(
            "select s.share_no, s.label, s.counterparty_id, s.amount_minor, "
            "b.book_id, b.invoice_document_id, b.counterparty_id, b.billed_at "
            "from gba.restaurant_check_split_shares s "
            "left join gba.restaurant_check_bills b "
            "  on b.tenant_id = s.tenant_id and b.check_id = s.check_id "
            " and b.share_no = s.share_no "
            "where s.tenant_id = %s and s.check_id = %s order by s.share_no",
            (business, check_id),
        )
    ).fetchall()
    line_rows = await (
        await conn.execute(
            "select share_no, check_line_id from gba.restaurant_check_split_share_lines "
            "where tenant_id = %s and check_id = %s order by share_no, check_line_id",
            (business, check_id),
        )
    ).fetchall()
    by_share: dict[int, list[UUID]] = {}
    for sno, lid in line_rows:
        by_share.setdefault(int(sno), []).append(lid)
    return CheckSplitView(
        check_id=head[0],
        location_id=head[1],
        split_mode=head[2],
        share_count=int(head[3]),
        total_minor=int(head[4]),
        recorded_by=head[5],
        recorded_at=head[6],
        shares=[
            SplitShareView(
                share_no=int(sno),
                label=label,
                counterparty_id=cp,
                amount_minor=int(amt),
                line_ids=by_share.get(int(sno), []),
                billed=inv is not None,
                book_id=book,
                invoice_document_id=inv,
                billed_counterparty_id=bcp,
                billed_at=bat,
            )
            for sno, label, cp, amt, book, inv, bcp, bat in share_rows
        ],
    )


async def split_check(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: SplitCheckInput,
) -> CheckSplitView:
    scope = IdempotencyScope(business, actor, "restaurant.check.split", key)
    fingerprint = commands.fingerprint(
        {"check_id": str(check_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _SplitReceipt)
    if receipt is not None:
        return await get_check_split(conn, business, receipt.check_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    chk = await (
        await conn.execute(
            "select location_id, status, subtotal_minor from gba.restaurant_checks "
            "where tenant_id = %s and id = %s for update",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    check_loc, check_status, subtotal = chk[0], str(chk[1]), int(chk[2])
    if location_scope is not None and check_loc != location_scope:
        raise PermissionDeniedError("You can only split checks in your assigned branch")
    if check_status == "voided":
        raise RestaurantStateError("Cannot split a voided check")
    if subtotal <= 0:
        raise RestaurantStateError("Cannot split a check with zero subtotal")

    existing = await (
        await conn.execute(
            "select 1 from gba.restaurant_check_splits where tenant_id = %s and check_id = %s",
            (business, check_id),
        )
    ).fetchone()
    if existing is not None:
        raise RestaurantStateError("Check has already been split")

    draft_cnt = await (
        await conn.execute(
            "select count(*) from gba.restaurant_check_lines "
            "where tenant_id = %s and check_id = %s and status = 'draft'",
            (business, check_id),
        )
    ).fetchone()
    if draft_cnt is not None and int(draft_cnt[0]) > 0:
        raise RestaurantStateError("Fire or void all draft lines before splitting the check")

    computed_shares: list[tuple[int, str, UUID | None, int, list[UUID]]] = []
    if body.split_mode == "by_amounts":
        total = 0
        for idx, sh in enumerate(body.shares, start=1):
            if sh.amount_minor is None:
                raise RestaurantStateError("by_amounts split requires amount_minor")
            total += sh.amount_minor
            computed_shares.append((idx, sh.label, sh.counterparty_id, sh.amount_minor, []))
        if total != subtotal:
            raise RestaurantStateError(
                f"Split share amounts ({total}) must equal check subtotal ({subtotal})"
            )
    else:
        active_rows = await (
            await conn.execute(
                "select id, line_total_minor from gba.restaurant_check_lines "
                "where tenant_id = %s and check_id = %s and status in ('fired', 'served')",
                (business, check_id),
            )
        ).fetchall()
        active_totals: dict[UUID, int] = {row[0]: int(row[1]) for row in active_rows}
        assigned: set[UUID] = set()
        for idx, sh in enumerate(body.shares, start=1):
            share_total = 0
            for lid in sh.line_ids:
                if lid not in active_totals:
                    raise InvalidReferenceError(
                        "Assigned line is not an active line on this check", field="shares"
                    )
                assigned.add(lid)
                share_total += active_totals[lid]
            if share_total <= 0:
                raise RestaurantStateError("Each split share must have a positive total")
            computed_shares.append(
                (idx, sh.label, sh.counterparty_id, share_total, list(sh.line_ids))
            )
        if assigned != set(active_totals):
            raise RestaurantStateError("by_items split must assign every active line exactly once")

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "insert into gba.restaurant_check_splits "
                "(tenant_id, check_id, location_id, split_mode, share_count, total_minor, "
                "recorded_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    check_id,
                    check_loc,
                    body.split_mode,
                    len(computed_shares),
                    subtotal,
                    user_id,
                ),
            )
            for sno, label, cp, amt, lids in computed_shares:
                await conn.execute(
                    "insert into gba.restaurant_check_split_shares "
                    "(tenant_id, check_id, share_no, location_id, label, counterparty_id, "
                    "amount_minor) values (%s, %s, %s, %s, %s, %s, %s)",
                    (business, check_id, sno, check_loc, label, cp, amt),
                )
                for lid in lids:
                    await conn.execute(
                        "insert into gba.restaurant_check_split_share_lines "
                        "(tenant_id, check_id, share_no, check_line_id, location_id) "
                        "values (%s, %s, %s, %s, %s)",
                        (business, check_id, sno, lid, check_loc),
                    )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced counterparty not found", field="shares"
            ) from exc
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_split",
        "restaurant_check",
        str(check_id),
        {"split_mode": body.split_mode, "share_count": len(computed_shares), "total": subtotal},
    )
    await commands.complete(conn, scope, _SplitReceipt(check_id=check_id))
    return await get_check_split(conn, business, check_id)


async def _load_bill(
    conn: RuntimeConnection, business: UUID, check_id: UUID, share_no: int
) -> CheckBillView:
    row = await (
        await conn.execute(
            "select check_id, share_no, location_id, counterparty_id, amount_minor, "
            "book_id, invoice_document_id, billed_by, billed_at "
            "from gba.restaurant_check_bills "
            "where tenant_id = %s and check_id = %s and share_no = %s",
            (business, check_id, share_no),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Restaurant check bill not found")
    return CheckBillView(
        check_id=row[0],
        share_no=int(row[1]),
        location_id=row[2],
        counterparty_id=row[3],
        amount_minor=int(row[4]),
        book_id=row[5],
        invoice_document_id=row[6],
        billed_by=row[7],
        billed_at=row[8],
    )


async def bill_check_share(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    share_no: int,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: BillShareInput,
) -> CheckBillView:
    if location_scope is not None:
        raise PermissionDeniedError(
            "Issuing FIN-03 check invoices requires company-wide owner or manager access"
        )
    scope = IdempotencyScope(business, actor, "restaurant.check.bill_share", key)
    fingerprint = commands.fingerprint(
        {
            "check_id": str(check_id),
            "share_no": share_no,
            "body": body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _BillReceipt)
    if receipt is not None:
        return await _load_bill(conn, business, receipt.check_id, receipt.share_no)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    row = await (
        await conn.execute(
            "select s.location_id, s.label, s.amount_minor, c.currency "
            "from gba.restaurant_check_split_shares s "
            "join gba.restaurant_checks c "
            "  on c.tenant_id = s.tenant_id and c.id = s.check_id "
            "where s.tenant_id = %s and s.check_id = %s and s.share_no = %s "
            "for update of c",
            (business, check_id, share_no),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Restaurant check split share not found")
    check_loc, share_label, share_amount, currency = row[0], str(row[1]), int(row[2]), str(row[3])

    existing = await (
        await conn.execute(
            "select 1 from gba.restaurant_check_bills "
            "where tenant_id = %s and check_id = %s and share_no = %s",
            (business, check_id, share_no),
        )
    ).fetchone()
    if existing is not None:
        raise RestaurantStateError("This split share has already been billed")

    cp_rev_row = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions "
            "where tenant_id = %s and counterparty_id = %s",
            (business, body.counterparty_id),
        )
    ).fetchone()
    if cp_rev_row is None or cp_rev_row[0] is None:
        raise InvalidReferenceError("Counterparty not found", field="counterparty_id")
    cp_rev = int(cp_rev_row[0])

    minor_row = await (
        await conn.execute("select minor_units from gba.currencies where code = %s", (currency,))
    ).fetchone()
    if minor_row is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    places = int(minor_row[0])

    invoice_doc_id = uuid7()
    await financial_documents.save_draft(
        conn,
        business_id=business,
        book_id=body.book_id,
        document_id=invoice_doc_id,
        user_id=user_id,
        actor=actor,
        key=key,
        body=InvoiceDraftInput(
            expected_revision=0,
            direction="receivable",
            counterparty_id=body.counterparty_id,
            counterparty_revision=cp_rev,
            currency=currency,
            invoice_date=body.invoice_date,
            due_date=body.due_date,
            control_account_id=body.receivable_account_id,
            title=body.title,
            number=body.number,
            lines=(
                InvoiceLineInput(
                    line_id=uuid7(),
                    counter_account_id=body.revenue_account_id,
                    description=f"Restaurant check share {share_no}: {share_label}",
                    amount=from_minor(share_amount, places),
                ),
            ),
        ),
    )

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "insert into gba.restaurant_check_bills "
                "(tenant_id, check_id, share_no, location_id, counterparty_id, amount_minor, "
                "book_id, invoice_document_id, billed_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    check_id,
                    share_no,
                    check_loc,
                    body.counterparty_id,
                    share_amount,
                    body.book_id,
                    invoice_doc_id,
                    user_id,
                ),
            )
        except errors.CheckViolation as exc:
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_share_billed",
        "restaurant_check",
        str(check_id),
        {
            "share_no": share_no,
            "amount_minor": share_amount,
            "invoice_document_id": str(invoice_doc_id),
        },
    )
    await commands.complete(conn, scope, _BillReceipt(check_id=check_id, share_no=share_no))
    return await _load_bill(conn, business, check_id, share_no)


async def _load_refund(
    conn: RuntimeConnection, business: UUID, check_id: UUID, number: int
) -> CheckRefundView:
    row = await (
        await conn.execute(
            "select check_id, number, share_no, location_id, returned_line_id, amount_minor, "
            "method, reason, reference, refunded_at, book_id, credit_document_id, "
            "recorded_by, recorded_at from gba.restaurant_check_refunds "
            "where tenant_id = %s and check_id = %s and number = %s",
            (business, check_id, number),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Restaurant check refund not found")
    return CheckRefundView(
        check_id=row[0],
        number=int(row[1]),
        share_no=int(row[2]),
        location_id=row[3],
        returned_line_id=row[4],
        amount_minor=int(row[5]),
        method=row[6],
        reason=row[7],
        reference=row[8],
        refunded_at=row[9],
        book_id=row[10],
        credit_document_id=row[11],
        recorded_by=row[12],
        recorded_at=row[13],
    )


async def _credit_lines_for_bill(
    conn: RuntimeConnection,
    business: UUID,
    book_id: UUID,
    invoice_doc_id: UUID,
    amount_minor: int,
    places: int,
    reason: str,
) -> tuple[UUID, tuple[CreditLineInput, ...]]:
    obligation = await (
        await conn.execute(
            "select o.id, o.source_revision from gba.financial_obligations o "
            "where o.tenant_id = %s and o.book_id = %s "
            "and o.source_kind = 'invoice' and o.source_id = %s",
            (business, book_id, invoice_doc_id),
        )
    ).fetchone()
    if obligation is None:
        raise RestaurantStateError("The share invoice must be issued in FIN-03 before crediting")
    obl_id, src_rev = obligation[0], int(obligation[1])
    inv_lines = await (
        await conn.execute(
            "select l.line_id, l.counter_account_id, l.amount_minor - coalesce(("
            "select sum(x.amount_minor) from gba.financial_document_lines x "
            "join gba.restaurant_check_refunds r "
            "  on r.tenant_id = x.tenant_id and r.book_id = x.book_id "
            " and r.credit_document_id = x.document_id "
            "where x.credited_line_id = l.line_id "
            "  and not gba.credit_voided(r.tenant_id, r.book_id, r.credit_document_id) "
            "  and x.revision = (select max(v.revision) from gba.financial_document_versions v "
            "      where v.tenant_id = x.tenant_id and v.book_id = x.book_id "
            "        and v.document_id = x.document_id)), 0) "
            "from gba.financial_document_lines l "
            "where l.tenant_id = %s and l.book_id = %s and l.document_id = %s "
            "and l.revision = %s order by l.line_no",
            (business, book_id, invoice_doc_id, src_rev),
        )
    ).fetchall()
    left = amount_minor
    credited: list[CreditLineInput] = []
    for lid, acct, open_minor in inv_lines:
        take = min(left, int(open_minor))
        if take > 0:
            credited.append(
                CreditLineInput(
                    line_id=uuid7(),
                    credited_line_id=lid,
                    counter_account_id=acct,
                    description=f"Restaurant refund: {reason[:80]}",
                    amount=from_minor(take, places),
                )
            )
            left -= take
    if left > 0:
        raise RestaurantRefundExceedsError("Refund exceeds remaining creditable invoice amount")
    return obl_id, tuple(credited)


async def record_check_refund(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: RefundCheckInput,
) -> CheckRefundView:
    if location_scope is not None:
        raise PermissionDeniedError(
            "Recording check refunds requires company-wide owner or manager access"
        )
    scope = IdempotencyScope(business, actor, "restaurant.check.refund", key)
    fingerprint = commands.fingerprint(
        {"check_id": str(check_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _RefundReceipt)
    if receipt is not None:
        return await _load_refund(conn, business, receipt.check_id, receipt.number)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    bill = await (
        await conn.execute(
            "select b.location_id, b.counterparty_id, b.amount_minor, b.book_id, "
            "b.invoice_document_id, c.currency "
            "from gba.restaurant_check_bills b "
            "join gba.restaurant_checks c "
            "  on c.tenant_id = b.tenant_id and c.id = b.check_id "
            "where b.tenant_id = %s and b.check_id = %s and b.share_no = %s "
            "for update of c",
            (business, check_id, body.share_no),
        )
    ).fetchone()
    if bill is None:
        raise NotFoundError("Billed share not found for this check")
    check_loc, cp_id, _bill_amt, bill_book, inv_doc_id, currency = bill

    max_num_row = await (
        await conn.execute(
            "select coalesce(max(number), 0) from gba.restaurant_check_refunds "
            "where tenant_id = %s and check_id = %s",
            (business, check_id),
        )
    ).fetchone()
    next_number = (int(max_num_row[0]) if max_num_row is not None else 0) + 1

    credit_book: UUID | None = None
    credit_doc_id: UUID | None = None
    if body.method == "credit":
        if body.credit_date is None or body.number is None:
            raise RestaurantStateError("credit refund requires credit_date and number")
        minor_row = await (
            await conn.execute(
                "select minor_units from gba.currencies where code = %s", (currency,)
            )
        ).fetchone()
        places = int(minor_row[0]) if minor_row is not None else 2
        cp_rev_row = await (
            await conn.execute(
                "select max(revision) from gba.counterparty_versions "
                "where tenant_id = %s and counterparty_id = %s",
                (business, cp_id),
            )
        ).fetchone()
        cp_rev = int(cp_rev_row[0]) if cp_rev_row is not None and cp_rev_row[0] is not None else 1
        obl_id, lines = await _credit_lines_for_bill(
            conn, business, bill_book, inv_doc_id, body.amount_minor, places, body.reason
        )
        credit_book = bill_book
        credit_doc_id = uuid7()
        await credit_notes.save_draft(
            conn,
            business_id=business,
            book_id=credit_book,
            document_id=credit_doc_id,
            user_id=user_id,
            actor=actor,
            key=key,
            body=CreditDraftInput(
                expected_revision=0,
                credited_obligation_id=obl_id,
                counterparty_revision=cp_rev,
                credit_date=body.credit_date,
                title=f"Restaurant refund #{next_number}",
                number=body.number,
                lines=lines,
            ),
        )

    async with module_writes(RESTAURANT_MODULE):
        try:
            await conn.execute(
                "insert into gba.restaurant_check_refunds "
                "(tenant_id, check_id, number, share_no, location_id, returned_line_id, "
                "amount_minor, method, reason, reference, refunded_at, book_id, "
                "credit_document_id, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    check_id,
                    next_number,
                    body.share_no,
                    check_loc,
                    body.returned_line_id,
                    body.amount_minor,
                    body.method,
                    body.reason,
                    body.reference,
                    body.refunded_at,
                    credit_book,
                    credit_doc_id,
                    user_id,
                ),
            )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced returned check line not found", field="returned_line_id"
            ) from exc
        except errors.CheckViolation as exc:
            if exc.diag.constraint_name == "restaurant_check_refunds_ceiling_check":
                raise RestaurantRefundExceedsError(
                    "Refunds for this share exceed the billed share amount"
                ) from exc
            raise RestaurantStateError(str(exc.diag.message_primary or exc)) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.check_refund_recorded",
        "restaurant_check",
        str(check_id),
        {
            "number": next_number,
            "share_no": body.share_no,
            "method": body.method,
            "amount_minor": body.amount_minor,
        },
    )
    await commands.complete(conn, scope, _RefundReceipt(check_id=check_id, number=next_number))
    return await _load_refund(conn, business, check_id, next_number)


async def _fin_balance(
    conn: RuntimeConnection, business: UUID, book: UUID, source_kind: str, source: UUID
) -> tuple[int, int, int, int] | None:
    row = await (
        await conn.execute(
            "select b.principal_minor, b.paid_minor, b.credited_minor, b.reserved_minor "
            "from gba.financial_obligations o, gba.obligation_balance(%s, o.book_id, o.id) b "
            "where o.tenant_id = %s and o.book_id = %s "
            "and o.source_kind = %s and o.source_id = %s",
            (business, business, book, source_kind, source),
        )
    ).fetchone()
    if row is None:
        return None
    return int(row[0]), int(row[1]), int(row[2]), int(row[3])


async def get_check_reconciliation(
    conn: RuntimeConnection,
    business: UUID,
    check_id: UUID,
    *,
    location_scope: UUID | None,
) -> CheckReconciliationView:
    if location_scope is not None:
        raise PermissionDeniedError(
            "Check financial reconciliation requires company-wide owner or manager access"
        )
    await require_module(conn, business, RESTAURANT_MODULE)
    chk = await (
        await conn.execute(
            "select c.location_id, c.currency, c.status, c.subtotal_minor, "
            "(cons.check_id is not null), cons.stock_document_id, sp.split_mode "
            "from gba.restaurant_checks c "
            "left join gba.restaurant_check_consumptions cons "
            "  on cons.tenant_id = c.tenant_id and cons.check_id = c.id "
            "left join gba.restaurant_check_splits sp "
            "  on sp.tenant_id = c.tenant_id and sp.check_id = c.id "
            "where c.tenant_id = %s and c.id = %s",
            (business, check_id),
        )
    ).fetchone()
    if chk is None:
        raise NotFoundError("Restaurant check not found")
    loc, currency, status, subtotal, cons_posted, stock_doc, split_mode = (
        chk[0],
        str(chk[1]),
        str(chk[2]),
        int(chk[3]),
        bool(chk[4]),
        chk[5],
        chk[6],
    )

    line_rows = await (
        await conn.execute(
            "select share_no, check_line_id from gba.restaurant_check_split_share_lines "
            "where tenant_id = %s and check_id = %s order by share_no, check_line_id",
            (business, check_id),
        )
    ).fetchall()
    lines_by_share: dict[int, list[UUID]] = {}
    for sno, lid in line_rows:
        lines_by_share.setdefault(int(sno), []).append(lid)

    share_rows = await (
        await conn.execute(
            "select s.share_no, s.label, s.amount_minor, b.book_id, b.invoice_document_id "
            "from gba.restaurant_check_split_shares s "
            "left join gba.restaurant_check_bills b "
            "  on b.tenant_id = s.tenant_id and b.check_id = s.check_id "
            " and b.share_no = s.share_no "
            "where s.tenant_id = %s and s.check_id = %s order by s.share_no",
            (business, check_id),
        )
    ).fetchall()

    reconciled_shares: list[ReconciledShareView] = []
    split_total = 0
    billed_total = 0
    invoiced_issued = 0
    paid_total = 0
    credited_total = 0
    open_total = 0

    for sno, label, amt, book_id, inv_id in share_rows:
        amt_i = int(amt)
        split_total += amt_i
        if inv_id is None:
            reconciled_shares.append(
                ReconciledShareView(
                    share_no=int(sno),
                    label=str(label),
                    amount_minor=amt_i,
                    line_ids=lines_by_share.get(int(sno), []),
                    book_id=None,
                    invoice_document_id=None,
                    invoice_state="unbilled",
                    principal_minor=0,
                    paid_minor=0,
                    credited_minor=0,
                    open_minor=0,
                )
            )
            continue
        billed_total += amt_i
        bal = await _fin_balance(conn, business, book_id, "invoice", inv_id)
        if bal is None:
            reconciled_shares.append(
                ReconciledShareView(
                    share_no=int(sno),
                    label=str(label),
                    amount_minor=amt_i,
                    line_ids=lines_by_share.get(int(sno), []),
                    book_id=book_id,
                    invoice_document_id=inv_id,
                    invoice_state="draft",
                    principal_minor=0,
                    paid_minor=0,
                    credited_minor=0,
                    open_minor=0,
                )
            )
        else:
            p, paid, cred, _res = bal
            open_m = max(0, p - paid - cred)
            invoiced_issued += p
            paid_total += paid
            credited_total += cred
            open_total += open_m
            reconciled_shares.append(
                ReconciledShareView(
                    share_no=int(sno),
                    label=str(label),
                    amount_minor=amt_i,
                    line_ids=lines_by_share.get(int(sno), []),
                    book_id=book_id,
                    invoice_document_id=inv_id,
                    invoice_state="issued",
                    principal_minor=p,
                    paid_minor=paid,
                    credited_minor=cred,
                    open_minor=open_m,
                )
            )

    refund_rows = await (
        await conn.execute(
            "select number, share_no, returned_line_id, method, amount_minor, "
            "book_id, credit_document_id from gba.restaurant_check_refunds "
            "where tenant_id = %s and check_id = %s order by number",
            (business, check_id),
        )
    ).fetchall()

    reconciled_refunds: list[ReconciledRefundView] = []
    ext_total = 0
    refund_owed = 0

    for num, sno, ret_lid, method, amt, book_id, cred_id in refund_rows:
        amt_i = int(amt)
        if method == "external":
            ext_total += amt_i
            reconciled_refunds.append(
                ReconciledRefundView(
                    number=int(num),
                    share_no=int(sno),
                    returned_line_id=ret_lid,
                    method="external",
                    amount_minor=amt_i,
                    state="recorded",
                    credit_document_id=None,
                    refund_obligation_minor=None,
                    refund_paid_minor=None,
                )
            )
            continue
        st_row = await (
            await conn.execute(
                "select state from gba.financial_document_versions "
                "where tenant_id = %s and book_id = %s and document_id = %s "
                "order by revision desc limit 1",
                (business, book_id, cred_id),
            )
        ).fetchone()
        credit_state: Literal["draft", "issued", "voided"] = "draft"
        if st_row is not None and st_row[0] in ("issued", "voided"):
            credit_state = st_row[0]
        if credit_state == "issued":
            rbal = await _fin_balance(conn, business, book_id, "credit_refund", cred_id)
            ro_minor = rbal[0] if rbal is not None else 0
            rp_minor = rbal[1] if rbal is not None else 0
            refund_owed += max(0, ro_minor - rp_minor)
            reconciled_refunds.append(
                ReconciledRefundView(
                    number=int(num),
                    share_no=int(sno),
                    returned_line_id=ret_lid,
                    method="credit",
                    amount_minor=amt_i,
                    state="issued",
                    credit_document_id=cred_id,
                    refund_obligation_minor=ro_minor,
                    refund_paid_minor=rp_minor,
                )
            )
        else:
            reconciled_refunds.append(
                ReconciledRefundView(
                    number=int(num),
                    share_no=int(sno),
                    returned_line_id=ret_lid,
                    method="credit",
                    amount_minor=amt_i,
                    state=credit_state,
                    credit_document_id=cred_id,
                    refund_obligation_minor=None,
                    refund_paid_minor=None,
                )
            )

    balanced = (
        (split_mode is None or split_total == subtotal)
        and (billed_total <= subtotal)
        and (credited_total + ext_total <= billed_total)
    )
    return CheckReconciliationView(
        check_id=check_id,
        location_id=loc,
        currency=currency,
        status=status,
        consumption_posted=cons_posted,
        stock_document_id=stock_doc,
        split_mode=split_mode,
        shares=reconciled_shares,
        refunds=reconciled_refunds,
        totals=CheckReconciliationTotals(
            check_subtotal_minor=subtotal,
            split_total_minor=split_total,
            billed_total_minor=billed_total,
            invoiced_issued_minor=invoiced_issued,
            paid_minor=paid_total,
            credited_minor=credited_total,
            open_minor=open_total,
            refunded_external_minor=ext_total,
            refund_owed_minor=refund_owed,
            balanced=balanced,
        ),
    )
