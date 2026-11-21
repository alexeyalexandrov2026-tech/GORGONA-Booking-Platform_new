# Design Note — PRO-01 Slice 3: Billable Time Tracking & Recurring Service Schedules (2026-11-21)

Aligned with `docs/adr/0038-projects-legal-matters-recurring-services.md` and `docs/plan/PACKAGE_PRO01_PLAN_2026-11-21.md`.

## Key Decisions
1. **Four new branch-scoped tables in `0136_projects_time_and_recurring.sql`** (invoker rights only, `require_enabled_module('projects')`, tenant RLS, branch RLS, AND restrictive PostgreSQL 18 FORCE RLS `*_matter_access` inheriting from `gba.project_matters`):
   - `project_time_entries`: billable and non-billable time entries tied to `(matter_id, optional stage_id, optional task_id, staff_user_id)` with exact `work_date`, `duration_minutes` (`1..1440`), `hourly_rate_minor` (`>= 0`), matter `currency`, `billable` boolean, derived `amount_minor = round_half_up(duration_minutes * hourly_rate_minor / 60)` when `billable` else `0`, lifecycle `draft -> submitted -> approved -> billed` (or `rejected -> draft`), and `revision`.
   - `project_time_entry_revisions`: append-only history snapshot of every edit and approval/rejection decision so time corrections never overwrite earlier versions.
   - `project_recurring_schedules`: recurring service agreements (retainers, monthly accounting, weekly cleaning/facility/security) with `cadence in ('weekly', 'biweekly', 'monthly', 'quarterly')`, `next_run_date`, `fixed_fee_minor`, matter `currency`, `task_template_title`, `status in ('active', 'paused', 'ended')`, and `revision`.
   - `project_recurring_runs`: idempotent materialized cycle runs unique on `(tenant_id, schedule_id, period_start, period_end)` that atomically create the cycle's work task in `gba.project_tasks`, advance `next_run_date`, and carry a billable status `'unbilled' | 'billed'` for Slice 4 `FIN-03` invoicing.
2. **Ethical Wall Enforcement**:
   - Every table enforces `*_matter_access` PostgreSQL 18 FORCE RLS so non-members cannot read, edit, approve, or run recurring cycles for a restricted matter.
   - `viewer` members on a restricted matter remain read-only; approving/rejecting time entries and managing recurring schedules require `PROJECTS_MANAGE` (and `'lead'` on restricted matters).
