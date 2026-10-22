# Package L, slice L2 — stage-by-stage occupancy: design and decisions (2026-10-22)

**Status: design; decisions taken by the agent under the owner's full delegation** («Делай как
считаешь нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22). Branch
`codex/package-l2-occupancy` from L1 (`d62beef`). Builds package L decision 2
([plan](PACKAGE_L_PLAN_2026-10-22.md)). Platform part, not salon code: any direction with staged
services (spa, clinic, workshop, rental) books through the same occupancy.

## What exists (inspected)

- A booking writes one row per resource in `gba.booking_allocations` (unique booking + resource),
  mirrored into the shared `gba.resource_allocations` (0018) whose exclusion constraint decides
  every conflict between bookings, staff reservations and shifts.
- The mirror's status update, the backfill and the mismatch count match a booking allocation by
  booking and resource only. The guard on the shared table already matches the interval too.
- Readers that assume one allocation per booking: the management booking summary, reschedule,
  `load_booking`, the hold-expiry query (per resource, fine) and the customer availability
  (per resource, fine).
- Bookings take `artist`, `chair` or `room` resources; `staff` resources are for shifts only.

## Decisions

1. **One allocation per resource and continuous span.** For a staged variant each stage occupies
   the resources of its kinds for its minutes; consecutive stages on the same resource join into
   one interval, a gap starts another. The specialist is therefore free during `processing`, the
   chair stays held. A variant without stages keeps exactly one allocation of the whole duration.
2. **Kinds map to resources.** `specialist` → an `artist` resource, `chair` → `chair`, `room` →
   `room`, `equipment` → `equipment`; every resource active and in the booking's branch.
3. **The request names the specialist; other kinds may be named or found.** `resource_id` keeps its
   meaning (the specialist for a staged variant). An optional `stage_resources` map names the
   others; a kind left out is filled with the first free active resource of that kind in the branch
   (ordered by id). Every candidate's schedule lock is taken in id order before any write, so two
   visits cannot deadlock; the exclusion constraint stays the final arbiter.
4. **Schema 0067.** `booking_allocations_one_per_resource` becomes unique (booking, resource,
   start of interval); the mirror's status update, the backfill and the mismatch count also match
   the interval. Old rows and their mirrors are unchanged.
5. **The primary resource.** Where a single resource is shown (summary, hold view), it is the
   specialist: the `artist` allocation that starts first, else the only allocation.
6. **Reschedule keeps the plan.** Moving a staged booking moves every interval by the same offset on
   the same resources (a new specialist may be named; other kinds are found again if theirs is busy).
7. **Customer site in L2b.** The guest availability and hold for staged variants (all stage
   resources free) and multi-service visits come in L2b. Until then the customer site refuses a
   staged variant clearly (`STAGED_SERVICE_NOT_ONLINE`) instead of booking it wrongly.

## Slices

| Slice | Deliverable |
|---|---|
| L2a | 0067; stage plan (pure); hold API, staff create and reschedule with stage occupancy; primary resource in views; races with an observed `pg_locks` wait |
| L2b | Customer availability and hold for staged variants; visits with several services |

## Acceptance for L2a (NOT TESTED)

| id | Requirement |
|---|---|
| L2-01 | A staged booking holds the specialist only in active and finish stages and the chair for the whole visit; another client can take the specialist during processing |
| L2-02 | All or nothing: a busy chair or equipment refuses the whole booking and writes nothing |
| L2-03 | A free resource of a left-out kind is found; none free is a conflict |
| L2-04 | Two racing visits for the same specialist and chair: one wins, with an observed `pg_locks` wait |
| L2-05 | Confirm, cancel and expiry move every interval of the booking; the shared table mirrors each one (mismatch count 0) |
| L2-06 | An unstaged booking and every old booking behave exactly as before |
| L2-07 | Reschedule moves every interval; the customer site refuses a staged variant until L2b |
