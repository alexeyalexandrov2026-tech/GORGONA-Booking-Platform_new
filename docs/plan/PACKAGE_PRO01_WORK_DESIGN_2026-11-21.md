# Design Note — PRO-01 Slice 2: Stages, Tasks, Dependencies, Restricted Matter Files & ACL Search (2026-11-21)

Aligned with `docs/adr/0038-projects-legal-matters-recurring-services.md` and `docs/plan/PACKAGE_PRO01_PLAN_2026-11-21.md`.

## Key Decisions
1. **Four new branch-scoped tables in `0135_projects_stages_tasks_and_files.sql`** (invoker rights only, `require_enabled_module('projects')`, tenant RLS, branch RLS, AND restrictive PostgreSQL 18 FORCE RLS `*_matter_access` inheriting from `gba.project_matters`):
   - `project_stages`: ordered milestones/phases (`stage_no`, `title`, `fixed_fee_minor`, `due_on`, `deliverable_summary`, `deliverable_revision`, `status in ('open', 'submitted', 'accepted', 'rejected')`).
   - `project_tasks`: work items optionally attached to a stage, with `assignee_user_id`, `priority`, `status in ('todo', 'in_progress', 'blocked', 'done', 'cancelled')`, optimistic `revision`, and blocked-by-incomplete-dependency checks if desired.
   - `project_task_dependencies`: directed DAG edges `(task_id -> depends_on_task_id)` within the same `(tenant_id, matter_id)` with a PostgreSQL `WITH RECURSIVE` cycle-prevention trigger.
   - `project_matter_files`: immutable, append-only matter-scoped files (PDF/PNG/JPEG validated by `gorgona_booking.business.file_validation.validate_file`, capped at `MAX_FILE_BYTES`, gated by malware-scanner flag in non-dev environments, plus optional `linked_document_id` FK to `gba.documents`). Storing matter-restricted binaries inside `project_matter_files` under `project_matter_files_matter_access` FORCE RLS guarantees that even a company-wide `owner`/`manager` with `DOCUMENTS_READ` cannot bypass an ethical wall to view or download a restricted matter's files.
2. **ACL-Enforced Unified Search (`GET /v1/businesses/{id}/projects/search`)**:
   - Searches matters, stages, tasks, and matter files using escaped `ILIKE`, backed directly by PostgreSQL 18 `*_matter_access` FORCE RLS so non-members receive zero hits for restricted matters across all four object types.
3. **Role enforcement on restricted matters**:
   - `viewer` members on a restricted matter have read-only access (cannot mutate tasks, deliverables, or upload files).
   - `lead`, `contributor`, and `billing` members with `PROJECTS_WORK` may update tasks and upload files; stage acceptance/rejection requires `PROJECTS_MANAGE` (and `lead` on restricted matters).
