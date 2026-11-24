# Design: REST-01 Slice 5 — Restaurant Management UI & Real-Browser E2E (2026-11-21)

Aligned with `docs/adr/0037-restaurant-tables-menu-kitchen-checks.md` and `docs/plan/PACKAGE_REST01_PLAN_2026-11-20.md`.
No database migration or backend API change (next migration remains `0134`).

## Screens (`/restaurant/`)
Mounted inside `ManagementLayout` for active non-delegated members (`owner`, `manager`, `front_desk`, `artist` — matching `restaurant.read`):

1. **Floor & Reservations tab**:
   - Lists branch dining areas, tables (`min_covers..max_covers`), and independent table reservations.
   - `restaurant.manage` (`owner`/`manager`): create dining areas and tables.
   - `restaurant.service` (`front_desk`/`manager`/`owner`): create independent table reservations and advance lifecycle (`Seat`, `Complete`, `Cancel`, `No-show`).
2. **Menu & Recipes tab**:
   - Lists versioned menu items (`hot`/`cold`/`bar`/`pastry`, minor-unit prices displayed in currency major units), modifier groups & options, and recipe BOMs referencing `STOCK-01` materials.
   - `restaurant.manage`: create menu items, modifier groups, modifier options (with optional `STOCK-01` ingredient link), attach modifier groups to items, and append recipe BOM revisions.
3. **Checks & Split Billing tab**:
   - Lists active and closed checks with frozen line items, modifiers, and totals.
   - `restaurant.service`: open independent checks (`dine_in`/`takeout`/`bar`/`delivery`, optional table), add order lines with modifiers, fire draft lines to kitchen stations, void draft lines, split checks (`by_items` or `by_amounts`), and close checks.
   - Company-wide `owner`/`manager`: preview and post `STOCK-01` ingredient write-offs, issue per-share `FIN-03` invoices, record `FIN-03` credit-note or external refunds, and view live `Reconciliation` totals.
4. **Kitchen Station Board tab**:
   - Station filter (`All`, `hot`, `cold`, `bar`, `pastry`) and ticket queue.
   - `restaurant.kitchen` (`artist`/`front_desk`/`manager`/`owner`): advance tickets (`Start`, `Mark ready`, `Serve`); `restaurant.manage` can also `Void`.

## Verification
- Web: `npm run typecheck`, `lint`, `format:check`, `test:unit`, `next build` (`out/restaurant/index.html`).
- Real-browser E2E (`web/tests/restaurant.spec.ts` + `api/tests/integration/test_restaurant_browser.py`): desktop + mobile (`390px`, zero horizontal scroll), `axe-core` (0 violations), keyboard tab navigation, multi-role isolation (`owner`, `front_desk`, `artist`), and PostgreSQL 18 read-back of checks, tickets, splits, and `STOCK-01` write-off balances.
