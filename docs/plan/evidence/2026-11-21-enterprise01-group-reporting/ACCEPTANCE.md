# Acceptance Evidence — ENTERPRISE-01 Slice 2: Consent-Based Consolidated Group Reporting (2026-11-21)

- **Branch**: `codex/package-enterprise-01-group-reporting`
- **Base commit**: `b6a5ec33003a60278e0ebf4c1687cbe6e0ed8b94` (`codex/package-enterprise-01-holding-and-governance`)
- **Verified code commit**: `3b34049f6edbac258476cddb09ac353b256aab04` (tree `89ae65ab5b2b9609dce23660f9cfe19d8f7f28a8`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0144_enterprise_group_reporting.sql` (invoker rights only)

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `3b34049f6edbac258476cddb09ac353b256aab04`):
  - **3088 passed, 0 failed, 4 skipped** out of **3092** (`duplicates=0`, `count_ok=True`, wall time **1410.76s**; browser **51/51**, serial **216/216**).
