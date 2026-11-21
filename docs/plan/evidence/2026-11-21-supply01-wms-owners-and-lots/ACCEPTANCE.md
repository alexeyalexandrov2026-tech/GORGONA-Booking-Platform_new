# Acceptance Evidence — SUPPLY-01 Slice 1: Multi-Warehouse WMS Bins, Goods-Owner Isolation & Lot/Serial Tracking (2026-11-21)

- **Branch**: `codex/package-supply-01-wms-owners-and-lots`
- **Base commit**: `48eeb0905bd3369ede58cbff49ab7afe99d9773a` (`codex/package-pro-01-ui`)
- **Verified code commit**: `7ecf6c8e4f5c625713674011bd14c0e54f71ec0b` (tree `3ec7966a127da4f84934b7e87b300eff924839aa`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0138_supply_wms_owners_and_lots.sql` (invoker rights only)
- **ADR & Plan**: `docs/adr/0039-supply-chain-wms-3pl-manufacturing.md`, `docs/plan/PACKAGE_SUPPLY01_PLAN_2026-11-21.md`

## Scope Delivered
1. Registered optional module `supply` (`Readiness.IMPLEMENTED`, `enableable=False`, `depends_on=("counterparties", "finance_documents", "inventory")`, `MODULE_REGISTRY_VERSION=10`) and permissions `SUPPLY_READ`, `SUPPLY_WORK`, `SUPPLY_MANAGE` (`PERMISSIONS_VERSION=19`, non-delegable).
2. Migration `0138_supply_wms_owners_and_lots.sql` adds 6 branch-scoped tables (`supply_goods_owners`, `supply_warehouse_bins`, `supply_lots`, `supply_lot_balances`, `supply_serial_units`, `supply_wms_movements`) with tenant RLS, restrictive branch RLS (`-- Supply WMS branch scope:`), `require_enabled_module('supply')`, and invoker-rights triggers enforcing dedicated-bin owner isolation and `STOCK-01` document consistency without altering the 12 core `stock_*` tables.
3. Inbound putaway, bin relocation, and outbound picking extending `STOCK-01` receipts, transfers, and write-offs for `company_entity` owners while isolating `counterparty_3pl` bailor goods off the company balance sheet.
4. Updated `schema_guard.py` (`_DEFINITIONS=210`, `_MODULE_TRIGGERS=65`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (639 files), `mypy src tests` (639 files): **PASS**
- `pytest tests/unit -q`: **929 passed, 0 failed**
- Focused integration + upgrade `0137 -> 0138`: **PASS**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `7ecf6c8e4f5c625713674011bd14c0e54f71ec0b`):
  - **3061 passed, 0 failed, 4 skipped** out of **3065** (`duplicates=0`, `count_ok=True`, wall time **1442.32s**; browser **49/49**, serial **216/216**).
