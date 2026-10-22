# L2b — guests book staged services: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l2b-guest-stages`, parent
`401c05d` (L2 design decisions 8–10, [design](../../PACKAGE_L2_DESIGN_2026-10-22.md)), source commit
`ca447852770e5303dab94b14966c864674502d0c`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob,
command, exit code and log digest. No network; no migration; readiness unchanged.

## What changed

| Area | Change |
|---|---|
| Availability | A staged start is offered for an artist when the artist is free in their working stages and some resource of every other stage kind is free for all its intervals (bookings, unexpired holds, blocks, staff reservations). The artist may serve another client while a colour develops |
| Guest hold | The guest names the artist; the hold locks the artist and every candidate of the other kinds in id order, re-checks the slot, places every stage with the L2a planner; an unplaced visit is a stored 409 |
| Web contract | `quoteSchema` accepts version 1 without stages and version 2 with them, strictly (new `tests/booking-contracts.spec.ts` in `test:unit`) |
| Removed | The L2a guest refusal `STAGED_SERVICE_NOT_ONLINE` and its test (superseded) |

## Failures kept

- **web red**: `booking-contracts.spec.ts` 1 failed (version 2 refused), 2 passed — expected.
- **red-1**: 5 failed (guests refused), 1 passed (an unstaged guest booking unchanged) — expected.
- The record script first failed on an apostrophe in a string (before any commit); fixed.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l2b-20261022-401c05d`: **static-1** PASS; **focused-1** PASS,
**219 passed**; **full-1** PASS, **2464 passed, 4 skipped**. Two guests racing for the last chair: one
hold, after an observed `pg_locks` wait.

## Remaining (by plan)

L2c: visits with several services. The customer screens show no stage detail yet (L7). Migrations
0001–0067 unchanged; the next is **0068**.
