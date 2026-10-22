# Package L — the beauty cycle (BEAUTY-01): plan and decisions (2026-10-22)

**Status: plan; decisions taken by the agent under the owner's full delegation** («Делай как считаешь
нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22). Local branch
`codex/package-l-plan` from `main` `0591d3a`. No code yet. Production stays one common launch of all
39 directions (master plan §1 item 13, §13); this package is **build order** for stage 3, not a beauty
launch.

## Why this package now

Stages 0–2 are technically verified except CORE-03's dispatcher part: booking and shared occupancy
(CORE-04), finance (FIN-01, FIN-02, FIN-03), workforce (WORK-01) and materials (STOCK-01). Stage 3
starts with BEAUTY-01, whose criterion joins exactly those foundations:

> BEAUTY-01: a multi-stage service, add-ons, resources, payment, commission and material consumption
> form a reconcilable cycle.

The master plan §5 lists the full beauty scope; §14.1 adds the beauty checks "service stages,
compatibility of add-ons, packages and consumables". The same building blocks serve other
directions later (stages and multi-resource visits for spas, clinics, workshops and rentals;
visit billing and commissions for any service business), so they are built as platform parts, not
salon code.

## What exists (inspected 2026-10-22)

- Catalog (0002): services, variants with price, currency and one `booking_duration_minutes`,
  components that a variant provides, add-ons with PROVIDES / REQUIRES / CONFLICTS_WITH rules, and the
  pure quote engine (`catalog/quote.py`): one variant plus add-ons, no duplicate component, total at
  most 720 minutes, snapshot stored with the booking.
- Booking (0003, ADR-0003): one variant on **one resource** (`artist`, `chair` or `room`, capacity
  one), HOLD / CONFIRMED / CANCELLED / EXPIRED, quote snapshot, idempotency; occupancy through the
  shared `resource_allocations` (ADR-0022, 0018) with an exclusion constraint and advisory locks; staff
  reservations of several resources already take all or none.
- Finance: invoices, obligations, settlements and external payments (FIN-03), provider payments
  (FIN-02), ledger (FIN-01). Workforce: staff profiles, skills, shifts, timesheets (WORK-01). Materials:
  material list, places, receipts and write-offs at moving-average cost (STOCK-01).

## Decisions (agent, under the owner's delegation)

1. **Stages belong to the variant.** A variant gets an ordered list of stages, each `active`
   (the specialist works), `processing` (the client waits, e.g. colour developing; the specialist is
   free) or `finish`, with minutes and the **resource kinds it occupies** (specialist, chair, room,
   equipment). A variant without stages keeps today's meaning: one active stage of
   `booking_duration_minutes` on its one resource. Old bookings and their snapshots never change.
2. **A visit is one booking with several service lines.** One booking may hold several variants
   (with their add-ons) in order; each stage of each line reserves its resources through the one shared
   occupancy mechanism, all or nothing (ADR-0022). During `processing` the specialist is released, so
   another client can be served in that gap; the chair or room stays occupied. Equipment becomes a
   resource kind. Add-ons extend the stage they belong to (default: the last active stage).
3. **Compatibility rules stay.** The quote engine's rules (no paid duplicate of an included
   component, requires, conflicts) apply across all lines of a visit; the 720-minute bound applies to
   the visit.
4. **Completion consumes materials.** A variant or add-on may have a recipe (material and quantity per
   stage). Completing a visit writes off the recipe quantities through STOCK-01 at moving-average cost,
   once (idempotent), from the branch's place; the staff member may record the actual quantity, which
   replaces the planned one and keeps both.
5. **Payment through the finance documents.** A completed visit produces one internal invoice in the
   visit's currency (FIN-03) with a line per service and add-on; a published prepayment policy may ask
   for a deposit at booking, which becomes a settlement of the same invoice. Payments are manual or
   observed provider payments (FIN-02); nothing is paid automatically; cancellation and no-show fees
   follow the published policy and are separate invoice lines.
6. **Commission when the money is in.** Commission rules per staff member and service (a percentage
   of the line's net price or a fixed amount) produce a commission obligation to the staff member when
   the visit's invoice is fully paid; it posts expense and a payable to staff in the ledger with
   lineage to the visit, once. Tips are recorded as a separate payable, never revenue. No payroll.
7. **Packages after the cycle.** Prepaid packages, gift certificates and loyalty come in a later slice
   of this package (prepaid units are a liability until used), after the paid cycle works.
8. **Module gates.** The cycle extends `booking_resources`; billing needs `finance_documents`,
   consumption needs `inventory`, commissions need `workforce` and `finance`. A company enables each as
   today; a missing module means that step is simply not offered, never a silent partial cycle.

## Slices (each: failing tests first, gates, record, code and docs commits)

| Slice | Deliverable |
|---|---|
| L1 | Stages and equipment: variant stages (kind, minutes, resource kinds), `equipment` resource kind, stage-aware quote; old variants unchanged |
| L2 | Multi-stage, multi-line visit booking through the shared occupancy (specialist free during processing), management API and the customer site; old single-variant API keeps working |
| L3 | Visit completion and material consumption (recipes, planned and actual quantities, STOCK-01 write-off, idempotent) |
| L4 | Visit billing: invoice from the visit, deposit by published policy, cancellation and no-show lines, payments manual or provider |
| L5 | Commissions and tips: rules, accrual when paid, ledger lineage, payables to staff |
| L6 | Packages and certificates: prepaid units as a liability, use against visit lines |
| L7 | Screens: catalog stages, visit booking, completion, billing, commissions; real browser desktop and mobile with axe |
| L8 | BEAUTY-01 acceptance: the full reconcilable cycle, gates, CI, one independent review, readiness record |

## Acceptance (all NOT TESTED)

| id | Requirement |
|---|---|
| L-01 | A variant with stages quotes its stages; one without stages behaves exactly as before; every old booking and snapshot is unchanged |
| L-02 | A visit with several services and add-ons rejects a paid duplicate of an included component, a missing requirement and a conflict across all lines |
| L-03 | Each stage reserves its resources all or none; two racing visits leave one; the specialist is free during processing while the chair stays held (observed pg_locks waits for races) |
| L-04 | Equipment and rooms are exclusive resources in the same occupancy as bookings and staff reservations |
| L-05 | Completion writes off each recipe material once at moving-average cost; a repeat writes nothing; the actual quantity replaces the planned and both stay |
| L-06 | The visit's invoice equals its quote lines; a deposit is a settlement of that invoice; cancellation and no-show lines follow the published policy |
| L-07 | Commission is owed only when the invoice is fully paid, posts once with lineage; a refund reverses it; tips are a payable, never revenue |
| L-08 | Packages: a prepaid unit is a liability until used; using it settles the visit line; it cannot be used twice |
| L-09 | Branch scope, company isolation and finance rights hold for every new table and route (direct SQL refusals) |
| L-10 | Disabled modules: each missing module removes its step, never leaves a half-done cycle |
| L-11 | Screens: real browser, desktop and mobile, keyboard and axe; complete pagination |
| L-12 | Full suite, CI, one independent review, regression of BOOKING, FIN-01–03, WORK-01, STOCK-01 |

## Out of scope

Waitlists, recurring visits, client photos and consents, cosmetics retail beyond the existing
materials, workstation rent and medical cosmetology (the clinical module) — later beauty slices or
stage 8. Payroll, tax filing, live payments, deployment and production migrations. Merging into `main`
follows the owner's earlier choice (fast-forward after green CI).
