# L1 — service stages and equipment: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l1-stages`, parent `5eb534c`
(the [package L plan](../../PACKAGE_L_PLAN_2026-10-22.md)), source commit `7ce60eff8765dc80ab59fd3f43d3c9cc09700318`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No network; readiness unchanged (BEAUTY-01 stays partial until L8).

Decisions: the owner's full delegation of 2026-10-22 («Делай как считаешь нужным и правильным! Я
полностью даю тебе право выбора») and package L decisions 1–2.

## What changed

| Area | Change |
|---|---|
| Schema (0066) | `gba.variant_stages`: ordered stages of a variant (`active`, `processing`, `finish`; 1–720 minutes; resource kinds `specialist`, `chair`, `room`, `equipment`; at most 10). Company row policy; the runtime role may read, insert and delete. A deferred constraint trigger keeps the variant's booking duration equal to the sum of its stages; changing the duration of a staged variant is refused (`service_variants_duration_of_stages`). `resources_kind_valid` admits `equipment` |
| Rules | The specialist works in `active` and `finish` stages only (free during `processing`); a staged service needs an active stage; no kind twice in a stage; total at most 720 minutes (API and SQL) |
| API | `PUT /v1/salons/{id}/services/{variant}/stages` with `expected_revision` replaces the stages and sets the duration to their sum (409 `SERVICE_REVISION_CONFLICT` on a stale revision); clearing stages keeps the duration. Every service view (list, update, publish, unpublish) shows `stages`. Staff can create an `equipment` resource |
| Quote | A variant without stages quotes exactly as before (snapshot version 1, no `stages`). A staged variant adds its stages (snapshot version 2); add-on minutes join the last active stage; stages that disagree with the duration are not bookable (`stages_mismatch`) |
| Booking | Unchanged: a staged variant still books one resource for the whole visit. Stage-by-stage occupancy is L2 |

## Failures kept

- **red-1**: collection error (`StageSpec` missing) — expected.
- **red-2**: 21 failed (stages route 404, equipment refused, upgrade target missing) — expected.
- **dev-1**: 4 failed in `test_h3_upgrade` — the new "no equipment before 0066" copy rule replaced the
  older "no staff before 0032" rule; one predicate now keeps both.
- **full-1**: 1 failed, 2438 passed — `test_workforce_visibility_upgrade` ran the packaged workforce
  guard on a schema stopped at 0035; the guard approves the packaged schema, which now admits
  `equipment`. The test upgrades the same data to the head before the guard.

## Gates (final, suffix 2)

Run folder `GorgonaBookingTests/package-l1-20261022-5eb534c`: **static-2** PASS (npm audit 0);
**focused-2** PASS, **133 passed**; **full-2** PASS, **2439 passed, 4 skipped**.

## Remaining (by plan)

L2: each stage reserves its own resources through the shared occupancy (the specialist free during
processing). Found for L2: `booking_allocations_one_per_resource` allows one interval per resource and
booking, and the occupancy mirror and its mismatch check match on booking and resource only — a
specialist in stages 1 and 3 needs two intervals, so L2 changes both. No screen for stages yet (L7).
Migrations 0001–0065 unchanged; the next is **0067**.
