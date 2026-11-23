# ADR-0042: Specialized Venues — Education, Fitness, Hospitality & Events (SPECIAL-01)

- Status: Proposed (implemented behind `hospitality_events` module `enableable=False` until acceptance)
- Date: 2026-11-21
- Stage 8 Profiles Covered: `12 education`, `13 fitness`, `17 hospitality`, `18 events`, `35 personal_services`

## Context
Master Plan §10 and §13 Stage 8 require typed domain workflows (never generic untyped EAV blobs, §12.2) for:
- **Education & Fitness**: cohorts/classes/memberships with capacity enforcement, attendance/visit balance tracking, and completion results.
- **Hospitality**: room inventory with housekeeping states (`clean`, `dirty`, `occupied`, `maintenance`) and stay lifecycle (`reserved` → `checked_in` → `checked_out`, automatically marking rooms `dirty` on check-out and blocking check-in to non-clean rooms).
- **Events & Culture**: venues/events with strict capacity control, ticket registration/check-in, and cancellation restoring capacity atomically.

## Decision
Implement `SPECIAL-01` behind optional module `hospitality_events` (`Readiness.IMPLEMENTED`, `enableable=False`, `MODULE_REGISTRY_VERSION=13`, `PERMISSIONS_VERSION=22` with `SPECIAL_READ` / `SPECIAL_WORK` / `SPECIAL_MANAGE`) with migration `0145_special_hospitality_events_education_fitness.sql` (invoker rights only, explicit tenant RLS + restrictive branch scope + module write gates).
