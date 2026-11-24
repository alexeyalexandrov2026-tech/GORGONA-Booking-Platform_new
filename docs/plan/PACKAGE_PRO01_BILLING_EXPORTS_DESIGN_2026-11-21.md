# Design Note — PRO-01 Slice 4: FIN-03 Matter Invoicing & ACL-Enforced Audited Exports (2026-11-21)

Aligned with `docs/adr/0038-projects-legal-matters-recurring-services.md`, `docs/plan/PACKAGE_PRO01_PLAN_2026-11-21.md`, and Master Plan §14.1.1 (`PRO-01`: matter/project access restrictions enforced across search, files, tasks, invoices, and export).

## Key Decisions
1. **Three new branch-scoped tables in `0137_projects_billing_and_exports.sql`** (invoker rights only, `require_enabled_module('projects')`, tenant RLS, branch RLS, AND restrictive PostgreSQL 18 FORCE RLS `*_matter_access`):
   - `project_matter_invoices`: links a matter to a real `FIN-03` receivable invoice draft created through `financial_documents.save_draft` (`book_id`, `invoice_document_id`, `counterparty_id`, `total_minor`, `currency`), with zero second ledger.
   - `project_matter_invoice_items`: append-only item traceability linking each billed `time_entry_id` (approved billable time), `stage_id` (accepted fixed-fee stage), or `recurring_run_id` (unbilled recurring cycle) with partial unique indexes so double-billing is impossible at the database level.
   - `project_exports`: append-only audit log of single-matter (`scope='matter'`) and branch portfolio (`scope='portfolio'`) exports, with `project_exports_matter_access` restricting matter exports to active matter members and portfolio export records to the requesting actor (`requested_by = gba.current_user_id()`).
2. **Ethical Wall Across Invoices & Exports**:
   - Creating a `FIN-03` invoice requires company-wide scope (`FINANCE_MANAGE` + `PROJECTS_MANAGE`) AND active `'lead'` or `'billing'` membership on a `'restricted'` matter.
   - Non-members (even a company-wide `owner` or `manager` with `FINANCE_MANAGE`) receive `404` when listing/creating invoices or exporting a restricted matter, AND portfolio exports (`POST /projects/exports`) strictly omit every restricted matter (plus its stages, tasks, files, time entries, recurring runs, and invoices) that the caller is not an active member of.
