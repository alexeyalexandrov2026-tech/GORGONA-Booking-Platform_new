# ADR-0016 — Limited delegation between independent businesses

Status: accepted for the stage-1 implementation increment; technical acceptance is recorded separately in the implementation registry.

## Context

The master plan requires independent companies — a carrier and its dispatch service, a franchise and a call centre, members of a holding — to work for each other without merging into one tenant (§7.4, §12.2, CORE-03). The owner keeps its data, its tenant and its audit trail. A shared account or a role that bypasses row-level security is not delegation.

The existing model admits only a membership of the business itself (ADR-0009) or audited read-only platform support. Branch work (ADR-0014) already shows the pattern for narrower access: handlers opt in, the transaction carries a verified scope and restrictive RLS limits what the database returns.

This increment provides the delegation foundation for current operational booking work. It does not implement transport, dispatch, financial or document workflows, company groups, departments or offline synchronization.

## Decision

### Ownership and records

- `business_id == tenant_id == legacy salon_id` stays the company boundary. A grant belongs to the **owner** business (`tenant_id`) and names exactly one other **serving** business. A business cannot delegate to itself. Delegated work runs in the owner's tenant and writes owner-owned rows; nothing is copied into the serving business.
- The owner controls the terms in append-only, numbered revisions (`delegation_grant_versions`): state `active` or `revoked`, sorted delegable permissions, an optional single owner location as the data area, and a validity window `[valid_from, valid_until)`. Every revision must end within 366 days of its start; renewing access is a new, explicitly confirmed revision. This is a platform safety limit, not a business fact, and can be changed by an owner decision with a new migration.
- Revisions are sequential, rows cannot be updated or deleted, and a revoked grant is terminal. The serving business of a grant never changes. Database triggers enforce these rules for every role, including the owner role.
- The serving business controls its people. Its owner designates specific active memberships of its **own** business for a grant (`delegation_designations`, owned by the serving tenant). Composite foreign keys guarantee that the grant is addressed to that business and that the stored user belongs to the membership. Removal is terminal; designating the person again creates a new row. A database trigger audits every designation change.

### Permissions

- New `delegation.manage` permission, granted to the `owner` role only (permission map version 3). It is required to create, change, revoke and read outgoing grants and to read incoming grants and designate or remove people. Managers keep their existing rights; platform support stays read-only and has no delegation access.
- Delegable permissions are exactly `booking.read`, `booking.write`, `catalog.read` and `staff.read`. `booking.write` requires the three read permissions, because creating or moving a booking needs services and staff. Business, catalog, staff and settings management, members, invitations, legal entities, profiles, readiness, delegation management, audit history and platform actions are never delegable.

### Authorization of a delegated request

`authorized_tenant(..., allow_delegation=True)` is accepted only by reviewed operational handlers: workspace, overview, availability, bookings (list, detail, create, reschedule, cancel), clients, services list, staff list and staff schedule. Every other handler keeps denying delegated callers. When the caller has no active membership in the owner business, the same transaction:

1. In owner context, finds the caller's active designations for that owner's grants whose current revision is active and in term. A suspended membership in the owner business blocks delegated access. Candidates are ordered business-wide first, then by grant ID. A grant must include the requested permission, and a location-limited grant is usable only by handlers that support location scope.
2. In serving context, locks the caller's active membership and the active designation `FOR SHARE`, and requires the serving business to be active. Concurrent suspension, revocation or removal waits for this request and applies to the next one.
3. Back in owner context, takes a shared transaction advisory lock for the grant, re-reads the current revision and checks state, term, permission and location again; the owner business must be active. Grant writers take the exclusive form of this lock, so a revocation waits for in-flight delegated work and the next request sees it.

If any check fails, the request is denied before business data is read, using the existing uniform errors. The transaction then carries tenant = owner, `gba.location_id` = the grant location (reusing the restrictive branch policies of migration 0009), `gba.delegation_grant_id` and `gba.actor = delegate:{user}@{serving business}/grant:{grant}`. Each delegated request records a `delegation.access` audit event in the owner tenant with the grant, revision, serving business, permission and location. Booking `created_by` and booking events use the delegated actor. Idempotency keys stay keyed to the user, so a retry after a grant is replaced cannot execute twice; every replay is authorized again and checked against the current location scope.

### Database boundaries

- Restrictive runtime policies deny a delegated transaction access to memberships, other users, invitations, legal entities and their versions, business profile versions/industries/formats, fact confirmations, embed origins, audit history and every delegation record. Operational tables, booking rules and the caller's own receipts remain available, subject to tenant and branch policies.
- Cross-tenant visibility is limited to: the serving business reads grants and revisions addressed to it and the owner's tenant row; the owner reads designations for its own grants (membership IDs, user IDs and dates, not names); a designated user reads its own designations, the related grants and revisions and the owner's tenant row. Branch-scoped transactions cannot read delegation records.
- Startup, readiness and every branch-scoped or delegated request verify both scope functions, every restrictive scope policy, the exact definitions of the cross-tenant delegation policies and the absence of any other policy on the delegation tables. A missing or altered definition returns unavailable before business data is queried. Definitions are compared with PostgreSQL 18's canonical rendering.

### API

- Owner: `GET/PUT /v1/businesses/{id}/delegations[/{grant_id}]` with revision history, and `POST …/{grant_id}/revoke`. Saves and revocations require `Idempotency-Key` and the expected revision; conflicts return 409. Unknown or unusable serving businesses and foreign locations return a uniform 422 `INVALID_REFERENCE`.
- Serving business: `GET /v1/businesses/{id}/incoming-delegations`, and `PUT`/`DELETE …/{grant_id}/delegates/{membership_id}` with `Idempotency-Key`.
- `GET /v1/me` adds the caller's currently effective delegated businesses. The management interface uses it to offer operational pages permitted by the grant.
- Contracts are typed, versioned and reject unknown fields. Responses distinguish stored state from the effective state (`scheduled`, `active`, `expired`, `revoked`).

## Acceptance

Contract, PostgreSQL/API and browser evidence must show:

1. Grant create/update/history/revoke with idempotent replay, key reuse rejection, stale revision conflict, immutable serving business, self-delegation and foreign-reference rejection; owner-only management.
2. Designation of own active members only; incoming visibility only for the addressed business; designation and removal audited.
3. A designated employee reads and writes owner bookings only within the granted permissions and location; created rows stay in the owner tenant with the delegated actor; every delegated request is audited; company records stay invisible even through direct SQL in a delegated transaction.
4. Revocation, expiry, a scheduled start, designation removal, suspension or revocation of the employee's membership, a suspended membership in the owner business and suspension of either company block the next request, including replays and commands prepared earlier. A revocation waits for an in-flight delegated transaction.
5. Database immutability, sequential revisions, terminal revocation and cross-tenant foreign keys hold under direct owner connections. Damaged or widened definitions fail readiness and delegated requests.
6. The existing membership, branch, platform-support, booking and legal-entity behaviour is unchanged.

## Consequences

The runtime now requires migration 0011 before serving a database as ready. It is additive; the established migrations are unchanged. Apply it to a disposable database and run the checks before any separately authorized environment migration.

This increment advances CORE-03 and prepares TMS-02 but closes neither. Company groups and consolidated reports, departments, multiple data areas per grant, owner-visible delegate names, document and financial permissions, offline draft synchronization (which must use this same authorization), transport workflows and per-action approval remain separate work. Registration facts, contracts between the companies and regulatory roles such as freight brokerage are not inferred from a grant.
