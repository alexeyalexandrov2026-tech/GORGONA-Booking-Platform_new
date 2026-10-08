"""H3 credit notes: an immutable reduction of one invoice or manual-accrual obligation.

The unpaid part becomes C of the credited obligation; the part already paid becomes a
separate opposite-direction refund obligation that settles like any other obligation.
Historical cash and the original principal never change. Issue writes the version,
the refund obligation, one balanced G journal and the receipt together under the
ledger lock, and SQL rechecks the complete effect at commit. A credit needs every
reserve of the credited obligation resolved first. Corrections and voids of a credit
are not offered here.
"""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal, NamedTuple
from uuid import UUID, uuid7

from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    SerializationFailure,
    UniqueViolation,
)
from pydantic import ValidationError

from gorgona_booking.business import commands, financial_commands, ledger
from gorgona_booking.business.financial_commands import Reference
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditIssueInput,
    CreditLineInput,
    CreditList,
    CreditNoteView,
    CreditSummary,
    FinancialReceipt,
)
from gorgona_booking.business.financial_documents import (
    FEATURE,
    FinancialDocumentStateError,
    require_workflow,
)
from gorgona_booking.business.financial_math import (
    FinancialAmountError,
    FinancialBalance,
    FinancialCapError,
    split_credit,
)
from gorgona_booking.business.ledger_contracts import (
    MAX_MINOR,
    CreditPosting,
    LineInput,
    from_minor,
    to_minor,
)
from gorgona_booking.business.module_gate import FINANCE_MODULE, module_writes
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DatabaseUnavailableError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)

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
_KIND = "credit_note"
_Operation = Literal["credit_draft", "credit_issue"]


class FinancialRefundAccountError(ConflictError):
    code = "FINANCIAL_REFUND_ACCOUNT_INVALID"


class FinancialTreatmentError(DomainError):
    code = "FINANCIAL_TREATMENT_INVALID"


class _Credited(NamedTuple):
    """The obligation a credit note reduces and the issued lines it may reduce."""

    document: UUID
    revision: int
    counterparty: UUID
    direction: Literal["receivable", "payable"]
    currency: str
    scale: int
    control: UUID
    accrued: date
    # line id -> (counter account, amount in minor units)
    lines: dict[UUID, tuple[UUID, int]]


class _Draft(NamedTuple):
    credited: UUID
    counterparty_revision: int
    credit_date: date
    due_date: date | None
    title: str
    number: str
    lines: tuple[CreditLineInput, ...]


async def _flush(conn: RuntimeConnection) -> None:
    await conn.execute("set constraints " + _CONSTRAINTS + " immediate")
    await conn.execute("set constraints " + _CONSTRAINTS + " deferred")


@asynccontextmanager
async def _writes(conn: RuntimeConnection) -> AsyncIterator[None]:
    try:
        async with module_writes(FINANCE_MODULE, FEATURE), conn.transaction():
            yield
            await _flush(conn)
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Every credit reference must belong to this company and book"
        ) from exc
    except (CheckViolation, UniqueViolation) as exc:
        raise FinancialDocumentStateError(
            "Credit note or obligation changed; reload before continuing"
        ) from exc
    except SerializationFailure as exc:
        raise DatabaseUnavailableError("Financial transaction settings are not ready") from exc


def _receipt(reference: Reference) -> FinancialReceipt:
    return FinancialReceipt(
        book_id=reference.book_id, document_id=reference.subject_id, revision=reference.revision
    )


async def _claim(
    conn: RuntimeConnection,
    business: UUID,
    actor: str,
    operation: _Operation,
    key: str,
    digest: str,
) -> Reference | None:
    return await financial_commands.claim(
        conn,
        business=business,
        actor=actor,
        operation=operation,
        key=key,
        request_hash=digest,
        model=FinancialReceipt,
        receipt=_receipt,
    )


async def _complete(
    conn: RuntimeConnection,
    business: UUID,
    actor: str,
    user: UUID,
    operation: _Operation,
    key: str,
    digest: str,
    reference: Reference,
) -> None:
    await financial_commands.complete(
        conn,
        business=business,
        actor=actor,
        user=user,
        operation=operation,
        key=key,
        request_hash=digest,
        reference=reference,
        receipt=_receipt(reference),
        flush=_flush,
    )


async def load_credit(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    *,
    revision: int | None = None,
) -> CreditNoteView | None:
    """The credit note as saved in `revision`; the latest version when omitted."""
    row = await (
        await conn.execute(
            "select v.revision,v.state,v.credited_obligation_id,v.direction,v.counterparty_id,"
            "v.counterparty_revision,v.currency,c.minor_units,v.invoice_date,v.due_date,"
            "v.control_account_id,v.title,v.number,v.principal_minor,v.entry_id,v.issued_on,"
            "v.attestation,v.applied_minor,v.refund_control_account_id,v.obligation_id,"
            "v.created_at from gba.financial_document_versions v "
            "join gba.currencies c on c.code=v.currency "
            "join gba.financial_documents d on d.tenant_id=v.tenant_id and d.book_id=v.book_id "
            "and d.id=v.document_id "
            "where v.tenant_id=%s and v.book_id=%s and v.document_id=%s and d.kind=%s "
            "and (%s::integer is null or v.revision=%s) order by v.revision desc limit 1",
            (business_id, book_id, document_id, _KIND, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    lines = await (
        await conn.execute(
            "select line_id,credited_line_id,counter_account_id,description,amount_minor,"
            "reason,reference_entry_id from gba.financial_document_lines "
            "where tenant_id=%s and book_id=%s and document_id=%s and revision=%s order by line_no",
            (business_id, book_id, document_id, row[0]),
        )
    ).fetchall()
    scale, principal, applied = row[7], row[13], row[17]
    return CreditNoteView(
        business_id=business_id,
        book_id=book_id,
        document_id=document_id,
        revision=row[0],
        state=row[1],
        credited_obligation_id=row[2],
        direction=row[3],
        counterparty_id=row[4],
        counterparty_revision=row[5],
        currency=row[6],
        minor_units=scale,
        credit_date=row[8],
        due_date=row[9],
        control_account_id=row[10],
        title=row[11],
        number=row[12],
        total=from_minor(principal, scale),
        entry_id=row[14],
        issued_on=row[15],
        attestation=row[16],
        applied=None if applied is None else from_minor(applied, scale),
        refund=None if applied is None else from_minor(principal - applied, scale),
        refund_control_account_id=row[18],
        refund_obligation_id=row[19],
        created_at=row[20],
        lines=tuple(
            CreditLineInput(
                line_id=line[0],
                credited_line_id=line[1],
                counter_account_id=line[2],
                description=line[3],
                amount=from_minor(line[4], scale),
                reason=line[5],
                reference_entry_id=line[6],
            )
            for line in lines
        ),
    )


async def _view(conn: RuntimeConnection, business: UUID, reference: Reference) -> CreditNoteView:
    result = await load_credit(
        conn, business, reference.book_id, reference.subject_id, revision=reference.revision
    )
    if result is None:
        raise DatabaseUnavailableError("The stored credit note version is missing")
    return result


async def list_credits(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    after: UUID | None,
    limit: int,
) -> CreditList:
    await ledger.require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            "select d.id,v.revision,v.state,v.credited_obligation_id,v.direction,"
            "v.counterparty_id,v.currency,c.minor_units,v.invoice_date,v.title,v.number,"
            "v.principal_minor,v.applied_minor,v.entry_id,v.obligation_id,v.created_at "
            "from gba.financial_documents d join lateral ("
            "select * from gba.financial_document_versions x where x.tenant_id=d.tenant_id "
            "and x.book_id=d.book_id and x.document_id=d.id order by x.revision desc limit 1"
            ") v on true join gba.currencies c on c.code=v.currency "
            "where d.tenant_id=%s and d.book_id=%s and d.kind=%s "
            "and (%s::uuid is null or d.id>%s) order by d.id limit %s",
            (business_id, book_id, _KIND, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        CreditSummary(
            document_id=r[0],
            revision=r[1],
            state=r[2],
            credited_obligation_id=r[3],
            direction=r[4],
            counterparty_id=r[5],
            currency=r[6],
            credit_date=r[8],
            title=r[9],
            number=r[10],
            total=from_minor(r[11], r[7]),
            applied=None if r[12] is None else from_minor(r[12], r[7]),
            refund=None if r[12] is None else from_minor(r[11] - r[12], r[7]),
            entry_id=r[13],
            refund_obligation_id=r[14],
            created_at=r[15],
        )
        for r in rows[:limit]
    )
    return CreditList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].document_id if len(rows) > limit else None,
    )


async def _credited(
    conn: RuntimeConnection, business: UUID, book: UUID, obligation: UUID
) -> _Credited:
    row = await (
        await conn.execute(
            "select o.source_kind,o.source_id,o.source_revision,o.counterparty_id,o.direction,"
            "o.currency,c.minor_units,o.control_account_id,v.issued_on "
            "from gba.financial_obligations o join gba.currencies c on c.code=o.currency "
            "join gba.financial_document_versions v on v.tenant_id=o.tenant_id "
            "and v.book_id=o.book_id and v.document_id=o.source_id "
            "and v.revision=o.source_revision "
            "where o.tenant_id=%s and o.book_id=%s and o.id=%s",
            (business, book, obligation),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError(
            "The credited obligation must belong to this book", field="credited_obligation_id"
        )
    if row[0] not in ("invoice", "manual"):
        raise FinancialDocumentStateError(
            "Only an invoice or manual accrual obligation is credited"
        )
    lines = await (
        await conn.execute(
            "select line_id,counter_account_id,amount_minor from gba.financial_document_lines "
            "where tenant_id=%s and book_id=%s and document_id=%s and revision=%s",
            (business, book, row[1], row[2]),
        )
    ).fetchall()
    return _Credited(
        document=row[1],
        revision=row[2],
        counterparty=row[3],
        direction=row[4],
        currency=row[5],
        scale=row[6],
        control=row[7],
        accrued=row[8],
        lines={line[0]: (line[1], int(line[2])) for line in lines},
    )


async def _amounts(
    conn: RuntimeConnection,
    business: UUID,
    book: UUID,
    credited: _Credited,
    lines: Sequence[CreditLineInput],
) -> list[int]:
    """Exact minor units of each line, checked against the line it credits."""
    amounts: list[int] = []
    for number, line in enumerate(lines, 1):
        original = credited.lines.get(line.credited_line_id)
        if original is None:
            raise InvalidReferenceError(
                "A credit line needs a line of the credited document", field="lines", line=number
            )
        try:
            amounts.append(to_minor(line.amount, credited.scale))
        except ValueError as exc:
            raise FinancialAmountError(str(exc), line=number, currency=credited.currency) from exc
        if amounts[-1] > original[1]:
            raise FinancialCapError("A credit line exceeds its original line", line=number)
        if (line.counter_account_id != original[0]) != (line.reason is not None):
            raise FinancialTreatmentError(
                "Give a reason exactly when the account differs from the credited line",
                line=number,
            )
        if line.reference_entry_id is not None:
            cited = await (
                await conn.execute(
                    "select 1 from gba.journal_entries where tenant_id=%s and book_id=%s "
                    "and id=%s and currency=%s",
                    (business, book, line.reference_entry_id, credited.currency),
                )
            ).fetchone()
            if cited is None:
                raise InvalidReferenceError(
                    "A cited entry must belong to this book and currency",
                    field="lines",
                    line=number,
                )
    if sum(amounts) > MAX_MINOR:
        raise FinancialAmountError("The credit total exceeds the supported principal range")
    return amounts


async def _insert_version(
    conn: RuntimeConnection,
    *,
    business: UUID,
    book: UUID,
    document: UUID,
    user: UUID,
    draft: _Draft,
    credited: _Credited,
    revision: int,
    amounts: Sequence[int],
    entry: UUID | None = None,
    refund_obligation: UUID | None = None,
    issue: CreditIssueInput | None = None,
    applied: int | None = None,
) -> None:
    await conn.execute(
        "insert into gba.financial_document_versions "
        "(tenant_id,book_id,document_id,revision,state,direction,counterparty_id,"
        "counterparty_revision,currency,invoice_date,due_date,control_account_id,title,number,"
        "principal_minor,line_count,credited_obligation_id,entry_id,obligation_id,issued_on,"
        "attestation,applied_minor,refund_control_account_id,created_by) "
        "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            business,
            book,
            document,
            revision,
            "draft" if issue is None else "issued",
            credited.direction,
            credited.counterparty,
            draft.counterparty_revision,
            credited.currency,
            draft.credit_date,
            draft.due_date,
            credited.control,
            draft.title,
            draft.number,
            sum(amounts),
            len(draft.lines),
            draft.credited,
            entry,
            refund_obligation,
            None if issue is None else issue.entry_date,
            None if issue is None else issue.attestation,
            applied,
            None if refund_obligation is None or issue is None else issue.refund_control_account_id,
            user,
        ),
    )
    await conn.execute(
        "insert into gba.financial_document_lines "
        "(tenant_id,book_id,document_id,revision,line_no,line_id,credited_line_id,"
        "counter_account_id,description,amount_minor,reason,reference_entry_id) "
        "select %s,%s,%s,%s,l.n::smallint,l.id,l.credited,l.account,l.description,l.amount,"
        "l.reason,l.cited from unnest(%s::uuid[],%s::uuid[],%s::uuid[],%s::text[],%s::bigint[],"
        "%s::text[],%s::uuid[]) with ordinality as l(id,credited,account,description,amount,"
        "reason,cited,n)",
        (
            business,
            book,
            document,
            revision,
            [line.line_id for line in draft.lines],
            [line.credited_line_id for line in draft.lines],
            [line.counter_account_id for line in draft.lines],
            [line.description for line in draft.lines],
            list(amounts),
            [line.reason for line in draft.lines],
            [line.reference_entry_id for line in draft.lines],
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
    body: CreditDraftInput,
) -> CreditNoteView:
    """Save the next draft revision; nothing is credited until the credit is issued."""
    digest = commands.fingerprint(
        {"book_id": str(book_id), "document_id": str(document_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(conn, business_id, actor, "credit_draft", key, digest)
    if prior is not None:
        return await _view(conn, business_id, prior)
    await require_workflow(conn, business_id)
    await ledger.require_book(conn, business_id, book_id)
    current = await load_credit(conn, business_id, book_id, document_id)
    if current is None:
        other = await (
            await conn.execute(
                "select 1 from gba.financial_documents where tenant_id=%s and book_id=%s and id=%s",
                (business_id, book_id, document_id),
            )
        ).fetchone()
        if other is not None:
            raise FinancialDocumentStateError(
                "This identifier belongs to another financial document"
            )
    actual = current.revision if current else 0
    if body.expected_revision != actual:
        raise ConflictError("Credit note changed; reload before saving", revision=actual)
    if current is not None and current.state != "draft":
        raise FinancialDocumentStateError("An issued credit note stays unchanged")
    credited = await _credited(conn, business_id, book_id, body.credited_obligation_id)
    amounts = await _amounts(conn, business_id, book_id, credited, body.lines)
    draft = _Draft(
        credited=body.credited_obligation_id,
        counterparty_revision=body.counterparty_revision,
        credit_date=body.credit_date,
        due_date=body.due_date,
        title=body.title,
        number=body.number,
        lines=body.lines,
    )
    reference = Reference(book_id, document_id, actual + 1)
    async with _writes(conn):
        if current is None:
            await conn.execute(
                "insert into gba.financial_documents (tenant_id,book_id,id,created_by,kind) "
                "values (%s,%s,%s,%s,%s)",
                (business_id, book_id, document_id, user_id, _KIND),
            )
        await _insert_version(
            conn,
            business=business_id,
            book=book_id,
            document=document_id,
            user=user_id,
            draft=draft,
            credited=credited,
            revision=reference.revision,
            amounts=amounts,
        )
        await _complete(conn, business_id, actor, user_id, "credit_draft", key, digest, reference)
    return await _view(conn, business_id, reference)


async def _balance(
    conn: RuntimeConnection, business: UUID, book: UUID, obligation: UUID
) -> FinancialBalance:
    row = await (
        await conn.execute(
            "select * from gba.obligation_balance(%s,%s,%s)", (business, book, obligation)
        )
    ).fetchone()
    if row is None:
        raise DatabaseUnavailableError("The credited obligation is missing")
    try:
        return FinancialBalance(
            principal_minor=row[0], paid_minor=row[1], credited_minor=row[2], reserved_minor=row[3]
        )
    except ValidationError as exc:
        raise DatabaseUnavailableError("A stored obligation balance is inconsistent") from exc


async def _require_refund_account(
    conn: RuntimeConnection,
    business: UUID,
    book: UUID,
    account: UUID | None,
    *,
    refund: int,
    credited: _Credited,
) -> None:
    """A refund needs an explicit open control of the opposite direction, never cash."""
    amount = from_minor(refund, credited.scale)
    if (refund > 0) != (account is not None):
        raise FinancialRefundAccountError(
            "Choose a refund account exactly when part of the credit was already paid",
            refund=amount,
        )
    if account is None:
        return
    kind = "liability" if credited.direction == "receivable" else "asset"
    row = await (
        await conn.execute(
            "select 1 from gba.ledger_accounts a join gba.ledger_account_versions v "
            "on v.tenant_id=a.tenant_id and v.account_id=a.id "
            "where a.tenant_id=%s and a.book_id=%s and a.id=%s and a.type=%s and not v.archived "
            "and v.revision=(select max(x.revision) from gba.ledger_account_versions x "
            "where x.tenant_id=a.tenant_id and x.account_id=a.id) "
            "and not exists (select 1 from gba.external_payments p where p.tenant_id=a.tenant_id "
            "and p.book_id=a.book_id and p.cash_account_id=a.id)",
            (business, book, account, kind),
        )
    ).fetchone()
    if row is None:
        raise FinancialRefundAccountError(
            f"The refund account must be an open {kind} that never received external cash",
            refund=amount,
        )


async def issue_credit(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: CreditIssueInput,
) -> CreditNoteView:
    """Issue once: version, refund obligation, balanced G journal and receipt together."""
    digest = commands.fingerprint(
        {"book_id": str(book_id), "document_id": str(document_id), **body.model_dump(mode="json")}
    )
    prior = await _claim(conn, business_id, actor, "credit_issue", key, digest)
    if prior is not None:
        return await _view(conn, business_id, prior)
    await require_workflow(conn, business_id)
    current = await load_credit(conn, business_id, book_id, document_id)
    if current is None:
        raise NotFoundError("Credit note not found")
    if current.state != "draft":
        raise FinancialDocumentStateError("Credit note was already issued")
    if current.revision != body.expected_revision:
        raise ConflictError("Credit note changed; reload before issue", revision=current.revision)
    credited = await _credited(conn, business_id, book_id, current.credited_obligation_id)
    amounts = await _amounts(conn, business_id, book_id, credited, current.lines)
    if body.entry_date < credited.accrued:
        raise ledger.LedgerDateError("A credit cannot be posted before the accrual it credits")
    rows = await (
        await conn.execute(
            "select c.credited_line_id,sum(c.amount_minor) from gba.financial_document_lines c "
            "join gba.financial_document_versions x on x.tenant_id=c.tenant_id "
            "and x.book_id=c.book_id and x.document_id=c.document_id and x.revision=c.revision "
            "where x.tenant_id=%s and x.book_id=%s and x.credited_obligation_id=%s "
            "and x.state='issued' group by c.credited_line_id",
            (business_id, book_id, current.credited_obligation_id),
        )
    ).fetchall()
    used = {row[0]: int(row[1]) for row in rows}
    requested: dict[UUID, int] = {}
    for line, amount in zip(current.lines, amounts, strict=True):
        requested[line.credited_line_id] = requested.get(line.credited_line_id, 0) + amount
    for original, amount in requested.items():
        if amount > credited.lines[original][1] - used.get(original, 0):
            raise FinancialCapError("The credit exceeds the uncredited amount of an original line")
    balance = await _balance(conn, business_id, book_id, current.credited_obligation_id)
    # The unpaid balance is credited first (C); only the rest is refunded.
    split = split_credit(
        balance, sum(amounts), uncredited_minor=balance.principal_minor - sum(used.values())
    )
    await _require_refund_account(
        conn,
        business_id,
        book_id,
        body.refund_control_account_id,
        refund=split.refund_minor,
        credited=credited,
    )
    draft = _Draft(
        credited=current.credited_obligation_id,
        counterparty_revision=current.counterparty_revision,
        credit_date=current.credit_date,
        due_date=current.due_date,
        title=current.title,
        number=current.number,
        lines=current.lines,
    )
    reference = Reference(book_id, document_id, current.revision + 1)
    entry = uuid7()
    refund_obligation = uuid7() if split.refund_minor else None
    receivable = credited.direction == "receivable"
    # Each credit line reverses its counter account; the controls take the reduction.
    reverse: Literal["debit", "credit"] = "debit" if receivable else "credit"
    reduce: Literal["debit", "credit"] = "credit" if receivable else "debit"
    lines = [
        LineInput(account_id=line.counter_account_id, side=reverse, amount=line.amount)
        for line in current.lines
    ]
    if split.unpaid_minor:
        lines.append(
            LineInput(
                account_id=credited.control,
                side=reduce,
                amount=from_minor(split.unpaid_minor, credited.scale),
            )
        )
    if refund_obligation is not None and body.refund_control_account_id is not None:
        lines.append(
            LineInput(
                account_id=body.refund_control_account_id,
                side=reduce,
                amount=from_minor(split.refund_minor, credited.scale),
            )
        )
    async with _writes(conn):
        await _insert_version(
            conn,
            business=business_id,
            book=book_id,
            document=document_id,
            user=user_id,
            draft=draft,
            credited=credited,
            revision=reference.revision,
            amounts=amounts,
            entry=entry,
            refund_obligation=refund_obligation,
            issue=body,
            applied=split.unpaid_minor,
        )
        if refund_obligation is not None:
            await conn.execute(
                "insert into gba.financial_obligations "
                "(tenant_id,book_id,id,source_kind,source_id,source_revision,component,"
                "counterparty_id,counterparty_revision,direction,currency,control_account_id,"
                "principal_minor,created_by) "
                "values (%s,%s,%s,'credit_refund',%s,%s,'principal',%s,%s,%s,%s,%s,%s,%s)",
                (
                    business_id,
                    book_id,
                    refund_obligation,
                    document_id,
                    reference.revision,
                    credited.counterparty,
                    current.counterparty_revision,
                    "payable" if receivable else "receivable",
                    credited.currency,
                    body.refund_control_account_id,
                    split.refund_minor,
                    user_id,
                ),
            )
        await ledger.append_financial_journal(
            conn,
            business_id=business_id,
            book_id=book_id,
            entry_id=entry,
            user_id=user_id,
            body=CreditPosting(
                entry_date=body.entry_date,
                currency=credited.currency,
                source_id=str(document_id),
                lines=tuple(lines),
            ),
        )
        if refund_obligation is not None:
            await conn.execute(
                "insert into gba.financial_operation_entries "
                "(tenant_id,book_id,document_id,revision,component,entry_id,obligation_id) "
                "values (%s,%s,%s,%s,'principal',%s,%s)",
                (business_id, book_id, document_id, reference.revision, entry, refund_obligation),
            )
        await _complete(conn, business_id, actor, user_id, "credit_issue", key, digest, reference)
    return await _view(conn, business_id, reference)
