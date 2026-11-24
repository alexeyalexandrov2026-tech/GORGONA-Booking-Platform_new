# PROPERTY-01 5c/6 UI — Acceptance & Verification Evidence (2026-11-20)

- **Branch**: `codex/package-property-01-maintenance-ui`
- **Base**: `f2a43062dc4f279b25ac29dc745daad07a623897` (Step 6a)
- **Code commit**: `46f7f3db3b1998c75a11e204232b3ba92cc31325` (tree `78c161950f965aa39b39f1307a6284db8a1359cc`)
- **Design doc**: [PACKAGE_PROPERTY01_MAINTENANCE_UI_DESIGN_2026-11-20.md](../../PACKAGE_PROPERTY01_MAINTENANCE_UI_DESIGN_2026-11-20.md)
- **Migrations**: none (0 new SQL migrations; schema unchanged from `0129`)
- **Registry / module gate**: unchanged (`PROPERTY-01` stays `planned`, `property` stays `enableable=False`)

## Delivered Scope
1. **Strict Zod contracts & retry-safe API client** (`web/lib/property-contracts.ts`, `web/lib/property-api.ts`, `web/tests/property-contracts.spec.ts`):
   - Added strict schemas and route bindings for `/property/leases/{lease_id}/move-out` and all 10 `/property/maintenance/*` routes.
   - `contractorWorkOrderSchema` rejects private company fields (`approved_limit_minor`, `currency`, `lease_id`, `contractor_id`, `obligations`).
   - Added integer minor-unit helpers (`parseMinorUnits`, `formatMinorUnits`) and fixed `describeAccess` in `web/lib/delegation-contracts.ts` to filter `property.*` out of booking permissions.
2. **Unit lease move-out UI** (`web/components/property-lease.tsx`):
   - Loads `GET /leases/{lease_id}/move-out` once move-in exists; renders `MoveOutRecord` or `MoveOutForm` with distinct labels, move-in report exclusion guard, optional note, report/photo downloads, stale term conflict recovery, and focus-preserving submit (`aria-disabled`).
3. **Internal maintenance UI** (`web/components/property-maintenance.tsx`, mounted in `web/components/property.tsx`):
   - Branch-scoped managers read `GET /property/maintenance?object_id=...` only (zero forms, zero `property.manage` requests).
   - Company-wide owners/managers create requests, approve (limit + currency), assign contractor counterparty, bind/unbind contractor company from live `property.contractor_work` delegation grants, open the single-request contractor link, refresh contractor updates, view event history and linked FIN-03 obligations, and complete/cancel requests.
4. **Standalone contractor work-order portal** (`web/app/property/contractor/page.tsx`, `web/app/property/contractor/contractor-work.tsx`):
   - Static-exported page `/property/contractor/?business=<uuid>&request=<uuid>&grant=<uuid>` reusing `CustomerAccessFeedback` (401 sign-in, 403/404 unavailable, network reload), displaying only the bound work order and supporting keyboard-accessible updates with retry-safe idempotency key retention.
5. **Real-browser E2E suite** (`web/tests/property-maintenance.spec.ts`, `api/tests/integration/test_property_maintenance_browser.py`):
   - Runs on desktop and mobile (390px) with real OIDC/PKCE, Chromium, FastAPI, PostgreSQL 18, axe accessibility audits, keyboard submission, dropped-network idempotency retry, single-assignment isolation (403 on unbound request), branch read-only verification, and PostgreSQL read-back.

## Verification Results (`gorgona-dev`, PostgreSQL 18.6, Chromium)
- `npm run typecheck`, `npm run lint`, `npm run format:check`: **PASS**
- `npm run test:unit`: **195 passed, 0 failed**
- `npm run build`: **PASS** (37/37 static pages, including `/property/contractor`)
- `ruff check src tests`, `ruff format --check src tests` (593 files), `mypy src tests` (593 files): **PASS**
- `pytest tests/unit -q`: **906 passed, 0 failed**
- Focused real-browser runs: `test_property_browser.py` (**PASS**, desktop + mobile) and `test_property_maintenance_browser.py` (**PASS**, desktop + mobile)
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on commit `46f7f3d`):
  - **3010 passed, 0 failed, 4 skipped** out of **3014** collected (`duplicates=0`, `count_ok=True`, wall `1173.6s` / `19m 33s`, browser lane `47/47`, serial lane `216/216`).
  - All 4 skips are standard opt-in gates: `test_tenant_site_embedding` (`GBA_REQUIRE_TENANT_SITE=1`, 1 test) and `test_container_image` (`GBA_REQUIRE_CONTAINER=1`, 3 tests).

## Remaining Scope (Not Included Here)
- Regulated / owner-decision steps of `PROPERTY-01`: public tenant screening (`2d`), security deposit custody/withholding (`4`), and owner accounting/settlement (`6b`).
- Exact-SHA GitHub Actions CI run will execute after pushing this branch.
