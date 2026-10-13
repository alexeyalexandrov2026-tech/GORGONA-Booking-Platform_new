"""Damaged boundaries of J1 fail closed, on the executor's disposable database."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration import test_inventory as shared
from tests.integration.test_inventory import Inventory, error, item_body, place_body

pytestmark = pytest.mark.anyio
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a

SCOPE = "(gba.current_location_id() is null or location_id=gba.current_location_id())"
PERMISSIVE_GUARD = (
    "create or replace function gba.guard_stock_item_version() returns trigger "
    "language plpgsql as $$ begin return new; end; $$"
)
# name: (damage, repair). The function case reads its repair from the catalog.
DAMAGE: dict[str, tuple[str, str]] = {
    "policy": (
        "alter policy stock_places_location_scope on gba.stock_places "
        "using (true) with check (true)",
        "alter policy stock_places_location_scope on gba.stock_places "
        f"using {SCOPE} with check {SCOPE}",
    ),
    "extra_policy": (
        "create policy stock_items_open on gba.stock_items for select using (true)",
        "drop policy stock_items_open on gba.stock_items",
    ),
    "immutability": (
        "alter table gba.stock_item_versions disable trigger stock_item_versions_immutable",
        "alter table gba.stock_item_versions enable trigger stock_item_versions_immutable",
    ),
    "module_gate": (
        "alter table gba.stock_places disable trigger stock_places_require_inventory",
        "alter table gba.stock_places enable trigger stock_places_require_inventory",
    ),
    "constraint": (
        "alter table gba.stock_items drop constraint stock_items_scale_check",
        "alter table gba.stock_items add constraint stock_items_scale_check "
        "check (quantity_scale between 0 and 3)",
    ),
    "grant": (
        "grant delete on gba.stock_place_versions to gba_runtime",
        "revoke delete on gba.stock_place_versions from gba_runtime",
    ),
    "row_security": (
        "alter table gba.stock_item_versions no force row level security",
        "alter table gba.stock_item_versions force row level security",
    ),
    "function": (PERMISSIVE_GUARD, ""),
}


@pytest.mark.parametrize("damage", sorted(DAMAGE))
async def test_damaged_inventory_schema_refuses_reads_and_writes(
    inventory: Inventory,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    damage: str,
) -> None:
    home = inventory.world.a.location_id
    material = await inventory.item()
    change, restore = DAMAGE[damage]
    if damage == "function":
        row = owner_conn.execute(
            "select pg_get_functiondef('gba.guard_stock_item_version()'::regprocedure)"
        ).fetchone()
        assert row is not None
        restore = str(row[0])
    try:
        owner_conn.execute(change.encode("utf-8"))
        async with tenant_transaction(app_pool, inventory.tenant) as conn:
            with pytest.raises(DatabaseUnavailableError):
                await assert_inventory_ready(conn)
        for path in ("/items", f"/items/{material['item_id']}", "/places"):
            assert error(await inventory.get(path)) == (503, "DATABASE_UNAVAILABLE")
        for path, body in (
            (f"/items/{uuid7()}", item_body()),
            (f"/places/{uuid7()}", place_body(home)),
        ):
            assert error(await inventory.put(path, body)) == (503, "DATABASE_UNAVAILABLE")
    finally:
        owner_conn.execute(restore.encode("utf-8"))
    async with tenant_transaction(app_pool, inventory.tenant) as conn:
        await assert_inventory_ready(conn)
    assert (await inventory.get(f"/items/{material['item_id']}")).json() == material
