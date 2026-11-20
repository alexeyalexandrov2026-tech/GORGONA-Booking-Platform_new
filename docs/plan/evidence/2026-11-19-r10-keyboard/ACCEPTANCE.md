# R-10 keyboard accessibility of the rental screens on gorgona-dev

**R-10 PASS on gorgona-dev and in GitHub Actions ([run 44692411664](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44692411664)).** The staff rental screens and the customer problem-report page are operated
by keyboard alone after sign-in on desktop and mobile Chromium viewports, with visible `:focus-visible`
outlines on every stop, zero axe accessibility violations, and no horizontal overflow. This closes the
keyboard coverage gap left in the [R9 acceptance record](../2026-11-13-r9-acceptance/ACCEPTANCE.md).
Rental stays registered as `implemented` (`planned` in the readiness registry); readiness and enablement
require an owner decision. The production launch scope covers all 39 industry directions.
[Package R plan](../../PACKAGE_RENT_PLAN_2026-11-03.md) · [Checks](CHECKS.json)

## Cases and evidence

| Case | Result | Evidence | Coverage limits |
|---|---|---|---|
| Skip link and visible focus ring | PASS | `web/tests/rental-keyboard.spec.ts` (desktop + mobile) activates "Skip to content", verifies `#main-content` and that Tab lands inside `main#main-content`, and checks `ringed()` (`:focus-visible`, non-none outline, width > 0) on every Tab stop. Global focus outline is `web/app/globals.css:192`; no rule removes outlines. | |
| Focus management on open, edit, cancel, and mark removal | PASS | Opening a class or "Booking N" focuses its `tabIndex={-1}` heading. Saving an edited class moves focus to the "New class" heading instead of dropping to `body`. Cancelling a booking moves focus to the "Booking N" heading after the cancel form unmounts. Removing a damage mark moves focus to the next remove button, else the previous one, else "Add mark". Verified in Chromium (`test_r10_rental_keyboard_browser.py`) with PostgreSQL read-back (`revision == 2`, edited name, unit, cancelled booking). | |
| Focus continuity during async submits | PASS | Rental submit buttons across `rental.tsx`, `rental-agreement.tsx`, and `rental-settlement.tsx` use `aria-disabled={busy}` with handler busy guards (styled alongside `button:disabled` in `globals.css`) so saving never blurs the button to `document.body`. Verified red before the fix (`Save class` lost focus to `inactive`) and green after. | |
| Destructive cancel confirmation | PASS | "Cancel booking" requires checking "I confirm this booking will be cancelled" before Enter in Reason or activation cancels the booking. Verified refused with zero POST requests without the box, then accepted with Space + Enter; `web/tests/rental.spec.ts` updated accordingly. | |
| Disclosures and customer form landmarks | PASS | "Manage/Close customer access" (`rental-customer-access.tsx`) and "Manage/Close agreement changes" (`rental-change-offers.tsx`) carry `aria-controls` pointing to an always-rendered wrapper (`useId`). Customer proposal (`proposal.tsx`) and agreement change (`offer.tsx`) forms carry explicit `aria-label`s. Verified in `rental-keyboard.spec.ts` and `rental-change-offer.spec.ts`. | |
| Customer problems keyboard walkthrough and staff company column | PASS | `web/tests/rental-problem-reports.spec.ts` (via `test_r09_rental_problem_reports_browser.py`, desktop + mobile) drives the customer page by keyboard (Tab with `:focus-visible` ring checks to Sign in, Kind, What happened, Date, Time, Send problem report, and Retry problem report; Enter submits; confirmation status receives focus) and verifies staff Reload shows `<servicer_display_name> on the platform`. | Date and time values are filled via Playwright `.fill()` after reaching the inputs by Tab, because native segmented editing depends on locale. |
| Automated accessibility and responsive fit | PASS | axe reports zero violations (including WCAG 2.0/2.1/2.2 A/AA on customer pages) and `scrollWidth <= innerWidth` holds on desktop and mobile across all 7 rental browser suites (`r10`, `r8a`, `r8b`, `r8c`, `r09` change offer, proposal, problem reports). | Customer proposal and change-offer pages have `aria-label`, axe, and full browser coverage; full Tab-only walkthrough is automated on the staff rental screen and customer problems page. |

## Commits (on top of `13d4a8c`)

| Commit | Tree | Content |
|---|---|---|
| `728e662` | `a34f35d` | Keyboard use of the rental screens: heading focus, cancel confirmation, `aria-controls` disclosures, form labels, damage-mark removal focus, `rental-keyboard.spec.ts` (cherry-picked from `d3d5689`) |
| `c7e3046` | `003cf11` | Keep focus across busy submits (`aria-disabled`), edited class saves, and booking cancel; add `test_r10_rental_keyboard_browser.py` harness (cherry-picked from `4345206`) |
| `b2a6fac` | `5239059` | Keyboard walkthrough of customer problems page and staff company column check |

## Checks on gorgona-dev

| Run | Tree | Result |
|---|---|---|
| R-10 base web checks (`d3d5689`) | `f6678bb` | typecheck, lint, format:check, test:unit (193 passed), build PASS |
| R-10 focus continuity red run (on `d3d5689`) | — | `test_r10_rental_keyboard_browser.py` failed as expected: `Save class` lost focus (`Received: inactive`) due to `disabled={busy}` |
| R-10 focus fixes + 7 browser suites (`4345206`) | `86aacaa` | web static + unit + build PASS; api ruff/mypy PASS; 7/7 rental browser suites passed in 98.31 s |
| Combined tree Step 4 first run | — | web PASS; api ruff caught `PT018`; second run (`step4b`) 6/7 passed, 1 failed (`rental-problem-reports.spec.ts` on `<input type="time">` shadow-DOM picker indicator) |
| Combined tree Step 4 final targeted run (`b2a6fac`) | `5239059` | web static + unit + build PASS; api ruff/mypy (583 files) PASS; **7/7 rental browser suites passed** in 92.27 s |
| Combined full suite (`b2a6fac`) | `5239059` | static PASS (web unit 194 passed); **2968 passed, 4 skipped, 1 failed** in 3182.82 s: the known flaky `test_l7a_catalog_browser` failed once and passed **2/2** when rerun alone on the same tree |

The four VM skips are three container tests (`GBA_REQUIRE_CONTAINER=1`) and the external tenant-site test
(`GBA_REQUIRE_TENANT_SITE=1`). PostgreSQL 18.7 and Chromium were required.

## Open items

- Readiness: RENT-01 stays `planned` in the readiness registry until the owner decides.
- Problem reports still have no photo attachments or staff notification.
