# Acceptance Evidence — PRO-01 Slice 4: FIN-03 Matter Invoicing & ACL-Enforced Audited Exports (2026-11-21)

- **Branch**: `codex/package-pro-01-billing-and-exports`
- **Base commit**: `11f02a6c4a1fc5458390d1048485b2e33d7ed312` (`codex/package-pro-01-time-and-recurring`)
- **Verified code commit**: `56a7ef9e8646bfb7949d7492aeea8dc42082953f` (tree `5b46ec2944573ed976dfcf5fe95473ad4ffefb4b`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0137_projects_billing_and_exports.sql` (invoker rights only)
- **Design**: `docs/plan/PACKAGE_PRO01_BILLING_EXPORTS_DESIGN_2026-11-21.md`

## Scope Delivered
1. Migration `0137_projects_billing_and_exports.sql` adds 3 branch-scoped tables (`project_matter_invoices`, `project_matter_invoice_items`, `project_exports`) with tenant RLS, restrictive branch RLS (`-- Projects billing branch scope:`), `require_enabled_module('projects')`, invoker-rights triggers only, deferred total conservation trigger (`project_matter_invoices_total_conserved`), partial unique indexes preventing double-billing of any time entry, stage, or recurring run, and PostgreSQL 18 restrictive `FORCE RLS` ethical-wall policies (`*_matter_access`).
2. Real `FIN-03` receivable invoice draft issuance (`financial_documents.save_draft`) from approved billable time entries, accepted fixed-fee stages, and unbilled recurring runs without creating a second ledger, requiring active `'lead'` or `'billing'` membership on restricted matters.
3. Single-matter (`POST /matters/{matter_id}/exports`) and branch portfolio (`POST /exports`) audited exports that strictly enforce the PostgreSQL 18 `FORCE RLS` ethical wall (non-members receive `404` on single-matter exports, and portfolio exports omit restricted matters and all their child artefacts for non-members).
4. Updated `schema_guard.py` (`_DEFINITIONS=198`, `_MODULE_TRIGGERS=59`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (634 files), `mypy src tests` (634 files): **PASS**
- `pytest tests/unit -q`: **927 passed, 0 failed**
- Focused integration + upgrade `0136 -> 0137` + `test_location_access.py` + `test_roles_and_migrations.py`: **36 passed, 0 failed (`37.82s`)**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `56a7ef9e8646bfb7949d7492aeea8dc42082953f`):
  - **3056 passed, 0 failed, 4 skipped** out of **3060** (`duplicates=0`, `count_ok=True`, wall time **1431.82s**; browser **48/48**, serial **216/216**).
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
