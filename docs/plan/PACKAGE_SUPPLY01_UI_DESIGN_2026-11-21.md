# Design Note — `SUPPLY-01` Slice 4: `/supply/` 4-Tab Operations UI & Real-Browser E2E (2026-11-21)

Aligned with `docs/adr/0039-supply-chain-wms-3pl-manufacturing.md`, `docs/plan/PACKAGE_SUPPLY01_PLAN_2026-11-21.md`, and `docs/plan/GORGONA_MASTER_PLAN.md` §14.1.1 (`SUPPLY-01`: «Товар другого собственника недоступен; выпуск/возврат сохраняют партии, движения и себестоимость»).

## Screen Layout (`/supply/`)
Four accessible tabs with keyboard navigation (`ArrowLeft`/`ArrowRight`), WCAG AAA active/hover contrast, focusable responsive tables (`tabIndex={0}`, `role="region"`), and zero horizontal overflow at `390px`:
1. **WMS Owners & Bins**: list/create/update goods owners (`company_entity` vs `counterparty_3pl`), warehouse zones/bins (`supply_warehouse_bins` with optional `dedicated_owner_id`), lots/batches (`supply_lots`), and serial units (`supply_serial_units`).
2. **Lots, Balances & Movements**: live owner-isolated bin/lot balances (`supply_lot_balances`) and WMS movement history (`supply_wms_movements`); record inbound putaway (auto-posting `STOCK-01` `receipt` for company owners), bin relocation (`STOCK-01` `transfer` across places), and outbound picking (`STOCK-01` `write_off`).
3. **Manufacturing & Costing**: versioned Bills of Materials (`supply_boms`), production work orders (`supply_work_orders`), component lot issue (`supply_work_order_issues` -> `STOCK-01` `write_off`), unused material return (`supply_work_order_returns` -> `STOCK-01` `return` restoring lot balance & cost), QC inspection (`supply_work_order_qc`), and finished-goods lot output (`supply_work_order_outputs` -> `STOCK-01` `receipt` at exact material + labor + overhead cost).
4. **Trade & 3PL Orders**: channel & contract price lists (`supply_price_lists`), retail/wholesale & 3PL fulfillment orders (`supply_trade_orders`), owner-isolated lot/serial shipment (`supply_order_shipments` -> `STOCK-01` COGS `write_off` + `FIN-03` receivable invoice), and customer return (`supply_order_returns` -> `STOCK-01` `return` + `FIN-03` credit note draft restoring exact lot/serial balance and cost).

## Verification
- Strict Zod contracts (`web/lib/supply-contracts.ts`, wired into `web/lib/management-contracts.ts`) + Playwright unit contract tests (`web/tests/supply-contracts.spec.ts`).
- Real Chromium desktop + mobile (`390px`) E2E (`web/tests/supply.spec.ts` + `api/tests/integration/test_supply_browser.py`) exercising `axe-core` on every tab, goods-owner isolation negative proof (`409 SUPPLY_OWNER_MISMATCH` surfaced in UI when attempting to use a 3PL bailor lot/bin for a company operation), manufacturing work-order issue/return/QC/output lot & cost conservation, trade order shipment/return lot & cost conservation, and PostgreSQL 18 read-back.
