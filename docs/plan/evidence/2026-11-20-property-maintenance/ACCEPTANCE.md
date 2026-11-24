# PROPERTY-01 5a · Maintenance requests, approvals, and separate FIN-03 obligations

- **Date:** 2026-11-20
- **Branch:** `codex/package-property-01-maintenance`
- **Base commit:** `c5d70774fdc2f4c16d9bec421500f94f6b7b0d8f`
- **Source code commit:** `34a595ceaa7c9af338924316ee9601ddbaec1a8f` (tree `8ad8c38caad7cb43dea663bb1c60e110167ec069`, stacked on `8cae17d8a335b3a29e368104621efb66d547c9bc`)
- **Design:** [PACKAGE_PROPERTY01_MAINTENANCE_DESIGN_2026-11-20.md](../../PACKAGE_PROPERTY01_MAINTENANCE_DESIGN_2026-11-20.md)
- **Migration:** `0127_property_maintenance.sql` (invoker rights only, no `SECURITY DEFINER`, SHA-256 `78e58f13eae1a2addd135abfc47ea40805b0332adcf3e0754b802d7e34747d1f`)

## What was implemented and verified

1. **Maintenance request lifecycle (`gba.property_maintenance_requests`, `gba.property_maintenance_events`):**
   - Requests attach to any property object (`parcel`, `building`, `unit`) with optional link to a lease of that exact object.
   - Append-only events (`approve`, `assign`, `complete`, `cancel`) advance revision and materialized state under `gba.lock_property_object` in `READ COMMITTED`.
   - Approval records explicit `approved_limit_minor` and `currency` before contractor assignment or obligation linkage.
   - Cancellation and contractor reassignment are refused once a FIN-03 work obligation is linked.
   - After disabling the `property` module, new requests/assignments/obligations are refused (`409`), earlier idempotency keys replay their original response, and already-assigned work can still be completed.
2. **Separate FIN-03 payable work obligations (`gba.property_maintenance_obligations`):**
   - Each linked obligation references a unique **issued** FIN-03 payable invoice (`kind = 'invoice'`, `state = 'issued'`, `direction = 'payable'`) for the assigned contractor in the approved currency.
   - PostgreSQL derives `obligation_id`, `amount_minor`, and `currency` directly from `gba.financial_document_versions` and enforces cumulative `sum(amount_minor) <= approved_limit_minor` under lock (verified under concurrent requests).
   - Draft invoices, receivable invoices (rent/customer), wrong-contractor invoices, wrong-currency invoices, duplicate links across the same or another request, and over-limit links are rejected.
   - Changing the property's owner or manager in `property_parties` preserves previously recorded maintenance obligations and their contractor payee.
3. **Isolation and guards:**
   - All 7 new maintenance routes are covered by the OpenAPI access matrix in `test_property_access.py` (26 Property routes total: 8 branch-readable `property.read`, 18 company-wide `property.manage`).
   - `schema_guard.py` enforces all 8 new RLS policies (`_DEFINITIONS = 111`) and 2 new module-gate triggers (`_MODULE_TRIGGERS = 30`).
   - `test_location_access.py` restores and verifies `0127` branch/company scope policies after boundary drop.
   - `test_property_maintenance_upgrade.py` verifies upgrading a populated `0126` database to `0127` preserves all rows and prior checksums.

## Verification results (`gorgona-dev`, PostgreSQL 18.6, Chromium)

- **RED baseline (before implementation):** `test_property_maintenance.py` failed with `404 Not Found`.
- **Static checks:** `git diff --check`, `ruff check src tests`, `ruff format --check src tests` (586 files), `mypy src tests` (586 files) — **PASS**.
- **API unit suite:** **894 passed, 0 failed** (17.86s), including `test_property_maintenance_contracts.py`, `test_document_contracts.py`, and `test_migration_files.py`.
- **Focused integration tests:** `test_property_maintenance.py`, `test_property_maintenance_upgrade.py`, `test_property_access.py` (**10 passed** in 21.76s); `test_inventory_upgrade.py`, `test_stock_upgrade.py` (**5 passed** in 11.18s).
- **Full parallel suite (`34a595c`):** `uv run --locked python -m tools.run_parallel_tests --workers 6` — **2991 passed, 0 failed, 4 skipped** out of 2995 collected tests (`duplicates=0`, `count_ok=True`, wall time **1147.5s / 19m 07s**). The 4 skips are the standard VM env-gated container (3) and tenant-site (1) checks.

## Open scope and limits

- Contractor cross-company single-assignment access via delegation grant (**Step 5b**, migration `0128`) is next.
- Maintenance UI screen and browser verification (**Step 5c**) follow Step 5b.
- Regulated integrations (Step 2d public screening; Step 4 statutory deposit custody) remain open pending owner decisions.
- `PROPERTY-01` remains `planned` in `readiness_registry.py` and `property` stays `enableable=False`; no PR, merge, or production deployment performed.
