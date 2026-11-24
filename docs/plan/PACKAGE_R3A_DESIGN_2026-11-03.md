# Package R, slice R3a — assigning a unit to a booking on the shared occupancy (2026-11-03)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 3 and acceptance R-03 (RENT-01 "a double
issue is impossible"). Previous slice: [R2](PACKAGE_R2_DESIGN_2026-11-03.md); handoff
[NEXT_AGENT_PACKAGE_R3_2026-11-03.md](NEXT_AGENT_PACKAGE_R3_2026-11-03.md). Branch `codex/package-r3-rental-assignment` from
the R2 docs commit `e96e8fc`, in the O5 worktree. Same process: failing tests first, gates on the VM `gorgona-dev`, a
source-bound record, code and docs commits, push for CI without a PR.

## R3 is split in two

The shared occupancy (ADR-0022) has one guard function for every source of an allocation, already replaced in 0019,
0032 and 0075; changing it is the riskiest step of the package. **R3a** (this) brings rental units onto it and
assigns them. **R3b** adds maintenance and blocks, moves between branches and their effect on availability.

## Scope of R3a

- Migration **0098**: resource kind `rental_unit`; allocation source kind `rental_assignment`; `rental_units.resource_id`
  (each unit has its own resource in its branch; existing units get one in the migration); `rental_assignments` and
  `rental_assignment_releases` (insert-only); the shared guard `gba.guard_resource_allocation()` replaced with the 0075
  body kept whole plus the rental lane; module gate; tenant isolation; the `-- Rental branch scope:` section last.
- Service `business/rental_assignments.py`; R1 unit saves create and move the unit's resource; R2 cancellation
  releases the booking's assignment. Routes: `POST bookings/{id}/assignment`, `GET bookings/{id}/assignments`.

## Decisions (R3a, agent)

1. **A unit is an occupancy resource**: kind `rental_unit`, its branch, active while the unit is active. Rental resources
   take only rental assignment allocations, and rental assignments only rental resources (the guard checks both ways).
   A unit's resource follows the unit: same branch, inactive once the unit is retired.
2. **Assigning** names a unit for a booking: the unit is active, of the booked class, at the pickup branch, and the
   booking is not cancelled. The assignment occupies the unit's resource for the whole booking period through one
   confirmed allocation, so **a unit can never be assigned to two overlapping bookings** (the exclusion constraint of
   0018); a busy unit is `RENTAL_UNIT_BUSY` (409).
3. **One current assignment per booking.** Assigning another unit replaces the current one: the earlier assignment gets a
   release (reason `replaced`) and its allocation is released in the same transaction; history stays. Cancelling a
   booking releases its current assignment (reason `cancelled`). A swap after handover comes with R6.
4. **The database** rechecks every rule: an allocation of a rental assignment matches its assignment exactly and is
   created with it; it is released only by a release written in the same transaction.
5. **Rules as before.** `rental.manage` to assign; idempotency scope `rental.assignment`; module off refuses and writes
   nothing; another company sees nothing; a branch-limited member assigns only at its branch; direct SQL updates and
   deletes are refused. Two racing assignments of one unit to two overlapping bookings leave one after an observed
   `pg_locks` wait (the service locks the unit row).

## Acceptance of R3a — PASS 2026-11-03 (code `ab98936`, [evidence](evidence/2026-11-03-r3a-rental-assignment/CHECKS.json))

Refined during the slice: migrations may not lift row security, so the upgrade does not fill existing units; no unit can exist before 0098 in a real database (rental was never enableable) and the not null refuses the upgrade loudly if one did. R3a-01 and R3a-06 are accepted in that form.

| id | Requirement | Result |
|---|---|---|
| R3a-01 | Every unit has its own active rental resource in its branch; existing units get one in the upgrade | PASS |
| R3a-02 | A unit of the booked class at the pickup branch is assigned for the booking period with one confirmed allocation; a wrong class, branch, retired unit or cancelled booking is refused | PASS |
| R3a-03 | A unit is never held by two overlapping bookings (database exclusion); two racing assignments leave one after an observed wait | PASS |
| R3a-04 | A new assignment replaces the current one and releases its allocation; a cancellation releases the booking's assignment; history stays | PASS |
| R3a-05 | The shared guard keeps every earlier lane (booking, reservation, shift, trip) and refuses forged rental allocations, updates and deletes; module off writes nothing; scope holds | PASS |
| R3a-06 | 0097 -> 0098 keeps every row and gives each existing unit its resource; the full suite stays green | PASS |

## Not in R3a

Maintenance and blocks, moves between branches and their effect on availability (R3b); swaps after handover (R6);
screens (R8).
