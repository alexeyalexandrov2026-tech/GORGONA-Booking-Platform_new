"""Nonempty J1 and J2 data upgrade to the current stock schema without rewriting facts."""

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
from tests.integration.test_stock_write_offs import hand_write_off, received

pytestmark = pytest.mark.anyio
previous_stock_database = previous_admission_database
stock = test_stock.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a


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
    with psycopg.connect(target.owner_dsn) as conn:
        prior: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    latest = load_migrations()[:38]
    applied = apply_migrations(target.owner_dsn, latest)
    assert [migration.version for migration in applied] == [37, 38]
    assert apply_migrations(target.owner_dsn, latest) == []
    after = snapshot(target)
    assert {table: after[table] for table in before} == before
    assert set(after) - set(before) == set(INVENTORY_TABLES) - set(J1_TABLES)
    assert all(after[table][0] == 0 for table in set(after) - set(before))
    with psycopg.connect(target.owner_dsn) as conn:
        current: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
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


async def test_nonempty_0037_upgrade_keeps_receipts_and_writes_off_earlier_stock(
    stock: Stock,
    test_database: ProvisionedDatabase,
    previous_stock_database: ProvisionedDatabase,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    target = previous_stock_database
    apply_migrations(target.owner_dsn, load_migrations()[:37])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    # The receipt schema really holds a posted receipt and its cost before the upgrade.
    assert before["stock_documents"][0] >= 1
    assert before["stock_costs"][0] >= 1
    with psycopg.connect(target.owner_dsn) as conn:
        prior: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    current = load_migrations()[:38]
    applied = apply_migrations(target.owner_dsn, current)
    assert [migration.version for migration in applied] == [38]
    assert apply_migrations(target.owner_dsn, current) == []
    # Write-offs add no table and rewrite no row.
    assert snapshot(target) == before
    with psycopg.connect(target.owner_dsn) as conn:
        now: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    assert {number: now[number] for number in prior} == prior
    pool = create_runtime_pool(target.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, stock.tenant) as conn:
            await assert_location_scope_ready(conn)
            await assert_inventory_ready(conn)
        # Stock received before the upgrade leaves after it, at its average cost.
        await hand_write_off(stock, item, pool, quantity=2, amount=400)
        async with tenant_transaction(pool, stock.tenant) as conn:
            left = await (
                await conn.execute(
                    "select quantity,value_minor from gba.stock_costs where item_id=%s", (item,)
                )
            ).fetchone()
        assert left == (3, 600)
    finally:
        await pool.close()
