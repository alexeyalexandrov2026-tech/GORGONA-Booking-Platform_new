# Package M, slice M6b — planning forms, fleet, carrier grants and the dispatcher's navigation (2026-10-25)

Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и
начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» 2026-10-24: «Делай как считаешь
нужным я доверяю тебе». 2026-10-25: «Поднятнуть а потом продолжить», then "Continue with M6b the same way."
Plan: [PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md), slice M6 second half after
[M6a](PACKAGE_M6A_DESIGN_2026-10-25.md). Branch `codex/package-m6b-transport-forms` from `1d8e6b2` (M6a).

## Scope

- **Complete order pagination:** `GET orders` returns up to 50 orders in id order with `next_cursor`, continued
  with `?after=`; today it stops silently at 100.
- **Fleet (owner or manager only, never a delegate — ADR-0031):** register a driver (name, location) or a truck
  or trailer (unit number, location) and correct a name or unit number (`PUT` with the same id).
- **Orders (owner or manager):** create an order for an active customer (counterparties with the customer role,
  read to the end) with up to 50 loads (description, quantity, unit), and edit it with its expected revision;
  each load shows how much is already planned on trips.
- **Trips (owner or manager):** plan a trip at a location with stops (pickup or delivery, place, time zone, date,
  window start and end entered in that stop's own zone) and legs (a load, quantity, pickup and delivery stop);
  edit a trip while it is planned and unassigned. Server refusals (overplanned load, invalid leg, unknown zone,
  stale revision) are shown in words and the form keeps what was entered.
- **Carrier grants:** the grant form offers transport actions — plan trips, assign crews, record stop events —
  with or without booking access (a new "No bookings" choice); any transport action brings `transport.read`.
  The grant list states rights in words.
- **Dispatcher's navigation:** a delegate sees "Transport" when the grant holds `transport.read` and the
  calendar and bookings only with `booking.read`. On the transport screen a delegate sees the board and trip page
  with only the forms the grant allows (assign with `transport.assign`, stop events with `transport.events`);
  planning forms for delegates stay out of M6b (a delegate cannot read the owner's customers or locations) and
  fleet forms never appear for a delegate.
- No new migration (next stays **0079**).

## Acceptance of M6b (NOT TESTED)

| id | Requirement |
|---|---|
| M6b-01 | Orders are listed completely in pages of 50 with a cursor; a malformed cursor is refused |
| M6b-02 | An owner registers a driver and a truck and corrects a driver's name; a delegate never sees fleet forms |
| M6b-03 | An owner creates an order for an active customer with several loads and edits it with its revision |
| M6b-04 | An owner plans a trip with stops in their own time zones and legs from the order's loads; an overplanned leg is refused in words and the corrected form saves |
| M6b-05 | The grant form offers transport actions with or without bookings; the list states the rights in words |
| M6b-06 | A carrier's dispatcher reaches the owner's Transport screen through the grant, sees only the granted forms, assigns a crew and records an arrival |
| M6b-07 | Real browser, desktop and mobile: keyboard reachable, axe clean, no horizontal scroll; the database holds exactly what the screens did |
| M6b-08 | Strict response contracts refuse unknown or missing fields; the full suite stays green |
