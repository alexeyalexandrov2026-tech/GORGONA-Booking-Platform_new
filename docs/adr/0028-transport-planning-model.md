# ADR-0028: Transport module and the planning model (shipment order, load, trip, stop, leg)

Status: accepted for package M slice M1 (2026-10-23). Owner's word 2026-10-23: «Да, добавь модуль «Транспорт и
логистика» в реестр модулей как невключаемый до приёмки и начинай пакет M с первого среза. Готовность BEAUTY-01
и main пока не трогай.»

## Context

Stage 3 of the master plan includes TMS-01..03 (carrier, then the independent dispatcher, then broker/3PL, in
build order, not separate launches). The master plan §7.2 requires that **shipment order, load, leg, trip and
stop exist separately**, so one trip carries several loads, a load can be split between trips, partial
delivery is possible and a vehicle can change while history stays. Package M's plan is
`docs/plan/PACKAGE_M_PLAN_2026-10-23.md`.

## Decision

1. **Module.** A new optional module `transport` ("Transport and logistics"), depending on `counterparties`.
   It is registered with readiness `implemented` once code exists and **cannot be enabled** until its
   acceptance (ADR-0020 rule). Adding a module id is a structural registry change: `MODULE_REGISTRY_VERSION`
   becomes 4 (as ADR-0026 raised it to 3); a published configuration is never altered (ADR-0019). Writes are
   gated by `gba.require_enabled_module('transport')` and the early `require_module`; reads are not gated.
2. **Permissions.** `transport.read` and `transport.manage`; owners and managers hold both; permissions
   version 8. Transport routes are never delegated in M1 (delegation of dispatcher actions is slice M4).
3. **Shipment order and loads.** An order belongs to the business, names a customer counterparty and a
   reference unique in the business; it lists its loads (description, quantity in whole units of a unit label,
   optional weight in grams, optional shipper and consignee counterparties) with ids chosen by the client. The
   order is replaced whole with its expected revision. A load already planned on a trip keeps its id and
   cannot shrink below what is planned or be removed (`TRANSPORT_LOAD_PLANNED`).
4. **Trip, stops and legs.** A trip belongs to one branch (location), has a reference unique in the business
   and is replaced whole with its expected revision while it is `planned`: ordered stops (kind pickup or
   delivery, a place, an IANA time zone, a window stored in UTC) and legs (a load, a quantity, a pickup stop and
   a later delivery stop of the same trip). One trip carries several loads; a load is split across legs and
   trips by quantity; the planned total of a load over all trips never exceeds its quantity
   (`TRANSPORT_LOAD_OVERPLANNED`), checked under a lock on the load rows.
5. **Interstate time.** Windows are stored in UTC and shown with each stop's own time zone; a time zone must be
   known to PostgreSQL (`pg_timezone_names`).
6. **Scope and isolation.** Every table has RLS by company; trips, their stops and legs are scoped to the
   caller's branch; orders and loads are company-wide. The runtime role may insert and update through the
   service only; deletes are refused except the replacement of a planned trip's stops and legs, which the
   service performs in one transaction.

## Consequences

Later slices add assignments with periods and shared occupancy (M2), stop events and partial delivery (M3),
dispatcher grants (M4), clearance (M5), screens (M6) and money (M7). The module stays `implemented` and not
enableable until package M's acceptance and the owner's word.
