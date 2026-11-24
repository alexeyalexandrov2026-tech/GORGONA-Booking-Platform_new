# Acceptance Evidence — SUPPLY-01 Slice 4: `/supply/` 4-Tab Operations UI & Real-Browser E2E (2026-11-21)

- **Branch**: `codex/package-supply-01-ui`
- **Base commit**: `b8650ae19bc2b62e2488c567ea6257efb25e8251` (`codex/package-supply-01-trade-and-3pl-orders`)
- **Verified code commit**: `f35a1d43c7d5fa906895cee19c4af5b8949d9a3c` (tree `cf960de9475c7846e1900e1d17b688c9a6a01c2e`)
- **Migration**: none (builds on `0138`..`0140`)

## Scope Delivered
1. Strict Zod contracts (`web/lib/supply-contracts.ts`, wired into `web/lib/management-contracts.ts`), API client (`web/lib/supply-api.ts`), and contract unit tests (`web/tests/supply-contracts.spec.ts`).
2. `/supply/` 4-tab responsive workspace (`web/components/supply.tsx`, `web/app/supply/page.tsx`, `web/app/supply.css`) covering:
   - **WMS Owners & Bins**: goods owners (`company_entity` vs `counterparty_3pl`), warehouse zones/bins (with optional `dedicated_owner_id`), lots/batches.
   - **Lots, Balances & Movements**: STOCK-01 linked inbound putaway, live bin/lot running balances, WMS movement ledger.
   - **Manufacturing & Costing**: versioned BOMs, production work orders, component lot issues (`STOCK-01` `write_off`), unused material returns (`STOCK-01` `return` restoring lot balance & cost), QC inspection, and finished-goods lot output (`STOCK-01` `receipt` at exact material + labor + overhead cost).
   - **Trade & 3PL Orders**: channel & contract price lists, retail/wholesale & 3PL fulfillment orders, owner-isolated lot/serial shipments (`STOCK-01` COGS `write_off` + `FIN-03` receivable invoice), and customer returns (`STOCK-01` `return` + `FIN-03` credit note draft restoring exact lot balance & cost).
3. Real Chromium desktop + mobile (`390px`) Playwright E2E (`web/tests/supply.spec.ts`, `api/tests/integration/test_supply_browser.py`) verifying `axe-core` (0 violations), goods-owner isolation negative proofs (`409 SUPPLY_OWNER_MISMATCH`), manufacturing and trade lot/movement/cost conservation, and PostgreSQL 18 read-back.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run test:unit`, `npm run build`: **PASS**
- `ruff check src tests`, `ruff format --check src tests` (649 files), `mypy src tests` (649 files): **PASS**
- Focused real-browser E2E (`pytest tests/integration/test_supply_browser.py -q`): **PASS**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `f35a1d43c7d5fa906895cee19c4af5b8949d9a3c`):
  - **3071 passed, 0 failed, 4 skipped** out of **3075** (`duplicates=0`, `count_ok=True`, wall time **1430.97s**; browser **50/50**, serial **216/216**).
