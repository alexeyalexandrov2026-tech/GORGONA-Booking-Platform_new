"""Ledger foundation: books, chart of accounts, double entry and periods (ADR-0023).

Callers hold the per-business `ledger` lock before the membership share lock; the
database triggers take the same lock, so a posting and a period close have one
order. A command claims its key, replays a stored reference-only receipt for the
same body, checks the module, writes, audits without names, memos or reasons and
stores its receipt in one transaction. Nothing is updated or deleted: a correction
is a reversal and a new entry. The database re-checks every rule.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, Literal, overload
from uuid import UUID, uuid7

from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    SerializationFailure,
    UniqueViolation,
)
from pydantic import BaseModel

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands
from gorgona_booking.business.ledger_contracts import (
    AccountInput,
    AccountReceipt,
    AccountType,
    Balances,
    BookInput,
    BookReceipt,
    CloseInput,
    CommandKind,
    CommandReference,
    CommandStatus,
    Currency,
    EntryInput,
    EntryReceipt,
    InvoicePosting,
    JournalEntryList,
    JournalEntryListV2,
    JournalEntrySummary,
    JournalEntrySummaryV2,
    JournalEntryView,
    JournalEntryViewV2,
    JournalLine,
    LedgerAccount,
    LedgerAccountList,
    LedgerAccountView,
    LedgerBookView,
    LedgerEntity,
    LedgerOverview,
    LedgerPeriod,
    LedgerPeriodList,
    LedgerPeriodView,
    PeriodAction,
    PeriodEvent,
    PeriodReceipt,
    ReopenInput,
    ReversalInput,
    TrialBalance,
    TrialBalanceRow,
    from_minor,
    month,
    month_text,
    to_minor,
)
from gorgona_booking.business.module_gate import FINANCE_MODULE, module_writes, require_module
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DatabaseUnavailableError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)


class LedgerInputError(DomainError):
    code = "LEDGER_INVALID"


class LedgerAmountError(DomainError):
    code = "LEDGER_AMOUNT_INVALID"


class UnbalancedEntryError(DomainError):
    code = "LEDGER_ENTRY_UNBALANCED"


class LedgerDateError(DomainError):
    code = "LEDGER_DATE_INVALID"


class LedgerStateError(ConflictError):
    code = "LEDGER_STATE_INVALID"


class PeriodClosedError(ConflictError):
    code = "LEDGER_PERIOD_CLOSED"


class OperationPostedError(ConflictError):
    code = "LEDGER_OPERATION_POSTED"


class EntryReversedError(ConflictError):
    code = "LEDGER_ENTRY_REVERSED"


class AccountCodeTakenError(ConflictError):
    code = "LEDGER_ACCOUNT_CODE_TAKEN"


class JournalUpgradeRequiredError(ConflictError):
    code = "JOURNAL_VERSION_REQUIRED"


class CommandCancelledError(ConflictError):
    code = "LEDGER_COMMAND_CANCELLED"


_BOOK = "business.ledger.book"
_ACCOUNT = "business.ledger.account"
_ENTRY = "business.ledger.entry"
_REVERSE = "business.ledger.reverse"
_PERIOD = {"closed": "business.ledger.close", "reopened": "business.ledger.reopen"}
_OPERATIONS: dict[CommandKind, str] = {
    "book": _BOOK,
    "account": _ACCOUNT,
    "entry": _ENTRY,
    "reverse": _REVERSE,
    "close": _PERIOD["closed"],
    "reopen": _PERIOD["reopened"],
}


async def _lock(conn: RuntimeConnection, business_id: UUID) -> None:
    try:
        await conn.execute("select gba.lock_ledger(%s)", (business_id,))
    except SerializationFailure as exc:
        raise DatabaseUnavailableError(
            "Required ledger transaction settings are not ready"
        ) from exc


async def _claim[T: BaseModel](
    conn: RuntimeConnection, scope: IdempotencyScope, request_hash: str, model: type[T]
) -> T | None:
    await _lock(conn, scope.tenant_id)
    cancelled = await (
        await conn.execute(
            "select 1 from gba.ledger_command_cancellations "
            "where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
            (scope.tenant_id, scope.actor_key, scope.operation, scope.key),
        )
    ).fetchone()
    if cancelled:
        raise CommandCancelledError("This unresolved command was cancelled; reload the ledger")
    return await commands.claim(conn, scope, request_hash, model)


async def resolve_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: CommandReference,
) -> CommandStatus:
    await _lock(conn, business_id)
    scope = IdempotencyScope(business_id, actor, _OPERATIONS[body.operation], key)
    cancelled = await (
        await conn.execute(
            "select 1 from gba.ledger_command_cancellations "
            "where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
            (business_id, actor, scope.operation, key),
        )
    ).fetchone()
    if cancelled:
        return CommandStatus(
            business_id=business_id, key=key, operation=body.operation, state="cancelled"
        )
    row = await (
        await conn.execute(
            "select response_status,response_body from gba.idempotency_keys "
            "where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
            (business_id, actor, scope.operation, key),
        )
    ).fetchone()
    if row is not None:
        if row[0] != 200 or row[1] is None:
            raise DatabaseUnavailableError("The command receipt is incomplete")
        receipt = row[1]
        if body.operation == "book":
            stored = BookReceipt.model_validate(receipt)
            matches = stored.book_id == body.book_id and stored.revision == body.revision
        elif body.operation == "account":
            account_receipt = AccountReceipt.model_validate(receipt)
            matches = (
                account_receipt.book_id == body.book_id
                and account_receipt.account_id == body.subject_id
                and account_receipt.revision == body.revision
            )
        elif body.operation in ("entry", "reverse"):
            entry_receipt = EntryReceipt.model_validate(receipt)
            matches = (
                entry_receipt.book_id == body.book_id and entry_receipt.entry_id == body.subject_id
            )
        else:
            period_receipt = PeriodReceipt.model_validate(receipt)
            matches = (
                period_receipt.book_id == body.book_id
                and period_receipt.period == body.period
                and period_receipt.sequence == body.sequence
            )
        if not matches:
            raise InvalidReferenceError("This receipt belongs to another command reference")
        return CommandStatus(
            business_id=business_id, key=key, operation=body.operation, state="committed"
        )
    # Ordinary receipts expire after 24 h. Immutable records keep the reference
    # resolvable after expiry; we never mistake a recorded entry for an absent one.
    if body.operation == "book":
        found = await (
            await conn.execute(
                "select 1 from gba.ledger_book_versions "
                "where tenant_id=%s and book_id=%s and revision=%s and created_by=%s",
                (business_id, body.book_id, body.revision, user_id),
            )
        ).fetchone()
    elif body.operation == "account":
        found = await (
            await conn.execute(
                "select 1 from gba.ledger_account_versions v "
                "join gba.ledger_accounts a on a.tenant_id=v.tenant_id and a.id=v.account_id "
                "where v.tenant_id=%s and a.book_id=%s and v.account_id=%s and v.revision=%s "
                "and v.created_by=%s",
                (business_id, body.book_id, body.subject_id, body.revision, user_id),
            )
        ).fetchone()
    elif body.operation in ("entry", "reverse"):
        found = await (
            await conn.execute(
                "select 1 from gba.journal_entries "
                "where tenant_id=%s and book_id=%s and id=%s and created_by=%s "
                "and (source_kind='reversal')=%s",
                (business_id, body.book_id, body.subject_id, user_id, body.operation == "reverse"),
            )
        ).fetchone()
    else:
        found = await (
            await conn.execute(
                "select 1 from gba.ledger_period_events "
                "where tenant_id=%s and book_id=%s and period=%s and sequence=%s "
                "and action=%s and decided_by=%s",
                (
                    business_id,
                    body.book_id,
                    month(body.period or ""),
                    body.sequence,
                    "closed" if body.operation == "close" else "reopened",
                    user_id,
                ),
            )
        ).fetchone()
    return CommandStatus(
        business_id=business_id,
        key=key,
        operation=body.operation,
        state="committed" if found else "unresolved",
    )


async def cancel_unresolved_command(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: CommandReference,
) -> CommandStatus:
    state = await resolve_command(
        conn, business_id=business_id, user_id=user_id, actor=actor, key=key, body=body
    )
    if state.state != "unresolved":
        return state
    await conn.execute(
        "insert into gba.ledger_command_cancellations "
        "(tenant_id,actor_key,operation,idempotency_key,book_id,cancelled_by) "
        "values (%s,%s,%s,%s,%s,%s)",
        (business_id, actor, _OPERATIONS[body.operation], key, body.book_id, user_id),
    )
    await _audit(
        conn,
        business_id,
        actor,
        "ledger.command_cancelled",
        ("ledger_command", key),
        {"book_id": str(body.book_id), "operation": body.operation},
    )
    return state.model_copy(update={"state": "cancelled"})


# Owner decision 2026-10-06 (2A): a neutral starter chart, no country tax accounts.
STARTER_CHART: tuple[tuple[str, AccountType, str], ...] = (
    ("1000", "asset", "Cash"),
    ("1100", "asset", "Bank accounts"),
    ("1200", "asset", "Accounts receivable"),
    ("1300", "asset", "Inventory and materials"),
    ("1400", "asset", "Prepaid expenses"),
    ("1500", "asset", "Equipment and other fixed assets"),
    ("2000", "liability", "Accounts payable"),
    ("2100", "liability", "Customer prepayments"),
    ("2200", "liability", "Wages payable"),
    ("2300", "liability", "Taxes payable"),
    ("2400", "liability", "Loans"),
    ("3000", "equity", "Owner's capital"),
    ("3100", "equity", "Retained earnings"),
    ("3900", "equity", "Opening balances"),
    ("4000", "revenue", "Sales of goods"),
    ("4100", "revenue", "Services"),
    ("4900", "revenue", "Other income"),
    ("5000", "expense", "Cost of goods and materials"),
    ("6000", "expense", "Wages and salaries"),
    ("6100", "expense", "Rent"),
    ("6200", "expense", "Utilities and communication"),
    ("6300", "expense", "Marketing"),
    ("6400", "expense", "Bank and payment fees"),
    ("6900", "expense", "Other expenses"),
)

# Trigger messages (no constraint name) and the errors they become.
_CHECKS: tuple[tuple[str, type[DomainError], str], ...] = (
    ("period of this entry is closed", PeriodClosedError, "This month is closed"),
    ("accounting start", LedgerDateError, "The date is before the book's accounting start"),
    ("open account", LedgerStateError, "An archived account cannot receive new entries"),
    ("balanced debits", UnbalancedEntryError, "Debits and credits must be equal"),
    ("reversal", LedgerStateError, "This entry cannot be reversed this way"),
    ("fixed once entries", LedgerStateError, "The book already has entries"),
)
_UNIQUE: dict[str, tuple[type[DomainError], str]] = {
    "journal_entries_pkey": (OperationPostedError, "This entry was already posted"),
    "journal_entries_operation_unique": (
        OperationPostedError,
        "This business operation was already posted in this book",
    ),
    "journal_entries_reversed_once": (EntryReversedError, "This entry was already reversed"),
    "ledger_books_one_per_entity": (ConflictError, "This legal entity already has a book"),
    "ledger_accounts_code_unique": (
        AccountCodeTakenError,
        "Another account of this book has this code",
    ),
}
_FOREIGN_KEYS = {
    "ledger_books_legal_entity_fk": "legal_entity_id",
    "ledger_book_versions_base_currency_fkey": "base_currency",
    "journal_entries_currency_fkey": "currency",
    "journal_lines_account_fk": "lines",
}


@asynccontextmanager
async def _writes(conn: RuntimeConnection) -> AsyncIterator[None]:
    """One savepoint of ledger inserts; database refusals become domain errors."""
    try:
        async with module_writes(FINANCE_MODULE, "finance_documents"), conn.transaction():
            yield
            # Run the deferred balance check now, inside this command.
            await conn.execute(
                "set constraints gba.journal_entries_balanced, gba.journal_lines_balanced immediate"
            )
            await conn.execute(
                "set constraints gba.journal_entries_balanced, gba.journal_lines_balanced deferred"
            )
    except CheckViolation as exc:
        if exc.diag.constraint_name:
            # A column rule the API input checks did not cover: never a conflict.
            raise LedgerInputError("The ledger does not accept this value") from exc
        message = exc.diag.message_primary or ""
        for text, error, answer in _CHECKS:
            if text in message:
                raise error(answer) from exc
        raise ConflictError("The ledger changed. Reload it.") from exc
    except UniqueViolation as exc:
        known = _UNIQUE.get(exc.diag.constraint_name or "")
        if known is None:
            raise ConflictError("The ledger changed. Reload it.") from exc
        raise known[0](known[1]) from exc
    except ForeignKeyViolation as exc:
        field = _FOREIGN_KEYS.get(exc.diag.constraint_name or "")
        if field is None:
            raise
        raise InvalidReferenceError("Unknown reference", field=field) from exc
    except SerializationFailure as exc:
        raise DatabaseUnavailableError(
            "Required ledger transaction settings are not ready"
        ) from exc


async def _audit(
    conn: RuntimeConnection,
    business_id: UUID,
    actor: str,
    action: str,
    target: tuple[str, str],
    details: dict[str, object],
) -> None:
    await commands.audit(conn, business_id, actor, action, target[0], target[1], details)


def _expect(current: int, expected: int, what: str) -> int:
    if expected != current:
        raise ConflictError(f"This {what} changed. Reload it before saving.", revision=current)
    return current + 1


async def currencies(conn: RuntimeConnection) -> tuple[Currency, ...]:
    rows = await (
        await conn.execute("select code, minor_units from gba.currencies order by code")
    ).fetchall()
    return tuple(Currency(code=r[0], minor_units=r[1]) for r in rows)


async def _scale(conn: RuntimeConnection, currency: str, field: str) -> int:
    row = await (
        await conn.execute("select minor_units from gba.currencies where code = %s", (currency,))
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown currency", field=field)
    return int(row[0])


# --- Books -------------------------------------------------------------------------


async def load_book(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, *, revision: int | None = None
) -> LedgerBookView | None:
    row = await (
        await conn.execute(
            "select b.legal_entity_id, v.revision, v.base_currency, c.minor_units, "
            "v.fiscal_year_start_month, v.accounting_start, v.created_at, "
            "exists (select 1 from gba.journal_entries e "
            "where e.tenant_id = v.tenant_id and e.book_id = v.book_id) "
            "from gba.ledger_book_versions v "
            "join gba.ledger_books b on b.tenant_id = v.tenant_id and b.id = v.book_id "
            "join gba.currencies c on c.code = v.base_currency "
            "where v.tenant_id = %s and v.book_id = %s "
            "and (%s::integer is null or v.revision = %s) order by v.revision desc limit 1",
            (business_id, book_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    return _book(business_id, book_id, tuple(row))


def _book(business_id: UUID, book_id: UUID, row: tuple[Any, ...]) -> LedgerBookView:
    return LedgerBookView(
        business_id=business_id,
        book_id=book_id,
        legal_entity_id=row[0],
        revision=row[1],
        base_currency=row[2],
        minor_units=row[3],
        fiscal_year_start_month=row[4],
        accounting_start=row[5],
        created_at=row[6],
        has_entries=row[7],
    )


async def require_book(conn: RuntimeConnection, business_id: UUID, book_id: UUID) -> LedgerBookView:
    book = await load_book(conn, business_id, book_id)
    if book is None:
        raise NotFoundError("Book not found")
    return book


async def _book_version(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, revision: int
) -> LedgerBookView:
    book = await load_book(conn, business_id, book_id, revision=revision)
    if book is None:
        raise RuntimeError("A stored book version is missing")
    return book


async def ledger_overview(
    conn: RuntimeConnection,
    business_id: UUID,
    *,
    after: str | None,
    limit: int,
    book_id: UUID | None = None,
) -> LedgerOverview:
    """Every legal entity of the company with its book, if it has one."""
    rows = await (
        await conn.execute(
            "select e.id, e.code, (select v.legal_name from gba.legal_entity_versions v "
            "where v.tenant_id = e.tenant_id and v.legal_entity_id = e.id "
            "order by v.revision desc limit 1), b.id, bv.revision, bv.base_currency, "
            "c.minor_units, bv.fiscal_year_start_month, bv.accounting_start, bv.created_at, "
            "exists (select 1 from gba.journal_entries j "
            "where j.tenant_id = e.tenant_id and j.book_id = b.id) "
            "from gba.legal_entities e left join gba.ledger_books b "
            "on b.tenant_id = e.tenant_id and b.legal_entity_id = e.id "
            "left join lateral (select * from gba.ledger_book_versions v "
            "where v.tenant_id = b.tenant_id and v.book_id = b.id "
            "order by v.revision desc limit 1) bv on true "
            "left join gba.currencies c on c.code = bv.base_currency "
            "where e.tenant_id = %s and (%s::text is null or e.code > %s) "
            "and (%s::uuid is null or b.id=%s) "
            "order by e.code limit %s",
            (business_id, after, after, book_id, book_id, limit + 1),
        )
    ).fetchall()
    items = []
    for row in rows[:limit]:
        book = _book(business_id, row[3], (row[0], *row[4:])) if row[3] is not None else None
        items.append(
            LedgerEntity(legal_entity_id=row[0], code=row[1], legal_name=row[2], book=book)
        )
    return LedgerOverview(
        business_id=business_id,
        items=tuple(items),
        next_cursor=items[-1].code if len(rows) > limit else None,
        currencies=await currencies(conn),
    )


async def save_book(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: BookInput,
) -> LedgerBookView:
    """Create the book of a legal entity, with the starter chart unless asked otherwise,
    or record new settings."""
    scope = IdempotencyScope(business_id, actor, _BOOK, key)
    request_hash = commands.fingerprint({"book_id": str(book_id), **body.model_dump(mode="json")})
    receipt = await _claim(conn, scope, request_hash, BookReceipt)
    if receipt is not None:
        return await _book_version(conn, business_id, receipt.book_id, receipt.revision)

    await require_module(conn, business_id, FINANCE_MODULE)
    current = await load_book(conn, business_id, book_id)
    revision = _expect(current.revision if current else 0, body.expected_revision, "book")
    chart = None
    if current is None:
        chart = body.chart or "starter"
        known = await (
            await conn.execute(
                "select exists (select 1 from gba.legal_entities "
                "where tenant_id = %s and id = %s), "
                "exists (select 1 from gba.ledger_books where tenant_id = %s "
                "and legal_entity_id = %s)",
                (business_id, body.legal_entity_id, business_id, body.legal_entity_id),
            )
        ).fetchone()
        if known is None or not known[0]:
            raise InvalidReferenceError("Unknown legal entity", field="legal_entity_id")
        if known[1]:
            raise ConflictError("This legal entity already has a book")
    else:
        if body.legal_entity_id != current.legal_entity_id:
            raise InvalidReferenceError("A book keeps its legal entity", field="legal_entity_id")
        if body.chart is not None:
            raise LedgerInputError("A chart template applies only when a book is created")
        if current.has_entries and (body.base_currency, body.accounting_start) != (
            current.base_currency,
            current.accounting_start,
        ):
            raise LedgerStateError(
                "The base currency and accounting start are fixed once the book has entries"
            )
    await _scale(conn, body.base_currency, "base_currency")
    starter = STARTER_CHART if chart == "starter" else ()
    async with _writes(conn):
        if current is None:
            await conn.execute(
                "insert into gba.ledger_books (tenant_id, id, legal_entity_id, created_by) "
                "values (%s, %s, %s, %s)",
                (business_id, book_id, body.legal_entity_id, user_id),
            )
        await conn.execute(
            "insert into gba.ledger_book_versions (tenant_id, book_id, revision, base_currency, "
            "fiscal_year_start_month, accounting_start, created_by) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            (
                business_id,
                book_id,
                revision,
                body.base_currency,
                body.fiscal_year_start_month,
                body.accounting_start,
                user_id,
            ),
        )
        if starter:
            ids = [uuid7() for _ in starter]
            await conn.execute(
                "insert into gba.ledger_accounts (tenant_id, id, book_id, code, type, created_by) "
                "select %s, a.id, %s, a.code, a.type, %s "
                "from unnest(%s::uuid[], %s::text[], %s::text[]) as a(id, code, type)",
                (
                    business_id,
                    book_id,
                    user_id,
                    ids,
                    [code for code, _, _ in starter],
                    [kind for _, kind, _ in starter],
                ),
            )
            await conn.execute(
                "insert into gba.ledger_account_versions "
                "(tenant_id, account_id, revision, name, archived, created_by) "
                "select %s, a.id, 1, a.name, false, %s "
                "from unnest(%s::uuid[], %s::text[]) as a(id, name)",
                (business_id, user_id, ids, [name for _, _, name in starter]),
            )
    await _audit(
        conn,
        business_id,
        actor,
        "ledger.book_saved",
        ("ledger_book", str(book_id)),
        {
            "revision": revision,
            "legal_entity_id": str(body.legal_entity_id),
            "base_currency": body.base_currency,
            "fiscal_year_start_month": body.fiscal_year_start_month,
            "accounting_start": body.accounting_start.isoformat(),
            "starter_accounts": len(starter),
        },
    )
    await commands.complete(conn, scope, BookReceipt(book_id=book_id, revision=revision))
    return await _book_version(conn, business_id, book_id, revision)


# --- Accounts ----------------------------------------------------------------------

_ACCOUNT_COLUMNS = (
    "a.id, a.code, a.type, v.name, v.archived, v.revision, v.created_at, "
    "exists (select 1 from gba.journal_lines l "
    "where l.tenant_id = a.tenant_id and l.account_id = a.id), a.book_id"
)
_LATEST_ACCOUNT_VERSION = (
    "join lateral (select x.name, x.archived, x.revision, x.created_at "
    "from gba.ledger_account_versions x where x.tenant_id = a.tenant_id "
    "and x.account_id = a.id order by x.revision desc limit 1) v on true"
)


def _account(row: tuple[Any, ...]) -> LedgerAccount:
    return LedgerAccount(
        account_id=row[0],
        code=row[1],
        type=row[2],
        name=row[3],
        archived=row[4],
        revision=row[5],
        updated_at=row[6],
        has_lines=row[7],
    )


async def _account_row(
    conn: RuntimeConnection, business_id: UUID, account_id: UUID
) -> tuple[Any, ...] | None:
    row = await (
        await conn.execute(
            f"select {_ACCOUNT_COLUMNS} from gba.ledger_accounts a "  # noqa: S608 - fixed
            f"{_LATEST_ACCOUNT_VERSION} where a.tenant_id = %s and a.id = %s",
            (business_id, account_id),
        )
    ).fetchone()
    return tuple(row) if row is not None else None


async def load_account(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, account_id: UUID
) -> LedgerAccountView | None:
    row = await _account_row(conn, business_id, account_id)
    if row is None or row[8] != book_id:
        return None
    return LedgerAccountView(business_id=business_id, book_id=book_id, **_account(row).model_dump())


async def list_accounts(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, *, after: str | None, limit: int
) -> LedgerAccountList:
    await require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            f"select {_ACCOUNT_COLUMNS} from gba.ledger_accounts a "  # noqa: S608 - fixed
            f"{_LATEST_ACCOUNT_VERSION} where a.tenant_id = %s and a.book_id = %s "
            "and (%s::text is null or a.code > %s) order by a.code limit %s",
            (business_id, book_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_account(tuple(row)) for row in rows[:limit])
    return LedgerAccountList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].code if len(rows) > limit else None,
    )


async def save_account(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    account_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: AccountInput,
) -> LedgerAccountView:
    """Add an account or record a new name or archive state; code and type stay."""
    scope = IdempotencyScope(business_id, actor, _ACCOUNT, key)
    request_hash = commands.fingerprint(
        {"book_id": str(book_id), "account_id": str(account_id), **body.model_dump(mode="json")}
    )
    receipt = await _claim(conn, scope, request_hash, AccountReceipt)
    if receipt is not None:
        return await _account_view(conn, business_id, book_id, receipt.account_id)

    await require_module(conn, business_id, FINANCE_MODULE)
    await require_book(conn, business_id, book_id)
    row = await _account_row(conn, business_id, account_id)
    if row is not None and row[8] != book_id:
        raise InvalidReferenceError("This account belongs to another book", field="account_id")
    current = _account(row) if row is not None else None
    revision = _expect(current.revision if current else 0, body.expected_revision, "account")
    if current is not None and (body.code, body.type) != (current.code, current.type):
        raise LedgerInputError(
            "An account keeps its code and type; archive it and add another account"
        )
    async with _writes(conn):
        if current is None:
            await conn.execute(
                "insert into gba.ledger_accounts (tenant_id, id, book_id, code, type, created_by) "
                "values (%s, %s, %s, %s, %s, %s)",
                (business_id, account_id, book_id, body.code, body.type, user_id),
            )
        await conn.execute(
            "insert into gba.ledger_account_versions "
            "(tenant_id, account_id, revision, name, archived, created_by) "
            "values (%s, %s, %s, %s, %s, %s)",
            (business_id, account_id, revision, body.name, body.archived, user_id),
        )
    await _audit(
        conn,
        business_id,
        actor,
        "ledger.account_saved",
        ("ledger_account", str(account_id)),
        {
            "book_id": str(book_id),
            "revision": revision,
            "type": body.type,
            "archived": body.archived,
        },
    )
    await commands.complete(
        conn, scope, AccountReceipt(book_id=book_id, account_id=account_id, revision=revision)
    )
    return await _account_view(conn, business_id, book_id, account_id)


async def _account_view(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, account_id: UUID
) -> LedgerAccountView:
    # Accounts answer with their latest version, also on a replay.
    account = await load_account(conn, business_id, book_id, account_id)
    if account is None:
        raise RuntimeError("A stored account is missing")
    return account


# --- Journal entries ---------------------------------------------------------------

_ENTRY_COLUMNS = (
    "e.id, e.entry_date, e.period, e.currency, c.minor_units, e.source_kind, e.source_id, "
    "e.memo, (select coalesce(sum(l.amount_minor), 0) from gba.journal_lines l "
    "where l.tenant_id = e.tenant_id and l.entry_id = e.id and l.side = 'debit'), "
    "e.reverses_entry_id, (select r.id from gba.journal_entries r "
    "where r.tenant_id = e.tenant_id and r.reverses_entry_id = e.id), e.created_at"
)


@overload
def _entry_summary(
    row: tuple[Any, ...], *, view_version: Literal[1] = 1
) -> JournalEntrySummary: ...
@overload
def _entry_summary(row: tuple[Any, ...], *, view_version: Literal[2]) -> JournalEntrySummaryV2: ...
def _entry_summary(
    row: tuple[Any, ...], *, view_version: Literal[1, 2] = 1
) -> JournalEntrySummary | JournalEntrySummaryV2:
    if view_version == 1 and row[5] not in ("manual", "opening", "reversal"):
        raise JournalUpgradeRequiredError(
            "This journal needs view schema version 2", required_version=2
        )
    model = JournalEntrySummaryV2 if view_version == 2 else JournalEntrySummary
    return model(
        entry_id=row[0],
        entry_date=row[1],
        period=month_text(row[2]),
        currency=row[3],
        source_kind=row[5],
        source_id=row[6],
        memo=row[7],
        total=from_minor(int(row[8]), row[4]),
        reverses_entry_id=row[9],
        reversed_by_entry_id=row[10],
        created_at=row[11],
    )


@overload
async def load_entry(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    *,
    view_version: Literal[1] = 1,
) -> JournalEntryView | None: ...
@overload
async def load_entry(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    *,
    view_version: Literal[2],
) -> JournalEntryViewV2 | None: ...
async def load_entry(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    *,
    view_version: Literal[1, 2] = 1,
) -> JournalEntryView | JournalEntryViewV2 | None:
    row = await (
        await conn.execute(
            f"select {_ENTRY_COLUMNS} from gba.journal_entries e "  # noqa: S608 - fixed
            "join gba.currencies c on c.code = e.currency "
            "where e.tenant_id = %s and e.book_id = %s and e.id = %s",
            (business_id, book_id, entry_id),
        )
    ).fetchone()
    if row is None:
        return None
    scale = row[4]
    lines = await (
        await conn.execute(
            "select l.line_no, l.account_id, a.code, v.name, l.side, l.amount_minor "  # noqa: S608 - fixed
            "from gba.journal_lines l join gba.ledger_accounts a "
            f"on a.tenant_id = l.tenant_id and a.id = l.account_id {_LATEST_ACCOUNT_VERSION} "
            "where l.tenant_id = %s and l.entry_id = %s order by l.line_no",
            (business_id, entry_id),
        )
    ).fetchall()
    model = JournalEntryViewV2 if view_version == 2 else JournalEntryView
    return model(
        business_id=business_id,
        book_id=book_id,
        minor_units=scale,
        lines=tuple(
            JournalLine(
                line_no=r[0],
                account_id=r[1],
                account_code=r[2],
                account_name=r[3],
                side=r[4],
                amount=from_minor(r[5], scale),
            )
            for r in lines
        ),
        **(
            _entry_summary(tuple(row), view_version=2)
            if view_version == 2
            else _entry_summary(tuple(row))
        ).model_dump(),
    )


async def _entry(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, entry_id: UUID
) -> JournalEntryView:
    entry = await load_entry(conn, business_id, book_id, entry_id)
    if entry is None:
        raise RuntimeError("A stored journal entry is missing")
    return entry


@overload
async def list_entries(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    period: date | None,
    after: UUID | None,
    limit: int,
    view_version: Literal[1] = 1,
) -> JournalEntryList: ...
@overload
async def list_entries(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    period: date | None,
    after: UUID | None,
    limit: int,
    view_version: Literal[2],
) -> JournalEntryListV2: ...
async def list_entries(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    period: date | None,
    after: UUID | None,
    limit: int,
    view_version: Literal[1, 2] = 1,
) -> JournalEntryList | JournalEntryListV2:
    """Newest entry date first; a reversal is listed on its own date."""
    await require_book(conn, business_id, book_id)
    if view_version == 1:
        owned = await (
            await conn.execute(
                "select 1 from gba.journal_entries where tenant_id=%s and book_id=%s "
                "and source_kind not in ('manual','opening','reversal') limit 1",
                (business_id, book_id),
            )
        ).fetchone()
        if owned:
            raise JournalUpgradeRequiredError(
                "This book needs journal view schema version 2", required_version=2
            )
    rows = await (
        await conn.execute(
            f"select {_ENTRY_COLUMNS} from gba.journal_entries e "  # noqa: S608 - fixed
            "join gba.currencies c on c.code = e.currency "
            "where e.tenant_id = %(business)s and e.book_id = %(book)s "
            "and (%(period)s::date is null or e.period = %(period)s) "
            "and (%(after)s::uuid is null or (e.entry_date, e.id) < "
            "(select x.entry_date, x.id from gba.journal_entries x "
            "where x.tenant_id = %(business)s and x.book_id = %(book)s and x.id = %(after)s)) "
            "order by e.entry_date desc, e.id desc limit %(limit)s",
            {
                "business": business_id,
                "book": book_id,
                "period": period,
                "after": after,
                "limit": limit + 1,
            },
        )
    ).fetchall()
    if view_version == 2:
        items_v2 = tuple(_entry_summary(tuple(row), view_version=2) for row in rows[:limit])
        return JournalEntryListV2(
            business_id=business_id,
            book_id=book_id,
            items=items_v2,
            next_cursor=items_v2[-1].entry_id if len(rows) > limit else None,
        )
    items = tuple(_entry_summary(tuple(row)) for row in rows[:limit])
    return JournalEntryList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].entry_id if len(rows) > limit else None,
    )


async def _require_open_month(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, entry_date: date
) -> None:
    row = await (
        await conn.execute(
            "select gba.ledger_period_closed(%s, %s, %s)",
            (business_id, book_id, entry_date.replace(day=1)),
        )
    ).fetchone()
    if row is not None and row[0]:
        text = month_text(entry_date)
        raise PeriodClosedError(f"{text} is closed", period=text)


async def _require_new_entry(conn: RuntimeConnection, business_id: UUID, entry_id: UUID) -> None:
    row = await (
        await conn.execute(
            "select 1 from gba.journal_entries where tenant_id = %s and id = %s",
            (business_id, entry_id),
        )
    ).fetchone()
    if row is not None:
        raise OperationPostedError("This entry was already posted; reverse it to correct it")


async def append_invoice_journal(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    user_id: UUID,
    body: InvoicePosting,
) -> None:
    """Append to G in the caller transaction; H must flush its complete lineage.

    This does not claim a command or write an invoice receipt. SQL rejects an
    arbitrary origin, incomplete lineage and later alterations independently.
    """
    await _lock(conn, business_id)
    await require_module(conn, business_id, FINANCE_MODULE)
    await _append_journal(
        conn,
        business_id=business_id,
        book_id=book_id,
        entry_id=entry_id,
        user_id=user_id,
        body=body,
    )


async def _append_journal(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    user_id: UUID,
    body: EntryInput | InvoicePosting,
) -> None:
    book = await require_book(conn, business_id, book_id)
    await _require_new_entry(conn, business_id, entry_id)
    scale = await _scale(conn, body.currency, "currency")
    amounts: list[int] = []
    for number, line in enumerate(body.lines, start=1):
        try:
            amounts.append(to_minor(line.amount, scale))
        except ValueError as exc:
            raise LedgerAmountError(str(exc), line=number, currency=body.currency) from exc
    sides = [line.side for line in body.lines]
    debit = sum(a for a, side in zip(amounts, sides, strict=True) if side == "debit")
    credit = sum(a for a, side in zip(amounts, sides, strict=True) if side == "credit")
    if debit != credit:
        raise UnbalancedEntryError(
            "Debits and credits must be equal",
            debit=from_minor(debit, scale),
            credit=from_minor(credit, scale),
        )
    account_ids = list({line.account_id for line in body.lines})
    accounts = await (
        await conn.execute(
            f"select a.id, v.archived from gba.ledger_accounts a {_LATEST_ACCOUNT_VERSION} "  # noqa: S608
            "where a.tenant_id = %s and a.book_id = %s and a.id = any(%s::uuid[])",
            (business_id, book_id, account_ids),
        )
    ).fetchall()
    if len(accounts) != len(account_ids):
        raise InvalidReferenceError("Every line needs an account of this book", field="lines")
    if any(archived for _, archived in accounts):
        raise LedgerStateError("An archived account cannot receive new entries")
    if body.entry_date < book.accounting_start:
        raise LedgerDateError("The date is before the book's accounting start")
    await _require_open_month(conn, business_id, book_id, body.entry_date)
    source_id = body.source_id or str(entry_id)
    posted = await (
        await conn.execute(
            "select 1 from gba.journal_entries where tenant_id = %s and book_id = %s "
            "and source_kind = %s and source_id = %s",
            (business_id, book_id, body.source_kind, source_id),
        )
    ).fetchone()
    if posted is not None:
        raise OperationPostedError("This business operation was already posted in this book")
    async with _writes(conn):
        await conn.execute(
            "insert into gba.journal_entries (tenant_id, id, book_id, entry_date, currency, "
            "source_kind, source_id, memo, created_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business_id,
                entry_id,
                book_id,
                body.entry_date,
                body.currency,
                body.source_kind,
                source_id,
                body.memo,
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.journal_lines "
            "(tenant_id, entry_id, line_no, book_id, account_id, side, amount_minor) "
            "select %s, %s, l.n::smallint, %s, l.account, l.side, l.amount "
            "from unnest(%s::uuid[], %s::text[], %s::bigint[]) "
            "with ordinality as l(account, side, amount, n)",
            (
                business_id,
                entry_id,
                book_id,
                [line.account_id for line in body.lines],
                sides,
                amounts,
            ),
        )


async def post_entry(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: EntryInput,
) -> JournalEntryView:
    """Post one balanced entry in one currency to an open month of the book."""
    scope = IdempotencyScope(business_id, actor, _ENTRY, key)
    request_hash = commands.fingerprint(
        {"book_id": str(book_id), "entry_id": str(entry_id), **body.model_dump(mode="json")}
    )
    receipt = await _claim(conn, scope, request_hash, EntryReceipt)
    if receipt is not None:
        return await _entry(conn, business_id, book_id, receipt.entry_id)

    await require_module(conn, business_id, FINANCE_MODULE)
    await _append_journal(
        conn,
        business_id=business_id,
        book_id=book_id,
        entry_id=entry_id,
        user_id=user_id,
        body=body,
    )
    await _audit(
        conn,
        business_id,
        actor,
        "ledger.entry_posted",
        ("journal_entry", str(entry_id)),
        {
            "book_id": str(book_id),
            "entry_date": body.entry_date.isoformat(),
            "currency": body.currency,
            "source_kind": body.source_kind,
            "lines": len(body.lines),
        },
    )
    await commands.complete(conn, scope, EntryReceipt(book_id=book_id, entry_id=entry_id))
    return await _entry(conn, business_id, book_id, entry_id)


async def reverse_entry(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    entry_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: ReversalInput,
) -> JournalEntryView:
    """Post the mirror of an entry once, in an open month from its original date."""
    scope = IdempotencyScope(business_id, actor, _REVERSE, key)
    request_hash = commands.fingerprint(
        {"book_id": str(book_id), "entry_id": str(entry_id), **body.model_dump(mode="json")}
    )
    receipt = await _claim(conn, scope, request_hash, EntryReceipt)
    if receipt is not None:
        return await _entry(conn, business_id, book_id, receipt.entry_id)

    await require_module(conn, business_id, FINANCE_MODULE)
    await require_book(conn, business_id, book_id)
    origin = await (
        await conn.execute(
            "select source_kind from gba.journal_entries "
            "where tenant_id=%s and book_id=%s and id=%s",
            (business_id, book_id, entry_id),
        )
    ).fetchone()
    if origin is not None and origin[0] == "invoice":
        raise LedgerStateError("Correct this entry through its financial document")
    original = await load_entry(conn, business_id, book_id, entry_id)
    if original is None:
        raise NotFoundError("Journal entry not found")
    if original.source_kind == "reversal":
        raise LedgerStateError("A reversal cannot be reversed; post a new entry instead")
    if original.reversed_by_entry_id is not None:
        raise EntryReversedError("This entry was already reversed")
    await _require_new_entry(conn, business_id, body.reversal_entry_id)
    if body.entry_date < original.entry_date:
        raise LedgerDateError("A reversal cannot be dated before its original entry")
    await _require_open_month(conn, business_id, book_id, body.entry_date)
    async with _writes(conn):
        await conn.execute(
            "insert into gba.journal_entries (tenant_id, id, book_id, entry_date, currency, "
            "source_kind, source_id, memo, reverses_entry_id, created_by) "
            "values (%s, %s, %s, %s, %s, 'reversal', %s, %s, %s, %s)",
            (
                business_id,
                body.reversal_entry_id,
                book_id,
                body.entry_date,
                original.currency,
                str(entry_id),
                body.memo,
                entry_id,
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.journal_lines "
            "(tenant_id, entry_id, line_no, book_id, account_id, side, amount_minor) "
            "select l.tenant_id, %s, l.line_no, l.book_id, l.account_id, "
            "case l.side when 'debit' then 'credit' else 'debit' end, l.amount_minor "
            "from gba.journal_lines l where l.tenant_id = %s and l.entry_id = %s",
            (body.reversal_entry_id, business_id, entry_id),
        )
    await _audit(
        conn,
        business_id,
        actor,
        "ledger.entry_reversed",
        ("journal_entry", str(body.reversal_entry_id)),
        {
            "book_id": str(book_id),
            "reverses_entry_id": str(entry_id),
            "entry_date": body.entry_date.isoformat(),
            "lines": len(original.lines),
        },
    )
    await commands.complete(
        conn, scope, EntryReceipt(book_id=book_id, entry_id=body.reversal_entry_id)
    )
    return await _entry(conn, business_id, book_id, body.reversal_entry_id)


# --- Periods -----------------------------------------------------------------------


def _event(row: tuple[Any, ...]) -> PeriodEvent:
    return PeriodEvent(sequence=row[0], action=row[1], reason=row[2], decided_at=row[3])


async def load_period(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, period: date
) -> LedgerPeriodView:
    await require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            "select sequence, action, reason, decided_at from gba.ledger_period_events "
            "where tenant_id = %s and book_id = %s and period = %s order by sequence desc",
            (business_id, book_id, period),
        )
    ).fetchall()
    events = tuple(_event(tuple(row)) for row in rows)
    latest = events[0] if events else None
    return LedgerPeriodView(
        business_id=business_id,
        book_id=book_id,
        period=month_text(period),
        state="closed" if latest is not None and latest.action == "closed" else "open",
        sequence=latest.sequence if latest else 0,
        last_event=latest,
        events=events,
    )


async def list_periods(
    conn: RuntimeConnection, business_id: UUID, book_id: UUID, *, before: date | None, limit: int
) -> LedgerPeriodList:
    await require_book(conn, business_id, book_id)
    rows = await (
        await conn.execute(
            "select distinct on (period) period, sequence, action, reason, decided_at "
            "from gba.ledger_period_events where tenant_id = %s and book_id = %s "
            "and (%s::date is null or period < %s) "
            "order by period desc, sequence desc limit %s",
            (business_id, book_id, before, before, limit + 1),
        )
    ).fetchall()
    items = tuple(
        LedgerPeriod(
            period=month_text(row[0]),
            state="closed" if row[2] == "closed" else "open",
            sequence=row[1],
            last_event=_event(tuple(row[1:])),
        )
        for row in rows[:limit]
    )
    return LedgerPeriodList(
        business_id=business_id,
        book_id=book_id,
        items=items,
        next_cursor=items[-1].period if len(rows) > limit else None,
    )


async def change_period(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    book_id: UUID,
    period: date,
    action: PeriodAction,
    user_id: UUID,
    actor: str,
    key: str,
    body: CloseInput | ReopenInput,
) -> LedgerPeriodView:
    """Close a month or reopen it with a reason; both are recorded events."""
    scope = IdempotencyScope(business_id, actor, _PERIOD[action], key)
    request_hash = commands.fingerprint(
        {"book_id": str(book_id), "period": month_text(period), **body.model_dump(mode="json")}
    )
    receipt = await _claim(conn, scope, request_hash, PeriodReceipt)
    if receipt is not None:
        return await load_period(conn, business_id, book_id, month(receipt.period))

    await require_module(conn, business_id, FINANCE_MODULE)
    book = await require_book(conn, business_id, book_id)
    current = await load_period(conn, business_id, book_id, period)
    if body.expected_sequence != current.sequence:
        raise ConflictError("This month changed. Reload it.", sequence=current.sequence)
    if action == "closed":
        if current.state == "closed":
            raise LedgerStateError("This month is already closed")
        if period < book.accounting_start.replace(day=1):
            raise LedgerDateError("A month before the accounting start has nothing to close")
    elif current.state != "closed":
        raise LedgerStateError("Only a closed month can be reopened")
    sequence = current.sequence + 1
    async with _writes(conn):
        await conn.execute(
            "insert into gba.ledger_period_events "
            "(tenant_id, book_id, period, sequence, action, reason, decided_by) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            (business_id, book_id, period, sequence, action, body.reason, user_id),
        )
    await _audit(
        conn,
        business_id,
        actor,
        f"ledger.period_{action}",
        ("ledger_period", f"{book_id}:{month_text(period)}"),
        {"book_id": str(book_id), "period": month_text(period), "sequence": sequence},
    )
    await commands.complete(
        conn, scope, PeriodReceipt(book_id=book_id, period=month_text(period), sequence=sequence)
    )
    return await load_period(conn, business_id, book_id, period)


# --- Trial balance -----------------------------------------------------------------


def _columns(opening: int, debit: int, credit: int) -> tuple[int, ...]:
    closing = opening + debit - credit
    return (max(opening, 0), max(-opening, 0), debit, credit, max(closing, 0), max(-closing, 0))


def _balances(values: tuple[int, ...], scale: int) -> dict[str, str]:
    names = (
        "opening_debit",
        "opening_credit",
        "debit",
        "credit",
        "closing_debit",
        "closing_credit",
    )
    return {name: from_minor(value, scale) for name, value in zip(names, values, strict=True)}


async def trial_balance(
    conn: RuntimeConnection,
    business_id: UUID,
    book_id: UUID,
    *,
    period_from: date,
    period_to: date,
    currency: str | None,
) -> TrialBalance:
    """Opening balance, turnover and closing balance per account, in one currency."""
    book = await require_book(conn, business_id, book_id)
    if period_to < period_from:
        raise LedgerInputError("The report cannot end before it starts")
    code = currency or book.base_currency
    scale = await _scale(conn, code, "currency")
    rows = await (
        await conn.execute(
            "with moves as (select l.account_id, e.period < %(from)s as earlier, l.side, "  # noqa: S608
            "l.amount_minor from gba.journal_lines l join gba.journal_entries e "
            "on e.tenant_id = l.tenant_id and e.id = l.entry_id "
            "where l.tenant_id = %(business)s and l.book_id = %(book)s "
            "and e.currency = %(currency)s and e.period <= %(to)s) "
            "select a.id, a.code, v.name, a.type, v.archived, "
            "coalesce(sum(case m.side when 'debit' then m.amount_minor "
            "else -m.amount_minor end) filter (where m.earlier), 0), "
            "coalesce(sum(m.amount_minor) filter (where not m.earlier and m.side = 'debit'), 0), "
            "coalesce(sum(m.amount_minor) filter (where not m.earlier and m.side = 'credit'), 0) "
            "from moves m join gba.ledger_accounts a "
            "on a.tenant_id = %(business)s and a.id = m.account_id "
            f"{_LATEST_ACCOUNT_VERSION} "
            "group by a.id, a.code, v.name, a.type, v.archived order by a.code",
            {
                "business": business_id,
                "book": book_id,
                "currency": code,
                "from": period_from,
                "to": period_to,
            },
        )
    ).fetchall()
    report: list[TrialBalanceRow] = []
    totals = [0] * 6
    for row in rows:
        opening, debit, credit = int(row[5]), int(row[6]), int(row[7])
        if opening == debit == credit == 0:
            continue
        values = _columns(opening, debit, credit)
        totals = [total + value for total, value in zip(totals, values, strict=True)]
        report.append(
            TrialBalanceRow(
                account_id=row[0],
                code=row[1],
                name=row[2],
                type=row[3],
                archived=row[4],
                **_balances(values, scale),
            )
        )
    present = await (
        await conn.execute(
            "select distinct currency from gba.journal_entries "
            "where tenant_id = %s and book_id = %s order by currency",
            (business_id, book_id),
        )
    ).fetchall()
    return TrialBalance(
        business_id=business_id,
        book_id=book_id,
        currency=code,
        minor_units=scale,
        period_from=month_text(period_from),
        period_to=month_text(period_to),
        currencies=tuple(r[0] for r in present),
        rows=tuple(report),
        totals=Balances(**_balances(tuple(totals), scale)),
    )
