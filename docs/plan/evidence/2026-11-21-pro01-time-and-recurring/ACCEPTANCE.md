# Acceptance Evidence — PRO-01 Slice 3: Billable Time Tracking & Recurring Service Schedules (2026-11-21)

- **Branch**: `codex/package-pro-01-time-and-recurring`
- **Base commit**: `9627bd54c34e7eb92e1cdb4fba739c0f1cb1edce` (`codex/package-pro-01-stages-tasks-and-files`)
- **Verified code commit**: `ba783574c240d93ebf591ee0cda12689b05ce1ef` (tree `3d48c6f8d96018d277b79bcaae2fe9655e26f268`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0136_projects_time_and_recurring.sql` (invoker rights only)
- **Design**: `docs/plan/PACKAGE_PRO01_TIME_RECURRING_DESIGN_2026-11-21.md`

## Scope Delivered
1. Migration `0136_projects_time_and_recurring.sql` adds 4 branch-scoped tables (`project_time_entries`, `project_time_entry_revisions`, `project_recurring_schedules`, `project_recurring_runs`) with tenant RLS, restrictive branch RLS (`-- Projects time & recurring branch scope:`), `require_enabled_module('projects')`, invoker-rights triggers only, and PostgreSQL 18 restrictive `FORCE RLS` ethical-wall policies (`*_matter_access` inheriting from `gba.project_matters`).
2. Versioned billable and non-billable time entries with `ROUND_HALF_UP` minor-unit computation, full append-only revision history on edits/decisions, and approval lifecycle (`draft -> submitted -> approved -> billed` or `rejected -> draft`).
3. Recurring service schedules (`weekly`, `biweekly`, `monthly`, `quarterly`) and idempotent cycle runs (`project_recurring_runs`) that materialize cycle tasks in `gba.project_tasks`, advance `next_run_date`, and track `unbilled/billed` state for Slice 4 `FIN-03` invoicing.
4. Updated `schema_guard.py` (`_DEFINITIONS=192`, `_MODULE_TRIGGERS=57`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (629 files), `mypy src tests` (629 files): **PASS**
- `pytest tests/unit -q`: **926 passed, 0 failed**
- Focused integration + upgrade `0135 -> 0136` + `test_location_access.py` + `test_roles_and_migrations.py`: **35 passed, 0 failed (`35.89s`)**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `ba783574c240d93ebf591ee0cda12689b05ce1ef`):
  - **3053 passed, 0 failed, 4 skipped** out of **3057** (`duplicates=0`, `count_ok=True`, wall time **1429.02s / 23m 49s**; browser **48/48**, serial **216/216**).
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
