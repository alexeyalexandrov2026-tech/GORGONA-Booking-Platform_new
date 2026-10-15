"""M2 of the independent review, migration 0042: histories that carry their running totals.

Every movement names its place in the history of its balance and the balance after it;
every valuation the quantity and value of its owner's material after it. The insert
triggers write them from the head of the history, after checking that the stored total
still equals that head, and the checks at commit compare a total with its head instead of
summing the whole history. A forged total is refused as before.
"""

import asyncio
from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.db.pool import tenant_transaction
from tests.integration import test_stock as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import seed_other_branch
from tests.integration.test_inventory import refused_sql
from tests.integration.test_stock import DAY, Stock
from tests.integration.test_stock_transfers import transfer, transfer_sql
from tests.integration.test_stock_write_offs import received, write_off, write_off_sql

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a

# Rows whose history disagrees with itself or with the total it ends in. Each must be zero.
UNCHAINED = {
    "movements": (
        "select count(*) from (select m.sequence,m.balance_after,row_number() over w as n,"
        "sum(case m.direction when 'in' then m.quantity else -m.quantity end) over w as total "
        "from gba.stock_movements m window w as (partition by m.tenant_id,m.item_id,"
        "m.place_id,m.legal_entity_id order by m.sequence)) x "
        "where x.sequence<>x.n or x.balance_after<>x.total"
    ),
    "balances": (
        "select count(*) from gba.stock_balances b where b.quantity is distinct from ("
        "select m.balance_after from gba.stock_movements m where m.tenant_id=b.tenant_id "
        "and m.item_id=b.item_id and m.place_id=b.place_id "
        "and m.legal_entity_id=b.legal_entity_id order by m.sequence desc limit 1)"
    ),
    "valuations": (
        "select count(*) from (select v.sequence,v.quantity_after,v.value_after,"
        "row_number() over w as n,"
        "sum(case v.direction when 'in' then v.quantity else -v.quantity end) over w as held,"
        "sum(case v.direction when 'in' then v.amount_minor else -v.amount_minor end) "
        "over w as worth from gba.stock_valuations v window w as (partition by v.tenant_id,"
        "v.legal_entity_id,v.item_id order by v.sequence)) x "
        "where x.sequence<>x.n or x.quantity_after<>x.held or x.value_after<>x.worth"
    ),
    "costs": (
        "select count(*) from gba.stock_costs c left join lateral (select v.quantity_after,"
        "v.value_after from gba.stock_valuations v where v.tenant_id=c.tenant_id "
        "and v.legal_entity_id=c.legal_entity_id and v.item_id=c.item_id "
        "order by v.sequence desc limit 1) h on true "
        "where c.quantity is distinct from h.quantity_after "
        "or c.value_minor is distinct from h.value_after"
    ),
}
BALANCE = "a stock balance equals the sum of its movements"
COST = "the cost of a material equals its valuations and its balances"


def chained(stock: Stock) -> None:
    for name, query in UNCHAINED.items():
        assert stock.rows(query) == [(0,)], name


def history(stock: Stock, item: object, place: object) -> list[tuple[object, ...]]:
    return stock.rows(
        "select sequence,direction,quantity,balance_after from gba.stock_movements "
        "where item_id=%s and place_id=%s order by sequence",
        item,
        place,
    )


async def test_every_kind_of_document_extends_its_history(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    # Two lines of one material in one receipt: two links of one history.
    receipt = uuid7()
    posted = await stock.post(
        stock.receipt(
            [
                {"item_id": item, "quantity": "5", "amount": "10.00"},
                {"item_id": item, "quantity": "3", "amount": "9.00"},
            ]
        ),
        receipt,
    )
    assert posted.status_code == 200, posted.text
    used = await stock.post(write_off(stock, [{"item_id": item, "quantity": "2"}]))
    assert used.status_code == 200, used.text
    moved = await stock.post(transfer(stock, shelf, [{"item_id": item, "quantity": "1"}]))
    assert moved.status_code == 200, moved.text
    back = await stock.post(
        {
            "kind": "return",
            "reason": "supplier_return",
            "legal_entity_id": str(stock.entity),
            "place_id": stock.place["place_id"],
            "document_date": DAY,
            "source_document_id": str(receipt),
            "lines": [{"source_line_no": 1, "quantity": "1"}],
        }
    )
    assert back.status_code == 200, back.text
    assert history(stock, item, stock.place["place_id"]) == [
        (1, "in", 5, 5),
        (2, "in", 3, 8),
        (3, "out", 2, 6),
        (4, "out", 1, 5),
        (5, "out", 1, 4),
    ]
    assert history(stock, item, shelf["place_id"]) == [(1, "in", 1, 1)]
    # The cost follows the moving average: 2 of 8 worth 19.00 leave at 4.75, then 1 of 6
    # worth 14.25 at 2.38. A transfer moves no value.
    assert stock.rows(
        "select sequence,direction,quantity_after,value_after from gba.stock_valuations "
        "where item_id=%s order by sequence",
        item,
    ) == [(1, "in", 5, 1000), (2, "in", 8, 1900), (3, "out", 6, 1425), (4, "out", 5, 1187)]
    chained(stock)


async def test_a_forged_total_is_refused_even_when_a_movement_follows(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    user = stock.inventory.manager.user_id

    async def forged_then_moved(forgery: str) -> None:
        async with tenant_transaction(stock.pool, stock.tenant) as conn:
            await set_user_context(conn, user)
            await conn.execute(forgery.encode("utf-8"), (item,))
            await write_off_sql(conn, stock, item, quantity=1, amount=200)

    forgeries = (
        ("update gba.stock_balances set quantity=quantity+1 where item_id=%s", BALANCE),
        ("update gba.stock_costs set value_minor=value_minor+1 where item_id=%s", COST),
    )
    for forgery, message in forgeries:
        # The forged total alone is refused at commit.
        state = await refused_sql(stock.pool, stock.tenant, user, forgery, (item,))
        assert state == "23514", forgery
        # And a movement that follows it in the same transaction is refused at once.
        with pytest.raises(psycopg.DatabaseError) as caught:
            await forged_then_moved(forgery)
        assert (caught.value.sqlstate, caught.value.diag.message_primary) == ("23514", message)
    assert history(stock, item, stock.place["place_id"]) == [(1, "in", 5, 5)]
    chained(stock)


async def test_a_forged_total_is_refused_when_the_context_changes_before_commit(
    stock: Stock,
) -> None:
    """Finding H1 of the review of J5 and J6: a check that cannot see the total refuses it.

    The runtime role sets the company and the branch of its own session; after forging a
    total it may hide the rows from the checks at commit by changing them.
    """
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    other = (await stock.inventory.item(quantity_scale=0))["item_id"]
    away, _ = seed_other_branch(stock.inventory.owner_conn, stock.inventory.world.a)
    user = stock.inventory.manager.user_id
    place, home = stock.place["place_id"], stock.place["location_id"]
    forgeries: tuple[tuple[str, tuple[object, ...]], ...] = (
        ("update gba.stock_balances set quantity=quantity+1000 where item_id=%s", (item,)),
        ("update gba.stock_costs set value_minor=value_minor+1 where item_id=%s", (item,)),
        # A balance with no history at all, of a material that the place never held.
        (
            "insert into gba.stock_balances (tenant_id,item_id,place_id,legal_entity_id,"
            "location_id,quantity) values (%s,%s,%s,%s,%s,7)",
            (stock.tenant, other, place, stock.entity, home),
        ),
    )
    hidings: tuple[tuple[str, tuple[object, ...]], ...] = (
        ("select set_config('gba.tenant_id','',true)", ()),
        ("select set_config('gba.location_id',%s,true)", (str(away),)),
    )

    async def forged_then_hidden(
        forgery: tuple[str, tuple[object, ...]], hiding: tuple[str, tuple[object, ...]]
    ) -> None:
        async with tenant_transaction(stock.pool, stock.tenant) as conn:
            await set_user_context(conn, user)
            await conn.execute(forgery[0].encode("utf-8"), forgery[1])
            await conn.execute(hiding[0].encode("utf-8"), hiding[1])

    for forgery in forgeries:
        for hiding in hidings:
            with pytest.raises(psycopg.DatabaseError) as caught:
                await forged_then_hidden(forgery, hiding)
            assert caught.value.sqlstate == "23514", (forgery[0], hiding[0])
    assert history(stock, item, place) == [(1, "in", 5, 5)]
    assert stock.rows("select count(*) from gba.stock_balances") == [(1,)]
    chained(stock)


async def test_the_history_is_written_by_the_database_alone(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    user = stock.inventory.manager.user_id
    for statement in (
        "update gba.stock_movements set balance_after=0 where item_id=%s",
        "update gba.stock_movements set sequence=sequence+1 where item_id=%s",
        "update gba.stock_valuations set value_after=0 where item_id=%s",
        "update gba.stock_valuations set quantity_after=0, sequence=9 where item_id=%s",
        "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,location_id,"
        "place_id,item_id,legal_entity_id,quantity,sequence,balance_after) select tenant_id,"
        "document_id,line_no,direction,location_id,place_id,item_id,legal_entity_id,quantity,"
        "7,7 from gba.stock_movements where item_id=%s",
    ):
        assert await refused_sql(stock.pool, stock.tenant, user, statement, (item,)) == "42501"
    chained(stock)


async def test_two_transfers_into_a_new_balance_wait_and_chain(
    stock: Stock, test_database: ProvisionedDatabase
) -> None:
    """The second writer of a balance that does not exist yet continues the first's history.

    The race counts only when the follower is seen in pg_locks waiting for a row lock.
    """
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    second_source = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    await received(stock, item, "5", "10.00", place_id=second_source["place_id"])
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    follower: asyncio.Task[object] | None = None
    try:
        async with tenant_transaction(stock.pool, stock.tenant) as leader:
            await set_user_context(leader, stock.inventory.manager.user_id)
            identity = await (
                await leader.execute("select pg_backend_pid(),pg_current_xact_id()::text")
            ).fetchone()
            assert identity is not None
            # The leader writes the first balance of the shelf and keeps it uncommitted.
            await transfer_sql(leader, stock, item, shelf, quantity=1)
            follower = asyncio.create_task(
                stock.post(
                    transfer(
                        stock,
                        shelf,
                        [{"item_id": item, "quantity": "1"}],
                        place_id=second_source["place_id"],
                    )
                )
            )
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                row = await (
                    await monitor.execute(
                        "select a.pid from pg_catalog.pg_locks l "
                        "join pg_catalog.pg_stat_activity a on a.pid=l.pid "
                        "where not l.granted and l.locktype='transactionid' "
                        "and l.transactionid::text=%s and %s=any(pg_blocking_pids(l.pid)) "
                        "and a.datname=current_database() "
                        "and a.query like 'insert into gba.stock_movements %%'",
                        (identity[1], identity[0]),
                    )
                ).fetchone()
                if row is not None:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("The follower must wait on the destination insert in pg_locks")
            assert not follower.done()
        moved = await asyncio.wait_for(follower, 15)
    finally:
        if follower is not None and not follower.done():
            follower.cancel()
        if follower is not None:
            await asyncio.gather(follower, return_exceptions=True)
        await monitor.close()
    assert getattr(moved, "status_code", None) == 200, getattr(moved, "text", moved)
    assert history(stock, item, shelf["place_id"]) == [(1, "in", 1, 1), (2, "in", 1, 2)]
    assert history(stock, item, stock.place["place_id"]) == [
        (1, "in", 5, 5),
        (2, "out", 1, 4),
    ]
    assert history(stock, item, second_source["place_id"]) == [
        (1, "in", 5, 5),
        (2, "out", 1, 4),
    ]
    assert stock.reconciled() == (2000, 2000)
    chained(stock)
