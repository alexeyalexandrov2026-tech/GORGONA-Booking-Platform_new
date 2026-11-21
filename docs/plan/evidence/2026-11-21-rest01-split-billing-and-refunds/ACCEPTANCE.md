# Acceptance Evidence — REST-01 Slice 4: Split Billing, FIN-03 Invoices & Coordinated Refunds (2026-11-21)

- **Branch**: `codex/package-rest-01-split-billing-and-refunds`
- **Base commit**: `578f80a9f6be2ecf060a93218be01ecba2538861` (`codex/package-rest-01-checks-and-kitchen`)
- **Verified code commit**: `d788d0810e5f7368c62fa686b69674a6c5b8bd2d` (tree `ae09f138cbb2a0ad2010bbc0a6f1cfb140d17e5f`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0133_restaurant_split_billing_and_refunds.sql` (invoker rights only)
- **Design**: `docs/plan/PACKAGE_REST01_SPLIT_BILLING_DESIGN_2026-11-21.md`

## Scope Delivered
1. Migration `0133_restaurant_split_billing_and_refunds.sql` adds 5 branch-scoped tables with tenant RLS, restrictive branch RLS (`-- Restaurant billing branch scope:`), invoker-rights triggers only, and `require_enabled_module('restaurant')`:
   - `restaurant_check_splits`, `restaurant_check_split_shares`, and `restaurant_check_split_share_lines` (`by_items` and `by_amounts` modes with deferred constraint trigger enforcing strict `sum(share.amount_minor) = check.subtotal_minor` and exact 1:1 active line assignment).
   - `restaurant_check_bills` linking each split share 1:1 to a `FIN-03` receivable invoice draft (`financial_documents.save_draft`) verified by DB trigger for exact amount, currency, and counterparty.
   - Append-only `restaurant_check_refunds` supporting `FIN-03` credit notes (`credit_notes.save_draft` against the share's issued invoice obligation) and attested external refunds with optional `returned_line_id` and per-share refund ceiling enforcement (excluding voided credit notes via `gba.credit_voided`).
2. Updated `guard_restaurant_check_line()` to forbid adding or voiding lines after a check is split.
3. Updated `schema_guard.py` (`_DEFINITIONS=168`, `_MODULE_TRIGGERS=47`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.
4. Implemented 5 REST API routes under `/v1/businesses/{business_id}/restaurant`: `GET/POST /checks/{id}/split`, `POST /checks/{id}/shares/{share_no}/bill`, `POST /checks/{id}/refunds`, and derived `GET /checks/{id}/reconciliation`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (613 files), `mypy src tests` (613 files): **PASS**
- `pytest tests/unit -q`: **917 passed, 0 failed**
- Focused integration + upgrade `0132 -> 0133` + `test_location_access.py` + `test_roles_and_migrations.py`: **40 passed, 0 failed** (`36.60s`)
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `d788d0810e5f7368c62fa686b69674a6c5b8bd2d`):
  - **3035 passed, 0 failed, 4 skipped** out of **3039** (`duplicates=0`, `count_ok=True`, wall time **1284.1s / 21m 24s**; browser **47/47**, serial **216/216**).
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
