# Package Plan: REST-01 — Restaurants and Food Service (2026-11-20)

Aligned with `docs/plan/GORGONA_MASTER_PLAN.md` §13–14.1.1 and `docs/adr/0037-restaurant-tables-menu-kitchen-checks.md`.
`REST-01` acceptance criterion:
> Table, shift, and kitchen order are independent; modifiers, split check, refund, and ingredient write-off are reconciled.

## Slices
1. **Slice 1 (`codex/package-rest-01-floor-and-tables`, migration `0130`)**:
   - Module `restaurant` (`Readiness.IMPLEMENTED`, `enableable=False`, `MODULE_REGISTRY_VERSION=8`) + `RESTAURANT_*` permissions (`PERMISSIONS_VERSION=17`).
   - Branch-scoped dining areas (with append-only revision history), tables bound to `gba.resources (kind='restaurant_table')`, and independent table reservations bound to `gba.resource_allocations (source_kind='restaurant_reservation')` with lifecycle (`booked` → `seated` → `completed` / `cancelled` / `no_show`), cover-range validation, and full branch RLS.
2. **Slice 2 (`codex/package-rest-01-menu-and-recipes`, migration `0131`)**:
   - Versioned menu items (minor-unit prices, currency, kitchen station), modifier groups and options (selection bounds, minor-unit price deltas), and recipe ingredient BOM links to `STOCK-01` (`inventory`) materials.
3. **Slice 3 (`codex/package-rest-01-checks-and-kitchen`, migration `0132`)**:
   - Independent guest checks (optional table/reservation link so walk-ins, takeout, and dine-in all work), order lines with frozen modifier snapshots, station-routed kitchen tickets (`queued` → `preparing` → `ready` → `served` / `voided`), and coordinated `STOCK-01` ingredient write-offs.
4. **Slice 4 (`codex/package-rest-01-split-billing-and-refunds`, migration `0133`)**:
   - Check splitting (by items or exact shares with strict total conservation), `FIN-03` invoice/obligation issuance per check, and coordinated refunds (`FIN-03` credit notes + refund obligations + voided/returned line reconciliation).
5. **Slice 5 (`codex/package-rest-01-ui`, no new migration)**:
   - Internal screens for Floor & Table Reservations, Menu/Modifiers/Recipes, Active Checks & Split Billing, and Kitchen Station Board with desktop + mobile (390px) + keyboard + axe real-browser E2E tests and PostgreSQL read-back.

## Non-Goals (Not Part of Technical Slices)
- Live payment gateway capture, hardware fiscal printers, delivery aggregator APIs, or alcohol/health-permit regulatory engines.
- Raising `REST-01` readiness or enabling `restaurant` without explicit owner approval.
