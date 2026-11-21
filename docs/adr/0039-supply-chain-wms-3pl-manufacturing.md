# ADR-0039 — Supply Chain, Multi-Warehouse 3PL WMS, Lot/Serial Traceability & Manufacturing Costing (`SUPPLY-01`)

- **Status**: Proposed (2026-11-21)
- **Stage**: Master Plan §13 Stage 6 (`SUPPLY-01`)
- **Depends on**: `ADR-0014` (location scope), `ADR-0015` (legal entities & counterparties), `ADR-0019` (module gates), `ADR-0023` (ledger), `ADR-0024` (`FIN-03` financial documents & credit notes), `ADR-0026` (`STOCK-01` materials, storage places, stock documents, movements, balances, and moving-average cost).

## Context

Master Plan §13 Stage 6 and §14.1.1 (`SUPPLY-01`) require:
1. **Extending `STOCK-01` rather than replacing it with a second inventory ledger** («исходные базовые складские движения расширены, не заменены вторым учетом»).
2. **Multi-warehouse WMS & 3PL goods-owner isolation** («Товар другого собственника недоступен; отдельный учет собственников товаров»):
   - A warehouse branch stores both **company-owned goods** (`owner_kind = 'company_entity'`, bound to a `gba.legal_entities` row and valued in `STOCK-01` `gba.stock_costs` / `gba.journal_entries`) and **3PL customer-owned goods** (`owner_kind = 'counterparty_3pl'`, bound to a bailor `gba.counterparties` row and held in custody off the company's balance sheet).
   - No operation (putaway into a dedicated bin, lot allocation, production issue, sales/3PL shipment, or return) may ever cross `goods_owner_id` boundaries.
3. **Lot/batch (`supply_lots`) and serial-number (`supply_serial_units`) traceability across warehouse bins (`supply_warehouse_bins`)**:
   - Every lot belongs to one `(tenant_id, item_id, goods_owner_id)`.
   - Every warehouse bin belongs to one `(tenant_id, location_id, place_id)` of `STOCK-01` `gba.stock_places` (with optional `dedicated_owner_id`).
   - Company-owned inbound, outbound, transfer, production, and return lot movements link directly to their authoritative `STOCK-01` `(stock_document_id, stock_line_no)` in `gba.stock_document_lines`.
4. **Manufacturing (`Производство`: BOM -> Work Order -> Material Issue -> QC -> Finished-Goods Output / Unused Material Return -> Costing)**:
   - Component issues post real `STOCK-01` `write_off` (`reason = 'used'`) documents at moving-average cost and deduct exact component lot/bin/serial balances.
   - Unused component returns post real `STOCK-01` `return` (`reason = 'unused'`) documents against the original `write_off` line, restoring component lot balances and reducing work-order net material cost.
   - Finished-goods output mints/credits a finished-goods lot at exact total cost (`material_cost_minor + labor_cost_minor + overhead_cost_minor`) and posts a real `STOCK-01` `receipt` document so `gba.stock_balances`, `gba.stock_costs`, and the general ledger stay 100% reconciled.
5. **Advanced Trade & 3PL Fulfillment (`Розница, интернет-магазины, опт` & `3PL`: Quote -> Order -> Allocation -> Shipment -> Return)**:
   - Channel and contract price lists (`retail`, `wholesale`, `ecommerce`, `3pl_handling`).
   - Company sales shipments post a real `STOCK-01` `write_off` (`reason = 'used'`) for COGS, deduct the allocated lot/bin/serial balances, and create a real `FIN-03` receivable invoice draft (`financial_documents.save_draft`).
   - Customer sales returns post a real `STOCK-01` `return` (`reason = 'unused'`) against the shipment's `write_off` line, restore the exact returned lot/bin/serial balances, and create a real `FIN-03` credit note draft (`credit_notes.save_draft`).
   - 3PL fulfillment orders allocate and ship only the bailor's (`counterparty_3pl`) own lots/serials and bill 3PL handling/storage fees via `FIN-03`.

## Decision

1. **Module & Permissions**:
   - Register optional module `supply` (`"Supply chain, 3PL WMS and manufacturing"`, `Readiness.IMPLEMENTED`, `enableable=False`, `depends_on=("counterparties", "finance_documents", "inventory")`, `MODULE_REGISTRY_VERSION = 10`).
   - Add permissions `SUPPLY_READ = "supply.read"`, `SUPPLY_WORK = "supply.work"`, `SUPPLY_MANAGE = "supply.manage"` (`PERMISSIONS_VERSION = 19`, non-delegable).
   - Keep `STOCK-01`'s 12 core `stock_*` tables and `inventory_guard.py` 100% unmodified.
2. **Four Vertical Slices**:
   - **Slice 1 (`0138_supply_wms_owners_and_lots.sql`)**: Goods owners (`company_entity` & `counterparty_3pl`), warehouse bins, lots/batches, serial units, lot/bin balances, and WMS movements linked to `STOCK-01` documents with strict DB-level owner isolation.
   - **Slice 2 (`0139_supply_manufacturing_and_costing.sql`)**: Versioned BOMs, production work orders, component lot consumption (`STOCK-01` `write_off`), unused material return (`STOCK-01` `return`), quality control, and finished-goods lot output (`STOCK-01` `receipt`) with exact cost conservation.
   - **Slice 3 (`0140_supply_trade_and_3pl_orders.sql`)**: Channel/contract price lists, retail/wholesale & 3PL orders, lot-isolated allocation & shipment (`STOCK-01` COGS `write_off` + `FIN-03` receivable invoice), and customer returns (`STOCK-01` `return` + `FIN-03` credit note).
   - **Slice 4 (no migration)**: `/supply/` 4-tab responsive workspace + real Chromium desktop & mobile (`390px`) Playwright E2E with two-owner isolation proof, lot/cost conservation proof, `axe-core`, and PostgreSQL 18 read-back.
3. **Database-First Invariants (Invoker Rights Only)**:
   - Zero `SECURITY DEFINER` functions.
   - Every table has `ENABLE ROW LEVEL SECURITY`, `FORCE ROW LEVEL SECURITY`, tenant isolation policy, restrictive branch-scope policy (`-- Supply ... branch scope:` at EOF), and `require_enabled_module('supply')` write triggers.
   - Composite foreign keys `(tenant_id, lot_id, item_id, goods_owner_id)` and `(tenant_id, bin_id, place_id, location_id)` make cross-owner lot/serial access or cross-place bin mismatch impossible at the PostgreSQL constraint layer.
