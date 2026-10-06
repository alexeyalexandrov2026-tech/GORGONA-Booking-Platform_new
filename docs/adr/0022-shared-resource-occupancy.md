# ADR-0022 — Shared resource occupancy (CORE-04)

- Status: **Accepted (2026-10-05)** — the owner answered the four open decisions
  (below) and asked to continue; implementation follows the
  [package F plan](../plan/PACKAGE_F_PLAN_2026-10-05.md).
- Scope: master plan §12.2.1 and criterion CORE-04; builds on ADR-0003
  (booking occupancy under a GiST exclusion constraint), ADR-0019 (module gates)
  and ADR-0014 (location scope).

## Context

Today occupancy exists only for booking: `gba.booking_allocations` (migration
0003) holds one row per reserved resource with a half-open `tstzrange`, carries
the booking status through a composite key with `ON UPDATE CASCADE`, and the
exclusion constraint `booking_allocations_no_overlap` rejects overlapping `HOLD`
and `CONFIRMED` rows per tenant and resource (SQLSTATE 23P01). The service takes
`pg_advisory_xact_lock('gba:resource:{tenant}:{resource}')` in resource-id order
before changing occupancy; the constraint stays the authority. Reschedule cancels
and re-inserts under the same locks. Availability reads `booking_allocations`
plus `gba.resource_blocks` (staff blocks; not part of the exclusion set).

CORE-04 requires: "the old booking API and a new rental request one resource at
the same time — exactly one confirmed interval; a failure rolls back all
resources". The master plan forbids new modules from reserving shared resources
in an independent table before the transition is accepted, and forbids double
writes without one locking mechanism. Resources today are `artist`, `chair` and
`room` with capacity one; booking is single-resource
(module `booking_resources` limits).

## Decision (proposed)

1. **One authoritative occupancy table** `gba.resource_allocations` for every
   module: tenant, resource, source (`source_kind` from a closed list, `source_id`),
   half-open bounded `during`, `state` (`held`, `confirmed`, `released`), consumed
   `units` (default 1) and audit columns. Domain tables (bookings now; rentals,
   trips, work orders later) keep their own lifecycle and reference their
   allocations explicitly. No module keeps a private occupancy table.
2. **Exclusive resources** keep a PostgreSQL exclusion constraint on
   `(tenant_id, resource_id, during)` for active states. **Capacity > 1**
   (when a consumer needs it) uses an atomic sum check in a trigger under the
   same per-resource advisory lock; it never relies on application reads alone.
3. **One transactional mechanism**: a single SQL entry point (function or
   insert path with triggers) and one Python service `occupancy.reserve(...)`
   take the existing per-resource advisory locks in a stable order, insert all
   allocations of one operation or none, and map 23P01/capacity violations to
   one typed conflict. Booking and every new consumer call it.
4. **Booking transition in reversible steps**, never a big-bang rewrite:
   extend → backfill active intervals → reconcile (counts, owners, intervals) →
   booking writes through the shared mechanism while `booking_allocations` stays
   the compatible shape → concurrency gates across sources → switch reads →
   keep a compatibility representation and a documented rollback. Historical
   migrations stay unchanged; status still follows the booking atomically.
5. **Tenant and branch boundary** as everywhere: FORCE RLS, restrictive scope
   policies (branch sessions see allocations of their location's resources only),
   schema-guard definitions, insert-mostly grants, audit without personal data.
6. **Module gate**: allocations inherit the gate of their source module
   (booking keeps `booking_resources`); the shared table itself is core
   infrastructure, not an optional module.

## Owner decisions (2026-10-05)

- **Second real consumer:** a minimal staff reservation of one or more resources
  for an interval (no customer, no payment) — source kind `reservation`. It
  belongs to the "Booking and resources" module of master plan §4, so it uses the
  `booking_resources` gate and the staff permissions with branch scope (ADR-0014).
- **Capacity > 1:** later, with its first consumer; all resources stay exclusive.
- **`gba.resource_blocks`:** stays separate (availability only) for now.
- **Read switch:** `booking_allocations` stays a table, written by the booking path
  and mirrored into the shared table in the same transaction, until stage 1 closes.

## Implementation shape

- Migration 0018 creates `gba.resource_allocations` (FORCE RLS, branch scope
  through the resource, insert and state change only under triggers) with the
  exclusion constraint `resource_allocations_no_overlap` for `held`/`confirmed`,
  mirrors every existing `booking_allocations` row per tenant (state from the
  booking status) and adds a reconciliation function; a mismatch fails the
  migration. Triggers on `booking_allocations` keep the mirror exact for every
  write path (insert, status cascade), so the shared constraint decides booking
  versus reservation conflicts even for raw SQL.
- `gba.resource_reservations` (insert, then one cancellation) with its allocations
  in the shared table; a cancellation releases all of them.
- Python `occupancy` takes the per-resource advisory locks in id order for both
  consumers and maps either exclusion constraint to the same typed conflict.
- Availability reads the shared table (active reservations block slots); booking
  summaries keep reading `booking_allocations`.

## Acceptance (when implemented)

- CORE-04 race: the booking API and the second consumer reserve the same
  resource concurrently — exactly one confirmed interval; a multi-resource
  failure leaves no allocation of that operation (raw SQL without the lock and
  service-level races, as in `test_booking_concurrency.py`).
- Backfill and reconciliation prove identical active intervals, owners and
  counts before and after; rollback restores booking reads without data loss.
- Existing booking contracts, customer site and `/v1/salons` stay compatible;
  the 100-attempt booking gate keeps one success and 99 typed conflicts.
- Guard, branch-scope marker, red→green, focused and full suites, exact-SHA CI.

## Consequences

- One place decides conflicts for all modules; rentals, transport and work orders
  can be added without new double-booking risks.
- The booking engine changes internally; its public behaviour must not change,
  which needs a careful migration and compatibility tests.
- Until approval nothing changes: CORE-04 stays NOT TESTED and the booking
  module's limits keep "no occupancy shared with other modules".
