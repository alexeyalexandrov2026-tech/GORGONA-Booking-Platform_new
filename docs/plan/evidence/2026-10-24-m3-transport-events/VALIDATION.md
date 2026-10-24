# M3 — stop events as idempotent facts; partial delivery: local validation

**PASS for this bounded local, synthetic slice (package M, TMS-01/TMS-03 build order).** Branch
`codex/package-m3-stop-events`, parent `fa86082` ([M3 design](../../PACKAGE_M3_DESIGN_2026-10-24.md),
[ADR-0030](../../../adr/0030-transport-stop-events.md)), source commit `f6ac5f1`. [CHECKS.json](CHECKS.json) was
written before the source commit and binds every source blob, command, exit code and log digest. Owner's word
2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и начинай
пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» User 2026-10-24: "Continue".

## What changed

- Migration **0076**: trip status `in_transit`; `transport_stop_events` (insert-only facts; source and source
  event id unique in the business; time stored in UTC) and `transport_event_quantities` per leg; a leg never
  loads more than planned nor resolves (delivered, refused, damaged) more than loaded — checked under the trip
  lock and again at commit. The first event starts the trip; a started trip keeps its plan (service and triggers
  on stops, legs and trips); assignments continue in transit. Branch scope, module gate, select and insert only.
- Route `POST /v1/businesses/{id}/transport/trips/{id}/events`; the trip view lists events and per-leg loaded,
  delivered, refused and damaged quantities.

## Proof

`tests/integration/test_m3_transport_events.py` (6, real PostgreSQL), M3-01..M3-07: an interstate trip starts
with its first event and records a partial delivery (leg 1: 7 delivered, 2 refused, 1 damaged; leg 2: 4 of 6
delivered, 2 open); a repeated event with the same source id changes nothing and other content is refused;
over-loading, over-resolving, wrong stop, wrong kind and unknown legs are refused and write nothing; a started
trip's plan is frozen also by direct SQL and its truck is replaced in transit; two racing deliveries leave one
after an observed `pg_locks` wait; module off, other company, other branch and direct SQL are refused.
`test_m3_upgrade.py`: 0075 -> 0076 keeps every row (M3-08).

## Failures kept

- red-1: 7 failed — no events route (404) and no migration 0076 (expected RED).
- Before dev: ruff E501 in the test docstring.
- dev-1: 72 passed on the first run; gates passed on the first run.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-m3-20261024-fa86082`: **static-1** PASS; **focused-1** PASS,
**660 passed**; **full-1** PASS, **2587 passed, 4 skipped** (0:41:26 locally).

## Remaining

M4: dispatcher scope on carrier grants (TMS-02, CORE-03 dispatcher part). Then M5-M8. Closing a trip and
proof-of-delivery documents come later. The module stays not enableable until package M's acceptance and the
owner's word. Next migration **0077**.
