"""J2 to J4 commands and reads: accounts of materials, receipts, write-offs, transfers,
returns, balances and cost.

A receipt, a write-off or a return is posted whole in the caller's transaction, under the
ledger posting lock: document, lines, movements, balances, cost and one `stock` journal
entry. A receipt carries its amounts; a write-off leaves at the moving-average cost; a
return moves against a line of an earlier receipt or write-off and takes its share of the
amount of that line. A transfer
moves quantities between two places of one owner and no money: it takes no posting lock,
and the rows of the balances it touches order it with every other document. The database
repeats every rule below in its triggers; this module answers sooner and names the
refusal.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid7

import psycopg

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, ledger
from gorgona_booking.business.inventory import InventoryConflictError, require_inventory
from gorgona_booking.business.inventory_contracts import InventoryReceipt
from gorgona_booking.business.ledger_contracts import (
    LineInput,
    Side,
    StockPosting,
    from_minor,
    month_text,
)
from gorgona_booking.business.module_gate import FINANCE_MODULE, INVENTORY_MODULE, module_writes
from gorgona_booking.business.stock_contracts import (
    MAX_AMOUNT,
    MAX_QUANTITY,
    Balance,
    BalanceList,
    Cost,
    CostList,
    DocumentLine,
    DocumentList,
    DocumentMoney,
    DocumentSummary,
    DocumentView,
    PostingRulesInput,
    PostingRulesView,
    ReceiptInput,
    ReturnInput,
    TransferInput,
    WriteOffInput,
    from_count,
    issue_value,
    to_count,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DatabaseUnavailableError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)
from gorgona_booking.tenancy.authorization import PermissionDeniedError


class StockBookRequiredError(ConflictError):
    code = "STOCK_BOOK_REQUIRED"


class StockRulesRequiredError(ConflictError):
    code = "STOCK_RULES_REQUIRED"


class StockArchivedError(ConflictError):
    code = "STOCK_ARCHIVED"


class StockInsufficientError(ConflictError):
    code = "STOCK_INSUFFICIENT"


class StockReturnExceededError(ConflictError):
    code = "STOCK_RETURN_EXCEEDED"


class StockAccountArchivedError(ConflictError):
    code = "STOCK_ACCOUNT_ARCHIVED"


class StockBusyError(ConflictError):
    code = "STOCK_BUSY"


class StockReturnError(DomainError):
    code = "STOCK_RETURN_INVALID"


class StockDateError(DomainError):
    code = "STOCK_DATE_INVALID"


class StockQuantityError(DomainError):
    code = "STOCK_QUANTITY_INVALID"


class StockAmountError(DomainError):
    code = "STOCK_AMOUNT_INVALID"


_FUTURE = "The document date is in the future of the branch"
_EARLY = "The document date is before the book's accounting start"
_SHORT = "The place does not hold this much of the material"
_OVER = "No more than this is left to return of the source line"
# Trigger messages and the errors they become when a check here did not answer first.
_REFUSALS: tuple[tuple[str, type[DomainError], str], ...] = (
    ("archived", StockArchivedError, "An archived material or storage place takes nothing in"),
    ("future of its branch", StockDateError, _FUTURE),
    ("accounting start", StockDateError, _EARLY),
    ("stock document is closed", ledger.PeriodClosedError, "This month is closed"),
    ("current posting rules", InventoryConflictError, "The posting rules have changed"),
)
# Positions in a posting rules row: the revision, then the seven accounts.
_INVENTORY, _CONSUMPTION, _LOSS, _DIFFERENCE = 1, 5, 6, 7
_RECEIPT_ACCOUNT = {"purchase": 2, "opening_balance": 3, "surplus": 4}
type _MoneyDocument = ReceiptInput | WriteOffInput | ReturnInput
type _Document = _MoneyDocument | TransferInput
# The documents whose lines name their material themselves.
type _Listed = ReceiptInput | WriteOffInput | TransferInput


@asynccontextmanager
async def _writes(
    conn: RuntimeConnection, business: UUID, *, money: bool = True
) -> AsyncIterator[None]:
    await require_inventory(conn, business)
    gated = (INVENTORY_MODULE, FINANCE_MODULE) if money else (INVENTORY_MODULE,)
    try:
        async with conn.transaction(), module_writes(*gated):
            if money:
                # Rule 16: a money document takes the posting lock of the company first.
                await conn.execute("select gba.lock_ledger(%s)", (business,))
            yield
            # Surface deferred integrity failures before returning the API result.
            await conn.execute("set constraints all immediate")
            await conn.execute("set constraints all deferred")
    except psycopg.errors.DeadlockDetected as exc:
        # PostgreSQL aborted this document to break a lock cycle; the same command with the
        # same key can simply be repeated.
        raise StockBusyError(
            "Another stock document took the same balances at the same moment; repeat it"
        ) from exc
    except psycopg.errors.SerializationFailure as exc:
        raise DatabaseUnavailableError(
            "Required ledger transaction settings are not ready"
        ) from exc
    except psycopg.errors.UniqueViolation as exc:
        raise InventoryConflictError("This stock record already exists") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("A stock reference is unavailable") from exc
    except psycopg.errors.InsufficientPrivilege as exc:
        raise PermissionDeniedError("This stock change is outside your access") from exc
    except psycopg.DatabaseError as exc:
        if exc.sqlstate == "GBS01":
            raise InventoryConflictError("The posting rules revision has changed") from exc
        if exc.sqlstate == "GBS02":
            raise StockInsufficientError(_SHORT) from exc
        if exc.sqlstate == "GBS03":
            raise StockReturnExceededError(_OVER) from exc
        if exc.sqlstate == "23514":
            message = exc.diag.message_primary or ""
            for text, error, answer in _REFUSALS:
                if text in message:
                    raise error(answer) from exc
            raise InvalidReferenceError("This stock state or reference is invalid") from exc
        raise


def _rules(business: UUID, book: UUID, row: tuple[Any, ...]) -> PostingRulesView:
    return PostingRulesView(
        business_id=business,
        book_id=book,
        revision=row[0],
        inventory_account_id=row[1],
        receipt_account_id=row[2],
        opening_account_id=row[3],
        surplus_account_id=row[4],
        consumption_account_id=row[5],
        loss_account_id=row[6],
        difference_account_id=row[7],
    )


async def _rules_row(
    conn: RuntimeConnection, business: UUID, book: UUID, revision: int | None
) -> tuple[Any, ...] | None:
    row = await (
        await conn.execute(
            "select revision,inventory_account_id,receipt_account_id,opening_account_id,"
            "surplus_account_id,consumption_account_id,loss_account_id,difference_account_id "
            "from gba.stock_posting_rules where tenant_id=%s and book_id=%s "
            "and (%s::integer is null or revision=%s) order by revision desc limit 1",
            (business, book, revision, revision),
        )
    ).fetchone()
    return tuple(row) if row is not None else None


async def load_rules(
    conn: RuntimeConnection, business: UUID, book: UUID, revision: int | None = None
) -> PostingRulesView:
    row = await _rules_row(conn, business, book, revision)
    if row is None:
        raise NotFoundError("Posting rules are not set for this book")
    return _rules(business, book, row)


async def save_rules(
    conn: RuntimeConnection,
    business: UUID,
    book: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: PostingRulesInput,
) -> PostingRulesView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "inventory.posting_rules", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(book), **body.model_dump(mode="json")}),
            InventoryReceipt,
        )
        if receipt is not None:
            return await load_rules(conn, business, book, receipt.revision)
        if await ledger.load_book(conn, business, book) is None:
            raise NotFoundError("Book not found")
        revision = body.expected_revision + 1
        await conn.execute(
            "insert into gba.stock_posting_rules (tenant_id,book_id,revision,"
            "inventory_account_id,receipt_account_id,opening_account_id,surplus_account_id,"
            "consumption_account_id,loss_account_id,difference_account_id,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                book,
                revision,
                body.inventory_account_id,
                body.receipt_account_id,
                body.opening_account_id,
                body.surplus_account_id,
                body.consumption_account_id,
                body.loss_account_id,
                body.difference_account_id,
                user,
            ),
        )
        await commands.audit(
            conn,
            business,
            actor,
            "inventory.posting_rules",
            "ledger_book",
            str(book),
            {"revision": revision},
        )
        await commands.complete(conn, scope, InventoryReceipt(subject_id=book, revision=revision))
        return await load_rules(conn, business, book, revision)


async def _place(
    conn: RuntimeConnection, business: UUID, body: _Document, *, inbound: bool
) -> UUID:
    """The branch of the place of a document; the date is not in the future of that branch.

    An archived place takes nothing in and still lets its balance leave.
    """
    row = await (
        await conn.execute(
            "select p.location_id,v.archived,"
            "%s::date>(pg_catalog.now() at time zone l.timezone)::date "
            "from gba.stock_places p join lateral (select archived "
            "from gba.stock_place_versions where tenant_id=p.tenant_id and place_id=p.id "
            "order by revision desc limit 1) v on true "
            "join gba.locations l on l.tenant_id=p.tenant_id and l.id=p.location_id "
            "where p.tenant_id=%s and p.id=%s",
            (body.document_date, business, body.place_id),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown storage place", field="place_id")
    if row[1] and inbound:
        raise StockArchivedError("An archived storage place takes nothing in", field="place_id")
    if row[2]:
        raise StockDateError(_FUTURE)
    return UUID(str(row[0]))


async def _destination(conn: RuntimeConnection, business: UUID, place: UUID) -> UUID:
    """The branch of the place a transfer arrives at; an archived place takes nothing in."""
    row = await (
        await conn.execute(
            "select p.location_id,v.archived from gba.stock_places p "
            "join lateral (select archived from gba.stock_place_versions "
            "where tenant_id=p.tenant_id and place_id=p.id order by revision desc limit 1) v "
            "on true where p.tenant_id=%s and p.id=%s",
            (business, place),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown storage place", field="to_place_id")
    if row[1]:
        raise StockArchivedError("An archived storage place takes no transfer", field="to_place_id")
    return UUID(str(row[0]))


async def _book(conn: RuntimeConnection, business: UUID, body: _MoneyDocument) -> tuple[Any, ...]:
    """The book of the owner: its id, base currency, currency scale and accounting start."""
    row = await (
        await conn.execute(
            "select b.id,v.base_currency,c.minor_units,v.accounting_start "
            "from gba.ledger_books b join lateral (select base_currency,accounting_start "
            "from gba.ledger_book_versions where tenant_id=b.tenant_id and book_id=b.id "
            "order by revision desc limit 1) v on true "
            "join gba.currencies c on c.code=v.base_currency "
            "where b.tenant_id=%s and b.legal_entity_id=%s",
            (business, body.legal_entity_id),
        )
    ).fetchone()
    if row is not None:
        return tuple(row)
    known = await (
        await conn.execute(
            "select 1 from gba.legal_entities where tenant_id=%s and id=%s",
            (business, body.legal_entity_id),
        )
    ).fetchone()
    if known is None:
        raise InvalidReferenceError("Unknown legal entity", field="legal_entity_id")
    raise StockBookRequiredError("The owner of these materials has no book yet")


async def _require_supplier(conn: RuntimeConnection, business: UUID, supplier: UUID) -> None:
    row = await (
        await conn.execute(
            "select 1 from gba.counterparty_versions v where v.tenant_id=%s "
            "and v.counterparty_id=%s and v.state='active' and 'supplier'=any(v.roles) "
            "and v.revision=(select max(x.revision) from gba.counterparty_versions x "
            "where x.tenant_id=v.tenant_id and x.counterparty_id=v.counterparty_id)",
            (business, supplier),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError(
            "A supplier is an active counterparty with the supplier role", field="supplier_id"
        )


async def _quantities(
    conn: RuntimeConnection, business: UUID, body: _Listed
) -> tuple[list[int], dict[UUID, int]]:
    """Whole quantities of the lines and the scale of each material; no rounding.

    An archived material takes no receipt and no transfer and still lets its balance leave.
    """
    rows = await (
        await conn.execute(
            "select s.id,s.quantity_scale,v.archived from gba.stock_items s "
            "join lateral (select archived from gba.stock_item_versions "
            "where tenant_id=s.tenant_id and item_id=s.id order by revision desc limit 1) v "
            "on true where s.tenant_id=%s and s.id=any(%s::uuid[])",
            (business, list({line.item_id for line in body.lines})),
        )
    ).fetchall()
    items = {row[0]: (int(row[1]), bool(row[2])) for row in rows}
    quantities: list[int] = []
    for number, line in enumerate(body.lines, start=1):
        item = items.get(line.item_id)
        if item is None:
            raise InvalidReferenceError("Unknown material", field="lines", line=number)
        if item[1] and body.kind != "write_off":
            raise StockArchivedError(
                "An archived material takes no receipt and no transfer", line=number
            )
        try:
            quantities.append(to_count(line.quantity, item[0], MAX_QUANTITY))
        except ValueError as exc:
            raise StockQuantityError(str(exc), line=number, quantity_scale=item[0]) from exc
    return quantities, {item: scale for item, (scale, _) in items.items()}


def _amounts(body: ReceiptInput, currency: str, scale: int) -> list[int]:
    """Whole amounts of the lines of a receipt; extra decimals are refused."""
    amounts: list[int] = []
    for number, line in enumerate(body.lines, start=1):
        try:
            amounts.append(to_count(line.amount, scale, MAX_AMOUNT, zero=True))
        except ValueError as exc:
            raise StockAmountError(str(exc), line=number, currency=currency) from exc
    return amounts


async def _held(
    conn: RuntimeConnection,
    business: UUID,
    owner: UUID,
    place: UUID,
    items: list[UUID],
    arrival: UUID | None = None,
) -> dict[UUID, int]:
    """What the place holds of these materials for their owner, under their row locks.

    Rule 16: balance rows are locked in the order material, place, owner. A transfer
    also locks the rows of the place it arrives at, in that same order.
    """
    rows = await (
        await conn.execute(
            "select item_id,place_id,quantity from gba.stock_balances where tenant_id=%s "
            "and legal_entity_id=%s and place_id=any(%s::uuid[]) and item_id=any(%s::uuid[]) "
            "order by item_id,place_id for update",
            (business, owner, [place] if arrival is None else [place, arrival], sorted(set(items))),
        )
    ).fetchall()
    return {row[0]: int(row[2]) for row in rows if row[1] == place}


async def _issued(
    conn: RuntimeConnection,
    business: UUID,
    body: WriteOffInput | ReturnInput,
    items: list[UUID],
    quantities: list[int],
    scales: dict[UUID, int],
    currency: str,
) -> list[int]:
    """What each outbound line takes of the moving-average value; never more than the
    place holds.

    The lines are valued in their order, each on what the lines before it left.
    """
    held = await _held(conn, business, body.legal_entity_id, body.place_id, items)
    costs = {
        row[0]: (int(row[1]), int(row[2]))
        for row in await (
            await conn.execute(
                "select item_id,quantity,value_minor from gba.stock_costs where tenant_id=%s "
                "and legal_entity_id=%s and item_id=any(%s::uuid[])",
                (business, body.legal_entity_id, sorted(set(items))),
            )
        ).fetchall()
    }
    amounts: list[int] = []
    for number, (item, quantity) in enumerate(zip(items, quantities, strict=True), start=1):
        available = held.get(item, 0)
        if quantity > available:
            raise StockInsufficientError(
                _SHORT, line=number, available=from_count(available, scales[item])
            )
        total, value = costs[item]
        amount = issue_value(value, total, quantity)
        if amount > MAX_AMOUNT:
            raise StockAmountError(
                "The value of this line is outside the supported range",
                line=number,
                currency=currency,
            )
        held[item] = available - quantity
        costs[item] = (total - quantity, value - amount)
        amounts.append(amount)
    return amounts


async def _source(
    conn: RuntimeConnection, business: UUID, body: ReturnInput
) -> tuple[str, str, UUID, int]:
    """The receipt or write-off that a return returns: kind, reason, book, rule revision."""
    row = await (
        await conn.execute(
            "select d.kind,d.reason,d.legal_entity_id,p.book_id,p.rule_revision "
            "from gba.stock_documents d left join gba.stock_document_postings p "
            "on p.tenant_id=d.tenant_id and p.document_id=d.id where d.tenant_id=%s and d.id=%s",
            (business, body.source_document_id),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown source document", field="source_document_id")
    if row[0] not in ("receipt", "write_off") or row[2] != body.legal_entity_id:
        raise StockReturnError(
            "A return names a receipt or a write-off of the same owner",
            field="source_document_id",
        )
    if body.reason not in ("entry_error", "supplier_return" if row[0] == "receipt" else "unused"):
        raise StockReturnError(
            "This reason does not belong to a return of this document", field="reason"
        )
    return str(row[0]), str(row[1]), UUID(str(row[3])), int(row[4])


async def _returned(
    conn: RuntimeConnection, business: UUID, body: ReturnInput, *, inbound: bool
) -> tuple[list[UUID], list[int], dict[UUID, int], list[int]]:
    """The materials and whole quantities of the lines of a return, the scale of each
    material and the share each line takes of the amount of its source line.

    Rule 16: after the posting lock the source lines are locked in their order, before
    any balance row. All returns of a line stay within its quantity. A share is what is
    left of the amount of the line, by the quantity returned of the quantity left, so the
    return that completes a line takes all that is left.
    """
    wanted = sorted(line.source_line_no for line in body.lines)
    rows = await (
        await conn.execute(
            "select l.line_no,l.item_id,l.quantity,v.amount_minor,s.quantity_scale,a.archived "
            "from gba.stock_document_lines l join gba.stock_valuations v "
            "on v.tenant_id=l.tenant_id and v.document_id=l.document_id and v.line_no=l.line_no "
            "join gba.stock_items s on s.tenant_id=l.tenant_id and s.id=l.item_id "
            "join lateral (select archived from gba.stock_item_versions "
            "where tenant_id=s.tenant_id and item_id=s.id order by revision desc limit 1) a "
            "on true where l.tenant_id=%s and l.document_id=%s "
            "and l.line_no=any(%s::smallint[]) order by l.line_no for update of l",
            (business, body.source_document_id, wanted),
        )
    ).fetchall()
    sources = {int(row[0]): row for row in rows}
    earlier = await (
        await conn.execute(
            "select r.source_line_no,sum(r.quantity),sum(v.basis_minor) "
            "from gba.stock_document_lines r join gba.stock_valuations v "
            "on v.tenant_id=r.tenant_id and v.document_id=r.document_id and v.line_no=r.line_no "
            "where r.tenant_id=%s and r.source_document_id=%s "
            "and r.source_line_no=any(%s::smallint[]) group by r.source_line_no",
            (business, body.source_document_id, wanted),
        )
    ).fetchall()
    back = {int(row[0]): (int(row[1]), int(row[2])) for row in earlier}
    items: list[UUID] = []
    quantities: list[int] = []
    shares: list[int] = []
    scales: dict[UUID, int] = {}
    for number, line in enumerate(body.lines, start=1):
        row = sources.get(line.source_line_no)
        if row is None:
            raise StockReturnError("The source document has no such line", line=number)
        item, scale = row[1], int(row[4])
        if row[5] and inbound:
            raise StockArchivedError("An archived material takes nothing in", line=number)
        try:
            quantity = to_count(line.quantity, scale, MAX_QUANTITY)
        except ValueError as exc:
            raise StockQuantityError(str(exc), line=number, quantity_scale=scale) from exc
        gone, taken = back.get(line.source_line_no, (0, 0))
        left = int(row[2]) - gone
        if quantity > left:
            raise StockReturnExceededError(_OVER, line=number, available=from_count(left, scale))
        items.append(item)
        quantities.append(quantity)
        scales[item] = scale
        shares.append(issue_value(int(row[3]) - taken, left, quantity))
    return items, quantities, scales, shares


def _entry(nets: list[tuple[UUID, int]]) -> list[tuple[UUID, Side, int]]:
    """The journal lines of a document from what it debits (above zero) and credits to
    each account: one line per account, debits first, and none when all are zero.
    """
    sums: dict[UUID, int] = {}
    for account, net in nets:
        sums[account] = sums.get(account, 0) + net
    lines: list[tuple[UUID, Side, int]] = []
    lines.extend((account, "debit", net) for account, net in sums.items() if net > 0)
    lines.extend((account, "credit", -net) for account, net in sums.items() if net < 0)
    return lines


async def _accounts_open(
    conn: RuntimeConnection, business: UUID, book: UUID, accounts: list[UUID]
) -> None:
    """Every account of the entry is open. The ledger would refuse an archived one too,
    only later and without naming it; nothing is written before this check.
    """
    if not accounts:
        return
    row = await (
        await conn.execute(
            "select a.id from gba.ledger_accounts a join lateral (select archived "
            "from gba.ledger_account_versions where tenant_id=a.tenant_id and account_id=a.id "
            "order by revision desc limit 1) v on true where a.tenant_id=%s and a.book_id=%s "
            "and a.id=any(%s::uuid[]) and v.archived order by a.id limit 1",
            (business, book, accounts),
        )
    ).fetchone()
    if row is not None:
        raise StockAccountArchivedError(
            "An account of this journal entry is archived", account_id=str(row[0])
        )


async def post_document(
    conn: RuntimeConnection,
    business: UUID,
    document: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: _MoneyDocument,
) -> DocumentView:
    """A receipt, a write-off or a return: quantities, cost and one journal entry of the
    owner's book.
    """
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "inventory.document", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(document), **body.model_dump(mode="json")}),
            InventoryReceipt,
        )
        if receipt is not None:
            return await load_document(conn, business, receipt.subject_id, money=True)
        posted = await (
            await conn.execute(
                "select 1 from gba.stock_documents where tenant_id=%s and id=%s",
                (business, document),
            )
        ).fetchone()
        if posted is not None:
            raise InventoryConflictError("This document is already posted")
        source = await _source(conn, business, body) if isinstance(body, ReturnInput) else None
        # A receipt and a returned write-off come in; everything else goes out.
        inbound = isinstance(body, ReceiptInput) or (source is not None and source[0] != "receipt")
        location = await _place(conn, business, body, inbound=inbound)
        book, currency, scale, started = await _book(conn, business, body)
        rules = await _rules_row(conn, business, book, None)
        if rules is None:
            raise StockRulesRequiredError("Choose the accounts of materials for this book first")
        if body.document_date < started:
            raise StockDateError(_EARLY)
        closed = await (
            await conn.execute(
                "select gba.ledger_period_closed(%s,%s,%s)",
                (business, book, body.document_date.replace(day=1)),
            )
        ).fetchone()
        if closed is not None and closed[0]:
            period = month_text(body.document_date)
            raise ledger.PeriodClosedError(f"{period} is closed", period=period)
        supplier = None if isinstance(body, WriteOffInput) else body.supplier_id
        if supplier is not None:
            await _require_supplier(conn, business, supplier)
        number = None if isinstance(body, WriteOffInput) else body.supplier_document
        way = "in" if inbound else "out"
        # Only a return line names a source line and carries a share of its amount.
        origins: list[int | None] = [None] * len(body.lines)
        shares: list[int | None] = [None] * len(body.lines)
        nets: list[tuple[UUID, int]]
        if isinstance(body, ReceiptInput):
            # A receipt debits inventory and credits the account of its reason.
            items = [line.item_id for line in body.lines]
            quantities, scales = await _quantities(conn, business, body)
            # Rule 16: an inbound document takes the balance rows that exist before it
            # inserts new ones, in the order material, place, like every other writer.
            await _held(conn, business, body.legal_entity_id, body.place_id, items)
            amounts = _amounts(body, currency, scale)
            total = sum(amounts)
            nets = [(rules[_INVENTORY], total), (rules[_RECEIPT_ACCOUNT[body.reason]], -total)]
        elif isinstance(body, WriteOffInput):
            # A write-off debits consumption or losses and credits inventory.
            items = [line.item_id for line in body.lines]
            quantities, scales = await _quantities(conn, business, body)
            amounts = await _issued(conn, business, body, items, quantities, scales, currency)
            total = sum(amounts)
            spent = rules[_CONSUMPTION if body.reason == "used" else _LOSS]
            nets = [(spent, total), (rules[_INVENTORY], -total)]
        else:
            if source is None:
                raise RuntimeError("A return was not given its source document")
            # The accounts of the source document come from the rules it was posted with.
            before = await _rules_row(conn, business, source[2], source[3])
            if before is None or source[2] != book:
                raise StockReturnError(
                    "A return posts to the book of its source document",
                    field="source_document_id",
                )
            items, quantities, scales, taken = await _returned(
                conn, business, body, inbound=inbound
            )
            origins, shares = [line.source_line_no for line in body.lines], list(taken)
            basis = sum(taken)
            if inbound:
                # A returned write-off enters inventory at its share of the cost, from the
                # account the write-off debited. Like a receipt, it takes the balance rows
                # that exist before it inserts new ones.
                await _held(conn, business, body.legal_entity_id, body.place_id, items)
                amounts, total = taken, basis
                spent = before[_CONSUMPTION if source[1] == "used" else _LOSS]
                nets = [(rules[_INVENTORY], total), (spent, -total)]
            else:
                # A returned receipt leaves inventory at the average cost; the account the
                # receipt credited is debited by the share of its lines, and the difference
                # goes to the account of price differences.
                amounts = await _issued(conn, business, body, items, quantities, scales, currency)
                total = sum(amounts)
                nets = [
                    (before[_RECEIPT_ACCOUNT[source[1]]], basis),
                    (rules[_DIFFERENCE], total - basis),
                    (rules[_INVENTORY], -total),
                ]
        posted_lines = _entry(nets)
        await _accounts_open(conn, business, book, [account for account, _, _ in posted_lines])
        entry = uuid7() if posted_lines else None
        origin = body.source_document_id if isinstance(body, ReturnInput) else None

        await conn.execute(
            "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,"
            "place_id,location_id,document_date,supplier_id,supplier_document,line_count,"
            "created_by,source_document_id) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                document,
                body.kind,
                body.reason,
                body.legal_entity_id,
                body.place_id,
                location,
                body.document_date,
                supplier,
                number,
                len(body.lines),
                user,
                origin,
            ),
        )
        # In the order of the source lines, which the database locks one by one.
        await conn.execute(
            "insert into gba.stock_document_lines "
            "(tenant_id,document_id,line_no,location_id,item_id,quantity,source_document_id,"
            "source_line_no) select %s,%s,l.n::smallint,%s,l.item,l.quantity,"
            "case when l.origin is null then null else %s::uuid end,l.origin::smallint "
            "from unnest(%s::uuid[],%s::bigint[],%s::integer[]) "
            "with ordinality as l(item,quantity,origin,n) order by l.origin,l.n",
            (business, document, location, origin, items, quantities, origins),
        )
        await conn.execute(
            "insert into gba.stock_document_postings "
            "(tenant_id,document_id,book_id,rule_revision,entry_id,total_minor,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s)",
            (business, document, book, rules[0], entry, total, user),
        )
        # In the order of the lines: the database values each outbound line on what the
        # lines before it left, exactly as `_issued` did.
        await conn.execute(
            "insert into gba.stock_valuations (tenant_id,document_id,line_no,direction,"
            "legal_entity_id,item_id,quantity,amount_minor,basis_minor) "
            "select %s,%s,l.n::smallint,%s,%s,l.item,l.quantity,l.amount,l.basis "
            "from unnest(%s::uuid[],%s::bigint[],%s::bigint[],%s::bigint[]) "
            "with ordinality as l(item,quantity,amount,basis,n) order by l.n",
            (business, document, way, body.legal_entity_id, items, quantities, amounts, shares),
        )
        # Rule 16: balance rows are locked in the order material, place, owner.
        await conn.execute(
            "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,"
            "location_id,place_id,item_id,legal_entity_id,quantity) "
            "select %s,%s,l.n::smallint,%s,%s,%s,l.item,%s,l.quantity "
            "from unnest(%s::uuid[],%s::bigint[]) with ordinality as l(item,quantity,n) "
            "order by l.item,l.n",
            (
                business,
                document,
                way,
                location,
                body.place_id,
                body.legal_entity_id,
                items,
                quantities,
            ),
        )
        if entry is not None:
            await ledger.append_financial_journal(
                conn,
                business_id=business,
                book_id=book,
                entry_id=entry,
                user_id=user,
                body=StockPosting(
                    entry_date=body.document_date,
                    currency=currency,
                    source_id=str(document),
                    lines=tuple(
                        LineInput(account_id=account, side=side, amount=from_minor(minor, scale))
                        for account, side, minor in posted_lines
                    ),
                ),
            )
        # Identifiers, the kind and the line count only: no names, amounts or notes.
        await commands.audit(
            conn,
            business,
            actor,
            "inventory.document",
            "stock_document",
            str(document),
            {"kind": body.kind, "lines": len(body.lines)},
        )
        await commands.complete(conn, scope, InventoryReceipt(subject_id=document))
        return await load_document(conn, business, document, money=True)


async def post_transfer(
    conn: RuntimeConnection,
    business: UUID,
    document: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: TransferInput,
) -> DocumentView:
    """A transfer: every line leaves one place and arrives at another of the same owner.

    It asks for no book and no posting rules and does not depend on the periods of a
    book. The branch scope of the caller decides which places exist for it.
    """
    async with _writes(conn, business, money=False):
        scope = IdempotencyScope(business, actor, "inventory.document", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(document), **body.model_dump(mode="json")}),
            InventoryReceipt,
        )
        if receipt is not None:
            return await load_document(conn, business, receipt.subject_id, money=False)
        posted = await (
            await conn.execute(
                "select 1 from gba.stock_documents where tenant_id=%s and id=%s",
                (business, document),
            )
        ).fetchone()
        if posted is not None:
            raise InventoryConflictError("This document is already posted")
        location = await _place(conn, business, body, inbound=False)
        arrival = await _destination(conn, business, body.to_place_id)
        quantities, scales = await _quantities(conn, business, body)
        items = [line.item_id for line in body.lines]
        held = await _held(
            conn, business, body.legal_entity_id, body.place_id, items, body.to_place_id
        )
        for number, (item, quantity) in enumerate(zip(items, quantities, strict=True), start=1):
            available = held.get(item, 0)
            if quantity > available:
                raise StockInsufficientError(
                    _SHORT, line=number, available=from_count(available, scales[item])
                )
            held[item] = available - quantity

        await conn.execute(
            "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,"
            "place_id,location_id,to_place_id,to_location_id,document_date,line_count,"
            "created_by) values (%s,%s,'transfer','relocation',%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                document,
                body.legal_entity_id,
                body.place_id,
                location,
                body.to_place_id,
                arrival,
                body.document_date,
                len(body.lines),
                user,
            ),
        )
        await conn.execute(
            "insert into gba.stock_document_lines "
            "(tenant_id,document_id,line_no,location_id,item_id,quantity) "
            "select %s,%s,l.n::smallint,%s,l.item,l.quantity "
            "from unnest(%s::uuid[],%s::bigint[]) with ordinality as l(item,quantity,n)",
            (business, document, location, items, quantities),
        )
        # Rule 16: balance rows are locked in the order material, place, owner. Every
        # line moves out of its place and into the destination.
        await conn.execute(
            "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,"
            "location_id,place_id,item_id,legal_entity_id,quantity) "
            "select %s,%s,l.n::smallint,m.direction,m.location,m.place,l.item,%s,l.quantity "
            "from unnest(%s::uuid[],%s::bigint[]) with ordinality as l(item,quantity,n) "
            "cross join (values ('out',%s::uuid,%s::uuid),('in',%s::uuid,%s::uuid)) "
            "as m(direction,location,place) order by l.item,m.place,l.n",
            (
                business,
                document,
                body.legal_entity_id,
                items,
                quantities,
                location,
                body.place_id,
                arrival,
                body.to_place_id,
            ),
        )
        # Identifiers, the kind and the line count only: no names or notes.
        await commands.audit(
            conn,
            business,
            actor,
            "inventory.document",
            "stock_document",
            str(document),
            {"kind": body.kind, "lines": len(body.lines)},
        )
        await commands.complete(conn, scope, InventoryReceipt(subject_id=document))
        return await load_document(conn, business, document, money=False)


def _line(row: tuple[Any, ...], valued: tuple[int, int | None] | None, scale: int) -> DocumentLine:
    """One line of a document; `valued` is absent for a reader without the amounts."""
    amount, basis = valued if valued is not None else (None, None)
    return DocumentLine(
        line_no=row[0],
        item_id=row[1],
        quantity=from_count(int(row[2]), int(row[3])),
        amount=None if amount is None else from_minor(amount, scale),
        source_line_no=row[4],
        source_amount=None if basis is None else from_minor(basis, scale),
    )


async def load_document(
    conn: RuntimeConnection, business: UUID, document: UUID, *, money: bool
) -> DocumentView:
    """A posted document. Amounts are read only for a company-wide finance reader.

    A transfer has no amounts for any reader.
    """
    head = await (
        await conn.execute(
            "select id,kind,reason,legal_entity_id,place_id,location_id,document_date,"
            "supplier_id,supplier_document,created_at,to_place_id,to_location_id,"
            "source_document_id from gba.stock_documents where tenant_id=%s and id=%s",
            (business, document),
        )
    ).fetchone()
    if head is None:
        raise NotFoundError("Stock document not found")
    rows = await (
        await conn.execute(
            "select l.line_no,l.item_id,l.quantity,s.quantity_scale,l.source_line_no "
            "from gba.stock_document_lines l join gba.stock_items s "
            "on s.tenant_id=l.tenant_id and s.id=l.item_id "
            "where l.tenant_id=%s and l.document_id=%s order by l.line_no",
            (business, document),
        )
    ).fetchall()
    posting = None
    amounts: dict[int, tuple[int, int | None]] = {}
    if money:
        posting = await (
            await conn.execute(
                "select p.book_id,p.rule_revision,p.entry_id,p.total_minor,v.base_currency,"
                "c.minor_units from gba.stock_document_postings p "
                "join lateral (select base_currency from gba.ledger_book_versions "
                "where tenant_id=p.tenant_id and book_id=p.book_id "
                "order by revision desc limit 1) v on true "
                "join gba.currencies c on c.code=v.base_currency "
                "where p.tenant_id=%s and p.document_id=%s",
                (business, document),
            )
        ).fetchone()
        valued = await (
            await conn.execute(
                "select line_no,amount_minor,basis_minor from gba.stock_valuations "
                "where tenant_id=%s and document_id=%s",
                (business, document),
            )
        ).fetchall()
        amounts = {
            int(row[0]): (int(row[1]), None if row[2] is None else int(row[2])) for row in valued
        }
    scale = int(posting[5]) if posting is not None else 0
    return DocumentView(
        business_id=business,
        document_id=head[0],
        kind=head[1],
        reason=head[2],
        legal_entity_id=head[3],
        place_id=head[4],
        location_id=head[5],
        to_place_id=head[10],
        to_location_id=head[11],
        source_document_id=head[12],
        document_date=head[6],
        # The supplier is company-wide data, like the counterparty it names: it is read only
        # together with the amounts.
        supplier_id=head[7] if money else None,
        supplier_document=head[8] if money else None,
        created_at=head[9],
        lines=tuple(_line(row, amounts.get(int(row[0])), scale) for row in rows),
        money=DocumentMoney(
            book_id=posting[0],
            rule_revision=posting[1],
            currency=posting[4],
            total=from_minor(int(posting[3]), scale),
            entry_id=posting[2],
        )
        if posting is not None
        else None,
    )


async def list_documents(
    conn: RuntimeConnection,
    business: UUID,
    place: UUID | None,
    after: UUID | None,
    limit: int,
) -> DocumentList:
    """Posted documents in the caller's branch scope; a place lists what left it, what was
    posted at it and what arrived there.
    """
    rows = await (
        await conn.execute(
            "select id,kind,reason,legal_entity_id,place_id,location_id,document_date,"
            "line_count,created_at,to_place_id,to_location_id,source_document_id "
            "from gba.stock_documents "
            "where tenant_id=%s and (%s::uuid is null or place_id=%s or to_place_id=%s) "
            "and (%s::uuid is null or id>%s) order by id limit %s",
            (business, place, place, place, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        DocumentSummary(
            document_id=row[0],
            kind=row[1],
            reason=row[2],
            legal_entity_id=row[3],
            place_id=row[4],
            location_id=row[5],
            to_place_id=row[9],
            to_location_id=row[10],
            source_document_id=row[11],
            document_date=row[6],
            line_count=row[7],
            created_at=row[8],
        )
        for row in rows[:limit]
    )
    return DocumentList(
        items=items, next_cursor=items[-1].document_id if len(rows) > limit else None
    )


async def list_balances(
    conn: RuntimeConnection,
    business: UUID,
    place: UUID | None,
    item: UUID | None,
    after: tuple[UUID, UUID, UUID] | None,
    limit: int,
) -> BalanceList:
    """Quantities by material, place and owner, in the caller's branch scope."""
    cursor = after or (None, None, None)
    rows = await (
        await conn.execute(
            "select b.item_id,b.place_id,b.location_id,b.legal_entity_id,b.quantity,"
            "s.quantity_scale from gba.stock_balances b join gba.stock_items s "
            "on s.tenant_id=b.tenant_id and s.id=b.item_id where b.tenant_id=%s "
            "and (%s::uuid is null or b.place_id=%s) and (%s::uuid is null or b.item_id=%s) "
            "and (%s::uuid is null or (b.item_id,b.place_id,b.legal_entity_id)>"
            "(%s::uuid,%s::uuid,%s::uuid)) "
            "order by b.item_id,b.place_id,b.legal_entity_id limit %s",
            (business, place, place, item, item, cursor[0], *cursor, limit + 1),
        )
    ).fetchall()
    items = tuple(
        Balance(
            item_id=row[0],
            place_id=row[1],
            location_id=row[2],
            legal_entity_id=row[3],
            quantity=from_count(int(row[4]), int(row[5])),
        )
        for row in rows[:limit]
    )
    last = items[-1] if len(rows) > limit else None
    return BalanceList(
        items=items,
        next_cursor=f"{last.item_id}:{last.place_id}:{last.legal_entity_id}" if last else None,
    )


async def list_costs(
    conn: RuntimeConnection, business: UUID, after: tuple[UUID, UUID] | None, limit: int
) -> CostList:
    """Moving-average cost by owner and material; company-wide finance readers only."""
    cursor = after or (None, None)
    rows = await (
        await conn.execute(
            "select c.legal_entity_id,c.item_id,c.quantity,c.value_minor,s.quantity_scale,"
            "v.base_currency,m.minor_units from gba.stock_costs c join gba.stock_items s "
            "on s.tenant_id=c.tenant_id and s.id=c.item_id "
            "join gba.ledger_books b on b.tenant_id=c.tenant_id "
            "and b.legal_entity_id=c.legal_entity_id "
            "join lateral (select base_currency from gba.ledger_book_versions "
            "where tenant_id=b.tenant_id and book_id=b.id order by revision desc limit 1) v "
            "on true join gba.currencies m on m.code=v.base_currency where c.tenant_id=%s "
            "and (%s::uuid is null or (c.legal_entity_id,c.item_id)>(%s::uuid,%s::uuid)) "
            "order by c.legal_entity_id,c.item_id limit %s",
            (business, cursor[0], *cursor, limit + 1),
        )
    ).fetchall()
    items = tuple(
        Cost(
            legal_entity_id=row[0],
            item_id=row[1],
            quantity=from_count(int(row[2]), int(row[4])),
            value=from_minor(int(row[3]), int(row[6])),
            currency=row[5],
        )
        for row in rows[:limit]
    )
    last = items[-1] if len(rows) > limit else None
    return CostList(
        items=items, next_cursor=f"{last.legal_entity_id}:{last.item_id}" if last else None
    )
