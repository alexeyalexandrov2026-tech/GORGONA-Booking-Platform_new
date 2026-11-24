# Acceptance Evidence — REST-01 Slice 2: Versioned Menu Items, Modifiers & Recipe BOMs (2026-11-21)

- **Branch**: `codex/package-rest-01-menu-and-recipes`
- **Base commit**: `cb492fe9d0cf901755d3960c6f00784c2384d3d9` (`codex/package-rest-01-floor-and-tables`, CI run `44874370128` success)
- **Verified code commit**: `69662f3a6bd0f76328c9298d3b08cde0b41b3261` (tree `1e38c850c6fa8584d3b6d8fbdc52dfeb57e07958`)
- **Migration**: `api/src/gorgona_booking/db/migrations/0131_restaurant_menu_and_recipes.sql` (invoker rights only)
- **Design**: `docs/plan/PACKAGE_REST01_MENU_RECIPES_DESIGN_2026-11-21.md`

## Scope Delivered
1. Migration `0131_restaurant_menu_and_recipes.sql` adds 7 branch-scoped tables with tenant RLS, restrictive branch RLS (`-- Restaurant menu branch scope:`), and `require_enabled_module('restaurant')`:
   - `restaurant_menu_items` + immutable append-only `restaurant_menu_item_revisions` (auto-snapshotted on insert/update, minor-unit prices, ISO currency, kitchen station `hot`/`cold`/`bar`/`pastry`).
   - `restaurant_modifier_groups`, `restaurant_modifier_options` (selection bounds `min_select..max_select`, signed `price_delta_minor`, optional `STOCK-01` material link `stock_item_id` + `stock_quantity`), and `restaurant_menu_item_modifier_groups` (currency match + active group guards).
   - Append-only `restaurant_recipes` + `restaurant_recipe_lines` referencing active `STOCK-01` (`gba.stock_items`) materials with deferred line-completeness constraint trigger.
2. Updated `schema_guard.py` (`_DEFINITIONS=144`, `_MODULE_TRIGGERS=41`), `test_location_access.py`, `test_inventory_upgrade.py`, `test_stock_upgrade.py`, and `test_document_contracts.py`.
3. Implemented 12 REST API endpoints under `/v1/businesses/{business_id}/restaurant` (`menu-items`, `revisions`, `modifier-groups`, `options`, `recipes`), audited via `commands.audit` and idempotent via `Idempotency-Key`.
4. Added unit contract tests (`test_restaurant_menu_contracts.py`), PostgreSQL integration tests (`test_restaurant_menu_and_recipes.py`), and `0130 -> 0131` upgrade tests (`test_restaurant_menu_upgrade.py`).

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check src tests`, `ruff format --check src tests` (603 files), `mypy src tests` (603 files): **PASS**
- `pytest tests/unit -q`: **913 passed, 0 failed** (`20.48s`)
- Focused integration + upgrade `0130 -> 0131` + `test_location_access.py` + `test_roles_and_migrations.py`: **37 passed, 0 failed** (`30.24s`)
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `69662f3a6bd0f76328c9298d3b08cde0b41b3261`):
  - **3025 passed, 0 failed, 4 skipped** out of **3029** (`duplicates=0`, `count_ok=True`, wall time **1255.4s / 20m 55s**)
  - Browser lane: **47/47 PASS**
  - Serial lane: **216/216 PASS**
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
