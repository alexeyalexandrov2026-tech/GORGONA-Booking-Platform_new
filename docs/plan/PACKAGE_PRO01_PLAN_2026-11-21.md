# Package Plan: PRO-01 — Legal Matters, Projects & Recurring Services (2026-11-21)

Aligned with `docs/plan/GORGONA_MASTER_PLAN.md` §4, §10, §13–14.1.1 and `docs/adr/0038-projects-legal-matters-recurring-services.md`.
`PRO-01` acceptance criterion:
> Matter/project access restrictions are enforced across search, files, tasks, invoices, and export.

## Slices
1. **Slice 1 (`codex/package-pro-01-matters-and-acl`, migration `0134`)**:
   - Update module `projects` (`Readiness.IMPLEMENTED`, `enableable=False`, `depends_on=("counterparties", "documents", "finance_documents")`, `MODULE_REGISTRY_VERSION=9`) + `PROJECTS_READ`, `PROJECTS_WORK`, `PROJECTS_MANAGE` permissions (`PERMISSIONS_VERSION=18`, non-delegable).
   - Tables: `project_matters`, `project_matter_revisions`, `project_conflict_checks`, `project_matter_members`.
   - Enforce tenant + branch + PostgreSQL 18 restrictive ethical-wall RLS (`gba.current_user_id()`), deferred active-lead invariant for restricted matters, legal-case conflict-check gate before activation, and audit trail.
2. **Slice 2 (`codex/package-pro-01-stages-tasks-and-files`, migration `0135`)**:
   - Tables: `project_stages` (deliverable acceptance workflow), `project_tasks`, `project_task_dependencies` (DAG cycle check), `project_matter_documents` (links to `gba.documents`).
   - Matter-ACL-enforced file listing & binary download route (`/projects/matters/{id}/documents/{doc_id}/versions/{ver_id}/content`) and unified ACL-enforced search (`GET /projects/search`) across matters, stages, tasks, and document titles.
3. **Slice 3 (`codex/package-pro-01-time-and-recurring`, migration `0136`)**:
   - Tables: `project_time_entries` (append-only revision chain on edits, approval lifecycle `draft -> submitted -> approved -> billed / rejected`), `project_recurring_schedules` (`weekly | biweekly | monthly | quarterly`), and idempotent `project_recurring_runs` (materializing cycle tasks and billable charges once per period).
4. **Slice 4 (`codex/package-pro-01-billing-and-exports`, migration `0137`)**:
   - Tables: `project_matter_invoices`, `project_matter_invoice_items`, `project_exports`.
   - Issue real `FIN-03` receivable invoices from approved billable time entries, accepted fixed-fee stages, and recurring runs with atomic one-time billing lock; provide single-matter and branch-wide audited exports that strictly exclude restricted matters for non-members.
5. **Slice 5 (`codex/package-pro-01-ui`, no new migration)**:
   - Four-tab `/projects/` operations UI (Matters & ACL, Stages/Tasks/Files & Search, Time & Recurring, Billing & Exports) with desktop + mobile (`390px`) + keyboard + `axe-core` real-browser E2E including negative ethical-wall proof across all 5 surfaces and PostgreSQL 18 read-back.

## Non-Goals (Not Part of Technical Slices)
- Jurisdiction-specific court e-filing, trust/IOLTA escrow bank connectors, electronic signatures, or malware scanning.
- Raising `PRO-01` readiness or enabling `projects` without explicit owner approval.
