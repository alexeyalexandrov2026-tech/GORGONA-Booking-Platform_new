# Acceptance Evidence — REST-01 Slice 3: Independent Checks, Kitchen Tickets & STOCK-01 Write-Offs (2026-11-21)

- **Branch**: `codex/package-rest-01-checks-and-kitchen`
- **Base commit**: `cefa04a0b1d75ae799c4d562f8b38fd7d1860947` (`codex/package-rest-01-menu-and-recipes`)
- **Verified code commit**: `8443b0b1a696412ca8924d082549becc5578cb4d` (tree `42e2be02a6fa086bf1a8a05c2f9fe16b58122018`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0132_restaurant_checks_and_kitchen.sql` (invoker rights only)
- **Design**: `docs/plan/PACKAGE_REST01_CHECKS_KITCHEN_DESIGN_2026-11-21.md`

## Scope Delivered
1. Migration `0132_restaurant_checks_and_kitchen.sql` adds `restaurant_tables_branch_key` and 7 branch-scoped tables with tenant RLS, restrictive branch RLS (`-- Restaurant checks branch scope:`), invoker-rights triggers only, and `require_enabled_module('restaurant')`:
   - `restaurant_checks` (`dine_in`/`takeout`/`bar`/`delivery`, optional `table_id` & `reservation_id` with table-match guard, zero shift dependency).
   - `restaurant_check_lines` + immutable `restaurant_check_line_modifiers` (frozen menu revision, recipe revision, base price, modifier deltas, optional `STOCK-01` links, validated against attached modifier group `min_select..max_select`).
   - `restaurant_kitchen_tickets` + append-only `restaurant_kitchen_ticket_events` (station-routed `hot`/`cold`/`bar`/`pastry`, lifecycle `queued -> preparing -> ready -> served / voided`).
   - Immutable `restaurant_check_consumptions` + `restaurant_check_consumption_lines` linked 1:1 to `gba.stock_documents` via `stock.post_document` (`kind='write_off'`, `reason='used'`) with deferred line-completeness constraint trigger.
2. Updated `schema_guard.py` (`_DEFINITIONS=158`, `_MODULE_TRIGGERS=44`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.
3. Implemented 12 REST API endpoints under `/v1/businesses/{business_id}/restaurant` (`checks`, `lines`, `void`, `fire`, `close`, `kitchen/tickets`, `events`, `consumption`, `post-consumption`).
4. Added unit contracts (`test_restaurant_checks_contracts.py`), PostgreSQL E2E tests (`test_restaurant_checks_and_kitchen.py`), and `0131 -> 0132` upgrade tests (`test_restaurant_checks_upgrade.py`).

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (608 files), `mypy src tests` (608 files): **PASS**
- `pytest tests/unit -q`: **915 passed, 0 failed** (`21.89s`)
- Focused integration + upgrade `0131 -> 0132` + `test_location_access.py` + `test_roles_and_migrations.py`: **38 passed, 0 failed** (`34.84s`)
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `8443b0b1a696412ca8924d082549becc5578cb4d`):
  - **3029 passed, 1 failed (unrelated flake), 4 skipped** out of **3034** (`duplicates=0`, `count_ok=True`, wall time **1301.1s / 21m 41s**; browser **47/47**, serial **216/216**).
  - Unrelated flake recorded honestly: `tests/integration/test_credit_notes.py::test_credit_and_reserve_wait_on_one_lock_and_keep_the_cap[False]` (409 vs 200 race under 6-worker load). Immediate rerun of `tests/integration/test_credit_notes.py` on `8443b0b1a696412ca8924d082549becc5578cb4d`: **PASS**.
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
