# Design Note — PRO-01 Slice 5: `/projects/` Operations UI & Real-Browser E2E (2026-11-21)

Aligned with `docs/adr/0038-projects-legal-matters-recurring-services.md`, `docs/plan/PACKAGE_PRO01_PLAN_2026-11-21.md`, and Master Plan §14.1.1 (`PRO-01`: matter/project access restrictions enforced across search, files, tasks, invoices, and export).

## Screen Layout (`/projects/`)
Four accessible tabs with keyboard navigation (`ArrowLeft`/`ArrowRight`), WCAG AAA active/hover contrast, focusable responsive tables (`tabIndex={0}`, `role="region"`), and zero horizontal overflow at `390px`:
1. **Matters & Ethical Wall**: list/create/update legal cases, projects, and recurring engagements; record conflict-of-interest checks (`clear`/`waived`/`blocked`) before activating legal cases; grant/revoke ethical-wall memberships (`lead`/`contributor`/`viewer`/`billing`).
2. **Stages, Tasks, Files & Search**: unified ACL-enforced search across matters, stages, tasks, and matter files; create stages & submit/accept/reject deliverables; create/update tasks and add DAG dependencies; upload/download matter-restricted PDF/PNG/JPEG files.
3. **Time & Recurring**: log/edit/submit/approve/reject versioned billable time entries; create recurring service schedules (`weekly`/`biweekly`/`monthly`/`quarterly`) and materialize idempotent cycle runs.
4. **Billing & Exports**: issue `FIN-03` receivable invoice drafts from approved time entries, accepted fixed-fee stages, and unbilled recurring runs; trigger audited single-matter and branch portfolio exports and inspect authorized export history.

## Verification
- Strict Zod contracts (`web/lib/projects-contracts.ts`, wired into `web/lib/management-contracts.ts`) + Playwright unit contract tests (`web/tests/projects-contracts.spec.ts`).
- Real Chromium desktop + mobile (`390px`) E2E (`web/tests/projects.spec.ts` + `api/tests/integration/test_projects_browser.py`) exercising `axe-core` on every tab, full end-to-end legal matter lifecycle (`intake -> conflict check -> active -> stage acceptance -> task -> restricted PDF upload -> approved time -> recurring run -> FIN-03 invoice -> export`), **AND multi-user negative ethical-wall proof** (a second company-wide manager not on the ethical wall verifies the restricted matter is completely invisible in Matters, Search, Files, Tasks, Invoices, and Portfolio Export), plus PostgreSQL 18 read-back.
