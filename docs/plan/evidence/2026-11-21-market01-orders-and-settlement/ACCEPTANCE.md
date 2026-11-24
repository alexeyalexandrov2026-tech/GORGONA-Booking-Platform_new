# Acceptance Evidence — MARKET-01 Slice 2: Single-Seller Basket Split, FIN-03 Invoices & Refunds (2026-11-21)

- **Branch**: `codex/package-market-01-orders-and-settlement`
- **Base commit**: `69c2312f80b2dbb1ffd9adde9a3b1d3ff19c0d47` (`codex/package-market-01-storefronts-and-publishing`)
- **Verified code commit**: `67e9b46fe6f44c12fd9b500eb54e29764b47a84f` (tree `246f68106125bc25fa8ad786fd90bdb1c002105b`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0142_market_orders_and_settlement.sql` (invoker rights only)

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `67e9b46fe6f44c12fd9b500eb54e29764b47a84f`):
  - **3080 passed, 0 failed, 4 skipped** out of **3084** (`duplicates=0`, `count_ok=True`, wall time **1413.44s**; browser **50/50**, serial **216/216**).
