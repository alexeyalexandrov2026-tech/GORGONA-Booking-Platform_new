"""Findings of the independent review of package J, on real PostgreSQL 18.

Each test names the finding of docs/plan/evidence/2026-10-13-j-review/REVIEW.md it covers.
"""

import asyncio
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.db.pool import tenant_transaction
from tests.integration import test_stock as shared
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_counterparties import card
from tests.integration.test_inventory import error, refused_sql
from tests.integration.test_stock import Stock
from tests.integration.test_stock_returns import (
    back,
    cost,
    giving_back,
    hand_return,
    posted,
    receipt_of,
)
from tests.integration.test_stock_transfers import (
    ROW_WAITERS,
    behind_the_balance_rows,
    held,
    transfer,
)
from tests.integration.test_stock_write_offs import received, write_off

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
type Body = dict[str, object]


class UndoneError(Exception):
    """Rolls a barrier transaction back on purpose."""


async def seen_waiting(monitor: psycopg.AsyncConnection, task: asyncio.Task[object]) -> None:
    """The follower is seen in pg_locks waiting for a row lock, and has not finished."""
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        row = await (await monitor.execute(ROW_WAITERS)).fetchone()
        if row is not None and row[0] >= 1:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("The follower must be seen in pg_locks waiting for a row lock")
    assert not task.done()


async def supplier_of(stock: Stock) -> UUID:
    """An active counterparty with the supplier role, after enabling counterparties."""
    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager,
        stock.tenant,
        1,
        ["booking_resources", "counterparties", "finance", "inventory"],
    )
    supplier = uuid7()
    saved = await stock.inventory.client.put(
        f"/v1/businesses/{stock.tenant}/counterparties/{supplier}",
        json=card(
            roles=["supplier"],
            display_name="FAKE supplier",
            email="fake.supplier@example.test",
            phone="+1 555 010 2001",
        ),
        headers=stock.keyed(),
    )
    assert saved.status_code == 200, saved.text
    return supplier


@pytest.mark.parametrize("inbound", ["receipt", "return"])
async def test_m1_inbound_documents_lock_existing_balance_rows_before_inserting_new_ones(
    stock: Stock, test_database: ProvisionedDatabase, inbound: str
) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    one = (await stock.inventory.item(quantity_scale=0))["item_id"]
    two = (await stock.inventory.item(quantity_scale=0))["item_id"]
    # The database orders balance rows by material: `first` comes before `second`.
    first, second = sorted([str(one), str(two)])
    # The shelf holds the second material and has no row for the first one yet.
    await received(stock, second, "5", "10.00", place_id=shelf["place_id"])
    body: Body
    if inbound == "receipt":
        body = stock.receipt(
            [
                {"item_id": first, "quantity": "1", "amount": "1.00"},
                {"item_id": second, "quantity": "1", "amount": "1.00"},
            ],
            place_id=shelf["place_id"],
        )
    else:
        await received(stock, first, "5", "10.00")
        await received(stock, second, "5", "10.00")
        lines: list[Body] = [
            {"item_id": first, "quantity": "1"},
            {"item_id": second, "quantity": "1"},
        ]
        used = await posted(stock, write_off(stock, lines))
        body = giving_back(
            stock, used, [back(1, "1"), back(2, "1")], reason="unused", place_id=shelf["place_id"]
        )
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    tasks: list[asyncio.Task[httpx.Response]] = []

    async def hold_then_write() -> None:
        async with tenant_transaction(stock.pool, stock.tenant) as barrier:
            await set_user_context(barrier, stock.inventory.manager.user_id)
            # Like a transfer to the shelf, the barrier first locks the rows that exist.
            await barrier.execute(
                "select 1 from gba.stock_balances where tenant_id=%s and item_id=%s "
                "and place_id=%s for update",
                (stock.tenant, second, shelf["place_id"]),
            )
            tasks.append(asyncio.create_task(stock.post(body)))
            await seen_waiting(monitor, tasks[0])
            # Then it writes the row of the first material. The document must not hold that
            # row yet: it waits for the existing rows before it inserts new ones.
            await barrier.execute("set local lock_timeout = '3s'")
            await barrier.execute(
                "insert into gba.stock_balances (tenant_id,item_id,place_id,legal_entity_id,"
                "location_id,quantity) values (%s,%s,%s,%s,%s,0) "
                "on conflict (tenant_id,item_id,place_id,legal_entity_id) "
                "do update set quantity=gba.stock_balances.quantity",
                (stock.tenant, first, shelf["place_id"], stock.entity, shelf["location_id"]),
            )
            raise UndoneError

    try:
        with pytest.raises(UndoneError):
            await hold_then_write()
        response = await asyncio.wait_for(tasks[0], 15)
        assert response.status_code == 200, response.text
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor.close()
    shelved = stock.rows(
        "select item_id::text,quantity from gba.stock_balances where place_id=%s",
        shelf["place_id"],
    )
    assert set(shelved) == {(first, 1), (second, 6)}
    value, entries = stock.reconciled()
    assert value == entries


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_a_return_waits_for_the_lock_of_its_source_line(
    stock: Stock, test_database: ProvisionedDatabase, raw_sql: bool
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    source = await receipt_of(stock, item, "5", "10.00")
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    task: asyncio.Task[object] | None = None
    try:
        # The barrier holds the source line without the ledger lock: only that row lock
        # stops the return.
        async with tenant_transaction(stock.pool, stock.tenant) as barrier:
            await set_user_context(barrier, stock.inventory.manager.user_id)
            await barrier.execute(
                "select 1 from gba.stock_document_lines where tenant_id=%s and document_id=%s "
                "and line_no=1 for update",
                (stock.tenant, source),
            )
            follower = (
                hand_return(stock, source, item, quantity=2, amount=400, basis=400)
                if raw_sql
                else stock.post(giving_back(stock, source, [back(1, "2")]))
            )
            task = asyncio.create_task(follower)
            await seen_waiting(monitor, task)
        result = await asyncio.wait_for(task, 15)
        if not raw_sql:
            assert isinstance(result, httpx.Response)
            assert result.status_code == 200, result.text
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await monitor.close()
    assert cost(stock, item) == (3, 600)
    # The column right that makes the lock possible changes nothing.
    user = stock.inventory.manager.user_id
    statement = "update gba.stock_document_lines set line_no=line_no where tenant_id=%s"
    assert await refused_sql(stock.pool, stock.tenant, user, statement, (stock.tenant,)) == "23514"


async def test_l1_balance_and_cost_rows_exist_only_through_documents(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    user = stock.inventory.manager.user_id
    place, home = stock.place["place_id"], stock.place["location_id"]
    # Even with nothing in it, a row that no document explains does not survive the commit.
    for statement, values in (
        (
            "insert into gba.stock_balances (tenant_id,item_id,place_id,legal_entity_id,"
            "location_id,quantity) values (%s,%s,%s,%s,%s,0)",
            (stock.tenant, item, place, stock.entity, home),
        ),
        (
            "insert into gba.stock_costs (tenant_id,legal_entity_id,item_id,quantity,value_minor) "
            "values (%s,%s,%s,0,0)",
            (stock.tenant, stock.entity, item),
        ),
    ):
        assert await refused_sql(stock.pool, stock.tenant, user, statement, values) == "23514"
    # A row brought to zero by documents stays.
    await received(stock, item, "2", "4.00")
    assert (await stock.post(write_off(stock, [{"item_id": item, "quantity": "2"}]))).is_success
    assert stock.rows("select quantity from gba.stock_balances where item_id=%s", item) == [(0,)]
    assert cost(stock, item) == (0, 0)


async def test_l2_an_archived_account_of_the_entry_is_named(stock: Stock) -> None:
    assert (await stock.set_rules(difference="6400")).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    purchase = await receipt_of(stock, item, "5", "10.00")
    # The rules move on to another receipt account, and the old one is archived.
    assert (await stock.set_rules(1, receipt="1500", difference="6400")).status_code == 200
    await stock.account("1400", "asset", "Prepaid expenses", 1, True)
    baseline = stock.counts()
    body = giving_back(stock, purchase, [back(1, "1")], reason="entry_error")
    refused = await stock.post(body)
    assert error(refused) == (409, "STOCK_ACCOUNT_ARCHIVED"), refused.text
    assert refused.json()["error"]["details"] == {"account_id": str(stock.accounts["1400"])}
    assert stock.counts() == baseline
    # Reopened, the same account takes the return.
    await stock.account("1400", "asset", "Prepaid expenses", 2, False)
    accepted_return = await stock.post(body)
    assert accepted_return.status_code == 200, accepted_return.text


async def test_l4_the_supplier_is_read_only_with_the_amounts(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    supplier = await supplier_of(stock)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    line: Body = {"item_id": item, "quantity": "1", "amount": "2.00"}
    document = await posted(
        stock, stock.receipt([line], supplier_id=str(supplier), supplier_document="INV-9")
    )
    seen = (await stock.inventory.get(f"/documents/{document}")).json()
    assert (seen["supplier_id"], seen["supplier_document"]) == (str(supplier), "INV-9")
    # A branch manager reads the receipt of the branch without its supplier, as without
    # its amounts: counterparties are company-wide data.
    _, branch = stock.inventory.member("manager", stock.inventory.world.a.location_id)
    hidden = await stock.inventory.get(f"/documents/{document}", headers=branch)
    assert hidden.status_code == 200, hidden.text
    assert (hidden.json()["supplier_id"], hidden.json()["supplier_document"]) == (None, None)
    assert hidden.json()["money"] is None


async def test_two_transfer_requests_with_one_key_post_one_document(
    stock: Stock, test_database: ProvisionedDatabase
) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    document, key = uuid7(), str(uuid7())
    body = transfer(stock, shelf, [{"item_id": item, "quantity": "2"}])

    async def racer() -> httpx.Response:
        return await stock.post(body, document, key)

    # The first waits for the balance rows, the second for the first's claim of the key.
    results = await behind_the_balance_rows(stock, test_database, item, [racer, racer])
    assert [response.status_code for response in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert stock.counts()["stock_documents"] == 2
    assert held(stock) == {str(stock.place["place_id"]): 3, str(shelf["place_id"]): 2}
