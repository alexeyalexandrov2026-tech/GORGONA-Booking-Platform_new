"""Immutable invoice and manual-accrual documents with atomic, attested accruals.

No cash fact, provider action, reserve or automatic revenue recognition occurs.
Commands, documents, obligations and G journal identity remain separate. The
caller owns the transaction; every completed effect is rechecked by SQL.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, NamedTuple
from uuid import UUID, uuid7

from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    SerializationFailure,
    UniqueViolation,
)

from gorgona_booking.business import commands, financial_commands, ledger, modules
from gorgona_booking.business.financial_commands import Reference
from gorgona_booking.business.financial_contracts import (
    DocumentKind,
    FinancialCommandKind,
    FinancialReceipt,
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceIssueInput,
    InvoiceLineInput,
    InvoiceList,
    InvoiceSummary,
)
from gorgona_booking.business.financial_math import quantize_invoice
from gorgona_booking.business.ledger_contracts import (
    AccrualPosting,
    InvoicePosting,
    LineInput,
    from_minor,
)
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


class _Kind(NamedTuple):
    draft: FinancialCommandKind
    issue: FinancialCommandKind
    obligation_source: Literal["invoice", "manual"]
    label: str


_KINDS: dict[DocumentKind, _Kind] = {
    "invoice": _Kind("invoice_draft", "invoice_issue", "invoice", "Invoice"),
    "manual_accrual": _Kind("accrual_draft", "accrual_issue", "manual", "Manual accrual"),
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


async def require_workflow(conn: RuntimeConnection, business: UUID) -> None:
    """New H effects need the current registry readiness and every published module."""
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


def _receipt(reference: Reference) -> FinancialReceipt:
    return FinancialReceipt(
        book_id=reference.book_id,
        document_id=reference.subject_id,
        revision=reference.revision,
    )


async def _claim(
    conn: RuntimeConnection,
    *,
    business: UUID,
    actor: str,
    operation: FinancialCommandKind,
    key: str,
    request_hash: str,
) -> FinancialReceipt | None:
    reference = await financial_commands.claim(
        conn,
        business=business,
        actor=actor,
        operation=operation,
        key=key,
        request_hash=request_hash,
        model=FinancialReceipt,
        receipt=_receipt,
    )
    return None if reference is None else _receipt(reference)


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
    await financial_commands.complete(
        conn,
        business=business,
        actor=actor,
        user=user,
        operation=operation,
        key=key,
        request_hash=request_hash,
        reference=Reference(receipt.book_id, receipt.document_id, receipt.revision),
        receipt=receipt,
        flush=_flush,
    )


async def load_invoice(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    *,
    revision: int | None = None,
    kind: DocumentKind = "invoice",
) -> InvoiceDocumentView | None:
    row = await (
        await conn.execute(
            "select v.revision,v.state,v.direction,v.counterparty_id,"
            "v.counterparty_revision,v.currency,"
            "c.minor_units,v.invoice_date,v.due_date,v.control_account_id,v.title,v.number,"
            "v.principal_minor,v.entry_id,v.obligation_id,v.issued_on,v.attestation,v.created_at "
            "from gba.financial_document_versions v join gba.currencies c on c.code=v.currency "
            "join gba.financial_documents d on d.tenant_id=v.tenant_id and d.book_id=v.book_id "
            "and d.id=v.document_id "
            "where v.tenant_id=%s and v.book_id=%s and v.document_id=%s and d.kind=%s "
            "and (%s::integer is null or v.revision=%s) order by v.revision desc limit 1",
            (business_id, book_id, document_id, kind, revision, revision),
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
        kind=kind,
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
    kind: DocumentKind,
) -> InvoiceDocumentView:
    result = await load_invoice(
        conn, business, receipt.book_id, receipt.document_id, revision=receipt.revision, kind=kind
    )
    if result is None:
        raise DatabaseUnavailableError("The stored financial document version is missing")
    return result


async def list_invoices(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
    kind: DocumentKind = "invoice",
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
            "where d.tenant_id=%s and d.book_id=%s and d.kind=%s "
            "and (%s::uuid is null or d.id>%s) order by d.id limit %s",
            (business_id, book_id, kind, after, after, limit + 1),
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


async def _document_exists(
    conn: RuntimeConnection, business: UUID, book: UUID, document: UUID
) -> bool:
    row = await (
        await conn.execute(
            "select 1 from gba.financial_documents where tenant_id=%s and book_id=%s and id=%s",
            (business, book, document),
        )
    ).fetchone()
    return row is not None


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
    kind: DocumentKind = "invoice",
) -> InvoiceDocumentView:
    spec = _KINDS[kind]
    digest = commands.fingerprint(
        {"book_id": str(book_id), "document_id": str(document_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(
        conn,
        business=business_id,
        actor=actor,
        operation=spec.draft,
        key=key,
        request_hash=digest,
    )
    if prior is not None:
        return await _invoice(conn, business_id, prior, kind)
    await require_workflow(conn, business_id)
    await ledger.require_book(conn, business_id, book_id)
    current = await load_invoice(conn, business_id, book_id, document_id, kind=kind)
    if current is None and await _document_exists(conn, business_id, book_id, document_id):
        raise FinancialDocumentStateError("This identifier belongs to another financial document")
    actual = current.revision if current else 0
    if body.expected_revision != actual:
        raise ConflictError(f"{spec.label} changed; reload before saving", revision=actual)
    if current is not None and current.state != "draft":
        raise FinancialDocumentStateError(f"An issued {spec.label.lower()} stays unchanged")
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
                "insert into gba.financial_documents (tenant_id,book_id,id,created_by,kind) "
                "values (%s,%s,%s,%s,%s)",
                (business_id, book_id, document_id, user_id, kind),
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
            operation=spec.draft,
            key=key,
            request_hash=digest,
            receipt=receipt,
        )
    return await _invoice(conn, business_id, receipt, kind)


async def issue_document(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: InvoiceIssueInput,
    kind: DocumentKind = "invoice",
) -> InvoiceDocumentView:
    """Issue once: version, obligation, balanced G journal, link and receipt together."""
    spec = _KINDS[kind]
    posting = InvoicePosting if kind == "invoice" else AccrualPosting
    digest = commands.fingerprint(
        {"book_id": str(book_id), "document_id": str(document_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(
        conn,
        business=business_id,
        actor=actor,
        operation=spec.issue,
        key=key,
        request_hash=digest,
    )
    if prior is not None:
        return await _invoice(conn, business_id, prior, kind)
    await require_workflow(conn, business_id)
    current = await load_invoice(conn, business_id, book_id, document_id, kind=kind)
    if current is None:
        raise NotFoundError(f"{spec.label} not found")
    if current.state != "draft":
        raise FinancialDocumentStateError(f"{spec.label} was already issued")
    if current.revision != body.expected_revision:
        raise ConflictError(f"{spec.label} changed; reload before issue", revision=current.revision)
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
            "values (%s,%s,%s,%s,%s,%s,'principal',%s,%s,%s,%s,%s,%s,%s)",
            (
                business_id,
                book_id,
                obligation,
                spec.obligation_source,
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
        await ledger.append_financial_journal(
            conn,
            business_id=business_id,
            book_id=book_id,
            entry_id=entry,
            user_id=user_id,
            body=posting(
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
            operation=spec.issue,
            key=key,
            request_hash=digest,
            receipt=receipt,
        )
    return await _invoice(conn, business_id, receipt, kind)
