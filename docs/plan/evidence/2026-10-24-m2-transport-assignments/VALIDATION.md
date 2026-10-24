# M2 — assignments with periods in the shared occupancy: local validation

**PASS for this bounded local, synthetic slice (package M, TMS-01 build order).** Branch
`codex/package-m2-assignments`, parent `0cfa590` ([M2 design](../../PACKAGE_M2_DESIGN_2026-10-24.md),
[ADR-0029](../../../adr/0029-transport-assignments-occupancy.md)), source commit `31bb854`. [CHECKS.json](CHECKS.json)
was written before the source commit and binds every source blob, command, exit code and log digest.
Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки
и начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.»

## What changed

- Migration **0075**: resource kinds `driver`, `truck`, `trailer`; allocation source `trip_assignment`;
  `transport_drivers`, `transport_vehicles` (each owns one resource in its branch; transport resources never
  change), `transport_assignments` and `transport_assignment_ends` (insert-only periods; one open period per
  role; periods of a role never overlap; the trip row is locked first). The shared occupancy guard learns trip
  holds; a deferred check keeps every assignment holding exactly its period and freezes the span of an assigned
  trip.
- Routes: `PUT/GET drivers`, `PUT/GET vehicles`, `PUT trips/{id}/assignments/{id}` (assign or replace),
  `POST trips/{id}/assignments/{id}/end`; the trip view lists its periods; a span change of an assigned trip is
  `TRANSPORT_TRIP_ASSIGNED`.
- Booking, reservations, the salon staff list and count and the onboarding fingerprint exclude transport kinds;
  `schema_guard` and `workforce_guard` approve the 0075 guard source and the widened checks.
- Plan decision 4 changed (ADR-0029): a driver is a transport record with its own lane, not the workforce staff
  lane (a trip inside the driver's shift would collide with the shift).

## Proof

`tests/integration/test_m2_transport_assignments.py` (8, real PostgreSQL) covers M2-01..M2-08: own lanes and
forged occupancy refused; assignments hold the span; a replacement at 12:00 keeps `[08:00, 12:00)` and opens
`[12:00, 17:00)`; a busy truck changes nothing; two racing assignments of one truck leave one and a stale
`replaces` is refused, both after an observed `pg_locks` wait; an open assignment freezes the span (service and
direct SQL at commit); ending releases the rest; module off, other company, other branch and direct SQL refused.
`test_m2_upgrade.py`: 0074 -> 0075 keeps every row (M2-09).

## Failures kept

- red-1: 9 failed — no routes (404) and no migration 0075 (expected RED).
- Before dev: ruff E501 in the guard pin, PT012 in the M2-06 test, mypy no-redef in `save_trip`.
- dev-1: 56 failed, 80 passed — `workforce_guard` also pins the kind and source-kind checks and the 0032 guard
  source, so every workforce route answered 503 (only `schema_guard` had been updated); the upgrade fixture copy
  carried trip holds into pre-0075 schemas (copy rule added).
- dev-2: 12 failed, 124 passed — a workforce damage case restored the old source-kind constraint, which the
  shared database's trip holds violate; the restore now includes `trip_assignment`.
- **Record slip found:** the L9a, L9b, zod and M1 records carry `added_migrations: []` and `next_migration: 72`,
  copied from an older record. True values: L9a 0072 -> 73, L9b 0073 -> 74, zod none -> 74, M1 0074 -> 75.
  Committed records are not rewritten; this record carries `0075` and next `76`.

## Gates (suffix 1, first pass)

Run folder `GorgonaBookingTests/package-m2-20261024-0cfa590`: **static-1** PASS; **focused-1** PASS,
**653 passed**; **full-1** PASS, **2580 passed, 4 skipped** (0:53:29 locally).

## Remaining

M3: stop events as idempotent facts and partial delivery. Then M4-M8. Team drivers, vehicle deactivation and
a driver's user account come later. The module stays not enableable until package M's acceptance and the owner's
word. Next migration **0076**.
