# Package R, slice R2 — rental class bookings and availability (2026-11-03)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 3 and acceptance R-02. Previous
slice: [R1](PACKAGE_R1_DESIGN_2026-11-03.md) and [ADR-0036](../adr/0036-rental-classes-and-units.md); handoff
[NEXT_AGENT_PACKAGE_R2_2026-11-03.md](NEXT_AGENT_PACKAGE_R2_2026-11-03.md). Branch `codex/package-r2-rental-bookings`
from the R1 docs commit `101e3ad`, in the O5 worktree. Same process: failing tests first, gates on the VM
`gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR.

## Scope

- Migration **0097**: `rental_bookings` (insert-only) and `rental_booking_cancellations` (insert-only, one per
  booking); guards that raise `check_violation` with a named constraint; module gate; tenant isolation; select and
  insert grants only; the `-- Rental branch scope:` section last.
- Service additions in `business/rental_bookings.py`; routes under `/v1/businesses/{id}/rental`: `GET bookings`
  (`?class_id=`, `?after=`), `GET bookings/{id}`, `POST bookings`, `POST bookings/{id}/cancellation`,
  `GET availability?class_id=&location_id=&starts_at=&ends_at=`.

## Decisions (R2, agent)

1. **A class booking holds a class, never a unit** (RENT-01 part 1): a number (per business, in sequence), the
   class, a customer (an active counterparty with the customer role), a pickup branch and a return branch, a period
   `[starts_at, ends_at)` in UTC (ends after starts, at most 366 days) and an optional note. It is insert-only; a
   cancellation is its own record with a reason, once (`RENTAL_BOOKING_CANCELLED`, 409, for another).
2. **Availability** of a class at a branch over a period = active units of the class at that branch minus the
   **largest number of bookings that overlap at the same instant** (pickup at that branch, not cancelled). A booking
   is accepted only while it leaves availability at or above zero; otherwise `RENTAL_UNAVAILABLE` (409). Bookings
   that touch end to start do not overlap. The availability read gives units, the peak of bookings and what is left.
3. **Races**: the service and the database both check under a lock on the class row; two racing bookings for the
   last unit leave one after an observed `pg_locks` wait. A forged insert above availability is refused by the
   database (`rental_bookings_availability_check`).
4. **References**: an unknown class, a retired-only class does not matter (units decide), an unknown branch or an
   unknown or non-customer counterparty is `INVALID_REFERENCE` (422); a bad period is 422.
5. **Rules as before.** `rental.read` to read, `rental.manage` to book and cancel; idempotency scopes
   `rental.booking` and `rental.cancellation`; module off refuses writes and nothing is written; another company sees
   nothing; a branch-limited member sees and books only at its own pickup branch; direct SQL updates and deletes are
   refused.

## Acceptance of R2 — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R2-01 | A booking holds a class with customer, branches and period, numbered and insert-only; references and periods are checked | NOT TESTED |
| R2-02 | Availability is units minus the peak of overlapping bookings; a booking that would go below zero is refused; touching periods and cancelled bookings do not count | NOT TESTED |
| R2-03 | A booking is cancelled once with a reason; the cancellation frees the class | NOT TESTED |
| R2-04 | Two racing bookings for the last unit leave one after an observed `pg_locks` wait | NOT TESTED |
| R2-05 | The database refuses a forged booking above availability, updates and deletes; module off writes nothing; another company sees nothing; a branch member sees and books only at its branch | NOT TESTED |
| R2-06 | 0096 -> 0097 keeps every row; the full suite stays green | NOT TESTED |

## Not in R2

Unit assignment and occupancy (R3), rates and quotes (R4), returns to another branch beyond recording the return
branch, screens (R8).
