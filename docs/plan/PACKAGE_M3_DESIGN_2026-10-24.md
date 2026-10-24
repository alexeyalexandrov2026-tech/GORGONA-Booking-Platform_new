# Package M, slice M3 — stop events as idempotent facts; partial delivery (2026-10-24)

Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и
начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» Plan:
[PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md). Architecture:
[ADR-0030](../adr/0030-transport-stop-events.md). Branch `codex/package-m3-stop-events` from `acc6185` (M2 docs).

## Scope

- Migration **0076**: trip status `in_transit`; `transport_stop_events` and `transport_event_quantities`
  (insert-only); the quantity rule at insert and at commit; the plan freeze of a started trip; assignments
  allowed while in transit; RLS, branch scope, module gate, select and insert only.
- Route `POST /v1/businesses/{business_id}/transport/trips/{trip_id}/events`; the trip view lists its events
  and, per leg, loaded, delivered, refused and damaged quantities.
- No screens (M6), no grants (M4), no closing of a trip.

## Decisions (M3)

1. Body: `schema_version`, `source` (`^[a-z][a-z0-9_.-]{0,31}$`), `source_event_id` (1-200 visible characters),
   `stop_position`, `kind`, `occurred_at` (with an offset), optional `note` (up to 500), `quantities`
   (`leg_position`, `quantity`; legs listed once). A wrong stop for a leg, quantities on a kind that has none,
   or none on a kind that needs them is `TRANSPORT_EVENT_INVALID` (422).
2. A repeat of `(source, source_event_id)` with the same content answers 200 with the trip and writes nothing;
   different content is `TRANSPORT_EVENT_CONFLICT` (409).
3. Over-loading or over-resolving a leg is `TRANSPORT_QUANTITY_EXCEEDED` (409) and writes nothing.
4. Replacing a started trip's plan is `TRANSPORT_TRIP_STARTED` (409); an assignment replacement in transit works.

## Acceptance of M3 (NOT TESTED)

| id | Requirement |
|---|---|
| M3-01 | Arrival, loading and departure are recorded; the first event moves the trip to `in_transit`; times are stored in UTC |
| M3-02 | Partial delivery records quantities per leg; the rest stays open; refusal and damage are recorded facts |
| M3-03 | A repeated event with the same source id changes nothing; different content with that id is refused |
| M3-04 | Loading beyond the plan or resolving beyond what was loaded is refused and writes nothing; wrong stop or kind is refused |
| M3-05 | A started trip's plan is frozen (service and direct SQL); a truck replacement in transit keeps its history |
| M3-06 | Two racing deliveries that together exceed the load leave one after an observed `pg_locks` wait |
| M3-07 | Without the module writes are refused and write nothing; another company and branch see nothing; direct SQL updates and deletes are refused |
| M3-08 | 0075 -> 0076 keeps every row; the full suite stays green |
