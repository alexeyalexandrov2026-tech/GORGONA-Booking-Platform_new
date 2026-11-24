# ADR-0038: Legal Matters, Projects, Recurring Services and Ethical-Wall Access Control (PRO-01)

- **Status**: Accepted (technical implementation in progress; module `projects` remains `enableable=False` until full `PRO-01` acceptance and owner approval)
- **Date**: 2026-11-21
- **Stage**: Master Plan Stage 5 (`PRO-01` — Legal services, accounting/consulting, IT/creative projects, and recurring facility/field services)

## Context
Master Plan §4, §10, §13, and §14.1.1 define `PRO-01`:
- Legal cases require intake, conflict-of-interest checks before activation, deadlines/documents, time tracking, `FIN-03` invoicing, closing, and **matter-level access restrictions (ethical walls)**.
- Projects and recurring engagements (consulting, accounting, IT/creative, recurring cleaning/maintenance/security) require stages/milestones, tasks with dependencies, assignees, deliverable acceptance, budgets, recurring service schedules, and `FIN-03` billing without creating a second ledger.
- Acceptance criterion `PRO-01` (§14.1.1):
  > Matter/project access restrictions are enforced across search, files, tasks, invoices, and export.

## Decision
1. **Optional module `projects`**: already present in `modules.py`; updated to `Readiness.IMPLEMENTED` (`enableable=False`) with `depends_on = ("counterparties", "documents", "finance_documents")` (`MODULE_REGISTRY_VERSION = 9`).
2. **Role-scoped, non-delegable permissions** (`PERMISSIONS_VERSION = 18`):
   - `projects.read`: read authorized matters/projects, stages, tasks, linked files, time entries, recurring schedules, invoices, and search results within branch and matter scope (`artist`, `front_desk`, `manager`, `owner`).
   - `projects.work`: update assigned/authorized tasks, submit stage deliverables, link authorized documents, and log time entries on authorized matters (`artist`, `front_desk`, `manager`, `owner`).
   - `projects.manage`: create/update matters/projects, record conflict checks, manage ethical-wall memberships, configure recurring schedules, approve time/milestones, issue `FIN-03` matter invoices, and generate audited exports (`manager`, `owner`, subject to matter ACL on restricted matters).
   - None of these permissions are cross-company delegable.
3. **Database-enforced Ethical Wall (PostgreSQL 18 FORCE RLS, Invoker Rights Only)**:
   - Every matter in `gba.project_matters` has `access_mode in ('branch', 'restricted')`.
   - `branch` matters are accessible to authorized members within tenant and branch scope (`gba.current_location_id()`).
   - `restricted` matters are accessible **only** to users with an active (`revoked_at is null`) row in `gba.project_matter_members` matching `gba.current_user_id()`, enforced directly by a restrictive PostgreSQL 18 RLS policy (`to gba_runtime`, no `SECURITY DEFINER`).
   - During the creating transaction only (`creation_xid = pg_current_xact_id()`), the creator may insert the restricted matter and its initial `'lead'` membership; a `DEFERRABLE INITIALLY DEFERRED` trigger ensures every restricted matter always retains at least one active `'lead'` member. Once committed, revoking any user (including the original creator) immediately removes visibility across SQL queries, search, files, tasks, invoices, and exports.
   - All child tables inherit the same matter-level RLS via `exists (select 1 from gba.project_matters ...)` without recursive RLS on `project_matter_members`.
4. **Conflict-of-Interest Gate for Legal Matters**:
   - Matters with `kind = 'legal_case'` start in `'intake'` or `'conflict_check'` and cannot transition to `'active'` without a recorded `'clear'` or `'waived'` decision in `gba.project_conflict_checks`.
5. **Reusing Verified Building Blocks**:
   - Client/counterparty links reference `gba.counterparties`; restricted files link to versioned `gba.documents` and are served through matter-ACL-checked proxy routes; invoicing issues real `FIN-03` receivable drafts via `financial_documents.save_draft` with one-time billing locks on time entries, milestones, and recurring runs.
