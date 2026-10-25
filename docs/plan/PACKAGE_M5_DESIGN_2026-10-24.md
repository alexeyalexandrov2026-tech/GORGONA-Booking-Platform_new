# Package M, slice M5 — hours-of-service profiles and telematics freshness (2026-10-24)

Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и
начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» 2026-10-24: «Делай как считаешь
нужным я доверяю тебе». Plan: [PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md). Architecture:
[ADR-0032](../adr/0032-transport-clearance.md). Branch `codex/package-m5-clearance` from `3a444ea`.

## Scope

- Migration **0078**: `transport_hos_profiles` (insert-only versions), `transport_duty_records` (no overlap per
  driver) and `transport_telematics_pings`; RLS, branch scope through drivers and vehicles, module gate, select
  and insert only.
- Routes: `PUT/GET hos-profile`, `POST drivers/{id}/duty-records`, `POST vehicles/{id}/pings`,
  `GET trips/{id}/clearance?at=`.
- No real ELD or telematics connection; FAKE sources only.

## Acceptance of M5 (NOT TESTED)

| id | Requirement |
|---|---|
| M5-01 | A profile is replaced with its revision and its versions stay; a stale revision is refused |
| M5-02 | Fresh, complete duty records within the limits and fresh pings give `cleared` |
| M5-03 | Missing, stale or gapped duty records, no profile, missing or stale pings and an unassigned driver or truck never give `cleared` (`unknown` with reasons) |
| M5-04 | A driving, window or cycle limit exceeded gives `not_cleared` with the reason |
| M5-05 | A repeated duty record or ping changes nothing; other content with that id and overlapping records are refused |
| M5-06 | Without the module writes are refused and write nothing; another company and branch see nothing; direct SQL updates and deletes are refused |
| M5-07 | 0077 -> 0078 keeps every row; the full suite stays green |
