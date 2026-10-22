# K6b2 — delivery source and stalled provider operations on the screen: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-k6b2-screen`, parent `9435e7f`
(K6b1), source commit `0af2a46d3399d460e91ce3bc4f7d398fe4bd5d1f`. [CHECKS.json](CHECKS.json) was written before the source commit and binds
every source blob, command, exit code and log digest. No network, nothing published, readiness
unchanged.

## What changed

| Part | Change |
|---|---|
| API | Each delivery in `GET …/provider-operations/{id}` names `source`: `webhook` (attested `stripe_snapshot_v1`), `provider_api` (attested `stripe_api_v1`, K6b1) or `null` (an unattested archive row). Each operation in the list and detail carries `stalled_since`: the provider time of its latest event when it is still `pending` or `not_final` and that event is more than 24 hours old |
| Screen | Each delivery reads *signed webhook* or *fetched by reconciliation*; a stalled operation shows **No final event for over 24 hours** with its latest time and a pointer to the provider's dashboard |
| Runbook | Both explained in *Details and what disagrees* |

## Acceptance (new tests: 3, plus the K4b and K4a checks)

| Requirement | Test | Result |
|---|---|---|
| A webhook and its retrieval show both sources | `test_each_delivery_names_how_it_arrived` | PASS |
| Old not-final is stalled; old final, fresh not-final are not | `test_an_operation_without_a_final_event_for_a_day_shows_since_when` | PASS |
| A pending operation waiting a day is stalled in list and detail | `test_a_pending_operation_waiting_a_day_is_stalled` | PASS |
| The K4b delivery view names its source | `test_the_detail_lists_every_event_decision_and_delivery` | PASS |
| Real browser (desktop, mobile): every old processing payment shows the marker | `test_k4a_real_browser_provider_operations` | PASS |
| Web contracts: only known sources; only pending or not-final may be stalled | `web/tests/financial-contracts.spec.ts` | PASS |

## Failures kept

- **red-1**: 3 failed — `source` and `stalled_since` did not exist (expected).
- **dev-1**: 1 failed, 675 passed — the K4b test listed the delivery keys without `source` (updated; it
  now asserts `webhook`).

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-k6b2-20261021-9435e7f`:

- **static-1** PASS (ruff, format, mypy, web typecheck, lint, format, unit, build). The optional npm
  audit could not reach the registry (network timeout) — **NOT TESTED** here; no dependency changed
  (checked), and K6b1's audit found 0.
- **focused-1** PASS: **676 passed**.
- **full-1** PASS: **2398 passed, 4 skipped**.

## Limits

The real sandbox run is K6c. No live mode, deployment or production migration. Next migration **0065**.
