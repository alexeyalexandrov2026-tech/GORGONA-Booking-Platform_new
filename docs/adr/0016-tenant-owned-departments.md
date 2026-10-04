# ADR-0016 — Tenant-owned departments

Status: accepted for the stage-1 implementation increment (CORE-03 step A). [Technical acceptance](../plan/evidence/2026-10-04-departments/ACCEPTANCE.md): full CI passed on `5b3c00b11e2bb2e844a3183bbd840ca36d764895`.

## Context

The master plan (§4, §12.2) places departments next to legal entities and locations inside one business: they organize a company, carry later financial and workforce dimensions, and must not create another company or copy its data. [ADR-0015](0015-tenant-owned-legal-entity-drafts.md) established owner-provided legal-entity drafts with immutable versions inside the existing tenant. Departments need the same ownership and history guarantees plus an acyclic structure and optional links to the company's own legal entities and locations.

This increment records owner-provided department structure only. It does not assign employees, heads, budgets, cost centers or access rights, does not publish a configuration, and does not create a group or delegation relationship. Unknown links are not invented or defaulted.

## Decision

- Keep `business_id == tenant_id == legacy salon_id`. A department is identified by `(tenant_id, id)` and never creates another company.
- An immutable internal reference (1–64 uppercase ASCII letters, numbers, dashes or underscores) is unique within the company. Equal names never merge departments.
- Store identity in `departments` and append-only numbered drafts in `department_versions`: name, optional parent department, optional legal entity, optional location and an archived flag. Saved identities and versions cannot be updated or deleted, including by the owner role through ordinary SQL.
- Every optional link uses a composite foreign key with the same `tenant_id`, so another company's department, legal entity or location cannot be referenced even by direct SQL. A department cannot be its own parent.
- `PUT` is a full replacement: every link and the archived flag must be stated, so a client cannot silently drop a link it did not send.
- Under the existing `business-structure` advisory lock, a save validates the latest structure: the parent exists and is active unless the saved department is archived; the parent chain must not reach the department (no cycle) and is bounded at 32 levels; a department with an active subdepartment cannot be archived; linked legal entities and locations belong to the company. Structure violations return 422 `DEPARTMENT_STRUCTURE_INVALID`; unknown links return 422 `INVALID_REFERENCE` with the field name.
- Reuse company-wide `business.read` and `business.manage`, the authorization transaction, idempotency service and audit table. Expected revision prevents stale updates; the request hash includes the department ID. Identity, revision, audit and receipt commit or roll back together. Audit details hold revision, reference, links and archived state, not the name.
- Migration 0011 is additive: ENABLE/FORCE RLS, tenant isolation and restrictive company-only scope policies. The schema guard requires the two new definitions (21 in total), at startup, readiness and scoped requests.
- Responses are typed and versioned; lists have a 1–100 limit and a stable internal-reference cursor; a detail can return an explicit saved revision.
- The Business profile page hosts the department UI with the same lost-response retry, conflict preservation, explicit reload and read-only history behavior as legal entities. Browser responses are checked for matching business/department IDs.

## Acceptance

1. Create/read/update keeps one tenant and department identity; the old revision stays unchanged.
2. Repeated commands and concurrent saves/references create one identity and one revision; stale versions conflict.
3. Failures roll back identity, version, audit and receipt together.
4. Cycles, self-parenting, archived parents, archiving with active children, and foreign or unknown links are rejected without a new version.
5. Other companies, branch-limited and revoked members cannot read or change departments; read permission does not allow saving; database policies, composite references and immutability hold under direct runtime/owner connections; damaged scope definitions fail readiness.
6. Real desktop/mobile browsers save, retry a lost response, reject a cycle and premature archive without locking the form, show history, detect a competing update and reload; SQL confirms the saved versions.

Tests: [contracts](../../api/tests/unit/test_department_contracts.py), [database/API](../../api/tests/integration/test_departments.py), [web response boundaries](../../web/tests/management-contracts.spec.ts), [browser](../../web/tests/management.spec.ts) and its [database assertions](../../api/tests/integration/test_management_browser.py).

## Consequences

The runtime requires migration 0011 before serving a database as ready. Apply it to a disposable database and run the checks before any separately authorized environment migration. Established migrations are unchanged; the destructive-boundary regression restores the 0010 and 0011 scope policies after its test-only cascade.

This increment does not close CORE-03. Cross-company delegation (step B) and the group model (step C) follow with their own ADRs and acceptance. Employee assignment, department-scoped permissions and financial dimensions belong to later validated packages.
