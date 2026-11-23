# Package Plan: SPECIAL-01 (Education, Fitness, Hospitality & Events)

Date: 2026-11-21
ADR: `docs/adr/0042-specialized-hospitality-events-education-fitness.md`
Profiles: `12 education`, `13 fitness`, `17 hospitality`, `18 events`, `35 personal_services`

## Deliverables
- Migration `0145_special_hospitality_events_education_fitness.sql` (6 branch-scoped tables: `special_programs`, `special_enrollments`, `special_rooms`, `special_stays`, `special_events`, `special_tickets`).
- Business & API layer (`/v1/businesses/{id}/special-venues/...`) with `Idempotency-Key` protection, `FOR UPDATE` capacity/housekeeping locks, and strict branch isolation.
- Unit contract tests, integration tests (capacity bounds, housekeeping state machine, ticket check-in/cancel conservation, branch isolation), and upgrade test `0144 -> 0145`.
