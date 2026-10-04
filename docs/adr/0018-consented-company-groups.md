# ADR-0018 — Consented company groups and limited operational reports

Status: implementation increment; technical evidence is recorded separately.

## Context

Independent businesses must retain their data ownership within a group (master plan §12.2, CORE-03 and ENTERPRISE-01). Existing booking rows have no legal-entity assignment or payment ledger. Group membership cannot imply financial consolidation, access to another tenant, or readiness of an industry workflow.

## Decision

- A group belongs to its operator business. Its stable internal reference and immutable numbered name versions reuse the existing company record, idempotency and audit patterns. `group.manage` is owner-only, business-wide, never delegated or granted to platform support (permissions map version 4).
- An operator invites one independent participant per active group relationship. Invitation identity is immutable; the operator may withdraw it once, preserving history. The participant owns append-only consent: acceptance revision 1, final withdrawal revision 2. Its owner explicitly accepts, independently of the operator. Re-entry requires the operator to withdraw the old invitation and issue a new one. A partial unique index prevents duplicate active invitations and double counting.
- Four new tables in additive migration 0013 use FORCE RLS and restrictive branch/delegation policies. Only invitation recipients can read the addressed group metadata; only operators can read consents addressed to them. These policies are included in the exact-definition access guard, including rejection of extra policies. No policy broadens `gba.tenants` or operational tables. An invitation, consent or group never changes memberships, grants or data ownership.
- API saves use strict version-1 contracts, expected revisions where applicable, user-scoped idempotency receipts and transactional audit. A replay returns the original receipt; the interface refreshes current relationship state so an old accepted receipt cannot restore consent.

### First report

The first report counts bookings by owning business, location and status over an explicitly supplied `[from_at, until_at)` period of at most 366 days. It reads existing booking rows; it stores no copy. It contains no client identities, prices, payments or revenue. Legal-entity ID is explicitly null/unassigned because existing bookings have no verified assignment.

Permission `report.booking.read` is separately delegable, extending the existing grant allowlist to five permissions. It does not include `booking.read`. The **participant/data owner grants to the operator/serving business**. The operator owner must also designate the individual employee through ADR-0016. Neither owning both companies nor platform support substitutes for this grant. The management selector does not offer an operational workspace through a report-only grant.

One operator-authorized transaction processes at most 25 invitation identities per report page. Each participant is read sequentially on that same connection. After a shared invitation advisory lock, the latest invitation and consent must still be active/accepted. A narrow authorization helper forces delegation from exactly this operator, with all existing membership, designation, grant, status, time and branch checks. It records the participant-owned delegation access audit. Report sources name the grant revision and its branch coverage; accepted participants without current permission are explicitly excluded. No data from them is included in counts.

The connection temporarily carries the verified participant tenant, branch and delegation context for its query, then restores the operator context. Group records remain inaccessible in delegated context. Missing or weakened access boundaries fail the request and readiness; they do not become an empty successful report.

### Concurrency

Report and structural/consent writes require READ COMMITTED. PostgreSQL gives successive statements current committed snapshots at this level; REPEATABLE READ retains the older snapshot. See the official [transaction isolation documentation](https://www.postgresql.org/docs/18/transaction-iso.html). Rejecting unsupported isolation prevents a lock wait from admitting previously revoked consent through an old snapshot.

The operator's company-groups lock precedes its membership lock. Invitation locks are acquired in ascending UUID order by reports, in shared mode; operator withdrawal and participant consent writes acquire the same key exclusively. Latest state is read after waiting. Append-only consent requires this common lock rather than a lock on an older revision row. Delegation then retains its existing serving membership/designation → grant order. Transaction locks remain until commit/rollback; withdrawal waits for in-flight reporting and the next request sees it. See PostgreSQL's [transaction advisory locks](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS).

## Acceptance and boundaries

Verify version history, replay, stale conflict, duplicate invitations, explicit two-party authority, terminal withdrawals, same-tenant ownership, typed strict contracts, RLS and guard damage, branch limits, report-only authority, wrong serving company, direct owner without designation, expiry/suspension, concurrent withdrawal, rejected old snapshots and rollback. Desktop/mobile browser flows must confirm real persistence, lost-response replay, owner consent, report access and withdrawal with test-only FAKE OIDC/PKCE.

This increment does not implement financial/group ledger consolidation, intercompany documents, employee-wide group access, multiple locations per grant, corporate SSO/SCIM, industry workflows or production acceptance. No production migration or deployment is authorized by implementation of this ADR.
