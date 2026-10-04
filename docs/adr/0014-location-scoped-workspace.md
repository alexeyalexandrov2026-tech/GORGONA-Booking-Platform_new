# ADR-0014: Location-scoped operational workspace

- Status: Technically verified (2026-10-04).
- Scope: existing booking, customer history, resources and schedules. No new tenancy model.

## Decision

`business_id == tenant_id == legacy salon_id` remains the company boundary. An active membership may grant access to one `location_id` inside that company. Authorization still locks the membership in the operation's transaction and checks the role. Revocation applies to subsequent requests.

`authorized_tenant` denies location grants by default. Only explicitly reviewed operational handlers opt into `allow_location_scope=True`. They receive a typed `TenantAccess.location_id`. The server sets the transaction-local branch context from that verified membership, never from a body, URL, token claim or browser selection.

Migration 0009 adds restrictive runtime RLS policies alongside the existing tenant policies. Locations, resources, business hours and bookings use their own location. Resource hours/services/blocks and booking customers/events/allocations use protected parent relationships. Allocation checks include both the booking and resource. The database therefore limits queries and writes even if a handler omits a location filter. This follows PostgreSQL's [restrictive-policy semantics](https://www.postgresql.org/docs/18/sql-createpolicy.html).

Before allowing a scoped operation, the same transaction verifies the approved scope function and all 17 policy definitions, including FORCE/ENABLE RLS, role, command, `USING` and `WITH CHECK`. Startup and database readiness use the same guard. A missing or altered boundary returns unavailable before business data is queried; it never silently broadens the grant. Definitions are compared with PostgreSQL 18's canonical expression rendering. Changing the definitions or major database version requires corresponding reviewed migration, guard and regression evidence.

`GET /v1/salons/{id}/workspace` returns only authorized locations, their timezones and business hours. Calendar, Bookings, staff and quick appointment creation use this operational response. The shared service catalog remains readable for service selection. Company profile, catalog changes, full settings, membership administration, policies and go-live remain business-wide operations. Historical company audit events lack a trusted location, so branch users receive no such events; audit writes continue.

An owner can issue an invitation with a validated company-owned location. The invitation's location is immutable, and acceptance copies it exactly into the membership. Scoped members cannot administer invitations or memberships. Owner invitations are business-wide. Existing invitations default to business-wide access. The last-owner check counts active business-wide owners.

Management idempotency receipts are checked against the current grant before returning data. Legacy receipts lacking `location_timezone` are enriched from the authorized real location without reexecuting the operation or changing captured prices, durations, client data or status. Malformed receipts are unavailable. A changed or revoked grant cannot retrieve a formerly authorized receipt outside its new scope.

## Compatibility and limits

- Public host/capability booking, tenant-wide roles and audited platform support keep their existing transaction flows. Empty branch context preserves those flows; context ends with the transaction.
- Migration 0009 is additive. It is applied only by the owner/migration role; the API never migrates at startup. Production/staging migration remains a separately authorized operation.
- This is one assigned branch per membership. Multiple branch grants, internal legal entities, corporate groups and independent dispatcher delegation are separate work.
- Branch-specific audit feeds, branch price overrides and configuration publication are not implemented by this decision.
- Technical tests do not establish industry pilot, external provider approval, load goals or production readiness.
