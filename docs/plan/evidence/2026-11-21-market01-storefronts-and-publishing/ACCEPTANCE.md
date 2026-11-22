# Acceptance Evidence — MARKET-01 Slice 1: Business Storefronts, Strict Public Field Projection & Marketplaces (2026-11-21)

- **Branch**: `codex/package-market-01-storefronts-and-publishing`
- **Base commit**: `a2c581711abf36c8ca293588dab1d572c5da3b3c` (`codex/package-supply-01-ui`)
- **Verified code commit**: `5f094dfe9a23ac89881bbabd74c20a8648e9392f` (tree `dd2049812bbef51e8d2aacbe68fc741eaadc906e`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0141_market_storefronts_and_publishing.sql` (invoker rights only)

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `5f094dfe9a23ac89881bbabd74c20a8648e9392f`):
  - **3076 passed, 0 failed, 4 skipped** out of **3080** (`duplicates=0`, `count_ok=True`, wall time **1377.77s**; browser **50/50**, serial **216/216**).
