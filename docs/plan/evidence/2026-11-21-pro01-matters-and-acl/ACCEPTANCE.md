# Acceptance Evidence — PRO-01 Slice 1: Legal Matters, Conflict Checks & Ethical-Wall FORCE RLS (2026-11-21)

- **Branch**: `codex/package-pro-01-matters-and-acl`
- **Base commit**: `94fea94b9f0b2502542494362868d2439558700f` (`codex/package-rest-01-ui`; GitHub Actions CI `44921492438` — `success`)
- **Verified code commit**: `f284b5f8180e1bbbeff2587781050693f4fd2907` (tree `6782fdebd698e5ef092d0dc2a011aa495e081243`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0134_projects_matters_and_acl.sql` (invoker rights only)
- **ADR & Plan**: `docs/adr/0038-projects-legal-matters-recurring-services.md`, `docs/plan/PACKAGE_PRO01_PLAN_2026-11-21.md`

## Scope Delivered
1. Updated optional module `projects` to `Readiness.IMPLEMENTED` (`enableable=False`, `depends_on=("counterparties", "documents", "finance_documents")`, `MODULE_REGISTRY_VERSION=9`) and added non-delegable permissions `projects.read`, `projects.work`, `projects.manage` (`PERMISSIONS_VERSION=18`).
2. Migration `0134_projects_matters_and_acl.sql` adds 4 branch-scoped tables (`project_matters`, `project_matter_members`, `project_matter_revisions`, `project_conflict_checks`) with:
   - Tenant isolation RLS, restrictive branch scope RLS (`-- Projects matters branch scope:`), `require_enabled_module('projects')`, and invoker-rights triggers only.
   - PostgreSQL 18 restrictive `FORCE RLS` ethical-wall policies (`*_matter_access` using `gba.current_user_id()`) so `access_mode='restricted'` matters and child records are completely invisible (0 rows in SQL and 404 via API) to non-members — including same-branch peer managers, company-wide owners, and revoked original creators (`creation_xid = pg_current_xact_id()` expires at commit).
   - Deferred constraint trigger ensuring every restricted matter retains at least one active `'lead'` member.
   - Conflict-of-interest gate forbidding legal-case activation without a `'clear'` or `'waived'` decision.
3. Updated `schema_guard.py` (`_DEFINITIONS=176`, `_MODULE_TRIGGERS=50`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and pinned version tests.
4. Implemented 9 REST API routes under `/v1/businesses/{business_id}/projects`: matters CRUD/list/revisions, conflict checks list/record, and matter member ACL list/grant/revoke.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (619 files), `mypy src tests` (619 files): **PASS**
- `pytest tests/unit -q`: **921 passed, 0 failed**
- Focused integration + upgrade `0133 -> 0134` + `test_location_access.py` + `test_roles_and_migrations.py` + `test_configurations.py`: **48 passed, 0 failed**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `f284b5f8180e1bbbeff2587781050693f4fd2907`):
  - **3044 passed, 0 failed, 4 skipped** out of **3048** (`duplicates=0`, `count_ok=True`, wall time **1395.88s / 23m 16s**; browser **48/48**, serial **216/216**).
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
