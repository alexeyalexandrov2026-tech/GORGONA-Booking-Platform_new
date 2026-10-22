# L2a — stage-by-stage occupancy: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l2-occupancy`, parent `f1403eb`
(the [L2 design](../../PACKAGE_L2_DESIGN_2026-10-22.md)), source commit `edd08491e239bc1eb9fe32ba035f0de3364115bb`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No network; readiness unchanged (BEAUTY-01 stays partial until L8).

Decisions: the owner's full delegation of 2026-10-22 («Делай как считаешь нужным и правильным! Я
полностью даю тебе право выбора») and the seven L2 design decisions.

## What changed

| Area | Change |
|---|---|
| Occupancy | A staged visit holds each resource only for its stages; consecutive stages join, a gap splits. The specialist is free while a colour develops; the chair and the processor stay held. All or nothing in one savepoint; the shared exclusion constraint decides |
| Resources | The request names the specialist (an active `artist`); chair, room or equipment may be named (kind, branch, activity checked: `STAGE_RESOURCE_INVALID`) or are found (first free in id order; none free is a conflict). Every candidate is locked in id order before any choice |
| Schema (0067) | One allocation per booking or source, resource and interval (`booking_allocations_one_per_interval`, `resource_allocations_one_per_interval`); the booking mirror, backfill and mismatch count match the interval; the schema guard approves the new mirror |
| Paths | Hold API (`stage_resources`), staff create and reschedule (the stored stages are kept; old resources preferred), specialist-aware slots (the artist may be busy during processing); a booking is shown under its specialist; the staff list filter matches any resource held |
| Customer site | Availability and hold refuse a staged service (`STAGED_SERVICE_NOT_ONLINE`) until L2b; unstaged services unchanged |
| Contracts | `QuoteView` accepts version 2 quotes with stages; version 1 output is byte-identical |

## Failures kept

- **red-1**: 2 collection errors (`StageResourceError` missing) — expected.
- **dev-1**: 3 failed — `QuoteView` refused version 2 quotes (an L1 gap: rescheduling a staged
  booking failed); a copy into a schema before 0067 could not hold two intervals per resource (the
  fixture copier keeps the first there); the L1 test of the interim one-resource booking was
  superseded and now checks the stored stages.
- **static-1**: mypy over the tests failed (keyword arguments from a dict in the new unit test, an
  untyped dict in an API test); I had run mypy on the sources only.
- The unit tests of the two pure helpers (`test_stage_spans.py`) were written after the code.

## Gates (final, suffix 2)

Run folder `GorgonaBookingTests/package-l2a-20261022-f1403eb`: **static-2** PASS; **focused-2** PASS,
**214 passed**; **full-2** PASS, **2459 passed, 4 skipped**.

## Remaining (by plan)

L2b: guest availability and hold for staged services (every stage resource free), visits with several
services. No screen for stage resources yet (L7). Migrations 0001–0066 unchanged; the next is **0068**.
