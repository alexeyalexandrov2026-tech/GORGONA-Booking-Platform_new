"""O5 (package O, BUILD-01): pay applications with retainage.

docs/plan/PACKAGE_O5_DESIGN_2026-11-01.md. The retainage rate is versioned on the contract. A pay
application closes a billing period: it bills the completed value of every budget line as of its
period end minus what earlier applications billed, holds retainage (rounded down) from that amount,
and drafts two FIN-03 documents that are never mixed: a receivable invoice for the amount due and a
receivable accrual without a due date for the retained amount. The database rechecks the period, the
arithmetic, the rate, the contract sum and both documents under the project lock.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, UniqueViolation
from pydantic import AfterValidator, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import financial_documents
from gorgona_booking.business.construction import (
    ConstructionRevisionConflictError,
    Strict,
    has_contract,
    lock_project,
    request_fingerprint,
    require_construction,
)
from gorgona_booking.business.construction_budget import BudgetKey, budget_lines
from gorgona_booking.business.construction_contracts import ConstructionNoContractError
from gorgona_booking.business.construction_progress import (
    ConstructionFutureDateError,
    ConstructionPeriodBilledError,
    SiteDate,
    check_contract,
    completed_by_line,
    completed_value,
    one_line,
    site_today,
)
from gorgona_booking.business.financial_contracts import (
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.ledger_contracts import from_minor
from gorgona_booking.business.module_gate import CONSTRUCTION_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

DocumentNumber = Annotated[str, Field(min_length=1, max_length=62), AfterValidator(one_line)]
DocumentTitle = Annotated[str, Field(min_length=1, max_length=200), AfterValidator(one_line)]
MAX_RATE_BP = 5000
BASIS = 10_000


class ConstructionNothingToBillError(ConflictError):
    code = "CONSTRUCTION_NOTHING_TO_BILL"


class RetainageInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=100_000)
    rate_bp: int = Field(ge=0, le=MAX_RATE_BP)


class RetainageView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    revision: int
    rate_bp: int
    recorded_at: datetime | None


class PayApplicationInput(Strict):
    schema_version: Literal[1]
    period_end: SiteDate
    book_id: UUID
    receivable_account_id: UUID
    revenue_account_id: UUID
    retainage_account_id: UUID
    invoice_date: date
    due_date: date | None = None
    number: DocumentNumber
    title: DocumentTitle = "Pay application"

    @model_validator(mode="after")
    def _separate_accounts(self) -> Self:
        if self.retainage_account_id == self.receivable_account_id:
            raise ValueError("retainage is held on an account other than the receivable one")
        if self.due_date is not None and self.due_date < self.invoice_date:
            raise ValueError("an invoice is not due before its date")
        return self


class PayLineView(BaseModel):
    change_order: int | None
    position: int
    phase: str
    description: str
    unit: str
    quantity: Decimal
    contract_minor: int
    completed: Decimal
    value_to_date_minor: int
    previous_minor: int
    this_period_minor: int


class PayApplicationView(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    number: int
    period_end: date
    currency: str
    rate_revision: int | None
    rate_bp: int
    previous_billed_minor: int
    billed_to_date_minor: int
    this_period_minor: int
    retained_minor: int
    due_minor: int
    lines: list[PayLineView]
    invoice: InvoiceDocumentView
    retainage: InvoiceDocumentView | None
    recorded_at: datetime


class PayApplicationSummary(BaseModel):
    number: int
    period_end: date
    billed_to_date_minor: int
    this_period_minor: int
    retained_minor: int
    due_minor: int
    invoice_state: str
    retainage_state: str | None


class PayApplicationList(BaseModel):
    schema_version: Literal[1] = 1
    project_id: UUID
    currency: str
    contract_minor: int
    billed_to_date_minor: int
    retained_minor: int
    due_minor: int
    remaining_minor: int
    items: list[PayApplicationSummary]


_HEAD = (
    "select number, period_end, rate_revision, rate_bp, previous_billed_minor, "
    "billed_to_date_minor, this_period_minor, retained_minor, due_minor, book_id, "
    "invoice_document_id, retainage_document_id, created_at "
    "from gba.construction_pay_applications where project_id = %s "
)


# Retainage rate ---------------------------------------------------------------------


async def _rate(
    conn: RuntimeConnection, project_id: UUID
) -> tuple[int | None, int, datetime | None]:
    row = await (
        await conn.execute(
            "select revision, rate_bp, created_at from gba.construction_retainage_rates "
            "where project_id = %s order by revision desc limit 1",
            (project_id,),
        )
    ).fetchone()
    return (int(row[0]), int(row[1]), row[2]) if row else (None, 0, None)


async def load_retainage(conn: RuntimeConnection, project_id: UUID) -> RetainageView:
    """The current retainage rate (decision 2); 0 before the first version."""
    await check_contract(conn, project_id)
    revision, rate, recorded = await _rate(conn, project_id)
    return RetainageView(
        project_id=project_id, revision=revision or 0, rate_bp=rate, recorded_at=recorded
    )


async def put_retainage(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RetainageInput,
) -> RetainageView:
    """The next version of the retainage rate, on the version the client read (decision 2)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.retainage", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_retainage(conn, project_id)
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A retainage rate needs a contract")
    current, _, _ = await _rate(conn, project_id)
    if body.expected_revision != (current or 0):
        raise ConstructionRevisionConflictError(
            "The retainage rate changed since it was read", revision=current or 0
        )
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_retainage_rates (tenant_id, project_id, revision, "
                "rate_bp, created_by) values (%s, %s, %s, %s, %s)",
                (business, project_id, (current or 0) + 1, body.rate_bp, user_id),
            )
    except (UniqueViolation, CheckViolation) as exc:
        raise ConstructionRevisionConflictError("The retainage rate changed meanwhile") from exc
    view = await load_retainage(conn, project_id)
    await idempotency.complete(conn, scope, 200, {"revision": view.revision})
    return view


# Pay applications -------------------------------------------------------------------


async def _lines(
    conn: RuntimeConnection, project_id: UUID, number: int
) -> dict[BudgetKey, tuple[Decimal, int]]:
    rows = await (
        await conn.execute(
            "select change_order, budget_position, quantity_to_date, value_to_date_minor "
            "from gba.construction_pay_application_lines where project_id = %s and number = %s",
            (project_id, number),
        )
    ).fetchall()
    return {(row[0], int(row[1])): (Decimal(row[2]), int(row[3])) for row in rows}


async def _document(
    conn: RuntimeConnection, business: UUID, book: UUID, document: UUID, kind: str
) -> InvoiceDocumentView:
    view = await financial_documents.load_invoice(
        conn, business, book, document, kind="invoice" if kind == "invoice" else "manual_accrual"
    )
    if view is None:
        raise NotFoundError("Financial document not found", document_id=str(document))
    return view


async def load_application(
    conn: RuntimeConnection, business: UUID, project_id: UUID, number: int
) -> PayApplicationView | None:
    """One application with its lines and both FIN-03 documents (decision 10), or None."""
    await check_contract(conn, project_id)
    row = await (await conn.execute(_HEAD + "and number = %s", (project_id, number))).fetchone()
    if row is None:
        return None
    currency = await (
        await conn.execute(
            "select currency from gba.construction_projects where id = %s", (project_id,)
        )
    ).fetchone()
    assert currency is not None  # noqa: S101 - checked above
    stored = await _lines(conn, project_id, number)
    earlier = await _lines(conn, project_id, number - 1) if number > 1 else {}
    budget = {
        (item["change_order"], item["position"]): item
        for item in await budget_lines(conn, project_id)
    }
    lines = []
    for key, (completed, value) in sorted(stored.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1])):
        item = budget[key]
        previous = earlier.get(key, (Decimal(0), 0))[1]
        lines.append(
            PayLineView(
                change_order=key[0],
                position=key[1],
                phase=item["phase"],
                description=item["description"],
                unit=item["unit"],
                quantity=item["quantity"],
                contract_minor=int(item["contract_minor"]),
                completed=completed,
                value_to_date_minor=value,
                previous_minor=previous,
                this_period_minor=value - previous,
            )
        )
    return PayApplicationView(
        project_id=project_id,
        number=row[0],
        period_end=row[1],
        currency=str(currency[0]),
        rate_revision=row[2],
        rate_bp=row[3],
        previous_billed_minor=row[4],
        billed_to_date_minor=row[5],
        this_period_minor=row[6],
        retained_minor=row[7],
        due_minor=row[8],
        lines=lines,
        invoice=await _document(conn, business, row[9], row[10], "invoice"),
        retainage=(
            await _document(conn, business, row[9], row[11], "accrual")
            if row[11] is not None
            else None
        ),
        recorded_at=row[12],
    )


async def list_applications(
    conn: RuntimeConnection, business: UUID, project_id: UUID
) -> PayApplicationList:
    """Every application with its FIN-03 states, and the totals against the contract (10)."""
    await check_contract(conn, project_id)
    currency = await (
        await conn.execute(
            "select currency from gba.construction_projects where id = %s", (project_id,)
        )
    ).fetchone()
    assert currency is not None  # noqa: S101 - checked above
    rows = await (await conn.execute(_HEAD + "order by number", (project_id,))).fetchall()
    items = []
    for row in rows:
        invoice = await _document(conn, business, row[9], row[10], "invoice")
        held = (
            await _document(conn, business, row[9], row[11], "accrual")
            if row[11] is not None
            else None
        )
        items.append(
            PayApplicationSummary(
                number=row[0],
                period_end=row[1],
                billed_to_date_minor=row[5],
                this_period_minor=row[6],
                retained_minor=row[7],
                due_minor=row[8],
                invoice_state=invoice.state,
                retainage_state=held.state if held is not None else None,
            )
        )
    contract = sum(int(item["contract_minor"]) for item in await budget_lines(conn, project_id))
    billed = int(rows[-1][5]) if rows else 0
    return PayApplicationList(
        project_id=project_id,
        currency=str(currency[0]),
        contract_minor=contract,
        billed_to_date_minor=billed,
        retained_minor=sum(int(row[7]) for row in rows),
        due_minor=sum(int(row[8]) for row in rows),
        remaining_minor=contract - billed,
        items=items,
    )


def _refused(exc: CheckViolation) -> Exception | None:
    """The database's answer to an application it refused, as the error the client sees."""
    name = str(exc.diag.constraint_name)
    if name == "construction_pay_applications_period_check":
        return ConstructionPeriodBilledError("This period is already billed")
    if name == "construction_pay_applications_date_check":
        return ConstructionFutureDateError("The period ends after today on the site")
    if name in (
        "construction_pay_applications_sequence_check",
        "construction_pay_applications_previous_check",
        "construction_pay_applications_rate_check",
        "construction_pay_applications_lines_check",
        "construction_pay_application_lines_quantity_check",
        "construction_pay_application_lines_record_check",
    ):
        return ConstructionRevisionConflictError("The project changed meanwhile; try again")
    return None


async def _party_revision(conn: RuntimeConnection, counterparty: UUID) -> int:
    row = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions where counterparty_id = %s",
            (counterparty,),
        )
    ).fetchone()
    if row is None or row[0] is None:
        raise InvalidReferenceError("Unknown customer", field="customer_id")
    return int(row[0])


async def record_application(
    conn: RuntimeConnection,
    business: UUID,
    project_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: PayApplicationInput,
) -> PayApplicationView:
    """The next pay application and its two FIN-03 drafts (decisions 3-6)."""
    await require_construction(conn, business)
    scope = IdempotencyScope(business, actor, "construction.pay_application", key)
    fingerprint = request_fingerprint(str(project_id), body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        saved = stored.body.get("number")
        view = (
            await load_application(conn, business, project_id, saved)
            if isinstance(saved, int)
            else None
        )
        if view is None:
            raise NotFoundError("Pay application not found", project_id=str(project_id))
        return view
    await lock_project(conn, project_id)
    if not await has_contract(conn, project_id):
        raise ConstructionNoContractError("A pay application needs a contract")
    if body.period_end > await site_today(conn, project_id):
        raise ConstructionFutureDateError("The period ends after today on the site")
    latest = await (
        await conn.execute(
            "select number, period_end, billed_to_date_minor "
            "from gba.construction_pay_applications where project_id = %s "
            "order by number desc limit 1",
            (project_id,),
        )
    ).fetchone()
    if latest is not None and body.period_end <= latest[1]:
        raise ConstructionPeriodBilledError("This period is already billed", billed=str(latest[1]))
    number = int(latest[0]) + 1 if latest else 1
    previous = int(latest[2]) if latest else 0
    completed = await completed_by_line(conn, project_id, body.period_end)
    rows: list[tuple[BudgetKey, Decimal, int]] = []
    for item in await budget_lines(conn, project_id):
        line_key: BudgetKey = (item["change_order"], item["position"])
        quantity = completed.get(line_key, Decimal(0))
        value = completed_value(quantity, item) if quantity > 0 else 0
        rows.append((line_key, quantity, value))
    billed = sum(value for _, _, value in rows)
    this_period = billed - previous
    if this_period <= 0:
        raise ConstructionNothingToBillError(
            "Nothing more is completed to bill", billed_to_date=previous
        )
    revision, rate, _ = await _rate(conn, project_id)
    retained = this_period * rate // BASIS
    due = this_period - retained
    project = await (
        await conn.execute(
            "select p.customer_id, p.currency, c.minor_units from gba.construction_projects p "
            "join gba.currencies c on c.code = p.currency where p.id = %s",
            (project_id,),
        )
    ).fetchone()
    assert project is not None  # noqa: S101 - locked above
    customer, currency, units = project[0], str(project[1]), int(project[2])
    customer_revision = await _party_revision(conn, customer)
    period = body.period_end.isoformat()
    invoice = uuid7()
    await financial_documents.save_draft(
        conn,
        business_id=business,
        book_id=body.book_id,
        document_id=invoice,
        user_id=user_id,
        actor=actor,
        key=key,
        body=InvoiceDraftInput(
            expected_revision=0,
            direction="receivable",
            counterparty_id=customer,
            counterparty_revision=customer_revision,
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
                    description=f"Pay application {number}: work to {period}, less retainage",
                    amount=from_minor(due, units),
                ),
            ),
        ),
    )
    held: UUID | None = None
    if retained > 0:
        held = uuid7()
        await financial_documents.save_draft(
            conn,
            business_id=business,
            book_id=body.book_id,
            document_id=held,
            user_id=user_id,
            actor=actor,
            key=key,
            body=InvoiceDraftInput(
                expected_revision=0,
                direction="receivable",
                counterparty_id=customer,
                counterparty_revision=customer_revision,
                currency=currency,
                invoice_date=body.invoice_date,
                due_date=None,
                control_account_id=body.retainage_account_id,
                title=f"Retainage held, pay application {number}",
                number=f"{body.number}-R",
                lines=(
                    InvoiceLineInput(
                        line_id=uuid7(),
                        counter_account_id=body.revenue_account_id,
                        description=f"Retainage held on pay application {number}",
                        amount=from_minor(retained, units),
                    ),
                ),
            ),
            kind="manual_accrual",
        )
    try:
        async with module_writes(CONSTRUCTION_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.construction_pay_applications (tenant_id, project_id, number, "
                "period_end, previous_billed_minor, billed_to_date_minor, this_period_minor, "
                "rate_revision, rate_bp, retained_minor, due_minor, book_id, "
                "invoice_document_id, retainage_document_id, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    project_id,
                    number,
                    body.period_end,
                    previous,
                    billed,
                    this_period,
                    revision,
                    rate,
                    retained,
                    due,
                    body.book_id,
                    invoice,
                    held,
                    user_id,
                ),
            )
            for (change_order, position), quantity, value in rows:
                await conn.execute(
                    "insert into gba.construction_pay_application_lines (tenant_id, project_id, "
                    "number, change_order, budget_position, quantity_to_date, "
                    "value_to_date_minor) values (%s, %s, %s, %s, %s, %s, %s)",
                    (business, project_id, number, change_order, position, quantity, value),
                )
            await conn.execute("set constraints gba.construction_pay_applications_lines immediate")
    except UniqueViolation as exc:
        raise ConstructionPeriodBilledError("This period is already billed") from exc
    except CheckViolation as exc:
        mapped = _refused(exc)
        if mapped is None:
            raise
        raise mapped from exc
    view = await load_application(conn, business, project_id, number)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"number": number})
    return view
