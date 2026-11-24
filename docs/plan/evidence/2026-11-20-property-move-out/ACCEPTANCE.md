# PROPERTY-01 6a · Move-out condition report and photos

- **Date:** 2026-11-20
- **Branch:** `codex/package-property-01-move-out`
- **Base commit:** `4292474756838cd1d76c31003e9b6437468755c1` (Step 5b CI [44850392881](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44850392881))
- **Source code commit:** `7bcd64515b294e0ffa64900aace7b495baa4359f` (tree `612d0925f9ff95f5a4b98ae3c9620ac397d12f2a`)
- **Design:** [PACKAGE_PROPERTY01_MOVE_OUT_DESIGN_2026-11-20.md](../../PACKAGE_PROPERTY01_MOVE_OUT_DESIGN_2026-11-20.md)
- **Migration:** `0129_property_move_out.sql` (invoker rights only, SHA-256 `4dd9f4c03b86db463988c3f7621eeb1ded303fbe1121e0bb99f44afa0ec39aa2`)

## What was implemented and verified

1. **Move-out condition report and photos (`gba.property_move_outs`, `gba.property_move_out_photos`):**
   - One immutable move-out report per lease (`GET/PUT /v1/businesses/{business_id}/property/leases/{lease_id}/move-out`, company-wide `property.manage`).
   - Requires an existing move-in record (`property_move_out_requires_move_in` -> `409`), matching `term_revision` (`409`), and `moved_out_on` within `[move_in.moved_in_on, coalesce(occupied_through, ends_on)]` up through the branch's current local day (`422`).
   - Requires a stored non-archived ADR-0020 `report` document version distinct from the move-in report (`property_move_out_report_distinct` -> `422`) and 1–50 unique PNG/JPEG photo versions enforced by a deferred constraint trigger.
   - Records structured `condition_summary` (`normal_wear` / `damage_noted`) and optional `note`.
2. **Lease term guard synchronization (`gba.guard_property_lease_term()`):**
   - Updated in migration `0129` and synchronized in `schema_guard.py` (`_PROPERTY_LEASE_TERM_GUARD_SOURCE`).
   - Once move-out is recorded, extending the lease or releasing to a day earlier than `moved_out_on` is refused (`409 PROPERTY_LEASE_MOVE_OUT_CONFLICT`), while finalizing a release on or after `moved_out_on` succeeds.
3. **Guards, access matrix, and upgrades:**
   - `schema_guard.py` enforces all 4 new RLS policies (`_DEFINITIONS = 120`) and 1 new module-gate trigger (`_MODULE_TRIGGERS = 33`).
   - `test_property_access.py` verifies all 33 Property OpenAPI routes (8 branch `property.read`, 23 company `property.manage`, 2 delegated `property.contractor_work`).
   - `test_location_access.py` restores and checks `0129` company scope; `test_property_move_out_upgrade.py` verifies populated `0128 -> 0129` upgrade preserves all rows and prior checksums.

## Verification results (`gorgona-dev`, PostgreSQL 18.6, Chromium)

- **RED baseline (before implementation):** `test_property_move_out.py` failed with `404 Not Found`.
- **Static checks (API):** `git diff --check`, `ruff check src tests`, `ruff format --check src tests` (592 files), `mypy src tests` (592 files) — **PASS**.
- **API unit suite:** **906 passed, 0 failed** (17.51s).
- **Focused integration tests:** `test_property_move_out.py`, `test_property_move_out_upgrade.py`, `test_property_access.py` (**7 passed** in 19.11s).
- **Full parallel suite (`7bcd645`):** `uv run --locked python -m tools.run_parallel_tests --workers 6` — **3009 passed, 0 failed, 4 skipped** out of 3013 collected tests (`duplicates=0`, `count_ok=True`, wall time **1151.36s / 19m 11s**; browser 46/46, serial 216/216). The 4 skips are the standard VM env-gated container (3) and tenant-site (1) checks.

## Open scope and limits

- **Step 5c / 6 UI:** Property maintenance, contractor work-order, and move-out browser screens (desktop, mobile, keyboard, axe).
- **Steps 2d, 4 & 6b:** Public storefront/screening, statutory deposit custody, and owner settlement rules (pending owner jurisdiction and provider decisions).
- `PROPERTY-01` remains `planned` in `readiness_registry.py` and `property` stays `enableable=False`; no PR, merge, or production deployment performed.
