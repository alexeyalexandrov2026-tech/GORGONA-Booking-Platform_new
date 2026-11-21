# Acceptance Evidence — REST-01 Slice 5: Restaurant Operations UI & Real-Browser E2E (2026-11-21)

- **Branch**: `codex/package-rest-01-ui`
- **Base commit**: `e75aba5342becf50ab6289cf18990105b1287912` (`codex/package-rest-01-split-billing-and-refunds`)
- **Verified code commit**: `84660dff2953c45f73099dd27b32cb16184e5f0d` (tree `5aa72894c3e9324381af4db52edb0fadc1f53f02`)
- **Migration**: none (next available migration remains `0134`)
- **Design**: `docs/plan/PACKAGE_REST01_UI_DESIGN_2026-11-21.md`

## Scope Delivered
1. Strict Zod contracts (`web/lib/restaurant-contracts.ts`), response-schema routing (`web/lib/management-contracts.ts`), cursor-paginated readers and `Idempotency-Key` command helpers (`web/lib/restaurant-api.ts`), plus unit contract tests (`web/tests/restaurant-contracts.spec.ts`).
2. Four-tab internal screen at `/restaurant/` (`web/app/restaurant/page.tsx`, `web/components/restaurant.tsx`, `web/app/restaurant.css`, navigation link in `web/components/management-layout.tsx`):
   - Tab 1: **Floor & Reservations** (dining areas, tables, independent reservations with lifecycle events).
   - Tab 2: **Menu & Recipes** (versioned menu items, modifier groups & options, menu attachments, `STOCK-01` recipe BOM revisions).
   - Tab 3: **Checks & Split Billing** (independent checks with sequence-guarded detail loader, order lines with modifiers, fire-to-kitchen, `STOCK-01` write-offs, split by items/amounts, `FIN-03` share billing, coordinated refunds & live reconciliation).
   - Tab 4: **Kitchen Station Board** (station filters, live `queued -> preparing -> ready -> served / voided` actions).
3. Accessible responsive controls: keyboard tab navigation (`ArrowLeft`/`ArrowRight`), WCAG AA/AAA tab active & hover contrast (`#1e293b`/`#0f172a`/`#f1f5f9`), focusable horizontal table regions (`tabIndex=0`, `role="region"`), and zero horizontal overflow at `390px`.
4. Real Chromium desktop + mobile (`390px`) E2E test (`web/tests/restaurant.spec.ts` + `api/tests/integration/test_restaurant_browser.py`) exercising 3 distinct roles (`owner`, `front_desk`, `artist`), `axe-core` on every tab, and PostgreSQL 18 read-back confirming 2 checks, 2 served tickets, 2 splits, 2 `STOCK-01` consumptions, and exact remaining stock balance (`640 g`).

## Verification on `gorgona-dev` (PostgreSQL 18.6, Chromium)
- `ruff check .`, `ruff format --check .`, `mypy src tests` (614 files): **PASS**
- `npm run typecheck`, `npm run lint` (0 warnings/errors), `npm run format:check`, `npm run test:unit` (**197 passed**), `npm run build` (**38 static pages including `/restaurant`**): **PASS**
- `pytest tests/integration/test_restaurant_browser.py -q` (real Chromium desktop + mobile 390px + `axe-core` + PG18 read-back): **1 passed (`29.91s`)**
- Full parallel suite (`uv run --locked python -m tools.run_parallel_tests --workers 6` on `84660dff2953c45f73099dd27b32cb16184e5f0d`):
  - **3036 passed, 0 failed, 4 skipped** out of **3040** (`duplicates=0`, `count_ok=True`, wall time **1311.85s / 21m 52s**; browser **48/48**, serial **216/216**).
  - Skips (4 opt-in container/tenant-site checks): `test_tenant_site_embeds_the_real_wizard` (`GBA_REQUIRE_TENANT_SITE=1`) and 3 tests in `test_container_image.py` (`GBA_REQUIRE_CONTAINER=1`).
