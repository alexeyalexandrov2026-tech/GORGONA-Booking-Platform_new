# Package M, slice M2 — assignments with periods in the shared occupancy (2026-10-24)

Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и
начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.» Plan:
[PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md). Architecture:
[ADR-0029](../adr/0029-transport-assignments-occupancy.md) on [ADR-0028](../adr/0028-transport-planning-model.md).
Branch `codex/package-m2-assignments` from `f056f6f` (M1 docs). Same process as M1.

## Scope

- Migration **0075**: resource kinds `driver`, `truck`, `trailer`; allocation source `trip_assignment`;
  `transport_drivers`, `transport_vehicles`, `transport_assignments`, `transport_assignment_ends`; the
  allocation guard for trip assignments; the deferred span check; RLS, branch scope, module gate, select and
  insert only.
- Service and routes under `/v1/businesses/{business_id}/transport`: `PUT/GET drivers/{driver_id}`,
  `GET drivers`, `PUT/GET vehicles/{vehicle_id}`, `GET vehicles`, `PUT trips/{trip_id}/assignments/{assignment_id}`
  (assign or replace), `POST trips/{trip_id}/assignments/{assignment_id}/end`; the trip view lists its
  assignment periods.
- Booking, stages, reservations and the salon staff list and count exclude transport kinds; the pinned guard
  source in `db/schema_guard.py` follows the migration.
- No screens (M6), no events (M3), no grants (M4).

## Decisions (M2)

1. Drivers and vehicles are registered once with client ids (`PUT` with the same body replays); a vehicle is a
   `truck` or `trailer` with a unit number unique in the business; each gets its own resource in its branch.
2. An assignment request: `schema_version`, `role`, `resource_id`, optional `starts_at` (default: the span
   start) and `replaces` (the open assignment of that role, or null). The resource must be active, of the
   role's kind and in the trip's branch; the trip must be planned with a non-empty span; `starts_at` lies in
   `[span start, span end)` and not before the end of an earlier period of that role
   (`TRANSPORT_ASSIGNMENT_INVALID`, 422). Replacing with the same resource is invalid.
3. `replaces` must name the open assignment of that role (null when none is open); anything else is
   `TRANSPORT_ASSIGNMENT_CONFLICT` (409). A replacement at `starts_at` equal to the old start leaves the old
   period empty: it is ended and released without a closed hold.
4. Ending: `ends_at` in `[start, span end]`; ending an already ended assignment is
   `TRANSPORT_ASSIGNMENT_CONFLICT`.
5. A busy resource is `TRANSPORT_RESOURCE_BUSY` (409) and the whole request writes nothing.
6. Saving a trip whose span would change while an assignment is open is `TRANSPORT_TRIP_ASSIGNED` (409).
7. A booking or reservation naming a transport resource is refused as unavailable before the database; the
   database guard refuses it too.

## Acceptance of M2 (NOT TESTED)

| id | Requirement |
|---|---|
| M2-01 | Drivers, trucks and trailers have their own lanes; booking, reservations and the staff list never use or show them; a forged allocation on them or a forged trip-assignment allocation is refused by the database |
| M2-02 | Assigning a driver, truck and trailer holds each for the trip's span; the trip view lists the periods |
| M2-03 | Replacing the truck at T closes `[start, T)` and opens `[T, end)`; the old period and its hold stay |
| M2-04 | A replacement onto a busy truck is refused and changes nothing: the old assignment stays open with its hold |
| M2-05 | Two racing assignments of one truck to overlapping trips leave one after an observed `pg_locks` wait; a stale `replaces` is refused |
| M2-06 | With an open assignment the trip's span cannot change (service and direct SQL at commit); legs inside the span still can |
| M2-07 | Ending an assignment releases the rest of its hold; the history stays |
| M2-08 | Without the module writes are refused and write nothing; another company and another branch see nothing; direct SQL updates and deletes are refused |
| M2-09 | 0074 -> 0075 keeps every row; the schema guard accepts the new guard; the full suite stays green |
