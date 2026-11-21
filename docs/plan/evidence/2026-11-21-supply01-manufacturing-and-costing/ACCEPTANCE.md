# Acceptance Evidence — SUPPLY-01 Slice 2: Manufacturing BOMs, Work Orders, QC & `STOCK-01` Lot/Cost Conservation (2026-11-21)

- **Branch**: `codex/package-supply-01-manufacturing-and-costing`
- **Base commit**: `06c959425f6ea2e60bc8a4dfe82fae4a862b5472` (`codex/package-supply-01-wms-owners-and-lots`)
- **Verified code commit**: `c838e4064cc8fb56688056de58a5d77c8adc435e` (tree `e24f256377d0d1ff3ec3ee0cdcd404bacb7e1aef`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0139_supply_manufacturing_and_costing.sql` (invoker rights only)
- **Design**: `docs/plan/PACKAGE_SUPPLY01_MANUFACTURING_DESIGN_2026-11-21.md`

## Scope Delivered
1. Migration `0139_supply_manufacturing_and_costing.sql` adds 7 branch-scoped tables (`supply_boms`, `supply_bom_components`, `supply_work_orders`, `supply_work_order_issues`, `supply_work_order_returns`, `supply_work_order_qc`, `supply_work_order_outputs`) with tenant RLS, restrictive branch RLS (`-- Supply manufacturing branch scope:`), `require_enabled_module('supply')`, and invoker-rights triggers enforcing `company_entity` work-order ownership and cross-owner component lot isolation.
2. Component lot consumption (`POST /work-orders/{id}/issues`) posts real `STOCK-01` `write_off` (`reason='used'`) documents, reads the exact moving-average valuation from `gba.stock_valuations`, deducts component lot balances, and records `production_issue` WMS movements.
3. Unused material return (`POST /work-orders/{id}/returns`) posts real `STOCK-01` `return` (`reason='unused'`) documents against the original `write_off` line, restores exact component lot balances, and credits returned material cost on the work order.
4. Quality control (`POST /work-orders/{id}/qc`) and finished-goods output (`POST /work-orders/{id}/output`) mint/update the output lot in `supply_lots` and post a real `STOCK-01` `receipt` (`reason='purchase'`) at exact `material_cost_minor + labor_cost_minor + overhead_cost_minor`, conserving lots, movements, and moving-average cost.
5. Updated `schema_guard.py` (`_DEFINITIONS=224`, `_MODULE_TRIGGERS=72`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (644 files), `mypy src tests` (644 files): **PASS**
- `pytest tests/unit -q`: **931 passed, 0 failed**
- Focused integration + upgrade `0138 -> 0139`: **PASS**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `c838e4064cc8fb56688056de58a5d77c8adc435e`):
  - **3065 passed, 0 failed, 4 skipped** out of **3069** (`duplicates=0`, `count_ok=True`, wall time **1520.04s**; browser **49/49**, serial **216/216**).
