"""J4 transfers between storage places against real PostgreSQL 18."""

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, Unpack
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.auth.principal import set_user_context
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership, grant_platform_admin
from tests.integration import test_stock as shared
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import seed_other_branch, seed_user
from tests.integration.test_inventory import error, material_input, refused_sql
from tests.integration.test_stock import DAY, Stock, entity_with_book
from tests.integration.test_stock_write_offs import received, write_off

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
# Backends of this database that wait for a row lock.
ROW_WAITERS = (
    "select count(distinct l.pid) from pg_catalog.pg_locks l "
    "where l.locktype in ('transactionid','tuple') and not l.granted "
    "and l.pid in (select a.pid from pg_catalog.pg_stat_activity a "
    "where a.datname=pg_catalog.current_database())"
)
HEAD = (
    "insert into gba.stock_documents (tenant_id,id,kind,reason,legal_entity_id,place_id,"
    "location_id,to_place_id,to_location_id,document_date,line_count,created_by) "
    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s)"
)
type Place = dict[str, object]


class Moved(TypedDict, total=False):
    """How a transfer written by SQL differs from five units leaving the first place."""

    quantity: int
    source: Place
    # Where the inbound movement is written; the destination unless a test says otherwise.
    inbound: Place
    skip_inbound: bool
    posting: bool


def transfer(stock: Stock, to: Place, lines: list[dict[str, object]], **changes: object) -> Place:
    return {
        "kind": "transfer",
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "to_place_id": to["place_id"],
        "document_date": DAY,
        "lines": lines,
        **changes,
    }


async def transfer_sql(
    conn: RuntimeConnection, stock: Stock, item: object, to: Place, **how: Unpack[Moved]
) -> UUID:
    """One transfer line written by SQL alone; movements in the order of their places."""
    tenant, user = stock.tenant, stock.inventory.manager.user_id
    quantity, source = how.get("quantity", 5), how.get("source", stock.place)
    document = uuid7()
    await conn.execute(
        HEAD,
        (
            tenant,
            document,
            "transfer",
            "relocation",
            stock.entity,
            source["place_id"],
            source["location_id"],
            to["place_id"],
            to["location_id"],
            DAY,
            user,
        ),
    )
    await conn.execute(
        "insert into gba.stock_document_lines (tenant_id,document_id,line_no,location_id,"
        "item_id,quantity) values (%s,%s,1,%s,%s,%s)",
        (tenant, document, source["location_id"], item, quantity),
    )
    moves = [("out", source)]
    if not how.get("skip_inbound", False):
        moves.append(("in", how.get("inbound", to)))
    # Rule 16: balance rows are taken in the order material, place, owner.
    for direction, place in sorted(moves, key=lambda move: str(move[1]["place_id"])):
        await conn.execute(
            "insert into gba.stock_movements (tenant_id,document_id,line_no,direction,"
            "location_id,place_id,item_id,legal_entity_id,quantity) "
            "values (%s,%s,1,%s,%s,%s,%s,%s,%s)",
            (
                tenant,
                document,
                direction,
                place["location_id"],
                place["place_id"],
                item,
                stock.entity,
                quantity,
            ),
        )
    if how.get("posting", False):
        await conn.execute(
            "insert into gba.stock_document_postings (tenant_id,document_id,book_id,"
            "rule_revision,entry_id,total_minor,created_by) values (%s,%s,%s,1,null,0,%s)",
            (tenant, document, stock.book, user),
        )
    return document


async def hand_transfer(
    stock: Stock, item: object, to: Place, pool: RuntimePool | None = None, **how: Unpack[Moved]
) -> UUID:
    async with tenant_transaction(pool or stock.pool, stock.tenant) as conn:
        await set_user_context(conn, stock.inventory.manager.user_id)
        return await transfer_sql(conn, stock, item, to, **how)


async def behind_the_balance_rows[T](
    stock: Stock,
    database: ProvisionedDatabase,
    item: object,
    followers: list[Callable[[], Coroutine[Any, Any, T]]],
) -> list[T]:
    """Run the followers while one transaction holds every balance row of the material.

    The race counts only when every follower is seen in pg_locks waiting for a row lock.
    """
    monitor = await psycopg.AsyncConnection.connect(
        database.admin_dsn, dbname=database.name, autocommit=True
    )
    tasks: list[asyncio.Task[T]] = []
    try:
        async with tenant_transaction(stock.pool, stock.tenant) as barrier:
            await barrier.execute(
                "select 1 from gba.stock_balances where tenant_id=%s and item_id=%s "
                "order by place_id for update",
                (stock.tenant, item),
            )
            tasks = [asyncio.create_task(follower()) for follower in followers]
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                row = await (await monitor.execute(ROW_WAITERS)).fetchone()
                if row is not None and row[0] >= len(tasks):
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Every follower must be seen in pg_locks waiting for a row lock")
            assert all(not task.done() for task in tasks)
        return list(await asyncio.wait_for(asyncio.gather(*tasks), 15))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor.close()


def held(stock: Stock) -> dict[str, int]:
    rows = stock.rows("select place_id,quantity from gba.stock_balances")
    return {str(place): int(str(quantity)) for place, quantity in rows}


async def test_transfer_moves_quantity_without_touching_cost_or_the_books(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    dye = (await stock.inventory.item(code="DYE", unit="ml", quantity_scale=1))["item_id"]
    await received(stock, dye, "10.0", "20.00")
    document = uuid7()
    moved = await stock.post(
        transfer(stock, shelf, [{"item_id": dye, "quantity": "4.0"}]), document
    )
    assert moved.status_code == 200, moved.text
    view = moved.json()
    assert {name: value for name, value in view.items() if name != "created_at"} == {
        "schema_version": 1,
        "business_id": str(stock.tenant),
        "document_id": str(document),
        "kind": "transfer",
        "reason": "relocation",
        "legal_entity_id": str(stock.entity),
        "place_id": stock.place["place_id"],
        "location_id": stock.place["location_id"],
        "to_place_id": shelf["place_id"],
        "to_location_id": shelf["location_id"],
        "document_date": DAY,
        "supplier_id": None,
        "supplier_document": None,
        # A transfer carries no amount and has no posting, even for a finance reader.
        "lines": [{"line_no": 1, "item_id": dye, "quantity": "4.0", "amount": None}],
        "money": None,
    }
    assert (await stock.inventory.get(f"/documents/{document}")).json() == view
    listed = (await stock.inventory.get("/documents")).json()["items"]
    assert [(row["kind"], row["to_place_id"]) for row in listed] == [
        ("receipt", None),
        ("transfer", shelf["place_id"]),
    ]
    # The documents of a place include what arrived there.
    arrived = await stock.inventory.get("/documents", place_id=str(shelf["place_id"]))
    assert [row["kind"] for row in arrived.json()["items"]] == ["transfer"]

    # Two movements of one line; the owner still holds 10.0 ml worth 20.00 and the books
    # did not move.
    assert held(stock) == {str(stock.place["place_id"]): 60, str(shelf["place_id"]): 40}
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(100, 2000)]
    assert stock.counts() == {
        "stock_documents": 2,
        "stock_document_lines": 2,
        "stock_movements": 3,
        "stock_balances": 2,
        "stock_document_postings": 1,
        "stock_valuations": 1,
        "stock_costs": 1,
        "stock_entries": 1,
    }
    assert stock.reconciled() == (2000, 2000)
    audit = stock.rows(
        "select action,target_type,details from gba.audit_events where target_id=%s",
        str(document),
    )
    assert audit == [("inventory.document", "stock_document", {"kind": "transfer", "lines": 1})]

    # What was moved leaves the other place at the same average cost.
    used = await stock.post(
        write_off(stock, [{"item_id": dye, "quantity": "4.0"}], place_id=shelf["place_id"])
    )
    assert (used.status_code, used.json()["money"]["total"]) == (200, "8.00"), used.text
    # A transfer moves no money, so a closed month does not stop it.
    closed = await stock.inventory.client.post(
        f"{stock.ledger}/periods/2026-09/close",
        json={"schema_version": 1, "expected_sequence": 0},
        headers=stock.keyed(),
    )
    assert closed.status_code == 200, closed.text
    late = await stock.post(
        transfer(stock, shelf, [{"item_id": dye, "quantity": "1.0"}], document_date="2026-09-20")
    )
    assert late.status_code == 200, late.text
    assert held(stock) == {str(stock.place["place_id"]): 50, str(shelf["place_id"]): 10}
    assert stock.reconciled() == (1200, 1200)


async def test_transfer_of_several_lines_moves_every_line_once(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    dye = (await stock.inventory.item(quantity_scale=0))["item_id"]
    foil = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, dye, "5", "10.00")
    await received(stock, foil, "3", "9.00")
    document = uuid7()
    # Two materials in three lines, one of them twice.
    lines: list[dict[str, object]] = [
        {"item_id": dye, "quantity": "2"},
        {"item_id": foil, "quantity": "1"},
        {"item_id": dye, "quantity": "1"},
    ]
    moved = await stock.post(transfer(stock, shelf, lines), document)
    assert moved.status_code == 200, moved.text
    assert [(row["line_no"], row["item_id"], row["quantity"]) for row in moved.json()["lines"]] == [
        (1, dye, "2"),
        (2, foil, "1"),
        (3, dye, "1"),
    ]
    home, away = stock.place["place_id"], shelf["place_id"]
    movements = stock.rows(
        "select line_no,direction,place_id::text,item_id::text,quantity "
        "from gba.stock_movements where document_id=%s order by line_no,direction desc",
        document,
    )
    assert movements == [
        (1, "out", home, dye, 2),
        (1, "in", away, dye, 2),
        (2, "out", home, foil, 1),
        (2, "in", away, foil, 1),
        (3, "out", home, dye, 1),
        (3, "in", away, dye, 1),
    ]
    balances = stock.rows("select item_id::text,place_id::text,quantity from gba.stock_balances")
    assert len(balances) == 4
    assert set(balances) == {(dye, home, 2), (dye, away, 3), (foil, home, 2), (foil, away, 1)}
    # The owner holds what it held, at the same cost.
    costs = stock.rows("select item_id::text,quantity,value_minor from gba.stock_costs")
    assert set(costs) == {(dye, 5, 1000), (foil, 3, 900)}
    assert stock.reconciled() == (1900, 1900)


async def test_transfer_takes_no_more_than_the_place_holds_and_keeps_its_shape(
    stock: Stock,
) -> None:
    home = stock.inventory.world.a.location_id
    shelf = await stock.inventory.place(home)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    six: dict[str, object] = {"item_id": item, "quantity": "6"}
    three: dict[str, object] = {"item_id": item, "quantity": "3"}
    # Nothing to move: no book and no posting rules are asked for, the place is simply short.
    empty = await stock.post(transfer(stock, shelf, [six]))
    assert error(empty) == (409, "STOCK_INSUFFICIENT"), empty.text
    assert empty.json()["error"]["details"]["available"] == "0"

    assert (await stock.set_rules()).status_code == 200
    await received(stock, item, "5", "10.00")
    old = await stock.inventory.item(quantity_scale=0)
    await received(stock, old["item_id"], "2", "2.00")
    retired = await stock.inventory.put(
        f"/items/{old['item_id']}", {**material_input(old), "archived": True}
    )
    assert retired.status_code == 200, retired.text
    sealed = await stock.inventory.place(home)
    shut = await stock.inventory.put(
        f"/places/{sealed['place_id']}",
        {
            "expected_revision": 1,
            "location_id": sealed["location_id"],
            "code": sealed["code"],
            "name": sealed["name"],
            "archived": True,
        },
    )
    assert shut.status_code == 200, shut.text
    other, _, _ = await entity_with_book(stock.inventory, stock.pool, "OTHER", book=False)
    baseline = stock.counts()

    for body, number, available in (
        (transfer(stock, shelf, [six]), 1, "5"),
        # Lines of one material add up.
        (transfer(stock, shelf, [three, three]), 2, "2"),
        # What one legal entity holds does not move for another.
        (transfer(stock, shelf, [three], legal_entity_id=str(other)), 1, "0"),
    ):
        short = await stock.post(body)
        assert error(short) == (409, "STOCK_INSUFFICIENT"), short.text
        details = short.json()["error"]["details"]
        assert (details["line"], details["available"]) == (number, available)
    # A transfer names two different places and quantities, and nothing else.
    for body in (
        transfer(stock, stock.place, [three]),
        transfer(stock, shelf, [{**three, "amount": "1.00"}]),
        transfer(stock, shelf, [three], reason="relocation"),
        transfer(stock, shelf, [three], supplier_document="INV-1"),
        transfer(stock, shelf, []),
        transfer(stock, shelf, [three] * 101),
    ):
        assert error(await stock.post(body)) == (422, "INVALID_REQUEST")
    for quantity in ("0", "1.5"):
        odd = await stock.post(transfer(stock, shelf, [{"item_id": item, "quantity": quantity}]))
        assert error(odd) == (422, "STOCK_QUANTITY_INVALID"), odd.text
    for body in (
        transfer(stock, shelf, [{"item_id": str(uuid7()), "quantity": "1"}]),
        transfer(stock, shelf, [three], to_place_id=str(uuid7())),
        transfer(stock, shelf, [three], place_id=str(uuid7())),
    ):
        unknown = await stock.post(body)
        assert error(unknown) == (422, "INVALID_REFERENCE"), unknown.text
    future = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    dated = await stock.post(transfer(stock, shelf, [three], document_date=future))
    assert error(dated) == (422, "STOCK_DATE_INVALID"), dated.text
    # An archived place and an archived material take no inbound movement.
    for body in (
        transfer(stock, sealed, [three]),
        transfer(stock, shelf, [{"item_id": old["item_id"], "quantity": "1"}]),
    ):
        assert error(await stock.post(body)) == (409, "STOCK_ARCHIVED")
    assert stock.counts() == baseline

    # The command is idempotent like every other document.
    document, key = uuid7(), str(uuid7())
    body = transfer(stock, shelf, [three])
    first = await stock.post(body, document, key)
    assert first.status_code == 200, first.text
    assert (await stock.post(body, document, key)).json() == first.json()
    reused = await stock.post(transfer(stock, shelf, [six]), document, key)
    assert error(reused) == (422, "IDEMPOTENCY_KEY_REUSED"), reused.text
    again = await stock.post(body, document)
    assert error(again) == (409, "INVENTORY_CONFLICT"), again.text
    # A place that is archived afterwards still lets its balance be moved out.
    left = await stock.inventory.put(
        f"/places/{stock.place['place_id']}",
        {
            "expected_revision": 1,
            "location_id": stock.place["location_id"],
            "code": stock.place["code"],
            "name": stock.place["name"],
            "archived": True,
        },
    )
    assert left.status_code == 200, left.text
    rest = await stock.post(transfer(stock, shelf, [{"item_id": item, "quantity": "2"}]))
    assert rest.status_code == 200, rest.text
    moved = stock.rows("select place_id,quantity from gba.stock_balances where item_id=%s", item)
    assert {str(place): quantity for place, quantity in moved} == {
        str(stock.place["place_id"]): 0,
        str(shelf["place_id"]): 5,
    }
    assert stock.reconciled() == (1200, 1200)


async def test_branch_manager_transfers_inside_the_branch_only(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    world = stock.inventory.world
    home = world.a.location_id
    away, _ = seed_other_branch(stock.inventory.owner_conn, world.a)
    shelf = await stock.inventory.place(home)
    remote = await stock.inventory.place(away)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    two: dict[str, object] = {"item_id": item, "quantity": "2"}
    local, branch = stock.inventory.member("manager", home)
    _, elsewhere = stock.inventory.member("manager", away)

    # Inside the branch its manager moves materials and needs no finance right.
    inside = await stock.post(transfer(stock, shelf, [two]), headers=branch)
    assert (inside.status_code, inside.json()["money"]) == (200, None), inside.text
    # A place of another branch does not exist for a branch manager, as a destination or
    # as a source.
    for headers in (branch, elsewhere):
        outside = await stock.post(transfer(stock, remote, [two]), headers=headers)
        assert error(outside) == (422, "INVALID_REFERENCE"), outside.text
    # By SQL alone the same holds, in the branch scope and without it.
    values = (
        stock.tenant,
        uuid7(),
        "transfer",
        "relocation",
        stock.entity,
        stock.place["place_id"],
        home,
        remote["place_id"],
        away,
        DAY,
        local.user_id,
    )
    for scope in (home, None):
        assert (
            await refused_sql(stock.pool, stock.tenant, local.user_id, HEAD, values, scope)
            == "42501"
        )

    # Between branches it takes a company-wide owner or manager; each branch then sees
    # its own balance, and the document belongs to the branch it leaves.
    across = await stock.post(transfer(stock, remote, [two]))
    assert across.status_code == 200, across.text
    seen = {}
    for name, headers in (("home", branch), ("away", elsewhere)):
        balances = await stock.inventory.get("/balances", headers=headers)
        documents = await stock.inventory.get("/documents", headers=headers)
        seen[name] = (
            sorted((row["place_id"], row["quantity"]) for row in balances.json()["items"]),
            len(documents.json()["items"]),
        )
    assert seen["home"] == (
        sorted([(stock.place["place_id"], "1"), (shelf["place_id"], "2")]),
        3,
    )
    assert seen["away"] == ([(remote["place_id"], "2")], 0)

    # Staff, another company and platform support move nothing.
    foreign = seed_user(stock.inventory.owner_conn, f"foreign-{uuid7()}")
    support = seed_user(stock.inventory.owner_conn, f"support-{uuid7()}")
    add_membership(
        stock.inventory.owner_conn,
        tenant_id=world.b.tenant_id,
        user_id=foreign.user_id,
        role="owner",
    )
    grant_platform_admin(
        stock.inventory.owner_conn, user_id=support.user_id, granted_by="test:transfer"
    )
    for headers in (
        stock.inventory.member("artist", home)[1],
        stock.inventory.member("front_desk")[1],
        stock.inventory.idp.bearer(foreign.subject, email=foreign.email),
        stock.inventory.idp.bearer(support.subject, email=support.email),
    ):
        assert (await stock.post(transfer(stock, shelf, [two]), headers=headers)).status_code == 403
    assert stock.counts()["stock_documents"] == 3
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(5, 1000)]


async def test_sql_transfer_needs_both_movements_and_carries_no_money(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    # Written whole by SQL alone a transfer is accepted: the database holds the rules.
    await hand_transfer(stock, item, shelf, quantity=2)
    assert held(stock) == {str(stock.place["place_id"]): 3, str(shelf["place_id"]): 2}
    counts = stock.counts()
    # Half a transfer, an inbound movement into the place it leaves, a posting and more
    # than the place holds are refused; nothing of the attempts remains.
    attempts: tuple[tuple[Moved, str], ...] = (
        ({"quantity": 2, "skip_inbound": True}, "23514"),
        ({"quantity": 2, "inbound": stock.place}, "23514"),
        ({"quantity": 2, "posting": True}, "23514"),
        ({"quantity": 4}, "GBS02"),
    )
    for how, state in attempts:
        with pytest.raises(psycopg.DatabaseError) as caught:
            await hand_transfer(stock, item, shelf, **how)
        assert caught.value.sqlstate == state, how
    # A destination belongs to a transfer and to nothing else.
    user, home = stock.inventory.manager.user_id, stock.place["location_id"]
    for kind, reason, to in (
        ("transfer", "relocation", (None, None)),
        ("transfer", "used", (shelf["place_id"], home)),
        ("write_off", "used", (shelf["place_id"], home)),
    ):
        values = (stock.tenant, uuid7(), kind, reason, stock.entity, stock.place["place_id"])
        document = (*values, home, *to, DAY, user)
        assert await refused_sql(stock.pool, stock.tenant, user, HEAD, document) == "23514", kind
    assert stock.counts() == counts
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(5, 1000)]
    assert stock.reconciled() == (1000, 1000)


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_two_transfers_of_the_last_balance_have_one_winner(
    stock: Stock, test_database: ProvisionedDatabase, raw_sql: bool
) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    body = transfer(stock, shelf, [{"item_id": item, "quantity": "5"}])

    async def racer() -> str:
        if raw_sql:
            try:
                await hand_transfer(stock, item, shelf)
            except psycopg.DatabaseError as exc:
                if exc.sqlstate != "GBS02":
                    raise
                return "short"
            return "moved"
        response = await stock.post(body)
        if response.status_code == 200:
            return "moved"
        assert error(response) == (409, "STOCK_INSUFFICIENT"), response.text
        return "short"

    results = await behind_the_balance_rows(stock, test_database, item, [racer, racer])
    assert sorted(results) == ["moved", "short"]
    assert held(stock) == {str(stock.place["place_id"]): 0, str(shelf["place_id"]): 5}
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(5, 1000)]
    assert stock.counts()["stock_documents"] == 2


@pytest.mark.parametrize("raw_sql", [False, True])
async def test_opposite_transfers_wait_in_one_order_and_both_pass(
    stock: Stock, test_database: ProvisionedDatabase, raw_sql: bool
) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    await received(stock, item, "5", "10.00", place_id=shelf["place_id"])

    async def move(source: Place, to: Place, quantity: int) -> str:
        if raw_sql:
            await hand_transfer(stock, item, to, source=source, quantity=quantity)
            return "moved"
        line: dict[str, object] = {"item_id": item, "quantity": str(quantity)}
        response = await stock.post(transfer(stock, to, [line], place_id=source["place_id"]))
        assert response.status_code == 200, response.text
        return "moved"

    # Each takes the two balance rows in the same order, so neither holds what the other
    # waits for.
    results = await behind_the_balance_rows(
        stock,
        test_database,
        item,
        [lambda: move(stock.place, shelf, 2), lambda: move(shelf, stock.place, 3)],
    )
    assert results == ["moved", "moved"]
    assert held(stock) == {str(stock.place["place_id"]): 6, str(shelf["place_id"]): 4}
    assert stock.rows("select quantity,value_minor from gba.stock_costs") == [(10, 2000)]
    assert stock.reconciled() == (2000, 2000)


async def test_transfer_and_write_off_of_the_last_balance_have_one_winner(
    stock: Stock, test_database: ProvisionedDatabase
) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    line: dict[str, object] = {"item_id": item, "quantity": "5"}

    async def answer(body: Place) -> str:
        response = await stock.post(body)
        if response.status_code == 200:
            return "done"
        assert error(response) == (409, "STOCK_INSUFFICIENT"), response.text
        return "short"

    # The write-off holds the ledger lock and the transfer does not: they meet at the
    # balance row.
    results = await behind_the_balance_rows(
        stock,
        test_database,
        item,
        [lambda: answer(transfer(stock, shelf, [line])), lambda: answer(write_off(stock, [line]))],
    )
    assert sorted(results) == ["done", "short"]
    # Whichever won, the places hold exactly what the cost row of the owner says.
    cost = stock.rows("select quantity,value_minor from gba.stock_costs")
    assert cost in ([(5, 1000)], [(0, 0)])
    assert sum(held(stock).values()) == cost[0][0]
    value, posted = stock.reconciled()
    assert value == posted == cost[0][1]


async def test_disabled_inventory_refuses_transfers(stock: Stock) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    await Config(stock.inventory.client, stock.inventory.idp).publish(
        stock.inventory.manager, stock.tenant, 1, ["booking_resources", "finance"]
    )
    refused = await stock.post(transfer(stock, shelf, [{"item_id": item, "quantity": "1"}]))
    assert error(refused) == (409, "MODULE_DISABLED"), refused.text
    with pytest.raises(psycopg.DatabaseError) as gated:
        await hand_transfer(stock, item, shelf, quantity=1)
    assert gated.value.sqlstate == "GBM01"
    assert stock.counts()["stock_documents"] == 1
    assert held(stock) == {str(stock.place["place_id"]): 5}
