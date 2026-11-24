# Acceptance Evidence — SUPPLY-01 Slice 3: Trade Price Lists, Retail/Wholesale & 3PL Orders, Shipments & Customer Returns (2026-11-21)

- **Branch**: `codex/package-supply-01-trade-and-3pl-orders`
- **Base commit**: `e42d1cc9f19016d994e0ef6c9e4f8f0a62cb01d7` (`codex/package-supply-01-manufacturing-and-costing`)
- **Verified code commit**: `9ef59ecd55197b67635de96314e62fd2e7112ffa` (tree `02f4e3f26b2fc5469f76464323bbdb506f93076a`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0140_supply_trade_and_3pl_orders.sql` (invoker rights only)

## Scope Delivered
1. Migration `0140_supply_trade_and_3pl_orders.sql` adds 6 branch-scoped tables (`supply_price_lists`, `supply_price_list_items`, `supply_trade_orders`, `supply_trade_order_lines`, `supply_order_shipments`, `supply_order_returns`) with tenant RLS, restrictive branch RLS (`-- Supply trade branch scope:`), `require_module_write_enabled('supply')`, and composite foreign keys enforcing goods-owner isolation across orders, lots, shipments, and returns.
2. Company retail/wholesale shipments post real `STOCK-01` COGS write-offs (`stock.post_document`) and `FIN-03` issued receivable invoices (`financial_documents.save_draft` + `issue_document`).
3. Customer returns restore exact lot/serial balances, post real `STOCK-01` returns restoring proportional COGS valuation, and save real `FIN-03` credit note drafts (`credit_notes.save_draft`).
4. Updated `schema_guard.py` (`_DEFINITIONS=236`, `_MODULE_TRIGGERS=78`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (648 files), `mypy src tests` (648 files): **PASS**
- `pytest tests/unit -q`: **935 passed, 0 failed**
- Focused integration + upgrade `0139 -> 0140`: **PASS**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `9ef59ecd55197b67635de96314e62fd2e7112ffa`):
  - **3070 passed, 0 failed, 4 skipped** out of **3074** (`duplicates=0`, `count_ok=True`, wall time **1472.66s**; browser **49/49**, serial **216/216**).
