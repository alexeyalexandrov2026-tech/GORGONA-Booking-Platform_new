# ADR-0015 — Tenant-owned legal-entity drafts

Status: accepted for the stage-1 implementation increment; technical acceptance is recorded separately.

## Context

The universal platform needs several legal entities within a business before it can introduce financial responsibility, company groups or independent dispatch delegation. The existing tenant is the data owner and authorization boundary. Copying it for each industry or legal-entity record would duplicate clients and resources and confuse ownership.

The current increment records owner-provided names and internal references only. It does not claim to verify registration, activate payments, publish a configuration, assign financial accounts or establish a group/delegation grant. Unknown country, tax identifiers, currency and branch assignments are not invented or defaulted.

## Decision

- Keep `business_id == tenant_id == legacy salon_id`. A legal entity is identified by the composite `(tenant_id, id)` and never creates another company.
- An immutable internal reference is unique within the company. It uses 1–64 uppercase ASCII letters, numbers, dashes or underscores, beginning with a letter/number. Equal names do not merge entities; matching an internal reference gives a conflict that the owner can resolve.
- Store identity in `legal_entities` and append-only, numbered drafts in `legal_entity_versions`. Saved names can change through a new revision; saved versions and references cannot be updated/deleted, including by the owner role through ordinary SQL.
- Reuse company-wide `business.read` and `business.manage`. Only company-wide owners/managers may save; scoped memberships cannot read or edit these organization records. Audited platform support remains read-only. These metadata permissions do not imply future financial permissions.
- Reuse the existing authorization transaction, idempotency service and audit table. A company structure advisory lock precedes the membership share lock. Expected revision prevents stale updates; the hash includes the entity ID, so reusing a key for a different identity is rejected. Identity, revision, audit and receipt commit or roll back together.
- Migration 0010 is additive. Both tables have composite tenant references, ENABLE/FORCE RLS and restrictive company-only policies. The existing schema guard requires the two new definitions in addition to the 17 established definitions, including startup/readiness and scoped operational requests.
- Keep API responses typed/versioned. Lists have a limit of 1–100 and a stable internal-reference cursor. The detail route can retrieve an explicit saved revision. Responses do not imply legal registration or industry readiness.
- The existing Business profile page hosts the draft UI. It preserves the exact entity ID/body/key after an uncertain result, locks changes until retry, preserves edits on a conflict and requires explicit reload. Read-only history never replaces the current editable revision. Browser responses are checked for matching business/entity IDs.

## Acceptance

The increment needs contract, PostgreSQL and browser evidence for:

1. Create/read/update with the same tenant and entity identity; old revision stays unchanged.
2. Repeated commands and concurrent saves/references create one identity and one revision; stale versions conflict.
3. Failures roll back identity, version, audit and receipt together.
4. Different companies, branch-limited members and revoked memberships cannot obtain an old response or edit the entity; ordinary read permission does not allow saving.
5. Database policies, compound references and immutability hold under direct runtime/owner connections; damaged scope definitions fail readiness.
6. Real browser saves, lost response/retry, competing update/reload, history, keyboard/accessibility and mobile viewport work with the existing OIDC/API/disposable PostgreSQL harness.

Tests: [contracts](../../api/tests/unit/test_legal_entity_contracts.py), [database/API](../../api/tests/integration/test_legal_entities.py), [web response boundaries](../../web/tests/management-contracts.spec.ts), [browser](../../web/tests/management.spec.ts) and its [database assertions](../../api/tests/integration/test_management_browser.py). The browser cycle exercises the real management helpers and central response validator through authenticated requests. No production migration or activation follows automatically from these tests.

## Consequences

The runtime now requires migration 0010 before serving a database as ready. Apply it to a disposable database and run the checks before any independently authorized environment migration. The established migrations are unchanged. The destructive-boundary regression restores both the established policies and the two new policies after its test-only damage.

This increment advances the organization foundation but does not close CORE-03. Groups, departments, independent delegation, expiry/revocation of grants, configuration publication, multiple branch grants and shared resource occupancy still need their own accepted implementation. Registration facts, legal approvals, currency, tax rules and payment accounts belong to later validated settings, with narrower permissions where appropriate.
