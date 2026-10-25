# Package M, slice M6a — dispatch board and trip page (2026-10-25)

Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и
начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» 2026-10-24: «Делай как считаешь
нужным я доверяю тебе». 2026-10-25: «Поднятнуть а потом продолжить» (main was brought up to `ad21888`, then
package M continues). Plan: [PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md), slice M6, split like L7:
**M6a** (this) the dispatch board and the trip page; **M6b** orders and trip planning forms, fleet registration,
transport rights in the grant form and the dispatcher's navigation. Branch `codex/package-m6a-transport-screens`
from `ad21888` (= main).

## Scope

- **Complete pagination** of the lists the board reads: `GET trips`, `GET drivers` and `GET vehicles` return up
  to 50 items in id order with `next_cursor`, continued with `?after=`; an unknown cursor starts after it.
- **Web:** `lib/transport-contracts.ts` (strict response contracts, wired into `managementResponseSchema`),
  `lib/transport-api.ts`, `components/transport.tsx`, `app/transport/page.tsx` and a "Transport" navigation
  entry for owners and managers (also branch-limited ones; never a delegate in M6a).
- **The board:** every trip (paged to the end) with its reference, status, first and last window in their own
  stops' time zones, and the driver and truck now assigned.
- **The trip page:** stops with each window in the stop's own time zone; legs with planned, loaded, delivered,
  refused, damaged and open quantities; assignment periods (current and history); the event log in each stop's
  time zone; **assign or replace** a driver, truck or trailer (a replacement moment entered in the first stop's
  time zone); **record a stop event** with quantities for the legs that load or unload at that stop (the source
  is `dispatcher`; one source event id per form, kept across retries, so a lost answer repeats safely); **check
  clearance** now, with each role's status and reasons in words.
- No new migration (next stays **0079**).

## Acceptance of M6a (NOT TESTED)

| id | Requirement |
|---|---|
| M6a-01 | Trips, drivers and vehicles are listed completely in pages of 50 with a cursor |
| M6a-02 | The board shows every trip with its status, windows in the stops' time zones and the assigned driver and truck |
| M6a-03 | The trip page assigns a driver and truck, replaces the truck at a local moment and keeps the history |
| M6a-04 | The trip page records arrival, loading and a partial delivery with quantities; a retried form records one event |
| M6a-05 | The trip page shows clearance with each role's reasons; stale or missing data never shows as cleared |
| M6a-06 | Real browser, desktop and mobile: keyboard reachable, axe clean, no horizontal scroll; the database holds exactly what the screens did |
| M6a-07 | Strict response contracts refuse unknown or missing fields; the full suite stays green |
