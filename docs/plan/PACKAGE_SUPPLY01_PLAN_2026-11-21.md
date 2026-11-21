# Package Plan — `SUPPLY-01`: Advanced Trade, Multi-Warehouse 3PL WMS, Lot/Serial Traceability & Manufacturing Costing (2026-11-21)

Aligned with `docs/plan/GORGONA_MASTER_PLAN.md` §10, §13 Stage 6, §14.1, §14.1.1 (`SUPPLY-01`), and `docs/adr/0039-supply-chain-wms-3pl-manufacturing.md`.

## Acceptance Criterion (`SUPPLY-01`)
> «Товар другого собственника недоступен; выпуск/возврат сохраняют партии, движения и себестоимость»
> «исходные базовые складские движения расширены, не заменены вторым учетом»

## Slice Breakdown

| Slice | Branch | Migration | Scope |
|---|---|---|---|
| **Slice 1** | `codex/package-supply-01-wms-owners-and-lots` | `0138_supply_wms_owners_and_lots.sql` | Register `supply` module (`MODULE_REGISTRY_VERSION=10`, `Readiness.IMPLEMENTED`, `enableable=False`) & permissions (`SUPPLY_READ/WORK/MANAGE`, `PERMISSIONS_VERSION=19`); goods owners (`company_entity` vs `counterparty_3pl`), warehouse zones/bins (`supply_warehouse_bins` with optional `dedicated_owner_id`), lots/batches (`supply_lots`), serial units (`supply_serial_units`), bin/lot running balances (`supply_lot_balances`), and WMS movements (`supply_wms_movements`) linked to `STOCK-01` documents (`gba.stock_document_lines`) with DB-enforced goods-owner isolation. |
| **Slice 2** | `codex/package-supply-01-manufacturing-and-costing` | `0139_supply_manufacturing_and_costing.sql` | Bills of Materials (`supply_boms`, `supply_bom_components`, `supply_bom_operations`), production work orders (`supply_work_orders`), component lot consumption (`supply_work_order_issues` posting real `STOCK-01` `write_off`), unused material return (`supply_work_order_returns` posting real `STOCK-01` `return` and restoring lot balance & cost), QC inspection (`supply_work_order_qc`), and finished-goods lot output (`supply_work_order_outputs` minting output lot and posting real `STOCK-01` `receipt` at exact material + labor + overhead cost). |
| **Slice 3** | `codex/package-supply-01-trade-and-3pl-orders` | `0140_supply_trade_and_3pl_orders.sql` | Channel & counterparty contract price lists (`supply_price_lists`, `supply_price_list_items`), retail/wholesale & 3PL fulfillment orders (`supply_trade_orders`, `supply_trade_order_lines`), owner-isolated lot/serial allocation & shipment (`supply_order_shipments` posting real `STOCK-01` COGS `write_off` + `FIN-03` receivable invoice), and customer returns (`supply_order_returns` restoring exact lot/serial balance and posting real `STOCK-01` `return` + `FIN-03` credit note). |
| **Slice 4** | `codex/package-supply-01-ui` | *(none)* | `/supply/` 4-tab operations UI (`web/components/supply.tsx`, `web/lib/supply-contracts.ts`, `web/lib/supply-api.ts`) + real Chromium desktop & mobile (`390px`) Playwright E2E (`web/tests/supply.spec.ts`, `api/tests/integration/test_supply_browser.py`) verifying goods-owner isolation, production output/return lot & cost conservation, customer shipment/return lot & cost conservation, `axe-core`, and PostgreSQL 18 read-back. |

## Non-Negotiable Constraints
1. `STOCK-01`'s 12 core `stock_*` tables and `inventory_guard.py` remain 100% untouched.
2. Company-owned inventory valuation and ledger entries flow exclusively through `STOCK-01` (`stock.post_receipt`, `stock.post_write_off`, `stock.post_return`, `stock.post_transfer`) and `FIN-03` (`financial_documents.save_draft`, `credit_notes.save_draft`).
3. `readiness_registry.py` remains untouched (`SUPPLY-01` stays `planned`, `supply` stays `enableable=False`).
4. Invoker rights only (zero `SECURITY DEFINER`), tenant + restrictive branch RLS on every table, and full 6-worker parallel verification on `gorgona-dev` before pushing each slice branch (no PRs).
