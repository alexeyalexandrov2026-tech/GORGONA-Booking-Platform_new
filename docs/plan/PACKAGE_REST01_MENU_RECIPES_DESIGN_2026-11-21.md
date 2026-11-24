# Design: REST-01 Slice 2 — Versioned Menu Items, Modifiers & Recipe Ingredient BOMs (2026-11-21)

Aligned with `docs/adr/0037-restaurant-tables-menu-kitchen-checks.md` and `docs/plan/PACKAGE_REST01_PLAN_2026-11-20.md`.

## Schema (`0131_restaurant_menu_and_recipes.sql`)
All 7 tables carry `(tenant_id, location_id)`, enforce tenant isolation RLS and restrictive branch-scope RLS (`-- Restaurant menu branch scope:`), and use invoker-rights triggers only:

1. `gba.restaurant_menu_items` + append-only `gba.restaurant_menu_item_revisions`:
   - Versioned branch menu items with immutable `code`, `name`, `category`, `kitchen_station` (`hot`/`cold`/`bar`/`pastry`), `price_minor` (bigint `>= 0`), ISO-4217 `currency`, optional `description`, `is_active`, and monotonically incrementing `revision`.
   - `AFTER INSERT OR UPDATE` trigger automatically snapshots every revision into `gba.restaurant_menu_item_revisions` so Slice 3 checks can bind immutably to `(tenant_id, menu_item_id, menu_item_revision, location_id)`.
2. `gba.restaurant_modifier_groups`, `gba.restaurant_modifier_options`, and `gba.restaurant_menu_item_modifier_groups`:
   - Modifier groups define `min_select` (`0..50`), `max_select` (`1..50`, `>= min_select`), and `currency`.
   - Modifier options belong to one group, define signed `price_delta_minor`, `sort_order`, and optional `(stock_item_id, stock_quantity)` linking directly to `STOCK-01` (`gba.stock_items`) for add-on ingredient reconciliation in Slice 3.
   - Menu item <-> modifier group attachments enforce same-branch composite FKs, active group on attach, and strict currency equality between menu item and modifier group (protected against currency drift on update).
3. Append-only `gba.restaurant_recipes` + `gba.restaurant_recipe_lines`:
   - Versioned per-portion ingredient BOMs for a menu item (`revision = latest + 1` under parent menu item row lock).
   - Lines reference `gba.stock_items(tenant_id, id)` with unique material per revision, positive integer `quantity` in each material's `quantity_scale`, and reject archived `STOCK-01` materials.
   - Deferred constraint trigger verifies lines `1..line_count` are complete on commit.

## API Routes (`/v1/businesses/{business_id}/restaurant`)
- `GET /menu-items`, `GET /menu-items/{menu_item_id}`, `GET /menu-items/{menu_item_id}/revisions`, `PUT /menu-items/{menu_item_id}`
- `GET /modifier-groups`, `GET /modifier-groups/{group_id}`, `PUT /modifier-groups/{group_id}`, `PUT /modifier-groups/{group_id}/options/{option_id}`
- `PUT /menu-items/{menu_item_id}/modifier-groups`
- `GET /menu-items/{menu_item_id}/recipes`, `GET /menu-items/{menu_item_id}/recipes/{revision}`, `POST /menu-items/{menu_item_id}/recipes`

Reads require `restaurant.read`; all mutations require `restaurant.manage` and `Idempotency-Key`. No cross-company delegation.
