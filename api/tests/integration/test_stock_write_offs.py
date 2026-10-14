"""J3 write-offs at the moving-average cost against real PostgreSQL 18."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, Unpack
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from tests.integration import test_stock as shared
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_inventory import error, material_input, refused_sql
from tests.integration.test_stock import DAY, RULE_CODES, Stock, entity_with_book

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
# Backends waiting for the ledger posting lock of one company, found by the key of that lock.
LEDGER_WAITERS = (
    "select count(distinct l.pid) from pg_catalog.pg_locks l "
    "where l.locktype='advisory' and not l.granted and l.objsubid=1 "
    "and l.database=(select d.oid from pg_catalog.pg_database d "
    "where d.datname=pg_catalog.current_database()) "
    "and ((l.classid::bigint << 32) | l.objid::bigint)=pg_catalog.hashtextextended(%s,0)"
)
CLOSE_SEPTEMBER = (
    "insert into gba.ledger_period_events (tenant_id,book_id,period,sequence,action,decided_by) "
    "values (%s,%s,'2026-09-01',1,'closed',%s)"
)


class Written(TypedDict, total=False):
    """How a write-off written by SQL differs from five units worth 10.00 used today."""

    quantity: int
    amount: int
    reason: str
    debit: str
    journal: int
    way: str
    day: str


def write_off(stock: Stock, lines: list[dict[str, object]], **changes: object) -> dict[str, object]:
    return {
        "kind": "write_off",
        "reason": "used",
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "document_date": DAY,
        "lines": lines,
        **changes,
    }


async def received(
    stock: Stock, item: object, quantity: str, amount: str, **changes: object
) -> None:
    line: dict[str, object] = {"item_id": item, "quantity": quantity, "amount": amount}
    posted = await stock.post(stock.receipt([line], **changes))
    assert posted.status_code == 200, posted.text


async def write_off_sql(
    conn: RuntimeConnection, stock: Stock, item: object, **how: Unpack[Written]
) -> UUID:
    """One write-off line written by SQL alone, in the order the service writes it."""
    tenant, user = stock.tenant, stock.inventory.manager.user_id
    quantity, amount = how.get("quantity", 5), how.get("amount", 1000)
    way, day = how.get("way", "out"), how.get("day", DAY)
    document = uuid7()
    entry = uuid7() if amount else None
    place, home = stock.place["place_id"], stock.place["location_id"]
    await conn.execute(
        "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,"
        "location_id,document_date,line_count,created_by) "
        "values (%s,%s,'write_off',%s,%s,%s,%s,%s,1,%s)",
        (tenant, document, how.get("reason", "used"), stock.entity, place, home, day, user),
    )
    await conn.execute(
        "insert into gba.stock_document_lines (tenant_id,document_id,line_no,location_id,"
        "item_id,quantity) values (%s,%s,1,%s,%s,%s)",
        (tenant, document, home, item, quantity),
    )
    await conn.execute(
        "insert into gba.stock_document_postings (tenant_id,document_id,book_id,"
        "rule_revision,entry_id,total_minor,created_by) values (%s,%s,%s,1,%s,%s,%s)",
        (tenant, document, stock.book, entry, amount, user),
    )
    await conn.execute(
        "insert into gba.stock_valuations (tenant_id,document_id,line_no,direction,"
        "legal_entity_id,item_id,quantity,amount_minor) values (%s,%s,1,%s,%s,%s,%s,%s)",
        (tenant, document, way, stock.entity, item, quantity, amount),
    )
    await conn.execute(
        "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,"
        "location_id,place_id,item_id,legal_entity_id,quantity) "
        "values (%s,%s,1,%s,%s,%s,%s,%s,%s)",
        (tenant, document, way, home, place, item, stock.entity, quantity),
    )
    if entry is not None:
        await conn.execute(
            "insert into gba.journal_entries (tenant_id,id,book_id,entry_date,currency,"
            "source_kind,source_id,created_by) values (%s,%s,%s,%s,'USD','stock',%s,%s)",
            (tenant, entry, stock.book, day, str(document), user),
        )
        debit = how.get("debit", "5000")
        for number, side, code in ((1, "debit", debit), (2, "credit", "1300")):
            await conn.execute(
                "insert into gba.journal_lines (tenant_id,entry_id,line_no,book_id,account_id,"
                "side,amount_minor) values (%s,%s,%s,%s,%s,%s,%s)",
                (
                    tenant,
                    entry,
                    number,
                    stock.book,
                    stock.accounts[code],
                    side,
                    how.get("journal", amount),
                ),
            )
    return document


async def hand_write_off(
    stock: Stock, item: object, pool: RuntimePool | None = None, **how: Unpack[Written]
) -> UUID:
    async with tenant_transaction(pool or stock.pool, stock.tenant) as conn:
        await set_user_context(conn, stock.inventory.manager.user_id)
        return await write_off_sql(conn, stock, item, **how)


async def behind_the_ledger_lock[T](
    stock: Stock,
    database: ProvisionedDatabase,
    followers: list[Callable[[], Coroutine[Any, Any, T]]],
    leading: Callable[[RuntimeConnection], Coroutine[Any, Any, object]] | None = None,
) -> list[T]:
    """Run the followers while one transaction holds the ledger lock of the company.

    The race counts only when every follower is seen in pg_locks waiting for that lock.
    """
    monitor = await psycopg.AsyncConnection.connect(
        database.admin_dsn, dbname=database.name, autocommit=True
    )
    tasks: list[asyncio.Task[T]] = []
    try:
        async with tenant_transaction(stock.pool, stock.tenant) as barrier:
            await set_user_context(barrier, stock.inventory.manager.user_id)
            await barrier.execute("select gba.lock_ledger(%s)", (stock.tenant,))
            if leading is not None:
                await leading(barrier)
            tasks = [asyncio.create_task(follower()) for follower in followers]
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                row = await (
                    await monitor.execute(LEDGER_WAITERS, (f"gba:ledger:{stock.tenant}",))
                ).fetchone()
                if row is not None and row[0] >= len(tasks):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Every follower must be seen in pg_locks waiting for the ledger lock")
            assert all(not task.done() for task in tasks)
        return list(await asyncio.wait_for(asyncio.gather(*tasks), 15))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor.close()


async def test_write_off_leaves_at_the_moving_average_and_posts_one_entry(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    dye = (await stock.inventory.item(code="DYE", unit="ml", quantity_scale=1))["item_id"]
    await received(stock, dye, "10.0", "10.00")
    await received(stock, dye, "5.0", "10.01")
    # 15.0 ml are worth 20.01: 4.0 ml leave at 2001 * 40 / 150 = 533.6, that is 534 minor units.
    document = uuid7()
    used = await stock.post(write_off(stock, [{"item_id": dye, "quantity": "4.0"}]), document)
    assert used.status_code == 200, used.text
    view = used.json()
    entry = view["money"]["entry_id"]
    assert {name: value for name, value in view.items() if name != "created_at"} == {
        "schema_version": 1,
        "business_id": str(stock.tenant),
        "document_id": str(document),
        "kind": "write_off",
        "reason": "used",
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "location_id": stock.place["location_id"],
        "to_place_id": None,
        "to_location_id": None,
        "document_date": DAY,
        "supplier_id": None,
        "supplier_document": None,
        "lines": [{"line_no": 1, "item_id": dye, "quantity": "4.0", "amount": "5.34"}],
        "money": {
            "book_id": str(stock.book),
            "rule_revision": 1,
            "currency": "USD",
            "total": "5.34",
            "entry_id": entry,
        },
    }
    assert (await stock.inventory.get(f"/documents/{document}")).json() == view

    # One journal entry of the document: consumption debited, inventory credited.
    journal = await stock.inventory.client.get(
        f"{stock.ledger}/entries/{entry}",
        params={"schema_version": "2"},
        headers=stock.inventory.headers,
    )
    assert journal.status_code == 200, journal.text
    assert (journal.json()["source_kind"], journal.json()["source_id"]) == ("stock", str(document))
    assert (journal.json()["entry_date"], journal.json()["total"]) == (DAY, "5.34")
    assert [
        (line["account_code"], line["side"], line["amount"]) for line in journal.json()["lines"]
    ] == [("5000", "debit", "5.34"), ("1300", "credit", "5.34")]
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(110, 1467)]
    assert stock.reconciled() == (1467, 1467)

    # Damage, loss, expiry and other reasons debit the loss account: 1467 * 10 / 110 = 133.36.
    damaged = await stock.post(
        write_off(stock, [{"item_id": dye, "quantity": "1.0"}], reason="damaged")
    )
    assert (damaged.status_code, damaged.json()["money"]["total"]) == (200, "1.33"), damaged.text
    # What is left leaves with the whole remaining value: rounding strands nothing.
    rest = await stock.post(
        write_off(stock, [{"item_id": dye, "quantity": "10.0"}], reason="expired")
    )
    assert (rest.status_code, rest.json()["money"]["total"]) == (200, "13.34"), rest.text
    debited = stock.rows(
        "select d.reason,a.code,l.amount_minor from gba.stock_documents d "
        "join gba.stock_document_postings p on p.tenant_id=d.tenant_id and p.document_id=d.id "
        "join gba.journal_lines l on l.tenant_id=p.tenant_id and l.entry_id=p.entry_id "
        "join gba.ledger_accounts a on a.tenant_id=l.tenant_id and a.id=l.account_id "
        "where d.kind='write_off' and l.side='debit' order by d.id"
    )
    assert debited == [("used", "5000", 534), ("damaged", "6900", 133), ("expired", "6900", 1334)]

    # Nothing is held and nothing is worth anything; the books agree.
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(0, 0)]
    assert stock.rows("select quantity from gba.stock_balances") == [(0,)]
    assert stock.reconciled() == (0, 0)
    balances = await stock.inventory.get("/balances")
    assert [(row["item_id"], row["quantity"]) for row in balances.json()["items"]] == [(dye, "0.0")]
    costs = await stock.inventory.get("/costs")
    assert [(row["quantity"], row["value"]) for row in costs.json()["items"]] == [("0.0", "0.00")]
    assert stock.counts() == {
        "stock_documents": 5,
        "stock_document_lines": 5,
        "stock_movements": 5,
        "stock_balances": 1,
        "stock_document_postings": 5,
        "stock_valuations": 5,
        "stock_costs": 1,
        "stock_entries": 5,
    }
    # The audit names the document, its kind and its line count, never names or amounts.
    audit = stock.rows(
        "select action,target_type,details from gba.audit_events where target_id=%s",
        str(document),
    )
    assert audit == [("inventory.document", "stock_document", {"kind": "write_off", "lines": 1})]


async def test_write_off_rounding_follows_the_running_average_and_repeats(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    seen: list[list[str]] = []
    for _ in range(2):
        item = (await stock.inventory.item(quantity_scale=0))["item_id"]
        await received(stock, item, "3", "10.00")
        # Two lines of one material: 1000 / 3 = 333.33 gives 333, then 667 / 2 = 333.5 gives 334.
        one: dict[str, object] = {"item_id": item, "quantity": "1"}
        posted = await stock.post(write_off(stock, [one, one]))
        assert posted.status_code == 200, posted.text
        seen.append(
            [*(line["amount"] for line in posted.json()["lines"]), posted.json()["money"]["total"]]
        )
        left = stock.rows("select quantity,value_minor from gba.stock_costs where item_id=%s", item)
        assert left == [(1, 333)]
    assert seen == [["3.33", "3.34", "6.67"]] * 2
    # A material received for nothing leaves for nothing and posts no journal entry.
    gift = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, gift, "2", "0", reason="surplus")
    free = await stock.post(write_off(stock, [{"item_id": gift, "quantity": "1"}], reason="lost"))
    assert free.status_code == 200, free.text
    assert (free.json()["money"]["total"], free.json()["money"]["entry_id"]) == ("0.00", None)
    assert free.json()["lines"][0]["amount"] == "0.00"
    assert stock.reconciled() == (666, 666)


async def test_write_off_never_takes_more_than_its_owner_holds_in_the_place(stock: Stock) -> None:
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    line: dict[str, object] = {"item_id": item, "quantity": "6"}
    assert error(await stock.post(write_off(stock, [line]))) == (409, "STOCK_RULES_REQUIRED")
    assert (await stock.set_rules()).status_code == 200
    empty = await stock.post(write_off(stock, [line]))
    assert error(empty) == (409, "STOCK_INSUFFICIENT"), empty.text
    assert empty.json()["error"]["details"]["available"] == "0"

    # Five here, five in another place of the branch, three of another legal entity here.
    await received(stock, item, "5", "10.00")
    spare = await stock.inventory.place(stock.inventory.world.a.location_id)
    await received(stock, item, "5", "10.00", place_id=spare["place_id"])
    other, other_book, accounts = await entity_with_book(stock.inventory, stock.pool, "OTHER")
    chosen = await stock.inventory.put(
        f"/posting-rules/{other_book}",
        {
            "expected_revision": 0,
            **{f"{name}_account_id": str(accounts[code]) for name, code in RULE_CODES.items()},
        },
    )
    assert chosen.status_code == 200, chosen.text
    await received(stock, item, "3", "9.00", legal_entity_id=str(other))
    baseline = stock.counts()
    three: dict[str, object] = {"item_id": item, "quantity": "3"}
    four: dict[str, object] = {"item_id": item, "quantity": "4"}
    for body, number, available in (
        # Neither the other place nor the other owner covers a write-off here.
        (write_off(stock, [line]), 1, "5"),
        # Lines of one material add up.
        (write_off(stock, [three, three]), 2, "2"),
        (write_off(stock, [four], legal_entity_id=str(other)), 1, "3"),
    ):
        refused = await stock.post(body)
        assert error(refused) == (409, "STOCK_INSUFFICIENT"), refused.text
        details = refused.json()["error"]["details"]
        assert (details["line"], details["available"]) == (number, available)

    # A write-off has a quantity and nothing else: no amount, no supplier, its own reasons.
    for body in (
        write_off(stock, [{**three, "amount": "1.00"}]),
        write_off(stock, [three], reason="purchase"),
        write_off(stock, [three], supplier_document="INV-1"),
        write_off(stock, []),
        write_off(stock, [three] * 101),
        write_off(stock, [three], kind="return"),
        {name: value for name, value in write_off(stock, [three]).items() if name != "kind"},
    ):
        assert error(await stock.post(body)) == (422, "INVALID_REQUEST")
    for quantity in ("0", "1.5"):
        odd = await stock.post(write_off(stock, [{"item_id": item, "quantity": quantity}]))
        assert error(odd) == (422, "STOCK_QUANTITY_INVALID"), odd.text
        assert odd.json()["error"]["details"]["line"] == 1
    unknown = await stock.post(write_off(stock, [{"item_id": str(uuid7()), "quantity": "1"}]))
    assert error(unknown) == (422, "INVALID_REFERENCE"), unknown.text
    nowhere = await stock.post(write_off(stock, [three], place_id=str(uuid7())))
    assert error(nowhere) == (422, "INVALID_REFERENCE"), nowhere.text
    # The date rules of a receipt hold for a write-off.
    future = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    for day in (future, "2025-12-31"):
        dated = await stock.post(write_off(stock, [three], document_date=day))
        assert error(dated) == (422, "STOCK_DATE_INVALID"), dated.text
    closed = await stock.inventory.client.post(
        f"{stock.ledger}/periods/2026-09/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=stock.keyed(),
    )
    assert closed.status_code == 200, closed.text
    late = await stock.post(write_off(stock, [three], document_date="2026-09-15"))
    assert error(late) == (409, "LEDGER_PERIOD_CLOSED"), late.text
    assert stock.counts() == baseline

    # Exactly what the place holds leaves; the other place and the other owner keep theirs.
    whole = await stock.post(write_off(stock, [{"item_id": item, "quantity": "5"}]))
    assert (whole.status_code, whole.json()["money"]["total"]) == (200, "10.00"), whole.text
    held = stock.rows(
        "select legal_entity_id,place_id,quantity from gba.stock_balances order by quantity"
    )
    assert [(str(owner), str(place), quantity) for owner, place, quantity in held] == [
        (str(stock.entity), stock.place["place_id"], 0),
        (str(other), stock.place["place_id"], 3),
        (str(stock.entity), spare["place_id"], 5),
    ]
    costs = stock.rows("select legal_entity_id,quantity,value_minor from gba.stock_costs")
    assert {(str(owner), quantity, value) for owner, quantity, value in costs} == {
        (str(stock.entity), 5, 1000),
        (str(other), 3, 900),
    }
    assert stock.reconciled() == (1000, 1000)


async def test_archived_material_and_place_take_no_receipt_and_still_write_off(
    stock: Stock,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    place = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = await stock.inventory.item(quantity_scale=0)
    there = {"place_id": place["place_id"]}
    await received(stock, item["item_id"], "5", "10.00", **there)
    retired = await stock.inventory.put(
        f"/items/{item['item_id']}", {**material_input(item), "archived": True}
    )
    assert retired.status_code == 200, retired.text
    shut = await stock.inventory.put(
        f"/places/{place['place_id']}",
        {
            "expected_revision": 1,
            "location_id": place["location_id"],
            "code": place["code"],
            "name": place["name"],
            "archived": True,
        },
    )
    assert shut.status_code == 200, shut.text
    two: dict[str, object] = {"item_id": item["item_id"], "quantity": "2"}
    more = await stock.post(stock.receipt([{**two, "amount": "4.00"}], **there))
    assert error(more) == (409, "STOCK_ARCHIVED"), more.text
    # Outbound movements stay allowed, so the balance can be brought to zero.
    first = await stock.post(write_off(stock, [two], reason="expired", **there))
    assert (first.status_code, first.json()["money"]["total"]) == (200, "4.00"), first.text
    rest = await stock.post(
        write_off(stock, [{"item_id": item["item_id"], "quantity": "3"}], reason="other", **there)
    )
    assert (rest.status_code, rest.json()["money"]["total"]) == (200, "6.00"), rest.text
    assert stock.rows("select quantity from gba.stock_balances") == [(0,)]
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(0, 0)]
    assert stock.reconciled() == (0, 0)


async def test_write_off_is_idempotent_and_posted_by_company_wide_finance_only(
    stock: Stock,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    body = write_off(stock, [{"item_id": item, "quantity": "2"}])
    document, key = uuid7(), str(uuid7())
    first = await stock.post(body, document, key)
    assert (first.status_code, first.json()["money"]["total"]) == (200, "4.00"), first.text
    counts = stock.counts()
    assert (await stock.post(body, document, key)).json() == first.json()
    other = await stock.post({**body, "reason": "lost"}, document, key)
    assert error(other) == (422, "IDEMPOTENCY_KEY_REUSED"), other.text
    # A posted document is never posted again, even with a new key.
    again = await stock.post(body, document)
    assert error(again) == (409, "INVENTORY_CONFLICT"), again.text

    # A branch manager posts no write-off and reads the one of the branch without money.
    home = stock.inventory.world.a.location_id
    local, branch = stock.inventory.member("manager", home)
    denied = await stock.post(body, headers=branch)
    assert error(denied) == (403, "PERMISSION_DENIED"), denied.text
    seen = await stock.inventory.get(f"/documents/{document}", headers=branch)
    assert (seen.status_code, seen.json()["money"]) == (200, None), seen.text
    assert seen.json()["lines"] == [
        {"line_no": 1, "item_id": item, "quantity": "2", "amount": None}
    ]
    head = (
        "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,"
        "location_id,document_date,line_count,created_by) "
        "values (%s,%s,'write_off','used',%s,%s,%s,%s,1,%s)"
    )
    values = (stock.tenant, uuid7(), stock.entity, stock.place["place_id"], home, DAY)
    for scope in (home, None):
        assert (
            await refused_sql(
                stock.pool, stock.tenant, local.user_id, head, (*values, local.user_id), scope
            )
            == "42501"
        )
    for headers in (
        stock.inventory.member("artist", home)[1],
        stock.inventory.member("front_desk")[1],
    ):
        assert (await stock.post(body, headers=headers)).status_code == 403
    assert stock.counts() == counts
    assert stock.rows("select quantity from gba.stock_balances") == [(3,)]
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(3, 600)]

    # With the module switched off the document is still read and nothing is written off.
    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager, stock.tenant, 1, ["booking_resources", "finance"]
    )
    assert (await stock.inventory.get(f"/documents/{document}")).json() == first.json()
    assert error(await stock.post(body)) == (409, "MODULE_DISABLED")
    with pytest.raises(psycopg.DatabaseError) as gated:
        await hand_write_off(stock, item, quantity=1, amount=200)
    assert gated.value.sqlstate == "GBM01"
    assert stock.counts() == counts


async def test_sql_write_off_needs_the_average_and_its_exact_journal(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "10", "20.01")
    # Written whole by SQL alone a write-off is accepted when it carries what the database
    # computes itself: 5 of 10 units worth 20.01 leave at 1000.5, that is 1001 minor units.
    await hand_write_off(stock, item, amount=1001)
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(5, 1000)]
    assert stock.reconciled() == (1000, 1000)
    counts = stock.counts()
    # The next two units are worth 400. Any other amount, direction, account or journal is
    # refused, and so is more than the owner holds; nothing of the attempts remains.
    attempts: tuple[tuple[Written, str], ...] = (
        ({"quantity": 2, "amount": 399}, "23514"),
        ({"quantity": 2, "amount": 401}, "23514"),
        ({"quantity": 2, "amount": 400, "way": "in"}, "23514"),
        ({"quantity": 2, "amount": 400, "debit": "1400"}, "23514"),
        ({"quantity": 2, "amount": 400, "journal": 399}, "23514"),
        ({"quantity": 2, "amount": 400, "reason": "purchase"}, "23514"),
        ({"quantity": 2, "amount": 400, "reason": "damaged"}, "23514"),
        ({"quantity": 6, "amount": 1000}, "GBS02"),
    )
    for how, state in attempts:
        with pytest.raises(psycopg.DatabaseError) as caught:
            await hand_write_off(stock, item, **how)
        assert caught.value.sqlstate == state, how
    assert stock.counts() == counts
    await hand_write_off(stock, item, quantity=2, amount=400, reason="damaged", debit="6900")
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(3, 600)]

    # The owner holds six in two places; four do not leave a place that holds three.
    spare = await stock.inventory.place(stock.inventory.world.a.location_id)
    await received(stock, item, "3", "6.00", place_id=spare["place_id"])
    counts = stock.counts()
    with pytest.raises(psycopg.DatabaseError) as short:
        await hand_write_off(stock, item, quantity=4, amount=800)
    assert short.value.sqlstate == "GBS02"
    assert stock.counts() == counts
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(6, 1200)]
    assert stock.reconciled() == (1200, 1200)


async def test_write_off_line_value_stays_in_the_supported_range(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    most = "9999999999999.99"
    costly: dict[str, object] = {"item_id": item, "quantity": "1", "amount": most}
    posted = await stock.post(stock.receipt([costly, costly]))
    assert posted.status_code == 200, posted.text
    assert posted.json()["money"]["total"] == "19999999999999.98"
    counts = stock.counts()
    # Both units together are worth more than one line carries: refused by the API and by SQL.
    both = await stock.post(write_off(stock, [{"item_id": item, "quantity": "2"}]))
    assert error(both) == (422, "STOCK_AMOUNT_INVALID"), both.text
    assert both.json()["error"]["details"]["line"] == 1
    with pytest.raises(psycopg.errors.CheckViolation):
        await hand_write_off(stock, item, quantity=2, amount=1_999_999_999_999_998)
    assert stock.counts() == counts
    # One by one they leave, each with half of the value.
    for _ in range(2):
        one = await stock.post(write_off(stock, [{"item_id": item, "quantity": "1"}]))
        assert (one.status_code, one.json()["money"]["total"]) == (200, most), one.text
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(0, 0)]
    assert stock.reconciled() == (0, 0)


@pytest.mark.parametrize("kind", ["receipt", "write_off"])
async def test_two_requests_with_one_key_post_one_document(
    stock: Stock, test_database: ProvisionedDatabase, kind: str
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    line: dict[str, object] = {"item_id": item, "quantity": "2"}
    body = (
        stock.receipt([{**line, "amount": "4.00"}])
        if kind == "receipt"
        else write_off(stock, [line])
    )
    document, key = uuid7(), str(uuid7())

    async def same() -> httpx.Response:
        return await stock.post(body, document, key)

    first, second = await behind_the_ledger_lock(stock, test_database, [same, same])
    assert (first.status_code, second.status_code) == (200, 200), first.text + second.text
    assert first.json() == second.json()
    assert stock.counts()["stock_documents"] == 2
    assert stock.rows("select quantity from gba.stock_balances") == [
        (7 if kind == "receipt" else 3,)
    ]
    assert stock.counts()["stock_entries"] == 2


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_two_write_offs_of_the_last_balance_have_one_winner(
    stock: Stock, test_database: ProvisionedDatabase, raw_sql: bool
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    body = write_off(stock, [{"item_id": item, "quantity": "5"}])

    async def racer() -> str:
        if raw_sql:
            try:
                await hand_write_off(stock, item)
            except psycopg.DatabaseError as exc:
                if exc.sqlstate != "GBS02":
                    raise
                return "insufficient"
            return "posted"
        response = await stock.post(body)
        if response.status_code == 200:
            return "posted"
        assert error(response) == (409, "STOCK_INSUFFICIENT"), response.text
        return "insufficient"

    results = await behind_the_ledger_lock(stock, test_database, [racer, racer])
    assert sorted(results) == ["insufficient", "posted"]
    assert stock.rows("select quantity from gba.stock_balances") == [(0,)]
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(0, 0)]
    assert stock.counts()["stock_documents"] == 2
    assert stock.reconciled() == (0, 0)


@pytest.mark.parametrize("raw_sql", [False, True])
@pytest.mark.parametrize("first", ["close", "post"])
async def test_period_close_and_write_off_take_one_order(
    stock: Stock, test_database: ProvisionedDatabase, first: str, raw_sql: bool
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00", document_date="2026-09-10")
    user = stock.inventory.manager.user_id
    september = (stock.tenant, stock.book, user)

    async def close() -> str:
        if raw_sql:
            async with tenant_transaction(stock.pool, stock.tenant) as conn:
                await set_user_context(conn, user)
                await conn.execute(CLOSE_SEPTEMBER, september)
            return "closed"
        response = await stock.inventory.client.post(
            f"{stock.ledger}/periods/2026-09/close",
            json={"schema_version": 1, "expected_sequence": 0},
            headers=stock.keyed(),
        )
        assert response.status_code == 200, response.text
        return "closed"

    async def post() -> str:
        if raw_sql:
            try:
                await hand_write_off(stock, item, day="2026-09-15")
            except psycopg.errors.CheckViolation as exc:
                if "closed" not in str(exc):
                    raise
                return "refused"
            return "posted"
        response = await stock.post(
            write_off(stock, [{"item_id": item, "quantity": "5"}], document_date="2026-09-15")
        )
        if response.status_code == 200:
            return "posted"
        assert error(response) == (409, "LEDGER_PERIOD_CLOSED"), response.text
        return "refused"

    async def leading(barrier: RuntimeConnection) -> None:
        if first == "close":
            await barrier.execute(CLOSE_SEPTEMBER, september)
        else:
            await write_off_sql(barrier, stock, item, day="2026-09-15")

    follower = post if first == "close" else close
    results = await behind_the_ledger_lock(stock, test_database, [follower], leading)
    # Closing first refuses the write-off; posting first is kept and the month then closes.
    assert results == ["refused" if first == "close" else "closed"]
    assert stock.counts()["stock_documents"] == (1 if first == "close" else 2)
    assert stock.reconciled() == ((1000, 1000) if first == "close" else (0, 0))
    late = await stock.post(
        write_off(stock, [{"item_id": item, "quantity": "1"}], document_date="2026-09-20")
    )
    assert error(late) == (409, "LEDGER_PERIOD_CLOSED"), late.text
