# Design Note — `SUPPLY-01` Slice 3 (`0140_supply_trade_and_3pl_orders.sql`): Channel & Contract Price Lists, Retail/Wholesale & 3PL Fulfillment Orders, Lot/Serial Shipments (`STOCK-01` COGS + `FIN-03` Invoice), and Customer Returns (`STOCK-01` Return + `FIN-03` Credit Note) (2026-11-21)

Aligned with `docs/plan/GORGONA_MASTER_PLAN.md` §10, §13 Stage 6, §14.1, §14.1.1 (`SUPPLY-01`), `docs/adr/0039-supply-chain-wms-3pl-manufacturing.md`, and `docs/plan/PACKAGE_SUPPLY01_PLAN_2026-11-21.md`.

## 1. Scope & Acceptance Invariants
- **Channel & Counterparty Contract Price Lists (`gba.supply_price_lists`, `gba.supply_price_list_items`)**:
  - Branch-scoped price lists (`retail`, `wholesale`, `contract_b2b`) with volume tiers (`min_quantity`, `unit_price_minor`) referencing `gba.stock_items` and optional `gba.counterparties`.
- **Retail/Wholesale & 3PL Fulfillment Orders (`gba.supply_trade_orders`, `gba.supply_trade_order_lines`)**:
  - Branch-scoped trade orders tied to an explicit `goods_owner_id` (`company_entity` for `retail_sale` / `wholesale_sale`, `counterparty_3pl` for `3pl_fulfillment`).
- **Owner-Isolated Lot/Serial Allocation & Shipment (`gba.supply_order_shipments`)**:
  - Enforces at both service and PostgreSQL composite-FK level (`supply_order_shipments_order_owner_fk`, `supply_order_shipments_lot_owner_fk`) that a shipment for an order can only allocate lots and bins belonging to the order's `goods_owner_id` («Товар другого собственника недоступен»).
  - Deducts from `gba.supply_lot_balances` (and transitions specified `gba.supply_serial_units` to `status = 'shipped'`) and records an immutable `gba.supply_wms_movements` (`outbound_shipment`).
  - For `company_entity` orders, posts a real `STOCK-01` COGS `write_off` (`stock.post_document(..., WriteOffInput(reason="consumption"))`), capturing exact moving-average COGS from `gba.stock_valuations`, and saves + issues a real `FIN-03` receivable invoice (`financial_documents.save_draft` -> `financial_documents.issue_document`), storing `invoice_document_id`, `invoice_line_id`, and `obligation_id`.
- **Customer Return with Exact Lot/Serial, Movement & Cost Conservation (`gba.supply_order_returns`)**:
  - Restores the returned quantity to `gba.supply_lot_balances` for the exact shipped `(goods_owner_id, item_id, lot_id)` in a valid bin of the same `place_id`, transitions returned `gba.supply_serial_units` back to `status = 'in_stock'`, and records an immutable `gba.supply_wms_movements` (`inbound_return`).
  - For `company_entity` shipments, posts a real `STOCK-01` `return` (`stock.post_document(..., ReturnInput(source_document_id=shipment.stock_document_id, ...))`) restoring exact proportional inventory valuation (`cogs_restored_minor`) in `gba.stock_valuations`, and saves a real `FIN-03` credit note draft (`credit_notes.save_draft`) against `shipment.obligation_id` and `shipment.invoice_line_id`.
