"""H1 immutable invoice drafts and atomic, explicitly attested accruals.

No cash fact, provider action, reserve or automatic revenue recognition occurs.
Commands, documents, obligations and G journal identity remain separate. The
caller owns the transaction; every completed effect is rechecked by SQL.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID, uuid7

from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    SerializationFailure,
    UniqueViolation,
)

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import commands, ledger, modules
from gorgona_booking.business.financial_contracts import (
    FinancialCommandKind,
    FinancialCommandReference,
    FinancialCommandStatus,
    FinancialReceipt,
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceIssueInput,
    InvoiceLineInput,
    InvoiceList,
    InvoiceSummary,
)
from gorgona_booking.business.financial_math import quantize_invoice
from gorgona_booking.business.ledger_contracts import InvoicePosting, LineInput, from_minor
from gorgona_booking.business.module_gate import FINANCE_MODULE, module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DatabaseUnavailableError,
    InvalidReferenceError,
    NotFoundError,
)

FEATURE = "finance_documents"
_OPERATIONS: dict[FinancialCommandKind, str] = {
    "invoice_draft": "business.finance.invoice_draft",
    "invoice_issue": "business.finance.invoice_issue",
}
_CONSTRAINTS = ", ".join(
    "gba." + name
    for name in (
        "financial_documents_consistent",
        "financial_document_versions_consistent",
        "financial_document_lines_consistent",
        "financial_obligations_consistent",
        "financial_operation_entries_consistent",
        "financial_command_receipts_consistent",
        "journal_entries_invoice_consistent",
        "journal_lines_invoice_consistent",
        "journal_entries_balanced",
        "journal_lines_balanced",
        "financial_versions_entry_fk",
        "financial_versions_obligation_fk",
    )
)


class FinancialWorkflowNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class FinancialDocumentStateError(ConflictError):
    code = "FINANCIAL_STATE_INVALID"


class FinancialCommandCancelledError(ConflictError):
    code = "FINANCIAL_COMMAND_CANCELLED"


async def _lock(conn: RuntimeConnection, business: UUID) -> None:
    try:
        await conn.execute("select gba.lock_ledger(%s)", (business,))
    except SerializationFailure as exc:
        raise DatabaseUnavailableError(
            "Financial writes require read committed transactions"
        ) from exc


async def _require_workflow(conn: RuntimeConnection, business: UUID) -> None:
    current = modules.MODULES_BY_ID[FEATURE]
    if not current.enableable or not at_least(current.readiness, modules.MINIMUM_READINESS):
        raise FinancialWorkflowNotReadyError(
            "This financial workflow is not ready", module_id=FEATURE
        )
    for dependency in current.depends_on:
        await require_module(conn, business, dependency)
    await require_module(conn, business, FEATURE)


@asynccontextmanager
async def _writes(conn: RuntimeConnection) -> AsyncIterator[None]:
    try:
        async with module_writes(FINANCE_MODULE, FEATURE), conn.transaction():
            yield
            await _flush(conn)
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Every invoice reference must belong to this company and book"
        ) from exc
    except (CheckViolation, UniqueViolation) as exc:
        raise FinancialDocumentStateError(
            "Financial document or source changed; reload before continuing"
        ) from exc
    except SerializationFailure as exc:
        raise DatabaseUnavailableError("Financial transaction settings are not ready") from exc


async def _flush(conn: RuntimeConnection) -> None:
    await conn.execute("set constraints " + _CONSTRAINTS + " immediate")
    await conn.execute("set constraints " + _CONSTRAINTS + " deferred")


async def _claim(
    conn: RuntimeConnection,
    *,
    business: UUID,
    actor: str,
    operation: FinancialCommandKind,
    key: str,
    request_hash: str,
) -> FinancialReceipt | None:
    await _lock(conn, business)
    cancelled = await (
        await conn.execute(
            "select 1 from gba.financial_command_cancellations "
            "where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
            (business, actor, operation, key),
        )
    ).fetchone()
    if cancelled:
        raise FinancialCommandCancelledError("This unresolved financial command was cancelled")
    row = await (
        await conn.execute(
            "select request_hash,book_id,document_id,revision from gba.financial_command_receipts "
            "where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
            (business, actor, operation, key),
        )
    ).fetchone()
    if row is not None and row[0] != request_hash:
        raise IdempotencyKeyReusedError("This key was already used with another financial command")
    scope = IdempotencyScope(business, actor, _OPERATIONS[operation], key)
    cached = await commands.claim(conn, scope, request_hash, FinancialReceipt)
    if row is None:
        if cached is not None:
            raise DatabaseUnavailableError("The financial command outcome is incomplete")
        return None
    receipt = FinancialReceipt(book_id=row[1], document_id=row[2], revision=row[3])
    if cached is not None and cached != receipt:
        raise DatabaseUnavailableError("The financial command references disagree")
    if cached is None:
        await commands.complete(conn, scope, receipt)
    return receipt


async def _complete(
    conn: RuntimeConnection,
    *,
    business: UUID,
    actor: str,
    user: UUID,
    operation: FinancialCommandKind,
    key: str,
    request_hash: str,
    receipt: FinancialReceipt,
) -> None:
    await _flush(conn)
    await conn.execute(
        "insert into gba.financial_command_receipts "
        "(tenant_id,actor_key,operation,idempotency_key,request_hash,book_id,"
        "document_id,revision,created_by) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business,
            actor,
            operation,
            key,
            request_hash,
            receipt.book_id,
            receipt.document_id,
            receipt.revision,
            user,
        ),
    )
    await _flush(conn)
    await commands.audit(
        conn,
        business,
        actor,
        "finance." + operation,
        "financial_document",
        str(receipt.document_id),
        {"book_id": str(receipt.book_id), "revision": receipt.revision},
    )
    await commands.complete(
        conn, IdempotencyScope(business, actor, _OPERATIONS[operation], key), receipt
    )


async def load_invoice(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    *,
    revision: int | None = None,
) -> InvoiceDocumentView | None:
    row = await (
        await conn.execute(
            "select v.revision,v.state,v.direction,v.counterparty_id,"
            "v.counterparty_revision,v.currency,"
            "c.minor_units,v.invoice_date,v.due_date,v.control_account_id,v.title,v.number,"
            "v.principal_minor,v.entry_id,v.obligation_id,v.issued_on,v.attestation,v.created_at "
            "from gba.financial_document_versions v join gba.currencies c on c.code=v.currency "
            "where v.tenant_id=%s and v.book_id=%s and v.document_id=%s "
            "and (%s::integer is null or v.revision=%s) order by v.revision desc limit 1",
            (business_id, book_id, document_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    lines = await (
        await conn.execute(
            "select line_id,counter_account_id,description,amount_minor "
            "from gba.financial_document_lines "
            "where tenant_id=%s and book_id=%s and document_id=%s and revision=%s order by line_no",
            (business_id, book_id, document_id, row[0]),
        )
    ).fetchall()
    return InvoiceDocumentView(
        business_id=business_id,
        book_id=book_id,
        document_id=document_id,
        revision=row[0],
        state=row[1],
        direction=row[2],
        counterparty_id=row[3],
        counterparty_revision=row[4],
        currency=row[5],
        minor_units=row[6],
        invoice_date=row[7],
        due_date=row[8],
        control_account_id=row[9],
        title=row[10],
        number=row[11],
        total=from_minor(row[12], row[6]),
        entry_id=row[13],
        obligation_id=row[14],
        issued_on=row[15],
        attestation=row[16],
        created_at=row[17],
        lines=tuple(
            InvoiceLineInput(
                line_id=line[0],
                counter_account_id=line[1],
                description=line[2],
                amount=from_minor(line[3], row[6]),
            )
            for line in lines
        ),
    )


async def _invoice(
    conn: RuntimeConnection,
    business: UUID,
    receipt: FinancialReceipt,
) -> InvoiceDocumentView:
    result = await load_invoice(
        conn, business, receipt.book_id, receipt.document_id, revision=receipt.revision
    )
    if result is None:
        raise DatabaseUnavailableError("The stored invoice version is missing")
    return result


async def list_invoices(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> InvoiceList:
    await ledger.require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            "select d.id,v.revision,v.state,v.direction,v.counterparty_id,v.currency,c.minor_units,"
            "v.invoice_date,v.due_date,v.title,v.number,v.principal_minor,"
            "v.entry_id,v.obligation_id,v.created_at "
            "from gba.financial_documents d join lateral ("
            "select * from gba.financial_document_versions x where x.tenant_id=d.tenant_id "
            "and x.book_id=d.book_id and x.document_id=d.id order by x.revision desc limit 1"
            ") v on true join gba.currencies c on c.code=v.currency "
            "where d.tenant_id=%s and d.book_id=%s and (%s::uuid is null or d.id>%s) "
            "order by d.id limit %s",
            (business_id, book_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        InvoiceSummary(
            document_id=r[0],
            revision=r[1],
            state=r[2],
            direction=r[3],
            counterparty_id=r[4],
            currency=r[5],
            invoice_date=r[7],
            due_date=r[8],
            title=r[9],
            number=r[10],
            total=from_minor(r[11], r[6]),
            entry_id=r[12],
            obligation_id=r[13],
            created_at=r[14],
        )
        for r in rows[:limit]
    )
    return InvoiceList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].document_id if len(rows) > limit else None,
    )


async def _insert_version(
    conn: RuntimeConnection,
    *,
    business: UUID,
    book: UUID,
    document: UUID,
    user: UUID,
    body: InvoiceDraftInput,
    revision: int,
    state: Literal["draft", "issued"],
    principal: int,
    amounts: tuple[int, ...],
    entry: UUID | None = None,
    obligation: UUID | None = None,
    issue: InvoiceIssueInput | None = None,
) -> None:
    await conn.execute(
        "insert into gba.financial_document_versions "
        "(tenant_id,book_id,document_id,revision,state,direction,counterparty_id,counterparty_revision,"
        "currency,invoice_date,due_date,control_account_id,title,number,principal_minor,line_count,"
        "entry_id,obligation_id,issued_on,attestation,created_by) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business,
            book,
            document,
            revision,
            state,
            body.direction,
            body.counterparty_id,
            body.counterparty_revision,
            body.currency,
            body.invoice_date,
            body.due_date,
            body.control_account_id,
            body.title,
            body.number,
            principal,
            len(body.lines),
            entry,
            obligation,
            issue.entry_date if issue else None,
            issue.attestation if issue else None,
            user,
        ),
    )
    await conn.execute(
        "insert into gba.financial_document_lines "
        "(tenant_id,book_id,document_id,revision,line_no,line_id,counter_account_id,"
        "description,amount_minor) "
        "select %s,%s,%s,%s,l.n::smallint,l.id,l.account,l.description,l.amount "
        "from unnest(%s::uuid[],%s::uuid[],%s::text[],%s::bigint[]) "
        "with ordinality as l(id,account,description,amount,n)",
        (
            business,
            book,
            document,
            revision,
            [line.line_id for line in body.lines],
            [line.counter_account_id for line in body.lines],
            [line.description for line in body.lines],
            list(amounts),
        ),
    )


async def save_draft(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: InvoiceDraftInput,
) -> InvoiceDocumentView:
    digest = commands.fingerprint(
        {"book_id": str(book_id), "document_id": str(document_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(
        conn,
        business=business_id,
        actor=actor,
        operation="invoice_draft",
        key=key,
        request_hash=digest,
    )
    if prior is not None:
        return await _invoice(conn, business_id, prior)
    await _require_workflow(conn, business_id)
    await ledger.require_book(conn, business_id, book_id)
    current = await load_invoice(conn, business_id, book_id, document_id)
    actual = current.revision if current else 0
    if body.expected_revision != actual:
        raise ConflictError("This invoice changed; reload before saving", revision=actual)
    if current is not None and current.state != "draft":
        raise FinancialDocumentStateError("An issued invoice stays unchanged")
    currency = await (
        await conn.execute("select minor_units from gba.currencies where code=%s", (body.currency,))
    ).fetchone()
    if currency is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    quantized = quantize_invoice(body, currency[0])
    receipt = FinancialReceipt(book_id=book_id, document_id=document_id, revision=actual + 1)
    async with _writes(conn):
        if current is None:
            await conn.execute(
                "insert into gba.financial_documents (tenant_id,book_id,id,created_by) "
                "values (%s,%s,%s,%s)",
                (business_id, book_id, document_id, user_id),
            )
        await _insert_version(
            conn,
            business=business_id,
            book=book_id,
            document=document_id,
            user=user_id,
            body=body,
            revision=receipt.revision,
            state="draft",
            principal=quantized.principal_minor,
            amounts=quantized.amounts_minor,
        )
        await _complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation="invoice_draft",
            key=key,
            request_hash=digest,
            receipt=receipt,
        )
    return await _invoice(conn, business_id, receipt)


async def issue_invoice(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: InvoiceIssueInput,
) -> InvoiceDocumentView:
    digest = commands.fingerprint(
        {"book_id": str(book_id), "document_id": str(document_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(
        conn,
        business=business_id,
        actor=actor,
        operation="invoice_issue",
        key=key,
        request_hash=digest,
    )
    if prior is not None:
        return await _invoice(conn, business_id, prior)
    await _require_workflow(conn, business_id)
    current = await load_invoice(conn, business_id, book_id, document_id)
    if current is None:
        raise NotFoundError("Invoice not found")
    if current.state != "draft":
        raise FinancialDocumentStateError("This invoice was already issued")
    if current.revision != body.expected_revision:
        raise ConflictError("This invoice changed; reload before issue", revision=current.revision)
    draft = InvoiceDraftInput(
        expected_revision=current.revision,
        direction=current.direction,
        counterparty_id=current.counterparty_id,
        counterparty_revision=current.counterparty_revision,
        currency=current.currency,
        invoice_date=current.invoice_date,
        due_date=current.due_date,
        control_account_id=current.control_account_id,
        title=current.title,
        number=current.number,
        lines=current.lines,
    )
    quantized = quantize_invoice(draft, current.minor_units)
    entry, obligation = uuid7(), uuid7()
    receipt = FinancialReceipt(
        book_id=book_id, document_id=document_id, revision=current.revision + 1
    )
    control_side: Literal["debit", "credit"] = (
        "debit" if current.direction == "receivable" else "credit"
    )
    counter_side: Literal["debit", "credit"] = "credit" if control_side == "debit" else "debit"
    async with _writes(conn):
        await _insert_version(
            conn,
            business=business_id,
            book=book_id,
            document=document_id,
            user=user_id,
            body=draft,
            revision=receipt.revision,
            state="issued",
            principal=quantized.principal_minor,
            amounts=quantized.amounts_minor,
            entry=entry,
            obligation=obligation,
            issue=body,
        )
        await conn.execute(
            "insert into gba.financial_obligations "
            "(tenant_id,book_id,id,source_kind,source_id,source_revision,component,"
            "counterparty_id,"
            "counterparty_revision,direction,currency,control_account_id,"
            "principal_minor,created_by) "
            "values (%s,%s,%s,'invoice',%s,%s,'principal',%s,%s,%s,%s,%s,%s,%s)",
            (
                business_id,
                book_id,
                obligation,
                document_id,
                receipt.revision,
                current.counterparty_id,
                current.counterparty_revision,
                current.direction,
                current.currency,
                current.control_account_id,
                quantized.principal_minor,
                user_id,
            ),
        )
        await ledger.append_invoice_journal(
            conn,
            business_id=business_id,
            book_id=book_id,
            entry_id=entry,
            user_id=user_id,
            body=InvoicePosting(
                entry_date=body.entry_date,
                currency=current.currency,
                source_id=str(document_id),
                lines=(
                    LineInput(
                        account_id=current.control_account_id,
                        side=control_side,
                        amount=current.total,
                    ),
                    *(
                        LineInput(
                            account_id=line.counter_account_id,
                            side=counter_side,
                            amount=line.amount,
                        )
                        for line in current.lines
                    ),
                ),
            ),
        )
        await conn.execute(
            "insert into gba.financial_operation_entries "
            "(tenant_id,book_id,document_id,revision,component,entry_id,obligation_id) "
            "values (%s,%s,%s,%s,'principal',%s,%s)",
            (business_id, book_id, document_id, receipt.revision, entry, obligation),
        )
        await _complete(
            conn,
            business=business_id,
            actor=actor,
            user=user_id,
            operation="invoice_issue",
            key=key,
            request_hash=digest,
            receipt=receipt,
        )
    return await _invoice(conn, business_id, receipt)


async def resolve_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    actor: str,
    key: str,
    body: FinancialCommandReference,
) -> FinancialCommandStatus:
    await _lock(conn, business_id)
    # Validate the bounded key even when no ordinary receipt is retained.
    IdempotencyScope(business_id, actor, _OPERATIONS[body.operation], key)
    state: Literal["committed", "unresolved", "cancelled"] = "unresolved"
    for table, found in (
        ("financial_command_receipts", "committed"),
        ("financial_command_cancellations", "cancelled"),
    ):
        row = await (
            await conn.execute(
                "select book_id,document_id,revision from gba."  # noqa: S608 - fixed finite tables
                + table
                + " where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
                (business_id, actor, body.operation, key),
            )
        ).fetchone()
        if row is not None:
            if (row[0], row[1], row[2]) != (body.book_id, body.subject_id, body.revision):
                raise InvalidReferenceError("This outcome belongs to another financial reference")
            state = "committed" if found == "committed" else "cancelled"
            break
    return FinancialCommandStatus(
        business_id=business_id, key=key, operation=body.operation, state=state
    )


async def cancel_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: FinancialCommandReference,
) -> FinancialCommandStatus:
    result = await resolve_command(conn, business_id=business_id, actor=actor, key=key, body=body)
    if result.state != "unresolved":
        return result
    await ledger.require_book(conn, business_id, body.book_id)
    await conn.execute(
        "insert into gba.financial_command_cancellations "
        "(tenant_id,actor_key,operation,idempotency_key,book_id,document_id,revision,cancelled_by) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business_id,
            actor,
            body.operation,
            key,
            body.book_id,
            body.subject_id,
            body.revision,
            user_id,
        ),
    )
    await commands.audit(
        conn,
        business_id,
        actor,
        "finance.command_cancelled",
        "financial_command",
        key,
        {"book_id": str(body.book_id), "operation": body.operation},
    )
    return result.model_copy(update={"state": "cancelled"})
