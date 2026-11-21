# PROPERTY-01 — Maintenance, Contractor Work Order & Move-Out UI Design (2026-11-20)

## Scope
This slice adds the internal web UI and single-assignment contractor portal for the verified
PROPERTY-01 backend slices (`5a` maintenance lifecycle & FIN-03 obligations, `5b` single-assignment
contractor delegation access, `6a` move-out condition report & photos), with zero new database
migrations:

1. **Strict response contracts & retry-safe API client** (`web/lib/property-contracts.ts`,
   `web/lib/property-api.ts`):
   - Strict Zod schemas and route regexes for `/property/leases/{lease_id}/move-out` and all
     10 `/property/maintenance/*` routes.
   - `contractorWorkOrderSchema` strictly forbids private fields (`approved_limit_minor`,
     `currency`, `lease_id`, `contractor_id`, `obligations`, `owner_id`, `manager_id`).
   - Exact integer minor-unit amount parsing/formatting (`parseMinorUnits`, `formatMinorUnits`).
   - All writes retain their `Idempotency-Key` until success (ADR-0030).
2. **Unit lease move-out UI** (`web/components/property-lease.tsx`):
   - Loads `GET /property/leases/{lease_id}/move-out` once move-in exists (404 maps to `null`).
   - Renders `MoveOutRecord` (date, condition summary, optional note, term revision, report/photo
     downloads) or `MoveOutForm` (move-out date, `normal_wear` / `damage_noted`, optional note,
     distinct condition report version, 1..50 PNG/JPEG photos, stale term conflict recovery).
   - All labels and buttons are distinct from move-in controls to prevent ambiguity.
3. **Internal maintenance UI** (`web/components/property-maintenance.tsx`, mounted in
   `web/components/property.tsx`):
   - Branch-scoped managers (`canManage === false`) read only
     `GET /property/maintenance?object_id=...` with zero write forms and zero `property.manage`
     requests.
   - Company-wide owners and managers (`canManage === true`) create requests, approve (amount +
     currency), assign a contractor counterparty, bind/unbind a contractor company with a live
     `property.contractor_work` delegation grant, copy/open the single-request contractor link,
     inspect contractor updates, inspect linked FIN-03 obligations and event history, and
     complete or cancel requests.
4. **Standalone contractor work-order portal** (`web/app/property/contractor/page.tsx`,
   `web/app/property/contractor/contractor-work.tsx`):
   - Static-exported route `/property/contractor/?business=<uuid>&request=<uuid>&grant=<uuid>`.
   - Reuses `CustomerAccessFeedback` for 401 sign-in, 403/404 unavailable, and network reload.
   - Displays only the bound work order and its updates; never displays budget, lease, parties,
     or FIN-03 obligations.
   - Supports keyboard-accessible progress updates with retry-safe idempotency key retention.

## Accessibility & Focus Preservation
- Semantic landmarks, headings, regions, tables, `role="status"` announcements, and `role="alert"`
  errors.
- Submit buttons use `aria-disabled` plus in-flight guards so keyboard focus never drops during
  async submission.
- Zero axe violations and zero horizontal overflow on desktop and mobile (390px).

## Non-Goals
- No new database migration, no change to `readiness_registry.py`, and `property` stays
  `enableable=False`.
- No security deposit withholding, settlement, or automated billing.
