# ADR-0037: Restaurant Tables, Menu, Kitchen Orders, Split Checks and Ingredient Write-Offs (REST-01)

- **Status**: Accepted (technical implementation in progress; module remains `enableable=False` until full `REST-01` acceptance and owner approval)
- **Date**: 2026-11-20
- **Stage**: Master Plan Stage 5 (`REST-01`, Industry ID `2`: Restaurants and food service)

## Context
Master Plan §13–14.1.1 defines `REST-01`:
- Guests, dining floor tables, kitchen tickets, and orders must reuse the verified platform building blocks (`booking_resources` / `CORE-04`, `workforce` / `WORK-01`, `finance_documents` / `FIN-03`, `inventory` / `STOCK-01`, `counterparties`).
- Table reservations, staff shifts, and kitchen orders must remain independent: a table can be reserved without a shift or order, a kitchen order can exist without a table (takeout/bar/delivery), and shifts never lock or depend on tables.
- Modifiers, check splitting, refunds, and ingredient write-offs must stay reconciled with zero duplicate postings or second ledgers.

## Decision
1. **Optional module `restaurant`**: added to `modules.py` (`MODULE_REGISTRY_VERSION = 8`) with `Readiness.IMPLEMENTED` (`enableable=False`) depending on `("booking_resources", "counterparties", "finance_documents", "inventory", "workforce")`.
2. **Role-scoped, non-delegable permissions** (`PERMISSIONS_VERSION = 17`):
   - `restaurant.read`: read floor plan, tables, reservations, menu, kitchen tickets, and checks within branch scope (`artist`, `front_desk`, `manager`, `owner`).
   - `restaurant.kitchen`: update kitchen ticket preparation states (`artist`, `front_desk`, `manager`, `owner`).
   - `restaurant.service`: manage table reservations, open checks, order lines, kitchen firing, and check splits (`front_desk`, `manager`, `owner`).
   - `restaurant.manage`: manage dining areas, tables, versioned menu items, modifiers, recipes, and void/refund approvals (`manager`, `owner`).
   - None of these permissions are cross-company delegable.
3. **Shared occupancy via `CORE-04`**: each dining table owns an active `gba.resources` row (`kind = 'restaurant_table'`), and every active table reservation inserts a `confirmed` row in `gba.resource_allocations` (`source_kind = 'restaurant_reservation'`), enforcing non-overlapping holds at the PostgreSQL exclusion constraint level while releasing on `complete`, `cancel`, or `no_show`.
4. **Branch-scoped RLS & Invoker Rights**: every restaurant table carries `tenant_id` and `location_id`, enforces tenant isolation and restrictive branch scope RLS, and uses invoker-rights triggers only.
