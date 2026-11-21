# Acceptance Evidence — PRO-01 Slice 5: `/projects/` Management UI & Real-Browser E2E (2026-11-21)

- **Branch**: `codex/package-pro-01-ui`
- **Base commit**: `03ae68a3fb3cc300deed56a31bbb801b2a90791e` (`codex/package-pro-01-billing-and-exports`)
- **Verified code commit**: `07df6c98be737b75b435727a329485957eafdaad` (tree `de5a7e1cf7f76b9e64aaa63491019993796731ec`)
- **Migration**: none (builds on `0134`–`0137`)
- **Design**: `docs/plan/PACKAGE_PRO01_UI_DESIGN_2026-11-21.md`

## Scope Delivered
1. Strict TypeScript runtime decoders (`web/lib/projects-contracts.ts` wired into `web/lib/management-contracts.ts`), API client (`web/lib/projects-api.ts`), and contract unit tests (`web/tests/projects-contracts.spec.ts`).
2. Responsive 4-tab `/projects/` workspace (`web/app/projects/page.tsx`, `web/components/projects.tsx`, `web/app/projects.css`, navigation entry in `web/components/management-layout.tsx`):
   - **Matters & Ethical Wall**: branch selector, matters list (`branch` & `restricted`), conflict checks, legal-case activation gate, and ethical-wall member grant/revoke.
   - **Stages, Tasks, Files & Search**: deliverable stages (`submit/accept/reject`), DAG tasks with cycle-checked dependencies, restricted matter file upload/download, and unified ACL search.
   - **Time & Recurring**: billable time entries with revision chain & approval decisions, recurring service schedules, and one-click cycle execution.
   - **Billing & Exports**: combined `FIN-03` receivable invoice draft issuance (`financial_documents.save_draft`) and single-matter + portfolio audited JSON exports.
3. Real Chromium desktop + mobile (`390px`) Playwright E2E (`web/tests/projects.spec.ts`, `api/tests/integration/test_projects_browser.py`) verifying the full workflow, two-user ethical-wall isolation (`outsider` sees `0` restricted matters/search hits/portfolio export entries), zero `axe-core` critical/serious violations, zero horizontal overflow, keyboard navigation, and direct PostgreSQL 18 read-back.

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run test:unit`, `npm run build`: **PASS**
- `ruff check src tests`, `ruff format --check src tests` (635 files), `mypy src tests` (635 files): **PASS**
- Focused real-browser E2E (`pytest tests/integration/test_projects_browser.py -q` on desktop + mobile `390px`): **PASS**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `07df6c98be737b75b435727a329485957eafdaad`):
  - **3057 passed, 0 failed, 4 skipped** out of **3061** (`duplicates=0`, `count_ok=True`, wall time **1452.44s**; browser **49/49**, serial **216/216**).
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
