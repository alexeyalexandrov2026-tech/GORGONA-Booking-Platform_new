"""Damaged boundaries of J2 fail closed, on the executor's disposable database."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration import test_stock as shared
from tests.integration.test_inventory import error
from tests.integration.test_stock import Stock

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a

COMPANY = "(gba.current_location_id() is null)"
PERMISSIVE_ORIGIN = (
    "create or replace function gba.enforce_stock_origin() returns trigger "
    "language plpgsql as $$ begin return new; end; $$"
)
# name: (damage, repair). The function case reads its repair from the catalog.
DAMAGE: dict[str, tuple[str, str]] = {
    "policy": (
        "alter policy stock_costs_location_scope on gba.stock_costs using (true) with check (true)",
        "alter policy stock_costs_location_scope on gba.stock_costs "
        f"using {COMPANY} with check {COMPANY}",
    ),
    "extra_policy": (
        "create policy stock_valuations_open on gba.stock_valuations for select using (true)",
        "drop policy stock_valuations_open on gba.stock_valuations",
    ),
    "immutability": (
        "alter table gba.stock_movements disable trigger stock_movements_immutable",
        "alter table gba.stock_movements enable trigger stock_movements_immutable",
    ),
    "module_gate": (
        "alter table gba.stock_documents disable trigger stock_documents_require_inventory",
        "alter table gba.stock_documents enable trigger stock_documents_require_inventory",
    ),
    "constraint": (
        "alter table gba.stock_balances drop constraint stock_balances_quantity_check",
        "alter table gba.stock_balances add constraint stock_balances_quantity_check "
        "check (quantity between 0 and 999999999999999)",
    ),
    "grant": (
        "grant update on gba.stock_documents to gba_runtime",
        "revoke update on gba.stock_documents from gba_runtime",
    ),
    "row_security": (
        "alter table gba.stock_document_postings no force row level security",
        "alter table gba.stock_document_postings force row level security",
    ),
    "balance_check": (
        "alter table gba.stock_balances disable trigger stock_balances_balanced",
        "alter table gba.stock_balances enable trigger stock_balances_balanced",
    ),
    "journal_origin": (
        "alter table gba.journal_entries disable trigger journal_entries_stock_origin",
        "alter table gba.journal_entries enable trigger journal_entries_stock_origin",
    ),
    "journal_consistency": (
        "alter table gba.journal_lines disable trigger journal_lines_stock_consistent",
        "alter table gba.journal_lines enable trigger journal_lines_stock_consistent",
    ),
    "function": (PERMISSIVE_ORIGIN, ""),
}


@pytest.mark.parametrize("damage", sorted(DAMAGE))
async def test_damaged_stock_schema_refuses_reads_and_writes(
    stock: Stock,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    damage: str,
) -> None:
    assert (await stock.set_rules()).status_code == 200
    item = await stock.inventory.item(quantity_scale=0)
    line: dict[str, object] = {"item_id": item["item_id"], "quantity": "1", "amount": "1.00"}
    posted = await stock.post(stock.receipt([line]))
    assert posted.status_code == 200, posted.text
    change, restore = DAMAGE[damage]
    if damage == "function":
        row = owner_conn.execute(
            "select pg_get_functiondef('gba.enforce_stock_origin()'::regprocedure)"
        ).fetchone()
        assert row is not None
        restore = str(row[0])
    reads = (
        "/documents",
        f"/documents/{posted.json()['document_id']}",
        "/balances",
        "/costs",
        f"/posting-rules/{stock.book}",
        "/items",
    )
    try:
        owner_conn.execute(change.encode("utf-8"))
        async with tenant_transaction(app_pool, stock.tenant) as conn:
            with pytest.raises(DatabaseUnavailableError):
                await assert_inventory_ready(conn)
        for path in reads:
            assert error(await stock.inventory.get(path)) == (503, "DATABASE_UNAVAILABLE"), path
        assert error(await stock.post(stock.receipt([line]))) == (503, "DATABASE_UNAVAILABLE")
        assert error(await stock.set_rules(1, surplus="4000")) == (503, "DATABASE_UNAVAILABLE")
    finally:
        owner_conn.execute(restore.encode("utf-8"))
    async with tenant_transaction(app_pool, stock.tenant) as conn:
        await assert_inventory_ready(conn)
    for path in reads:
        assert (await stock.inventory.get(path)).status_code == 200, path
    assert (await stock.post(stock.receipt([line]), uuid7())).status_code == 200
    assert stock.counts()["stock_documents"] == 2
