"""Nonempty stock data of earlier slices upgrades to the current schema without rewriting facts."""

import psycopg
import pytest

from gorgona_booking.db.inventory_guard import INVENTORY_TABLES, assert_inventory_ready
from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import create_runtime_pool, tenant_transaction
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from tests.integration import test_inventory as shared
from tests.integration import test_stock
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_inventory import J1_TABLES, Inventory
from tests.integration.test_provider_admission_upgrade import previous_admission_database
from tests.integration.test_stock import Stock
from tests.integration.test_stock_transfers import hand_transfer
from tests.integration.test_stock_write_offs import hand_write_off, received, write_off

pytestmark = pytest.mark.anyio
previous_stock_database = previous_admission_database
stock = test_stock.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
LATEST = 39
# The columns of a document that every schema since 0037 has; later slices only add to them.
DOCUMENTS = (
    "select tenant_id,id,kind,reason,legal_entity_id,place_id,location_id,document_date,"
    "supplier_id,supplier_document,line_count,created_by,created_at,created_transaction::text "
    "from gba.stock_documents order by tenant_id,id"
)


def checksums(database: ProvisionedDatabase) -> dict[int, str]:
    with psycopg.connect(database.owner_dsn) as conn:
        return dict(conn.execute("select version,checksum from public.gba_schema_migrations"))


async def test_nonempty_0036_upgrade_keeps_materials_places_and_prior_checksums(
    inventory: Inventory,
    test_database: ProvisionedDatabase,
    previous_stock_database: ProvisionedDatabase,
) -> None:
    home = inventory.world.a.location_id
    await inventory.item()
    await inventory.place(home)
    await inventory.place(home)
    target = previous_stock_database
    apply_migrations(target.owner_dsn, load_migrations()[:36])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    # The old schema really holds materials and places before the upgrade.
    assert before["stock_items"][0] >= 1
    assert before["stock_places"][0] >= 2
    assert before["stock_place_versions"][0] >= before["stock_places"][0]
    prior = checksums(target)
    latest = load_migrations()[:LATEST]
    applied = apply_migrations(target.owner_dsn, latest)
    assert [migration.version for migration in applied] == list(range(37, LATEST + 1))
    assert apply_migrations(target.owner_dsn, latest) == []
    after = snapshot(target)
    assert {table: after[table] for table in before} == before
    assert set(after) - set(before) == set(INVENTORY_TABLES) - set(J1_TABLES)
    assert all(after[table][0] == 0 for table in set(after) - set(before))
    current = checksums(target)
    assert {number: current[number] for number in prior} == prior
    pool = create_runtime_pool(target.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, inventory.tenant) as conn:
            # The journal source kinds changed: the ledger guards accept the new check.
            await assert_location_scope_ready(conn)
            await assert_inventory_ready(conn)
    finally:
        await pool.close()


@pytest.mark.parametrize("start", [37, 38])
async def test_nonempty_documents_upgrade_and_earlier_stock_leaves_and_moves(
    stock: Stock,
    test_database: ProvisionedDatabase,
    previous_stock_database: ProvisionedDatabase,
    start: int,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    if start == 38:
        # The schema of write-offs also holds one: four units worth 8.00 are left.
        used = await stock.post(write_off(stock, [{"item_id": item, "quantity": "1"}]))
        assert used.status_code == 200, used.text
    target = previous_stock_database
    apply_migrations(target.owner_dsn, load_migrations()[:start])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    # The old schema really holds the posted documents and their cost before the upgrade.
    assert before["stock_documents"][0] >= start - 36
    assert before["stock_costs"][0] >= 1
    with psycopg.connect(target.admin_dsn) as conn:
        rows = conn.execute(DOCUMENTS).fetchall()
    prior = checksums(target)
    latest = load_migrations()[:LATEST]
    applied = apply_migrations(target.owner_dsn, latest)
    assert [migration.version for migration in applied] == list(range(start + 1, LATEST + 1))
    assert apply_migrations(target.owner_dsn, latest) == []
    # No table is added and no row is rewritten: a document only gains its empty
    # destination columns.
    after = snapshot(target)
    assert set(after) == set(before)
    assert all(after[table] == before[table] for table in before if table != "stock_documents")
    with psycopg.connect(target.admin_dsn) as conn:
        assert conn.execute(DOCUMENTS).fetchall() == rows
        moved = conn.execute(
            "select count(*) from gba.stock_documents "
            "where to_place_id is not null or to_location_id is not null"
        ).fetchone()
    assert moved == (0,)
    current = checksums(target)
    assert {number: current[number] for number in prior} == prior
    pool = create_runtime_pool(target.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, stock.tenant) as conn:
            await assert_location_scope_ready(conn)
            await assert_inventory_ready(conn)
        # Stock received before the upgrade leaves after it at its average cost, and moves.
        await hand_write_off(stock, item, pool, quantity=2, amount=400)
        await hand_transfer(stock, item, shelf, pool, quantity=1)
        async with tenant_transaction(pool, stock.tenant) as conn:
            cost = await (
                await conn.execute(
                    "select quantity,value_minor from gba.stock_costs where item_id=%s", (item,)
                )
            ).fetchone()
            places = await (
                await conn.execute(
                    "select quantity from gba.stock_balances where item_id=%s order by quantity",
                    (item,),
                )
            ).fetchall()
        left = 40 - start
        assert cost == (left, left * 200)
        assert places == [(1,), (left - 1,)]
    finally:
        await pool.close()
