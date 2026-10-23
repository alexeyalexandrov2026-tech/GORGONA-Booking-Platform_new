# Next agent — package L after L7b2b: L7c (customer site) and L8 (BEAUTY-01 acceptance), 2026-10-23

Read this whole file before any command. It is the current entry point and replaces the
[FIN-02 handoff](NEXT_AGENT_AFTER_FIN02_2026-10-20.md) for package L. The ready-to-paste prompt is
[NEXT_AGENT_PACKAGE_L7C_PROMPT_2026-10-23.md](NEXT_AGENT_PACKAGE_L7C_PROMPT_2026-10-23.md).

## 0. The goal (owner)

Production is **all 39 directions of the master plan at once**, one launch; any business of any
direction signs up and works. Never plan, describe or estimate a salon-only or one-industry launch
(master plan top block, §1 item 13, §13, §14.3; `AGENTS.md`). Package L builds the beauty cycle
(BEAUTY-01) as **platform parts** — stages, multi-service visits, consumption, visit billing,
commissions, prepaid balances — that spas, clinics, workshops and rentals reuse. Screens use neutral
words: specialist, service, visit, materials, prepaid balance.

The owner gave full delegation on 2026-10-22: «Делай как считаешь нужным и правильным! Я полностью даю
тебе право выбора»; since then only «continue». The hard limits in section 5 still apply.

## 1. State (verified 2026-10-23)

### Branches

Package L is a chain of branches; each starts from the previous head. All are **published for CI only**
(no PR); `main` is still `0591d3a` and is an ancestor of the chain (the chain is 37 commits ahead).

| Slice | Branch | Head (docs) | CI |
|---|---|---|---|
| plan | `codex/package-l-plan` | `5eb534c` | SUCCESS 39758206876 |
| L1 stages, equipment (0066) | `codex/package-l1-stages` | `d62beef` | SUCCESS 39758206502 |
| L2a stage occupancy (0067) | `codex/package-l2-occupancy` | `80e91b0` | SUCCESS 39765610640 |
| L2b guests book staged services | `codex/package-l2b-guest-stages` | `a6b6844` | SUCCESS 39777287553 |
| L2c visits of several services | `codex/package-l2c-visits` | `f255e6b` | SUCCESS 39783826823 |
| L3 completion, consumption (0068); CI limit 75 min | `codex/package-l3-consumption` | `ef83b91` | SUCCESS 39805277086 |
| L4 visit billing (0069) | `codex/package-l4-billing` | `0904f2f` | SUCCESS 39812765674 |
| L5 commissions (0070) | `codex/package-l5-commissions` | `ffddb66` | SUCCESS 39819887470 |
| L6 prepaid (0071) | `codex/package-l6-prepaid` | `1df0a6c` | SUCCESS 39828302644 |
| L7a catalog screens; Next.js 16.4.2 security fix | `codex/package-l7a-catalog-screens` | `9c4dfbb` | SUCCESS 39838977982 |
| L7b1 visit desk | `codex/package-l7b1-visit-desk` | `9d9ca65` | SUCCESS 39855981830 |
| L7b2a billing, commission, plan screens + date fix | `codex/package-l7b2a-billing-desk` | `d2ac158` | SUCCESS 39879172808 (first run 39873748480 FAILED, see 7) |
| L7b2b prepaid screen, redemption on the desk | `codex/package-l7b2b-prepaid-screens` | `594682a` + this handoff | SUCCESS 39886335939 |

- Migrations **0001–0071 are immutable**; the next is **0072**.
- Readiness: BEAUTY-01 stays **partial**; no readiness change in package L yet.
- `main` still pins Next.js 16.3.8 (GHSA-2464-fhr4-w9xw); the chain has 16.4.2. Merging fixes it.

### Worktrees on this computer

- **Use** `C:/Users/alexa/.codex/worktrees/package-l7b2b/Gorgona Booking` — branch
  `codex/package-l7b2b-prepaid-screens`, clean, `web/node_modules` installed (`npm ci`), **no `api/.venv`**.
  Run Python with the first worktree's interpreter
  `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking/api/.venv/Scripts/python.exe`;
  the run-folder `runner.py` puts this worktree's `api/src` first on `PYTHONPATH`, so its code is the
  code under test (proven: L7b2b's new route existed only here and its tests passed). `ruff` and `mypy`
  work through the same interpreter. Do not run `uv sync` unless needed; if you do, use `--frozen`.
- **Do not touch** `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`: another
  session the owner started ("Keep Playwright snapshots when browser wrappers fail") works there on the
  local branch `codex/browser-failure-snapshots` (`015f28f` on `d2ac158`, not published). It makes every
  browser wrapper append `web/test-results/*/error-context.md` to its failure message. Ask the owner
  before building on it or merging it into the chain.
- Never touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.

### Run folders (evidence of the last slices)

`C:/Users/alexa/AppData/Local/GorgonaBookingTests/` (physically under
`Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/...`): `package-l7b2b-20261023-fa30344` (the newest
harness: `runner.py`, `run_gates.py`, `write_record.py`, `STATE.md`), `package-l7b2a-fix-20261023-cdbc441`,
`package-l7b2a-20261022-9d9ca65`.

## 2. What package L contains

Plan: [PACKAGE_L_PLAN_2026-10-22.md](PACKAGE_L_PLAN_2026-10-22.md) (decisions 1–8, acceptance L-01..L-12).
Designs: [L2](PACKAGE_L2_DESIGN_2026-10-22.md) (1–15), [L3](PACKAGE_L3_DESIGN_2026-10-22.md) (16–21),
[L4](PACKAGE_L4_DESIGN_2026-10-22.md) (22–27), [L5](PACKAGE_L5_DESIGN_2026-10-22.md) (28–33, 30 revised),
[L6](PACKAGE_L6_DESIGN_2026-10-22.md) (34–39), [L7](PACKAGE_L7_DESIGN_2026-10-22.md) (40–47, L7b and
L7b2 splits, acceptance L7-01..L7-15). Evidence: `docs/plan/evidence/2026-10-22-l*` and `2026-10-23-l7b2b-*`,
each with `VALIDATION.md` and a source-bound `CHECKS.json`.

| Area | Where |
|---|---|
| Stages, quote, occupancy | `api/.../booking/stages.py`, `booking/models.py`, `catalog/quote.py` (`build_visit_quote`), migrations 0066–0067 |
| Guest site API | `api/.../customer/contracts.py` (`Selection.extra_lines` ≤ 4, quote v1/v2), `customer/queries.py`, `customer/service.py`, `api/customer.py` (`POST /availability`, holds) |
| Completion, consumption | `business/visits.py`, migration 0068 |
| Visit billing | `business/visit_billing.py`, migration 0069 |
| Commissions | `business/commissions.py`, migration 0070 |
| Prepaid | `business/prepaid.py` (`sell`, `redeem`, `list_prepaid`), migration 0071 |
| Visit routes | `api/.../api/visits.py` (recipes, complete, completion, consumption, invoice, commission, plan, prepaid list/sale, redeem) |
| Management screens | `web/components/service-catalog-editors.tsx`, `visit-desk.tsx`, `visit-billing.tsx`, `commission-plan-dialog.tsx`, `prepaid-screen.tsx`; `web/app/prepaid/page.tsx`; strict contracts in `web/lib/management-contracts.ts`, calls in `web/lib/management-api.ts` |
| Customer screens | `web/components/booking.tsx`, `booking-parts.tsx`, `web/lib/contracts.ts` (`quoteSchema` v1/v2), `web/lib/api.ts` |

## 3. Next: L7c — the customer site (several services, stages shown)

The API is already done (L2b, L2c: decisions 8–15): the guest `Selection` accepts `extra_lines` (up to
four more services, each with its own add-ons), one specialist serves the whole visit (decision 14),
and a visit of two or more lines or a staged service is a **version 2 quote with stages**. The web
customer site still books one service and does not show stages.

Steps:

1. **Design first.** Append "L7c decisions" (48 onwards) and acceptance rows (L7-16 onwards) to
   `PACKAGE_L7_DESIGN_2026-10-22.md` on a new branch `codex/package-l7c-customer-site` from the head of
   `codex/package-l7b2b-prepaid-screens`, and commit the docs before any test. Suggested decisions:
   (a) "Add another service" adds up to four more lines, each with its own add-ons, in order; (b) the
   summary lists every line with its price and the visit total and duration; (c) a version 2 quote
   shows its stages in order (kind in plain words, minutes; a processing stage says the specialist is
   free meanwhile); (d) availability and the hold send `extra_lines`; a refusal (a specialist who does
   not serve every service, a conflict or missing requirement across lines, more than 720 minutes) shows
   the server's plain reason; (e) the strict contract of the version 2 quote is reused, never loosened.
2. **Failing tests first**: a contract test for a two-line version 2 quote; extend
   `web/tests/booking.spec.ts` (run by `npm run test:e2e` from `api/tests/integration/test_customer_browser.py`)
   or add a new spec with its own Python wrapper: a guest books two services, sees both lines and the
   stages, holds and confirms; then read the booking back from the database (two quote lines, the right
   intervals). Desktop and mobile, keyboard only, axe without violations, no horizontal scroll. Record
   the red run.
3. Code, then the slice process of section 6.

## 4. Then: L8 — BEAUTY-01 acceptance

1. Map L-01..L-12 of the plan to the evidence of L1–L7c; list every gap honestly. Known points: L-07 says
   "a refund reverses it", but L5 left automatic reversal on refund to a later decision (a manual FIN-03
   credit note on the accrual reverses it) — record it, do not pretend; L-03 races need an **observed
   `pg_locks` wait**; L-10 disabled modules must remove their step; L-12 regression of BOOKING,
   FIN-01–03, WORK-01, STOCK-01.
2. **One independent review** of package L. An extra agent needs the **owner's consent** — ask in
   Russian, simply, before starting it. Fix its findings in their own slice.
3. Readiness record for BEAUTY-01 (an acceptance document like
   `evidence/2026-10-20-fin-02-acceptance/ACCEPTANCE.md`). **Changing the readiness registry needs the
   owner's word.**
4. Merge: the L plan records the owner's earlier choice — fast-forward `main` after green CI. Confirm
   with the owner before fast-forwarding, then watch CI on `main`.

## 5. Rules (hard)

- No PR, merge, `main` change, rebase, amend, reset, clean or force-push, readiness change, CodeRabbit,
  Azure action, production or live-mode provider action, deployment or production migration without the
  owner's separate direct word. Under the full delegation, **pushing a new slice branch for CI only**
  (no PR) has been the practice for every L slice. Each Azure action needs its own consent; never repeat
  the Azure sign-in address.
- Stripe: sandbox or test mode only; the owner alone signs in and accepts terms; never enter or print a
  password, key, token or secret; no live mode.
- One executor and one own disposable PostgreSQL 18 cluster per run (the runner does this; explicit
  port on 127.0.0.1; never 51454, 51458, 51474, 51511, 49981; check `postmaster.pid` before stopping).
- Races only with an observed `pg_locks` wait. Failing tests first. Never hide a failure: every red,
  slip and flake goes into `STATE.md` and the record's `preserved_failures`. Do not edit `api/`, `web/`
  or `docs/runbooks/` while a run is going (the runner checks the source did not change).
- An extra agent only with the owner's consent. Write to the owner in Russian, simply; the owner is
  they/them. Commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- GateGuard hook: the first Bash command of a session and the first Write/Edit of each file are denied
  once — state the facts it asks for (request, callers, schema, the owner's words), then retry. Write a
  one-line placeholder with Bash first when creating a file. Do not use shell heredocs for Python with
  backslashes or long text blocks (they broke twice); write the script to the scratchpad and run it.

## 6. The slice process (exactly as L1–L7b2b)

1. Design and decisions committed (docs commit) on the new branch.
2. Failing tests first; run them red in a new run folder
   `GorgonaBookingTests/package-<slice>-<yyyymmdd>-<base sha>` with copies of `runner.py`,
   `run_gates.py`, `write_record.py` from `package-l7b2b-20261023-fa30344`; set `ROOT` and the docstring
   in `runner.py`; keep a `STATE.md` log.
   `python runner.py red-1 focused tests/integration/<file>.py ...` — paths **relative to `api/`**;
   `python` is the interpreter named in section 1. A browser focused run needs `web/out` built first
   (`npm run build` in `web/`, or run the static phase).
3. Code; dev runs (`dev-N`) until green; record each failure and its cause in `STATE.md`.
4. Gates: add the new test modules to `run_gates.py`'s focused list, then `python run_gates.py N`
   (static → focused → full; never advance on failure). Full takes 42–51 minutes locally.
5. Record **before** the code commit: adapt `write_record.py` (`ROOT`, `BASE`, `BRANCH`, `EVIDENCE`,
   `SOURCES` = exactly the changed files under `api/`, `web/`, `docs/runbooks/`, `NEW_MODULES`,
   `NEW_CASES`, `REQUIRED`, new modules into `REGRESSION`, `ARCHITECTURE`, `FAILURES`, `REMAINING`,
   status; with a migration also the immutable count and `added_migrations`), then
   `python write_record.py N`.
6. Code commit of exactly `SOURCES`; docs commit: `evidence/.../VALIDATION.md` + `CHECKS.json`, the
   design doc, and the checkpoint at the top of `GORGONA_IMPLEMENTATION_STATUS.md`,
   `GORGONA_MASTER_PLAN.md` and `CLOUD_CODE_HANDOFF.md`.
7. `git push -u origin <branch>` (CI only), then watch CI by branch every 180 s with the GitHub API
   (`/actions/runs?branch=<branch>`; filtering by `head_sha` can come back empty). A failed CI run is
   readable without sign-in through `/actions/runs/<id>/jobs` and `/check-runs/<job id>/annotations`.
8. Update the memory file `gorgona-package-l-state.md` and its line in `MEMORY.md`.

## 7. Lessons from package L

- **Dates in tests: never "today" in UTC.** The server checks stock dates against the branch zone and
  ledger dates against the business zone (America/New_York in fixtures). Use `zone_today` with
  `BRANCH_ZONE` or `BUSINESS_ZONE` from `tests/integration/test_l7b_visit_desk_browser.py`. CI after
  00:00 UTC failed on this (run 39873748480).
- **Name every `<select>` with `aria-label`.** A wrapping `<label>` includes all option texts, so
  `getByLabel("Customer")` also matched "Revenue account" once "2100 Customer prepayments" loaded, and a
  "Kind" select read as "Percentage".
- **A scrollable table needs a focusable region** (`role="region"`, `aria-label`, `tabIndex={0}`, as in
  `financial-workspace.tsx`), or axe fails on mobile (`scrollable-region-focusable`).
- Browser specs should wait for a screen's own loading text to disappear with a longer timeout and
  throw the refusal text, instead of timing out on the final line.
- `asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)` for psycopg async in sync tests on Windows.
- Repository tests: `test_migration_files` wants literal `alter table … enable/force row level security`;
  `test_delegation_contracts` — delegated routes are exactly the booking workspace (no delegation on new
  routes); `test_location_access` re-creates policies from each migration's marked tail; the upgrade
  tests' table lists (`test_inventory_upgrade.py`, `test_stock_upgrade.py`) need new tables;
  `test_h3_upgrade.copy_fixture_data` needs rules for older target versions.
- Group by the whole key `(tenant_id, id)`; ids are uuid7, so `order by id` is creation order.
- The static phase builds `web/out` and runs the web unit specs; run `npx prettier --write` on every new
  web file (a missed spec failed static once). Playwright clears `web/test-results` on every run.
- Run mypy over `src` **and** tests before the gates.

## 8. Open items and known flakes

- Two load-only flakes, causes **not proven**: `test_h4_browser` (finance, mobile) once under the full
  suite; the L7b2a "Paid 50.00 of 50.00" line once in a slow run. Both passed alone repeatedly. If one
  returns, keep its page snapshot (see the snapshots session above) and diagnose before rerunning.
- A credited (prepaid) visit's commission is accrued by hand (L5); automatic reversal on refund is a
  later decision.
- `main` needs the chain merged (owner's word) to carry Next.js 16.4.2.
