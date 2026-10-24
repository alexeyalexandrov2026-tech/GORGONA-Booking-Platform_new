# M4 — dispatcher scope on carrier grants: local validation

**PASS for this bounded local, synthetic slice (package M, TMS-02 and the dispatcher part of CORE-03).** Branch
`codex/package-m4-dispatcher-grants`, parent `c0f63e7` ([M4 design](../../PACKAGE_M4_DESIGN_2026-10-24.md),
[ADR-0031](../../../adr/0031-transport-dispatcher-grants.md)), source commit `4b6cd75`. [CHECKS.json](CHECKS.json)
was written before the source commit and binds every source blob, command, exit code and log digest. Owner's word
2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и начинай
пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» User 2026-10-24: "Continue with M4 the same
way."

## What changed

- Permissions version 9: `transport.read`, `transport.plan` (orders, trips), `transport.assign` (assignments),
  `transport.events` (stop events); `transport.manage` is now fleet registration only and never delegable.
- The delegable set is the four booking rights plus the four transport rights; migration **0077** widens the
  grant check to 1-8 rights; the API (`delegation_contracts.py`) and web (`web/lib/delegation-contracts.ts`)
  contracts accept them.
- Every transport route opts in to the ADR-0017 delegated path except driver and vehicle registration; the
  existing rules hold: both accounts checked per request, effective permission = grant ∩ the delegate's role,
  branch scope from the grant, `delegation.access` audit, authorization before idempotency.
- Pinned tests updated: `PERMISSIONS_VERSION` 8 -> 9 in three unit tests; `test_delegation_contracts` now pins
  the booking and transport delegable sets, `transport.manage` never delegable, front desk covers booking work
  and managers cover all of it. The upgrade fixture copy leaves out grants naming transport rights before 0077.

## Proof

`tests/integration/test_m4_dispatcher_grants.py` (5, real PostgreSQL), M4-01..M4-06: transport rights are
granted (8 rights) and shown in `/v1/me`, fleet registration is refused as a term; a named dispatcher reads and
records events but cannot assign, plan or register a vehicle, an unnamed member and the servicer's own owner get
nothing, every request is audited with the grant and permission; a dispatcher serving two carriers acts in each
only within that carrier's grant; owner revocation, servicer revocation, delegate removal and expiry block the
next command and an old receipt replay, while earlier assignments and events keep the dispatcher as executor; a
location-limited grant hides another branch's trips. `test_m4_upgrade.py`: 0076 -> 0077 keeps every row (M4-07).

## Failures kept

- red-1: 6 failed — the grant contract refused transport rights (422) and no migration 0077 (expected RED).
- Before dev: ruff E501 in the test docstring.
- dev-1: 132 passed on the first run; gates passed on the first run.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-m4-20261024-c0f63e7`: **static-1** PASS (API and web); **focused-1**
PASS, **676 passed**; **full-1** PASS, **2593 passed, 4 skipped** (0:41:24 locally).

## Remaining

The web workspace still shows a delegated business with booking navigation; transport screens and a dispatcher
board come in M6. Next: M5 (hours-of-service profiles and telematics freshness; TMS-03). The module stays not
enableable until package M's acceptance and the owner's word. Next migration **0078**.
