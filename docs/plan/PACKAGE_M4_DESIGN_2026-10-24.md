# Package M, slice M4 — dispatcher scope on carrier grants (2026-10-24)

Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и
начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» User 2026-10-24: "Continue with M4
the same way." Plan: [PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md). Architecture:
[ADR-0031](../adr/0031-transport-dispatcher-grants.md). Branch `codex/package-m4-dispatcher-grants` from `bc4c793`.

## Scope

- Permissions `transport.plan`, `transport.assign`, `transport.events` (new) beside `transport.read` and
  `transport.manage` (now fleet registration only); permissions version 9.
- Migration **0077**: the grant permission check allows the four transport rights and up to 8 rights.
- API and web delegation contracts accept the transport rights; transport routes opt in to delegation except
  driver and vehicle registration.
- No screens (M6).

## Acceptance of M4 (PASS locally in `4b6cd75`)

| id | Requirement |
|---|---|
| M4-01 | A grant may name the transport rights (up to 8 rights); fleet registration is never delegable; database, API and web contracts agree |
| M4-02 | A named dispatcher of the servicing company plans, assigns and records events for the carrier only within the granted actions; an ungranted action, the fleet registration and an unnamed member are refused |
| M4-03 | A dispatcher serving two carriers acts in each only within that carrier's grant |
| M4-04 | Revocation by either side, delegate removal and expiry block the next transport command and an old receipt replay; earlier assignments and events stay with their executor |
| M4-05 | Every delegated transport request audits the executor, the servicer company, the grant and the permission |
| M4-06 | A location-limited grant keeps the dispatcher out of another branch's trips |
| M4-07 | 0076 -> 0077 keeps every row; the full suite stays green |
