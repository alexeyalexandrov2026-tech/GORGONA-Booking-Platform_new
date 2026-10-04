# ADR-0017 — Cross-company delegation grants

Status: accepted for the stage-1 implementation increment (CORE-03 step B). [Technical acceptance](../plan/evidence/2026-10-04-delegation/ACCEPTANCE.md): full CI passed on `ed370c6`.

## Context

The master plan (§7.4, §12.2, §12.5, CORE-03, TMS-02) requires that an independent business, such as a dispatcher, can work for another business without either company losing ownership of its data. The delegation must name the owner business, the servicing business, the specific employees, the allowed actions, the data scope, the term, a version and revocation. Every operation must check both accounts and the active grant, run in one target `tenant_id` transaction, and audit the real executor, their company, the owner company and the grant used. Revocation must block the next operation and the application of deferred drafts. A shared account or an RLS bypass is not delegation.

Owner decisions (2026-10-04): grants require two-sided consent (the owner offers, the servicer accepts; either side ends an active grant); a delegate may read and change bookings only; settings, members, organization records and structure are never delegated.

## Decision

- `delegation_grants` belongs to the owner business and names the servicer. Terms — permissions, optional owner location, expiry, owner name snapshot — are immutable after issue. Changing terms means revoking and issuing a new grant; one open (pending or active) grant per pair is allowed.
- Delegable permissions are exactly `booking.read`, `booking.write`, `catalog.read` and `staff.read`. Expiry is required, in the future and at most 366 days ahead.
- States are pending → active | declined (servicer), pending → revoked (owner), active → revoked (either side, recorded as `revoked_by_side`). Expiry is computed, not stored. Every change increments `revision`; commands require the expected revision and an `Idempotency-Key`, and write an audit event in the acting company.
- On acceptance, the servicer names delegates from its own active company-wide members (`delegation_grant_members`, with removal history). It can later replace the delegate set. Branch-limited servicer members cannot be delegates.
- A database trigger enforces immutable terms, allowed transitions per side (from the tenant context), one-step revision increments, one-time decision and revocation details, and delegate eligibility. Deletes are impossible: there is no delete policy and the trigger is a backstop. RLS lets either party read the relationship and lets a named delegate read the grants it works under. Only the owner inserts grants; only the servicer adds or removes delegates. Restrictive company-only scope policies keep branch-limited sessions out. The schema guard now requires 23 definitions.
- Authorization: handlers opt in with `allow_delegation`, which requires `allow_location_scope`. Exactly eleven booking workspace handlers opt in: workspace, overview, availability, bookings list/create/detail/reschedule/cancel, services read, staff read and staff schedule read. Clients, activity, settings and all catalog/staff changes are excluded.
- If the caller has no active membership in the owner business, the delegated path locks the active, unexpired grant and the delegate row (`FOR SHARE`). It refuses a person whom the owner has suspended. It then switches the transaction-local tenant context to the servicer, locks the caller's active company-wide servicer membership and checks that the servicer company is active, and restores the owner context. Effective permission is grant ∩ servicer role. Grant location becomes the existing location RLS scope. No SECURITY DEFINER function and no RLS bypass are used.
- Each delegated request writes `delegation.access` in the owner company's audit: executor, servicer company, grant, revision and permission. Booking row audit records the executor as the actor.
- Authorization runs before idempotency, so after revocation, expiry or removal, a replayed command is refused without revealing its stored receipt. This is the server-side guarantee for deferred drafts; client offline drafts (§12.8) will be checked the same way when they exist.
- `/v1/me` lists usable delegated businesses separately from memberships. The web workspace switcher shows them with a delegation notice and booking-only navigation. Business profile has a "Delegated access" panel: owners offer and revoke; servicer owners/managers accept or decline, choose delegates and end access.
- The owner learns the servicer's name only after acceptance, from a snapshot. A business ID that does not exist returns 422 through the foreign key; IDs are unguessable UUIDs.

## Acceptance

1. Offer → acceptance → delegated booking cycle in the owner company; the servicer's own owner gets no access; non-delegated owner areas are refused; audit rows name both companies and the grant.
2. Delegate removal, owner revocation, servicer revocation and expiry block the next command; an old receipt replay is refused.
3. Servicer membership suspension, branch limitation, role limits, non-named members and suspension of either company deny access; an owner-side suspension is not bypassed.
4. Read-only and location-limited terms are enforced.
5. Parties, terms, states, stale revisions and races behave as specified; a third company sees nothing.
6. Direct SQL cannot change terms, forge transitions or decision details, insert in the other party's name, or delete history; damaged scope policies fail readiness.
7. Real browsers: the servicer accepts after a lost response, offers and revokes its own access, books for the owner as a delegate within the granted location, and ends access; SQL confirms both grants and the booking.

Tests: [contracts](../../api/tests/unit/test_delegation_contracts.py), [database/API](../../api/tests/integration/test_delegations.py), [web response boundaries](../../web/tests/management-contracts.spec.ts), [browser](../../web/tests/delegation.spec.ts) and its [database assertions](../../api/tests/integration/test_management_browser.py).

## Consequences

The runtime requires migration 0012 before readiness. The same work fixed `list_members`, which returned the caller's memberships in other companies because of the self-read policy (regression test included). Other unfiltered membership queries are tracked separately.

This does not finish CORE-03: the group model (step C) follows. Document and financial data scopes, multi-carrier dispatcher workflows (TMS-02) and offline drafts arrive with their modules and must reuse this authorization path. Per-request access audit is deliberately complete; volume controls can be revisited with evidence.
