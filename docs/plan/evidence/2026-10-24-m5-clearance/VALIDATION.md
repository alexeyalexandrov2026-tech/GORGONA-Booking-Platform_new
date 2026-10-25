# M5 — hours-of-service profiles, telematics freshness and clearance: local validation

**PASS for this bounded local, synthetic slice (package M, TMS-03).** Branch `codex/package-m5-clearance`, parent
`e9ca58b` ([M5 design](../../PACKAGE_M5_DESIGN_2026-10-24.md), [ADR-0032](../../../adr/0032-transport-clearance.md)),
source commit `1180d41`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every source
blob, command, exit code and log digest. Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в
реестр модулей как невключаемый до приёмки и начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не
трогай.» User 2026-10-24: "Ok" (start M5), «Делай как считаешь нужным я доверяю тебе», "Continue".

## What changed

- Migration **0078**: `transport_hos_profiles` (insert-only versions of the business's rule profile, replaced
  with the expected revision), `transport_duty_records` (a driver's duty status over an interval; never
  overlapping) and `transport_telematics_pings` (a vehicle's observation time); facts carry a source and the
  source's record id; branch scope through the driver and the vehicle; module gate; select and insert only.
- Routes: `PUT/GET hos-profile` (`transport.manage`, never delegated), `POST drivers/{id}/duty-records` and
  `POST vehicles/{id}/pings` (`transport.events`), `GET trips/{id}/clearance?at=` (`transport.read`).
- Clearance is computed for a moment and never stored: each role is `cleared`, `not_cleared` (driving, window
  or cycle limit) or `unknown` (no profile, no data, stale data, a gap over the cycle, no or stale telematics,
  unassigned); the trip is `cleared` only when a driver and a truck are assigned and every role is `cleared`.

## Proof

`tests/integration/test_m5_transport_clearance.py` (6, real PostgreSQL), M5-01..M5-06: profile versions and a
stale revision; fresh, complete data within the US 11/14/10 and 70-hour/8-day profile clears the trip; no
profile, no data, stale duty data, stale telematics, a gap in the cycle and an unassigned driver or truck stay
`unknown`; driving, window and cycle limits give `not_cleared` with their reason; a repeated duty record or ping
changes nothing, other content and overlapping records are refused; module off, other company, other branch and
direct SQL are refused. `test_m5_upgrade.py`: 0077 -> 0078 keeps every row (M5-07).

## Failures kept

- red-1: 7 failed — M5 routes answered 404 and no migration 0078 (expected RED). M5-01's first assertion (no
  profile answers 404) held trivially before the route existed; the rest of that test failed.
- Before dev: ruff import order and a mypy `no-any-return` in a test helper.
- dev-1: 43 passed on the first run; gates passed on the first run.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-m5-20261024-e9ca58b`: **static-1** PASS; **focused-1** PASS,
**683 passed**; **full-1** PASS, **2600 passed, 4 skipped** (0:53:11 locally).

## Remaining

M6 (screens: dispatch board, trip page, events, grants, clearance; real browser desktop and mobile), M7 (money),
M8 (acceptance). Per-driver rule sets, exemptions, split sleeper berth and real ELD connectors come later. The
module stays not enableable until package M's acceptance and the owner's word. Next migration **0079**.
