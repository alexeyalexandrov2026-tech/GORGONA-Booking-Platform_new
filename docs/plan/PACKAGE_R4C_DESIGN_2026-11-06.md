# Package R, slice R4c — extensions and shortened periods on the shared occupancy (2026-11-06)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 4, acceptance R-04.
Previous slice: [R4b](PACKAGE_R4B_DESIGN_2026-11-06.md); handoff [NEXT_AGENT_PACKAGE_R4C_2026-11-06.md](NEXT_AGENT_PACKAGE_R4C_2026-11-06.md).
Branch `codex/package-r4c-rental-extensions` from the R4b docs commit `86d2cad`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after R4b.

## Scope

- Migration **0102**: `rental_booking_periods` (insert-only period changes of a booking); `gba.rental_booking_peak`
  (0099), `gba.guard_rental_assignment` (0098) and `gba.guard_rental_agreement_version` (0101) replaced, each from its
  latest body, so they use the booking's **current period**; guards on period changes; module gate; tenant isolation;
  branch scope last. The shared occupancy guard is not changed: an assignment's hold already follows the assignment's
  own period.
- Service `business/rental_extensions.py`; route `POST bookings/{id}/agreement/period`; `load_booking` reports the
  current period.

## Decisions (R4c, agent)

1. **A period change** (an extension, an earlier return or a moved start) is an insert-only row numbered 2, 3 per
   booking; the booking's current period is its latest change, or the booked period when there is none. The booking
   row itself never changes. A cancelled booking, a booking without an agreement and a period of more than 366 days
   are refused.
2. **It is an agreement change**: the same transaction records the next agreement version with a reason, the new
   period, the same frozen rate card and the chosen extras priced from it (R4b); the database checks at commit that the
   latest version carries the current period.
3. **Occupancy moves with it**: availability counts every booking by its current period, so a change that would leave
   a booking of the class without a unit is refused (`RENTAL_UNAVAILABLE`, checked after the row, under the class
   lock). A booking holding a unit keeps the same unit: the current assignment is released and the same unit is
   assigned again for the new period, so its hold moves; a hold that would meet another hold or block of that unit is
   refused (`RENTAL_UNIT_BUSY`). The database checks at commit that a current assignment carries the current period.
4. **Assignments, availability and agreements use the current period** after a change; history stays (earlier
   periods, the released assignment and earlier agreement versions).
5. **Rules as before**: `rental.manage`; idempotency scope `rental.period`; module off writes nothing; branch scope by
   the booking's pickup branch; another company sees nothing; direct SQL updates and deletes refused.

## Acceptance of R4c — PASS 2026-11-07 (code `c38efe8`, [evidence](evidence/2026-11-06-r4c-rental-extensions/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R4c-01 | An extension records the period change, the next agreement version priced from the frozen card, and moves the unit's hold; history stays | PASS |
| R4c-02 | A change that leaves a booking of the class without a unit is `RENTAL_UNAVAILABLE`; one that meets another hold of the unit is `RENTAL_UNIT_BUSY`; a shorter period frees availability | PASS |
| R4c-03 | No agreement, a cancelled booking, a blank reason and a bad period are refused | PASS |
| R4c-04 | The database refuses updates, deletes, a period change without its agreement version and an assignment for an old period; module off writes nothing; scope holds | PASS |
| R4c-05 | 0101 -> 0102 keeps every row; R2, R3 and R4 behave as before without changes; the full suite stays green | PASS |

## Not in R4c

Security of payment (R5); handover, return and late return (R6); invoices (R7); screens (R8); moving the pickup or
return branch.
