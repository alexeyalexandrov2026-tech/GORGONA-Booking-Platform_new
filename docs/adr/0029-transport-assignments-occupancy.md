# ADR-0029: Transport assignments with periods in the shared occupancy

Status: accepted for package M slice M2 (2026-10-24), under the owner's word for package M (2026-10-23):
«Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и начинай пакет M с первого
среза. Готовность BEAUTY-01 и main пока не трогай.» Builds on [ADR-0028](0028-transport-planning-model.md),
ADR-0022 (shared occupancy) and ADR-0025 (workforce shifts).

## Context

TMS-01 requires that a driver, truck or trailer can change on a trip while the history stays, and package M's
plan (decisions 3 and 4) puts vehicles and drivers into the shared occupancy so one truck is never on two trips
at once. `gba.resource_allocations` is the one occupancy table for every module (ADR-0022): its exclusion
constraint rejects two active allocations of one resource that overlap, an allocation keeps its resource,
source and interval for ever, and only its state moves forward. Workforce people already occupy their `staff`
resource with their **shifts** (ADR-0025), and the allocation guard allows only shifts there.

## Decision

1. **Own occupancy lanes.** Drivers, trucks and trailers are registered in transport (`transport_drivers`,
   `transport_vehicles`), each with its own `gba.resources` row of a new kind `driver`, `truck` or `trailer`
   in the trip's branch. A driver's trips do not use the workforce `staff` resource: the staff lane holds the
   person's shift, and a trip inside the shift would collide with it in the same exclusion constraint. Whether
   a trip fits the driver's hours is clearance (slice M5), not occupancy. *This changes plan decision 4
   ("drivers are workforce people")*: in M2 a driver is a named transport record; linking it to a user account
   comes with the driver's own screens, so the transport module gains no dependency on workforce.
2. **Transport kinds are for trips only.** The allocation guard refuses any allocation on a `driver`, `truck`
   or `trailer` resource that is not a trip assignment, and any trip assignment on another kind (as it already
   does for `staff` and shifts). Booking, stages, reservations and the salon staff list and count never use or
   show transport kinds.
3. **Assignment periods are insert-only.** An assignment names a trip, a role (`driver`, `truck`, `trailer`), a
   resource of that kind in the trip's branch and its start. Ending it is a separate insert-only fact with an end
   time. A period is `[start, end)`; while it has no end it runs to the end of the trip's span. A trip has at
   most one open assignment per role, and periods of one role on one trip never overlap.
4. **The span.** A trip's span is `[earliest window start, latest window end)` of its stops. An open assignment
   holds its resource from its start to the span end. While any assignment is open the span cannot change
   (`TRANSPORT_TRIP_ASSIGNED`); loads and legs inside the same span still can. A deferred check at commit
   keeps every open hold equal to the current span, so direct SQL cannot break it either.
5. **Replacement is one transaction, all or none.** Replacing at moment T: the old assignment ends at T, its
   open hold is released and a closed hold `[start, T)` for the old resource is inserted; the new assignment
   starts at T and holds `[T, span end)`. If the new resource is busy, the exclusion constraint refuses it and
   nothing changes (`TRANSPORT_RESOURCE_BUSY`). The request names the assignment it replaces; a stale one is
   `TRANSPORT_ASSIGNMENT_CONFLICT`. Ending without a successor releases the rest the same way.
6. **The guard ties holds to facts.** A `trip_assignment` allocation is inserted only in the transaction that
   created its assignment (hold to the span end) or its end (closed hold to the end time), with exactly that
   interval, resource and state `confirmed`; it is released only in the transaction that ended its assignment.
   The pinned guard source in `db/schema_guard.py` changes with it.
7. **Races.** Writes lock the trip row; each new hold first takes the resource's schedule lock (the existing
   `lock_resource_schedule`), so two racing assignments of one truck wait instead of deadlocking, and the
   exclusion constraint decides. Two racing replacements on one trip serialize on the trip row and the second
   sees a stale `replaces`.
8. **Scope and gates.** RLS by company; drivers and vehicles are scoped by their branch, assignments and their
   ends by their trip's branch. Inserts need the enabled transport module; the runtime role may only select
   and insert on the new tables. Routes need `transport.manage` to write and `transport.read` to read.

## Consequences

Stop events and partial delivery (M3) add facts to the same trip; dispatcher grants (M4) decide who may assign;
clearance (M5) reads the driver's lane and hours. Team drivers (two drivers at once), vehicle deactivation and
linking a driver to a user account come with later slices.
