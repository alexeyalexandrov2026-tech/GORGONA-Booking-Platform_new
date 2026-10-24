# Package M, slice M1 — transport module and the planning model (2026-10-23)

Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и
начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» Plan:
[PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md). Architecture: [ADR-0028](../adr/0028-transport-planning-model.md).
Branch `codex/package-m1-planning` from `06d5a24`. Same process as package L.

## Scope

- Module `transport` registered (readiness `implemented`, not enableable); registry version 4; permissions
  `transport.read` / `transport.manage` (version 8).
- Migration **0074**: `transport_orders`, `transport_loads`, `transport_trips`, `transport_stops`,
  `transport_legs`; RLS, branch scope for trips, the module gate on inserts, insert/update through the service.
- Routes under `/v1/businesses/{business_id}/transport`: `PUT/GET orders/{order_id}`, `GET orders`,
  `PUT/GET trips/{trip_id}`, `GET trips`.

## Decisions (M1)

1. Ids are chosen by the client (orders, loads, trips) so a lost answer is retried safely with the same body;
   each replacement needs the expected revision (0 to create) and a stale one is `TRANSPORT_REVISION_CONFLICT`.
2. A trip is replaced whole while planned: stops in order (2 to 50), legs (1 to 100). A leg's pickup stop is a
   pickup and comes before its delivery stop, which is a delivery (`TRANSPORT_LEG_INVALID`).
3. A load's planned quantity over all trips never exceeds its quantity (`TRANSPORT_LOAD_OVERPLANNED`); the
   trip save locks the loads it touches, so two racing plans of one load leave at most its quantity (proved
   with an observed `pg_locks` wait).
4. An order's load that is planned cannot be removed or shrunk below its planned quantity
   (`TRANSPORT_LOAD_PLANNED`).
5. Windows: `window_start <= window_end`, both with an offset; the stop's time zone must be known.
6. Without the module enabled every write answers `MODULE_DISABLED` and writes nothing; reads continue.

## Acceptance of M1 (NOT TESTED)

| id | Requirement |
|---|---|
| M1-01 | The module is listed, `implemented`, not enableable; a configuration enabling it is refused (`MODULE_NOT_READY`) |
| M1-02 | An order with several loads is saved and replaced with its revision; a stale revision is refused |
| M1-03 | One trip carries several loads; a load is split across two trips; over-planning is refused |
| M1-04 | Stops keep their time zones and windows (interstate); a leg must go from a pickup to a later delivery |
| M1-05 | A planned load cannot be removed or shrunk below its plan |
| M1-06 | Two racing plans of one load leave at most its quantity after an observed `pg_locks` wait |
| M1-07 | Without the module writes are refused and write nothing; another company sees nothing; direct SQL deletes are refused |
| M1-08 | 0073 -> 0074 keeps every row; the full suite stays green |
