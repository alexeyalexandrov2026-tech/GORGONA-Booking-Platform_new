# ADR-0018 — Company groups without shared access

Status: accepted for the stage-1 implementation increment (CORE-03 step C). Technical acceptance is recorded separately after full CI on the exact commit.

## Context

The master plan places the group model in stage 1 and group features in stage 7: "a group of companies links businesses through explicit permissions; belonging to a group gives no access to other companies' rows; a consolidated report reads only permitted sets" (§12.2, §13, CORE-03, ENTERPRISE-01). Holding companies, networks and franchises must keep each member's ownership. Access between companies already has its own mechanism, the consent-based grants of [ADR-0017](0017-cross-company-delegation.md).

## Decision

- `business_groups` belongs to an organizer business: an immutable identity, an internal reference unique per organizer, a name and an organizer-name snapshot. Renaming is not part of this increment.
- `business_group_members` records each invitation as its own row: invited → active | declined by the member; active → left by the member; invited | active → removed by the organizer. Each change increments `revision`; the decision and end details are written once. After a membership ends, a new invitation creates a new row, so history is never overwritten. A database trigger enforces immutable identity, the allowed transitions for the acting side (from the tenant context) and one-time decision details. There are no update or delete policies for group identities and no delete policy for memberships.
- RLS: the organizer sees its groups and all memberships. An invited or member business sees the group and only its own membership row; it never learns who else is invited. Only the organizer inserts groups and invitations. Restrictive company-only scope policies keep branch-limited sessions out. The schema guard requires 25 definitions.
- Membership is referenced by no authorization path. A group grants no access to bookings, settings, organization records or any other rows of any party. Stage-7 consolidated reports must read only sets each owner explicitly grants, through a mechanism like ADR-0017, never through group membership.
- API under `/v1/businesses/{id}/groups`: list and detail (`business.read`); create, invite, remove, accept, decline and leave (`business.manage`, company-wide). Every command needs an expected revision where applicable and an `Idempotency-Key`, and is audited in the acting company.
- The Business profile page hosts a "Company groups" panel with the same uncertain-result retry used elsewhere.

## Acceptance

1. Create, invite, accept, leave, remove and re-invite keep history; replays return the stored result and reused keys are rejected.
2. Membership exposes no bookings, workspace, profile, legal entities or departments of the other party; `/v1/me` gains no membership or delegation.
3. Members see only their own membership; a third company sees nothing.
4. Wrong parties, roles, states and stale revisions are refused; a concurrent accept/remove has one winner.
5. Direct SQL cannot change identities or forge transitions, insert in the organizer's name, or delete history; damaged scope policies fail readiness.
6. Real browsers: a member joins after a lost response with the same key, cannot read the partner's bookings, creates its own group, invites and removes the partner, and leaves; SQL confirms the memberships and audit.

Tests: [contracts](../../api/tests/unit/test_group_contracts.py), [database/API](../../api/tests/integration/test_groups.py), [web response boundaries](../../web/tests/management-contracts.spec.ts), [browser](../../web/tests/groups.spec.ts) and its [database assertions](../../api/tests/integration/test_management_browser.py).

## Consequences

The runtime requires migration 0013 before readiness. Known limits, recorded by review: group responses include all memberships without pagination (large networks need paging later); any business that knows another's ID can invite it (no block list yet); idempotent command helpers are duplicated across the stage-1 modules and should move to a shared module.

With steps A–C, CORE-03 has its organization foundation: departments, delegation and groups. TMS dispatcher operations, offline draft synchronization and consolidated group reports arrive with their modules and must reuse these mechanisms.
