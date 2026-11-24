# Design: REST-01 Slice 3 — Independent Checks, Kitchen Station Tickets & STOCK-01 Write-Offs (2026-11-21)

Aligned with `docs/adr/0037-restaurant-tables-menu-kitchen-checks.md` and `docs/plan/PACKAGE_REST01_PLAN_2026-11-20.md`.

## Acceptance Invariants
- **Independence**: A guest check can be opened for `dine_in`, `takeout`, `bar`, or `delivery` with optional `table_id` and/or `reservation_id`, and never requires an active workforce shift or table reservation.
- **Frozen Pricing & Modifiers**: Adding an order line snapshots the menu item revision (`menu_item_revision`, `base_price_minor`, `kitchen_station`), latest recipe revision (`recipe_revision`), and selected modifier options (validated against attached modifier group `min_select..max_select` bounds, active status, and currency equality), freezing each option's `price_delta_minor` and optional `(stock_item_id, stock_quantity)`.
- **Station-Routed Kitchen Tickets**: Firing draft lines (`POST /checks/{check_id}/fire`) creates one `restaurant_kitchen_tickets` record per distinct `kitchen_station` (`hot`, `cold`, `bar`, `pastry`) in `queued` state. Kitchen staff (`restaurant.kitchen`) advance tickets through `queued -> preparing -> ready -> served` (or `voided`) with append-only `restaurant_kitchen_ticket_events`.
- **Coordinated `STOCK-01` Ingredient Write-Off**: `POST /checks/{check_id}/post-consumption` aggregates planned ingredient quantities across all non-voided fired/served lines (base recipe BOM lines × quantity + modifier option stock links × quantity), posts a single `STOCK-01` `write_off` (`reason='used'`) via `stock.post_document` when non-empty, and records an immutable `restaurant_check_consumptions` + `restaurant_check_consumption_lines` audit record bound to `stock_document_id` so consumption can never be double-posted.

## Schema (`0132_restaurant_checks_and_kitchen.sql`)
Adds `restaurant_tables_branch_key` unique `(tenant_id, id, location_id)` and 7 branch-scoped tables with tenant RLS, restrictive branch RLS (`-- Restaurant checks branch scope:`), invoker-rights triggers only, and `require_enabled_module('restaurant')`:
1. `gba.restaurant_checks`
2. `gba.restaurant_kitchen_tickets`
3. `gba.restaurant_kitchen_ticket_events`
4. `gba.restaurant_check_lines`
5. `gba.restaurant_check_line_modifiers`
6. `gba.restaurant_check_consumptions`
7. `gba.restaurant_check_consumption_lines`

## API Routes (`/v1/businesses/{business_id}/restaurant`)
- `GET /checks`, `GET /checks/{check_id}`, `POST /checks` (`restaurant.service`)
- `POST /checks/{check_id}/lines` (`restaurant.service`)
- `POST /checks/{check_id}/lines/{line_id}/void` (`restaurant.service` for `draft`, `restaurant.manage` for `fired`/`served`)
- `POST /checks/{check_id}/fire` (`restaurant.service`)
- `POST /checks/{check_id}/close` (`restaurant.service`)
- `GET /kitchen/tickets`, `GET /kitchen/tickets/{ticket_id}` (`restaurant.read`), `POST /kitchen/tickets/{ticket_id}/events` (`restaurant.kitchen` for `start`/`mark_ready`/`serve`; `restaurant.manage` for `void`)
- `GET /checks/{check_id}/consumption` (`restaurant.read`), `POST /checks/{check_id}/post-consumption` (company-wide `restaurant.manage` + `inventory.manage`, matching `STOCK-01` posting rules)
