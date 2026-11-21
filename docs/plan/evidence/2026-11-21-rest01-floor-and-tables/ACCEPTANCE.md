# Acceptance Evidence — REST-01 Slice 1: Floor Areas, Tables & Independent Reservations (2026-11-21)

- **Branch**: `codex/package-rest-01-floor-and-tables`
- **Base commit**: `617223abe570adeb40bfab922eb1b44894476baf` (`codex/package-property-01-maintenance-ui`)
- **Verified code commit**: `5dc0b05d0b17a926073f9bb2e3798c471652d281` (tree `873f5d11278cc413238b9aeb5e92db7230c63646`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0130_restaurant_floor_and_tables.sql` (invoker rights only)
- **Design & ADR**:
  - `docs/adr/0037-restaurant-tables-menu-kitchen-checks.md`
  - `docs/plan/PACKAGE_REST01_PLAN_2026-11-20.md`
  - `docs/plan/PACKAGE_REST01_FLOOR_TABLES_DESIGN_2026-11-20.md`

## Scope Delivered
1. Registered optional module `restaurant` (`Readiness.IMPLEMENTED`, `enableable=False`, `MODULE_REGISTRY_VERSION=8`, total modules `24`) depending on `booking_resources`, `counterparties`, `finance_documents`, `inventory`, and `workforce`. `REST-01` readiness in `readiness_registry.py` was **not** raised.
2. Added `RESTAURANT_READ`, `RESTAURANT_KITCHEN`, `RESTAURANT_SERVICE`, and `RESTAURANT_MANAGE` permissions (`PERMISSIONS_VERSION=17`, none delegable).
3. Added migration `0130_restaurant_floor_and_tables.sql`:
   - Extends `gba.resources.kind` with `'restaurant_table'` and `gba.resource_allocations.source_kind` with `'restaurant_reservation'`.
   - Creates `restaurant_areas`, `restaurant_area_revisions` (append-only revision history), `restaurant_tables` (1:1 bound to `gba.resources`), `restaurant_table_reservations` (bound to `gba.resource_allocations`), and `restaurant_table_reservation_events` (append-only lifecycle events: `booked` -> `seated` -> `completed` / `cancelled` / `no_show`).
   - Enforces cover-range bounds (`min_covers <= party_size <= max_covers`), cross-table/branch consistency, deferred allocation binding, automatic allocation release on terminal events, tenant RLS, restrictive branch RLS (`-- Restaurant floor branch scope:`), and `require_enabled_module('restaurant')`.
   - Updates `gba.guard_resource_allocation()`, `schema_guard.py` (`_DEFINITIONS=130`, `_OCCUPANCY_TRIGGERS=20`, `_MODULE_TRIGGERS=36`), and `workforce_guard.py`.
4. Implemented 11 REST API routes under `/v1/businesses/{business_id}/restaurant`:
   - `GET/PUT /areas`, `GET /areas/{area_id}`
   - `GET/PUT /tables`, `GET /tables/{table_id}`
   - `GET/PUT /reservations`, `GET /reservations/{reservation_id}`
   - `GET/POST /reservations/{reservation_id}/events`
5. Added unit contracts (`test_restaurant_floor_contracts.py`), PostgreSQL integration tests (`test_restaurant_floor_and_tables.py`), and `0129 -> 0130` upgrade tests (`test_restaurant_floor_upgrade.py`), plus registered migration `130` branch-scope restoration in `test_location_access.py` and pre-130 fixture filtering in `test_h3_upgrade.py`.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`: **PASS**
- `ruff format --check src tests`: **PASS (598 files)**
- `mypy src tests`: **PASS (598 files)**
- `pytest tests/unit -q`: **910 passed, 0 failed**
- Focused integration (`test_restaurant_floor_and_tables.py`, `test_restaurant_floor_upgrade.py`, `test_configurations.py`, `test_property_showings.py`, `test_workforce.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`): **55 passed, 0 failed**
- Serial + location access integration (`test_location_access.py`, `test_roles_and_migrations.py`, `test_delegations.py`, `test_resource_occupancy.py`, `test_workforce_guards.py`, `test_property_move_in.py`): **85 passed, 0 failed (39.95s)**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `5dc0b05d0b17a926073f9bb2e3798c471652d281`):
  - **3018 passed, 0 failed, 4 skipped** out of **3022** (`duplicates=0`, `count_ok=True`, wall time **1177.1s / 19m 37s**)
  - Browser lane: **47/47 PASS**
  - Serial lane: **216/216 PASS**
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
