# Acceptance Evidence — PRO-01 Slice 2: Stages, Tasks, DAG Dependencies, Restricted Files & ACL Search (2026-11-21)

- **Branch**: `codex/package-pro-01-stages-tasks-and-files`
- **Base commit**: `a0e53929b2568bef1d66b6efc1fa5badbee00136` (`codex/package-pro-01-matters-and-acl`)
- **Verified code commit**: `335ac61bd0a0db2a42b3b26489f917643689a1b3` (tree `582d4c19360368c3f0a84c7896f2d5e095c79368`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0135_projects_stages_tasks_and_files.sql` (invoker rights only)
- **Design**: `docs/plan/PACKAGE_PRO01_WORK_DESIGN_2026-11-21.md`

## Scope Delivered
1. Migration `0135_projects_stages_tasks_and_files.sql` adds 4 branch-scoped tables (`project_stages`, `project_tasks`, `project_task_dependencies`, `project_matter_files`) with tenant RLS, restrictive branch RLS (`-- Projects work branch scope:`), `require_enabled_module('projects')`, invoker-rights triggers only, and PostgreSQL 18 restrictive `FORCE RLS` ethical-wall policies (`*_matter_access` inheriting from `gba.project_matters`).
2. Stage deliverable submission & lead acceptance/rejection workflow (`open -> submitted -> accepted/rejected`, accepted stages immutable).
3. Tasks with restricted-matter assignee allowlist checks and PostgreSQL `WITH RECURSIVE` DAG cycle-prevention trigger on `project_task_dependencies`.
4. Immutable matter-restricted PDF/PNG/JPEG files validated by `file_validation.validate_file`, gated by malware-scanner setting in non-dev environments, served with `Content-Security-Policy: default-src 'none'; sandbox` + `frame-ancestors 'none'`, and unreachable (`404` / 0 SQL rows) to non-members including company-wide owners/managers.
5. Unified ACL-enforced search (`GET /v1/businesses/{business_id}/projects/search`) across matters, stages, tasks, and files — proven to return zero restricted hits to non-members.
6. Updated `schema_guard.py` (`_DEFINITIONS=184`, `_MODULE_TRIGGERS=54`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (624 files), `mypy src tests` (624 files): **PASS**
- `pytest tests/unit -q`: **923 passed, 0 failed**
- Focused integration + upgrade `0134 -> 0135` + `test_location_access.py` + `test_roles_and_migrations.py`: **34 passed, 0 failed (`30.46s`)**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `335ac61bd0a0db2a42b3b26489f917643689a1b3`):
  - **3048 passed, 0 failed, 4 skipped** out of **3052** (`duplicates=0`, `count_ok=True`, wall time **1438.79s / 23m 59s**; browser **48/48**, serial **216/216**).
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
