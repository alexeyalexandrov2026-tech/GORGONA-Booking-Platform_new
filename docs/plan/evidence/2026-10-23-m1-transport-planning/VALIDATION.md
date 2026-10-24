# M1 — transport module and planning model: local validation

**PASS for this bounded local, synthetic slice (package M, TMS-01 build order).** Branch
`codex/package-m1-planning`, parent `917308a` ([M1 design](../../PACKAGE_M1_DESIGN_2026-10-23.md),
[ADR-0028](../../../adr/0028-transport-planning-model.md)), source commit `32bb8a4`. [CHECKS.json](CHECKS.json)
was written before the source commit and binds every source blob, command, exit code and log digest.
Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки
и начинай пакет M с первого среза. Готовность BEAUTY-01 и main пока не трогай.»

## What changed

- Module `transport` ("Transport and logistics"): optional, depends on counterparties, readiness
  `implemented`, **not enableable** until package M's acceptance. Registry version 4 (a new module id is a
  structural change); permissions `transport.read` / `transport.manage` for owners and managers (version 8).
- Migration **0074**: `transport_orders`, `transport_loads` (never deleted; a removed load is marked),
  `transport_trips`, `transport_stops` (a known IANA time zone; windows stored in UTC),
  `transport_legs` (from a pickup to a later delivery of the same trip). A load is never planned beyond its
  quantity: the trip save locks the loads, and a deferred trigger rechecks at commit. Writes are gated by the
  module; RLS by company; trips, stops and legs scoped to the branch.
- Routes under `/v1/businesses/{business_id}/transport`: `PUT/GET orders/{order_id}`, `GET orders`,
  `PUT/GET trips/{trip_id}`, `GET trips` (idempotent, replaced whole with the expected revision).

## Proof

`tests/integration/test_m1_transport_planning.py` (7, real PostgreSQL): the module is listed, implemented and
not enableable, and writes answer `MODULE_NOT_READY`; an order with two loads is replaced with its revision, a
stale revision and a taken reference are refused; one trip (Chicago, Indianapolis, New York) carries two loads
while a second trip takes the rest of a split load, over-planning is refused and the stops keep their time
zones with windows in UTC; legs must go from a pickup to a later delivery, an unknown zone or a backwards
window is refused; a planned load cannot be removed or shrunk below its plan; two racing plans of one load
leave at most its quantity after an observed `pg_locks` wait; with the module off writes answer
`MODULE_DISABLED` and write nothing, another company sees nothing, direct SQL deletes of orders, loads and
trips are refused. `test_m1_upgrade.py`: 0073 -> 0074 keeps every row.

## Failures kept

- red-1: 1 failed, 6 errors — `KeyError: 'transport'`, the module did not exist (expected RED).
- Before dev: M1-01 sent a minimal order body that fails validation (422) before the module check; now a
  full body.
- **L9 gap found:** `test_location_access` did not re-create the branch-scope policies of 0072 and 0073
  after its damage case; their markers were added with 0074.
- dev-1: 3 failed, 80 passed — the unknown-zone case built its time with `ZoneInfo` in the test; two pinned
  registry-version assertions (3 -> 4).
- gates-1: static-1 failed on mypy — a fifth pinned registry version (`tests/unit/test_financial_documents.py`).
- gates-2: full-2 1 failed, 2570 passed — a sixth pin, 19 modules in `tests/unit/test_configuration_contracts.py`;
  all tests were then searched for module and version pins.

## Gates (final, suffix 3)

Run folder `GorgonaBookingTests/package-m1-20261023-917308a`: **static-3** PASS; **focused-3** PASS,
**494 passed**; **full-3** PASS, **2571 passed, 4 skipped** (0:49:18 locally).

## Remaining

M2: assignments of driver, truck and trailer with periods and shared occupancy. Then M3-M8. The module stays
not enableable until package M's acceptance and the owner's word. Next migration **0075**.
