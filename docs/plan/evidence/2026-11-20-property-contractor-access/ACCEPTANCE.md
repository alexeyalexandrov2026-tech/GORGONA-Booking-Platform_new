# PROPERTY-01 5b · Single-assignment contractor access through delegation grants

- **Date:** 2026-11-20
- **Branch:** `codex/package-property-01-contractor-access`
- **Base commit:** `a85f0bcc4e9d8fc387232a7be34ecba9c52de554` (Step 5a CI [44766786482](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44766786482) — success)
- **Source code commit:** `c1f3e8eaf02661d7316b8fac0e8193cd780a1204` (tree `09d494e0a8eac2525ccf37d0fc63ce73cc7fec7d`)
- **Design:** [PACKAGE_PROPERTY01_CONTRACTOR_ACCESS_DESIGN_2026-11-20.md](../../PACKAGE_PROPERTY01_CONTRACTOR_ACCESS_DESIGN_2026-11-20.md)
- **Migration:** `0128_property_contractor_access.sql` (invoker rights only, SHA-256 `603518d1b3a5873ab92382904cd7b011c4975e36cc73285167fe20fcc7a68e5e`)

## What was implemented and verified

1. **Delegable permission `property.contractor_work` (`PERMISSIONS_VERSION = 16`):**
   - Added to `DELEGABLE_PERMISSIONS`, `DelegablePermission`, `web/lib/delegation-contracts.ts`, and `delegation_grants_permissions_check` (preserving `max_length = 9`).
   - `test_delegation_contracts.py` locks the exact two contractor delegated routes in `api/property_maintenance.py`.
2. **Explicit single-assignment contractor binding (`gba.property_maintenance_contractor_links`):**
   - Append-only revisions binding one assigned maintenance request to one external contractor company (`company_id <> tenant_id`, or `null` to unbind).
   - Unbound requests of the same company and contractor counterparty remain strictly unreachable (`403`) even with a live grant.
3. **Contractor work-order view and progress updates (`gba.property_maintenance_contractor_updates`):**
   - `GET /property/maintenance/{request_id}/contractor-work/{grant_id}` returns only the single bound work order (`object_name`, `object_kind`, `location_id`, `category`, `priority`, `title`, `description`, `state`, `revision`, `binding_revision`, `updates`) and excludes `lease_id`, `approved_limit_minor`, `currency`, FIN-03 obligations, `owner_id`/`manager_id`, internal events, and all other requests.
   - `POST /property/maintenance/{request_id}/contractor-work/{grant_id}/updates` records idempotent `acknowledged` / `in_progress` / `parts_needed` / `work_done` updates while `state = 'assigned'` (refused `409` after company completion).
   - Owner company managers are refused (`403`) on delegate routes and read contractor updates with company display name via `GET /property/maintenance/{request_id}/contractor-updates`.
4. **Revocation, branch scope, and invoker-rights DB trigger recheck (0126 pattern):**
   - Unbinding (`company_id = null`) or revoking the delegation grant immediately blocks `GET`, `POST`, and idempotency-key replays (`403`).
   - Wrong-branch and wrong-permission grants are refused (`403`); matching branch-scoped grants work end-to-end.
   - Direct SQL `INSERT` into `gba.property_maintenance_contractor_updates` inside a branch-scoped session using a revoked grant is rejected by PostgreSQL (`property_maintenance_contractor_updates_scope`).
5. **Guards, access matrix, and upgrades:**
   - `schema_guard.py` enforces all 5 new RLS policies (`_DEFINITIONS = 116`) and 2 new module-gate triggers (`_MODULE_TRIGGERS = 32`).
   - `test_property_access.py` verifies all 31 Property OpenAPI routes (8 branch `property.read`, 21 company `property.manage`, 2 delegated `property.contractor_work`).
   - `test_location_access.py` restores and checks `0128` branch scope; `test_property_contractor_access_upgrade.py` verifies populated `0127 -> 0128` upgrade preserves all rows and prior checksums.

## Verification results (`gorgona-dev`, PostgreSQL 18.6, Chromium)

- **RED baseline (before implementation):** `test_property_contractor_access.py` failed with `404 Not Found` on `/contractor-company`.
- **Static checks (API):** `git diff --check`, `ruff check src tests`, `ruff format --check src tests` (588 files), `mypy src tests` (588 files) — **PASS**.
- **Static checks & build (web):** `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run test:unit` (**194 passed**), `npm run build` (36/36 static pages) — **PASS**.
- **API unit suite:** **895 passed, 0 failed** (17.57s).
- **Focused integration suite (9 files):** **55 passed, 0 failed** (44.70s).
- **Full parallel suite (`c1f3e8e`):** `uv run --locked python -m tools.run_parallel_tests --workers 6` — **2995 passed, 0 failed, 4 skipped** out of 2999 collected tests (`duplicates=0`, `count_ok=True`, wall time **1142.55s / 19m 02s**; browser 46/46, serial 216/216). The 4 skips are the standard VM env-gated container (3) and tenant-site (1) checks.

## Open scope and limits

- **Step 5c:** Property maintenance operations screen and contractor work-order browser screen (desktop, mobile, keyboard, axe).
- **Step 6a:** Move-out condition report and photos (`property_move_outs`).
- **Steps 2d & 4:** Public storefront/screening and statutory deposit custody rules (pending owner jurisdiction and provider decisions).
- `PROPERTY-01` remains `planned` in `readiness_registry.py` and `property` stays `enableable=False`; no PR, merge, or production deployment performed.
