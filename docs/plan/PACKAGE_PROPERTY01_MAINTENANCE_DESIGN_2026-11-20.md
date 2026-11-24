# PROPERTY-01 5a · Maintenance requests, approvals and separate FIN-03 obligations

Design for step 5 of [the PROPERTY-01 plan](PACKAGE_PROPERTY01_PLAN_2026-11-14.md) and §9.2 / §14.1.1
of [the master plan](GORGONA_MASTER_PLAN.md) ("Аренда, депозит, ремонт и расчет собственника имеют
раздельные обязательства и права"). Next migration: **0127**.

## Scope

- Internal maintenance requests for any catalog object (`parcel`, `building`, or `unit`), optionally
  referencing a recorded lease of that exact object.
- Append-only lifecycle events (`approve`, `assign`, `complete`, `cancel`) advancing the request's
  materialized state (`open` → `approved` → `assigned` → `completed`, or `cancelled` before any
  obligation is linked).
- Explicit human approval with a currency and maximum approved amount (`approved_limit_minor`)
  before assignment and before any work obligation can be linked.
- Separate FIN-03 payable work obligations (`gba.property_maintenance_obligations`): each link
  references a unique **issued** FIN-03 `invoice` (`direction = 'payable'`, matching assigned
  `contractor_id` and approved `currency`). PostgreSQL derives `obligation_id`, `amount_minor`,
  and `currency` directly from the issued `financial_document_versions` row and enforces that the
  cumulative linked obligations never exceed `approved_limit_minor`.
- Owner or manager changes in `property_parties` leave all previously recorded maintenance
  requests, events, and FIN-03 payable obligations unchanged with their original contractor payee.

## Out of scope (subsequent slices)

- **Step 5b (migration 0128):** Cross-company single-assignment contractor access through an
  explicit delegation grant (revocation, expiry, single-order isolation).
- **Step 5c:** Property maintenance UI screen and browser verification (desktop, mobile, keyboard, axe).
- **Steps 2d & 4:** Public storefront/screening and statutory deposit custody rules (pending owner
  jurisdiction and provider decisions).
- Module enablement (`property.enableable`) and `readiness_registry.py` (`PROPERTY-01 = planned`)
  remain unchanged.

## Security, isolation and concurrency

- **No `SECURITY DEFINER`** anywhere in migration `0127`.
- **Serialization:** All writes on a property object acquire `gba.lock_property_object(tenant_id, object_id)`
  and require `READ COMMITTED` isolation so concurrent approvals, assignments, and FIN-03 obligation
  links serialize cleanly and never exceed `approved_limit_minor`.
- **RLS & permissions:**
  - `GET /property/maintenance` and `GET /property/maintenance/{request_id}` require `property.read`
    and are branch-scoped (`location_id = gba.current_location_id()`).
  - Writes (`PUT /maintenance/{id}`, `POST /maintenance/{id}/events`, `POST /maintenance/{id}/obligations`)
    and private history/financial reads (`GET .../events`, `GET .../obligations`) require
    `property.manage` and company-wide scope (`gba.current_location_id() is null`).
  - Optional module gate (`gba.require_enabled_module('property')`) applies to new requests,
    approvals, assignments, and obligation links; completing or cancelling already-assigned work
    remains allowed after disablement (matching ADR-0035 and `0116_property_lease_terms.sql`).
- **Immutability:** Direct `UPDATE`/`DELETE` on events and obligations, or mutation of request
  identity fields, is rejected by PostgreSQL triggers. All policies and triggers are enforced by
  `schema_guard.py`.
