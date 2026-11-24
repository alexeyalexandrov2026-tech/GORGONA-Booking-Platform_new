# Package R, slice R3b — rental unit blocks, moves between branches and availability (2026-11-03)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decisions 3 and 7, acceptance R-02 and R-03.
Previous slice: [R3a](PACKAGE_R3A_DESIGN_2026-11-03.md); handoff [NEXT_AGENT_PACKAGE_R3B_2026-11-03.md](NEXT_AGENT_PACKAGE_R3B_2026-11-03.md).
Branch `codex/package-r3b-rental-blocks` from the R3a docs commit `cf9ff3f`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR.

## Scope

- Migration **0099**: allocation source kind `rental_block`; `rental_unit_blocks` and `rental_unit_block_releases`
  (insert-only); the shared guard replaced again from the 0098 body kept whole, the rental lane taking blocks too;
  `gba.rental_booking_peak` replaced so availability counts blocked units; the unit guard replaced so a unit holding
  an unreleased future hold does not change its branch; module gate; tenant isolation; branch scope last.
- Service `business/rental_blocks.py`; routes `POST units/{id}/blocks`, `GET units/{id}/blocks`,
  `POST units/{id}/blocks/{block_id}/release`.

## Decisions (R3b, agent)

1. **A block** takes a unit out of service for a period `[starts_at, ends_at)` with a kind (`maintenance`, `repair`,
   `other`) and a reason: insert-only, it holds the unit's resource through a confirmed allocation of source kind
   `rental_block`, so it can never overlap an assignment of the unit (and no later assignment can overlap it):
   `RENTAL_UNIT_BUSY` (409). A block is released once (early end of maintenance); its hold is released with it.
2. **Availability counts blocks**: at every instant the bookings of the class at the branch plus the blocked units of
   the class there stay at or below the active units there. A block that would leave a booking without a unit is
   refused (`RENTAL_UNAVAILABLE`, 409), and a booking that meets a blocked unit is refused as before. The
   availability read reports the peak of bookings and blocks together.
3. **Moves between branches**: a unit changes its branch (and its resource follows) only while it holds nothing that
   ends after now (no current or future assignment or block): `RENTAL_UNIT_HELD` (409). Transit occupancy and
   one-way returns come with handover and return (R6).
4. **The database** rechecks every rule under the class lock (blocks and bookings) and the unit lock (holds and
   moves); the shared guard accepts a rental block hold only with its exact block created in the same transaction and
   releases it only with its release.
5. **Rules as before**: `rental.manage` to block and release; idempotency scopes `rental.block` and
   `rental.block_release`; module off writes nothing; branch scope by the unit's branch; another company sees nothing;
   direct SQL updates and deletes refused.

## Acceptance of R3b — PASS 2026-11-03 (code `b5cff95`, [evidence](evidence/2026-11-03-r3b-rental-blocks/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R3b-01 | A block holds its unit for a period with a kind and reason; it never overlaps an assignment of the unit either way; it is released once with its hold | PASS |
| R3b-02 | Availability counts blocked units; a block that would leave a booking without a unit and a booking that meets a blocked unit are refused | PASS |
| R3b-03 | A unit with a current or future hold does not move; without one it moves and its resource follows | PASS |
| R3b-04 | The shared guard keeps every earlier lane; the database refuses forged blocks, holds, updates and deletes; module off writes nothing; scope holds | PASS |
| R3b-05 | 0098 -> 0099 keeps every row; the full suite stays green | PASS |

## Not in R3b

Transit occupancy and one-way returns (R6); rates (R4); screens (R8).
