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
from tests.integration.test_stock_returns import hand_return
from tests.integration.test_stock_running_totals import UNCHAINED
from tests.integration.test_stock_transfers import hand_transfer, transfer
from tests.integration.test_stock_write_offs import hand_write_off, received, write_off

pytestmark = pytest.mark.anyio
# Package K tables of migrations 0044-0046, 0050 and 0052, which the upgrade to the latest state
# creates.
K_TABLES = {
    "provider_receipt_connections",
    "provider_event_inbox",
    "provider_event_deliveries",
    "provider_event_attestations",
    "provider_verification_configs",
    "provider_receipt_routes",
    "provider_operations",
    "provider_event_leases",
    "provider_event_decisions",
    # K3a (0052): the clearing account and the provenance of provider payments.
    "provider_clearing_accounts",
    "external_payment_provenance",
    # K4b (0053): acknowledgements of decisions without an operation.
    "provider_event_acknowledgements",
    # K3b (0054): links of manual payments to provider operations.
    "provider_payment_links",
    # K0b (0057): the owner's admissions of receipt connections.
    "provider_connection_admissions",
}
previous_stock_database = previous_admission_database
stock = test_stock.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
# Every migration: the packaged guards approve only the latest state (K1i added 0047).
LATEST = len(load_migrations())
# The columns that every schema since 0037 has in the tables later slices only add to.
GAINED = {
    # Migration 0042 gives every movement its place in the history of its balance.
    "stock_movements": (
        "select tenant_id,document_id,line_no,direction,location_id,place_id,item_id,"
        "legal_entity_id,quantity,created_at from gba.stock_movements "
        "order by tenant_id,document_id,line_no,direction"
    ),
    "stock_documents": (
        "select tenant_id,id,kind,reason,legal_entity_id,place_id,location_id,document_date,"
        "supplier_id,supplier_document,line_count,created_by,created_at,"
        "created_transaction::text from gba.stock_documents order by tenant_id,id"
    ),
    "stock_document_lines": (
        "select tenant_id,document_id,line_no,location_id,item_id,quantity "
        "from gba.stock_document_lines order by tenant_id,document_id,line_no"
    ),
    "stock_valuations": (
        "select tenant_id,document_id,line_no,direction,legal_entity_id,item_id,quantity,"
        "amount_minor from gba.stock_valuations order by tenant_id,document_id,line_no"
    ),
}
# What migration 0040 adds, and the destination of a transfer that 0039 added.
FRESH = (
    "select (select count(*) from gba.stock_documents where source_document_id is not null),"
    "(select count(*) from gba.stock_document_lines "
    "where source_document_id is not null or source_line_no is not null),"
    "(select count(*) from gba.stock_valuations where basis_minor is not null),"
    "(select count(*) from gba.stock_documents where to_place_id is not null)"
)
# After the upgrade one unit goes back to the supplier, one is used and one is moved:
# the cost row of the owner and what the two places hold, by the schema the data came from.
LEFT = {
    37: ((3, 600), [(1,), (2,)]),
    38: ((2, 400), [(1,), (1,)]),
    39: ((2, 400), [(0,), (2,)]),
}


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
    assert set(after) - set(before) == set(INVENTORY_TABLES) - set(J1_TABLES) | K_TABLES
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


@pytest.mark.parametrize("start", sorted(LEFT))
async def test_nonempty_documents_upgrade_and_earlier_stock_returns_leaves_and_moves(
    stock: Stock,
    test_database: ProvisionedDatabase,
    previous_stock_database: ProvisionedDatabase,
    start: int,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    shelf = await stock.inventory.place(stock.inventory.world.a.location_id)
    item = (await stock.inventory.item(quantity_scale=0))["item_id"]
    await received(stock, item, "5", "10.00")
    source = stock.rows(
        "select id from gba.stock_documents where legal_entity_id=%s", stock.entity
    )[0][0]
    one: dict[str, object] = {"item_id": item, "quantity": "1"}
    if start >= 38:
        # The schema of write-offs also holds one: four units worth 8.00 are left.
        used = await stock.post(write_off(stock, [one]))
        assert used.status_code == 200, used.text
    if start >= 39:
        # The schema of transfers also holds one: three units here and one on the shelf.
        moved = await stock.post(transfer(stock, shelf, [one]))
        assert moved.status_code == 200, moved.text
    target = previous_stock_database
    apply_migrations(target.owner_dsn, load_migrations()[:start])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    # The old schema really holds the posted documents and their cost before the upgrade.
    assert before["stock_documents"][0] >= start - 36
    assert before["stock_costs"][0] >= 1
    with psycopg.connect(target.admin_dsn) as conn:
        rows = {table: conn.execute(query).fetchall() for table, query in GAINED.items()}
    prior = checksums(target)
    latest = load_migrations()[:LATEST]
    applied = apply_migrations(target.owner_dsn, latest)
    assert [migration.version for migration in applied] == list(range(start + 1, LATEST + 1))
    assert apply_migrations(target.owner_dsn, latest) == []
    # No stock table is added and no row is rewritten: documents, lines and valuations only
    # gain empty columns. The empty package K tables come from 0044-0046.
    after = snapshot(target)
    assert set(after) == set(before) | K_TABLES
    assert all(after[table][0] == 0 for table in K_TABLES)
    assert all(after[table] == before[table] for table in before if table not in GAINED)
    with psycopg.connect(target.admin_dsn) as conn:
        for table, query in GAINED.items():
            assert conn.execute(query).fetchall() == rows[table], table
        fresh = conn.execute(FRESH).fetchone()
        # The upgraded history carries its running totals and ends in today's totals.
        broken = {name: conn.execute(query).fetchone() for name, query in UNCHAINED.items()}
    assert broken == dict.fromkeys(UNCHAINED, (0,))
    assert fresh is not None
    assert fresh[:3] == (0, 0, 0)
    assert fresh[3] >= 1 if start >= 39 else fresh[3] == 0
    current = checksums(target)
    assert {number: current[number] for number in prior} == prior
    pool = create_runtime_pool(target.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, stock.tenant) as conn:
            await assert_location_scope_ready(conn)
            await assert_inventory_ready(conn)
        # Stock received before the upgrade goes back to its supplier after it, leaves at
        # its average cost, and moves.
        await hand_return(
            stock,
            source,
            item,
            pool,
            quantity=1,
            amount=200,
            basis=200,
            journal=[("1400", "debit", 200), ("1300", "credit", 200)],
        )
        await hand_write_off(stock, item, pool, quantity=1, amount=200)
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
        assert (cost, places) == LEFT[start]
    finally:
        await pool.close()
