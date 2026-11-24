# PROPERTY-01 5b · Single-assignment contractor access through delegation grants

Design for step 5 ("Доступ подрядчика ограничен конкретным поручением") of
[the PROPERTY-01 plan](PACKAGE_PROPERTY01_PLAN_2026-11-14.md), stacked on
[step 5a](PACKAGE_PROPERTY01_MAINTENANCE_DESIGN_2026-11-20.md). Next migration: **0128**.

## Scope

- New delegable permission `property.contractor_work` (`PERMISSIONS_VERSION = 16`), added to
  `DELEGABLE_PERMISSIONS`, `DelegablePermission`, `web/lib/delegation-contracts.ts`, and
  `delegation_grants_permissions_check` (keeping the existing `max_length = 9` bound).
- Explicit per-request contractor company binding (`gba.property_maintenance_contractor_links`):
  append-only revisions recording which external company (`company_id <> tenant_id`, or `null` to
  unbind) is authorized for a single assigned maintenance request.
- Contractor progress updates (`gba.property_maintenance_contractor_updates`): append-only updates
  (`acknowledged`, `in_progress`, `parts_needed`, `work_done`) numbered `1, 2, 3` per request,
  storing `company_id`, `grant_id`, `binding_revision`, and `recorded_by`.
- Five routes under `/v1/businesses/{business_id}/property/maintenance/{request_id}`:
  - `GET /contractor-company`, `PUT /contractor-company`, `GET /contractor-updates` (`property.manage`,
    company-wide).
  - `GET /contractor-work/{grant_id}`, `POST /contractor-work/{grant_id}/updates` (delegated
    `property.contractor_work` only; even the owner company's own manager is refused).
- Contractor view exposes only the single bound work order (`object_name`, `object_kind`,
  `location_id`, `category`, `priority`, `title`, `description`, `state`, `revision`,
  `binding_revision`, `updates`) and excludes `lease_id`, `approved_limit_minor`, `currency`,
  FIN-03 obligations, `owner_id`/`manager_id`, internal events, and all other requests.

## Security and database guards (invoker rights only)

- No privileged functions; every trigger executes with caller row security.
- Adopting the 0126 hardening pattern, `guard_property_maintenance_contractor_update()` rechecks the
  active, unexpired grant, `property.contractor_work` permission, live delegate row, branch match,
  and latest binding revision on this exact `request_id` in **both** company-wide and branch-scoped
  sessions.
- Revocation, expiry, delegate removal, unbinding (`company_id = null`), or rebinding to another
  company immediately blocks reads, writes, and idempotency-key replays (`403`).
- Contractors cannot approve, reassign, link FIN-03 obligations, or mark the request `completed`.
