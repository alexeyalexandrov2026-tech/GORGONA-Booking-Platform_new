# REST-01 Slice 1 — Floor Areas, Tables & Independent Table Reservations Design (2026-11-20)

## Scope
- Migration `0130_restaurant_floor_and_tables.sql` (invoker rights only):
  - Extends `gba.resources.kind` with `'restaurant_table'` and `gba.resource_allocations.source_kind` with `'restaurant_reservation'`.
  - Adds `gba.restaurant_areas`, `gba.restaurant_area_revisions`, `gba.restaurant_tables`, `gba.restaurant_table_reservations`, and `gba.restaurant_table_reservation_events`.
  - Enforces table resource identity, active cover range (`min_covers..max_covers`), reservation state machine (`booked -> seated|cancelled|no_show`, `seated -> completed|cancelled`), atomic allocation creation (deferred constraint trigger), and automatic allocation release on `complete`/`cancel`/`no_show`.
  - All 5 tables have tenant-isolation and restrictive branch-scope RLS (`location_id`).
- API routes under `/v1/businesses/{business_id}/restaurant`:
  - `GET/PUT /areas`, `GET /areas/{area_id}`
  - `GET/PUT /tables`, `GET /tables/{table_id}`
  - `GET/PUT /reservations`, `GET /reservations/{reservation_id}`, `GET/POST /reservations/{reservation_id}/events`
- Branch-scoped operations (`allow_location_scope=True`, `allow_delegation=False`).
