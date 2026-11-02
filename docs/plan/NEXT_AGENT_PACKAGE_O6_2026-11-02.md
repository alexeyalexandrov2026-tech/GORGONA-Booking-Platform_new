# Handoff — package O (construction, BUILD-01) after O5; next is O6 (2026-11-02)

Written by the agent that built O3b-O5. Read this whole file before any action.

## 1. Where things stand

Production remains **one common launch of all 39 directions** (master plan top block, §13). Package O
is stage 4 build order for the construction direction, not a separate launch. The owner delegated
package O fully («Делай как считаешь нужным я доверяю тебе») and then said "continue" for each slice.
That delegation covers designing, building and pushing each slice branch **for CI only, without a PR**.
It does not cover PRs, merges, `main`, readiness or enabling modules.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| O3b actual costs | `codex/package-o3b-costs` | `e02025e` | `c464df9` | `9557ae2` | 0090 | run 41288503088 success |
| O4a schedule, daily reports, completed quantities | `codex/package-o4a-execution` | `aa20810` | `6afdbd7` | `852c117` | 0091 | run 41313515832 success |
| O4b inspections, defects, punch list | `codex/package-o4b-quality` | `5864c85` | `6b6124f` | `88cf16e` | 0092 | run 41333075606 success |
| O5 pay applications with retainage | `codex/package-o5-pay-applications` | `67a6bed` | `11a5508` | the docs commit with this file | 0093 | pushed for CI with this commit; check it first |

Each slice branch starts from the previous slice's docs commit, so the O5 branch holds everything.
`main` is `590a8f3` (package M review fixes); the O5 branch is about 45 commits ahead of it
(packages N and O). **Never** merge, fast-forward or open a PR without the owner's direct word.

Readiness registry: `construction` is implemented and **not enableable**; BUILD-01 is not accepted.
Tests use an `accepted` fixture that patches the registry in memory only.

Next migration: **0094**. Migrations 0001-0093 are immutable (the record checks their bytes).

## 2. Worktrees — important

- **Use** `C:/Users/alexa/.codex/worktrees/package-o5/Gorgona Booking` (branch
  `codex/package-o5-pay-applications`). Its `web/node_modules` came from `npm ci` on 2026-11-01. npm
  printed an `allow-scripts` warning, but the web build and every browser test passed.
- **Do not touch** `C:/Users/alexa/.codex/worktrees/package-l7b2b/Gorgona Booking`. A separate session
  the owner started (task "Make scrollable management tables keyboard-reachable") switched it to branch
  `codex/a11y-table-regions` and edits `web/` there. Ask the owner before using it.
- Python tools come from `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking/api/.venv/Scripts`
  (`python.exe`, `ruff.exe`, `mypy.exe`). Use only those executables from that checkout; touch nothing
  else there.
- Never touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.
- For a new slice, create a branch in the O5 worktree from the O5 docs commit:
  `git switch -c codex/package-o6-acceptance`. A new worktree is fine if the O5 one is busy.

## 3. How each slice is done (the process the record checks)

1. Design document `docs/plan/PACKAGE_O6_DESIGN_<date>.md`, with decisions and an acceptance table
   marked NOT TESTED. Commit it; it becomes `BASE`.
2. **Failing tests first**: new test file(s) plus an upgrade test (copy the latest `test_o5_upgrade.py`
   and move the numbers up by one). Add the new tables to `test_inventory_upgrade.py` and
   `test_stock_upgrade.py`, and `(94, "-- Construction branch scope:")` to `test_location_access.py`.
   Run red-1 **before writing any code**. In O5 I wrote the migration first and had to move it aside
   for an honest red-1; that is recorded as a slip. Do not repeat it.
3. Code: migration (insert-only tables, guards that raise `check_violation` with a named constraint,
   module gate, RLS and tenant policies, select and insert grants only, and the
   `-- Construction branch scope:` section **last**), service in `business/`, routes in
   `api/construction.py`. Run ruff, format and mypy on `src` and `tests`.
4. dev-1: the new tests plus every construction test, `test_location_access.py`,
   `test_roles_and_migrations.py`, and any module you touch (for example `test_m7a_transport_money.py`
   when touching FIN-03).
5. Final gates: `run_gates.py N` runs static, then focused, then full (about 1 to 1.5 hours). Start
   `disk_monitor.ps1 N` beside it; it now writes UTC.
6. Record: `adapt_<slice>_record.py "<final gates text>" "<extra FAILURES lines>"` writes
   `write_record.py`; then run `write_record.py N`. It writes `docs/plan/evidence/<date>-<slice>/CHECKS.json`.
7. Code commit (exact api/ files), then a docs commit (acceptance PASS, the "Current checkpoint" in
   `GORGONA_IMPLEMENTATION_STATUS.md` and `GORGONA_MASTER_PLAN.md`, the evidence). Push the branch for
   CI, no PR. Watch CI with curl on
   `https://api.github.com/repos/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs?branch=<branch>`
   (the `gh` CLI is not on the Bash PATH). Write the result to `ci-<slice>.txt` in the run folder.

Run folders sit under `C:/Users/alexa/AppData/Local/GorgonaBookingTests/`. Physically they are in
`.../Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/`. The latest is
`package-o5-20261101-67a6bed`: copy `runner.py`, `run_gates.py`, `disk_monitor.ps1` and
`adapt_o5_record.py` from it. In `runner.py`, set `ROOT` to the worktree you use. In `run_gates.py`, add
the new test files to the focused list. `runner.py <phase> focused <files>` runs one disposable
PostgreSQL 18 cluster on a free port and redacts the logs. Keep `STATE.md` in the run folder, one line
per step, with every slip.

## 4. Next: O6 (plan decisions 9-10, acceptance O-08 and BUILD-01)

Plan text: stage and final acceptance are recorded facts (who, source, time) on a phase or on the
project. A phase's acceptance is required before its retainage is released. Final acceptance closes
billing except the retainage release and starts the **warranty period** (dates on the contract).
Warranty claims are items with states, and their repair cost links to actual costs. The
**reconciliation view** shows per project: contract sum, budget, committed, actual, completed value,
billed, retained, released, paid (from FIN-03) and the differences, all derived.

What O6 builds on:

- Retainage held = the receivable manual accruals that pay applications drafted
  (`construction_pay_applications.retainage_document_id`, no due date; `retained_minor` per
  application). FIN-03 cannot know about "release". O6 must decide whether release is only a
  construction fact that the reconciliation view reports, or whether collection must be blocked until
  release. FIN-03 settlements cannot be gated per obligation today; check `settlements.py` before
  promising a block.
- O4b deferred one question to O6: whether open punch or defect items block a stage acceptance. The
  item list (`GET quality-items`) has a summary per phase and kind for this.
- Plan decision 11: a customer answers on the platform only through a grant, as carriers do in
  package N. Otherwise the business records the answer with its source (paper, email). O2 used
  `construction.approve` for the customer's acceptance; reuse it.
- Warranty repair cost: O3b actual cost links (`construction_cost_links`) already link STOCK-01,
  FIN-03 payables and WORK-01 time to budget lines. A warranty claim may need its own link target.
- Reconciliation: budget, committed and actual come from O3a/O3b (`construction_budget.py`); completed
  value from O4a (`construction_progress.load_progress`); billed, retained and due from O5
  (`construction_billing.list_applications`); paid from FIN-03 obligations (`settlements.load_obligation`).

Consider splitting O6 like O3 and O4. One option: O6a acceptance plus retainage release; O6b warranty
plus reconciliation. Then O7 (screens, real browser desktop and mobile, axe) and O8 (BUILD-01 and
O-01..O-10 acceptance; an independent review **only with the owner's consent**; readiness only on the
owner's word).

## 5. Hard rules

- No PR, merge, change to `main`, readiness, enabling transport or construction, deploy, Azure,
  production migration or live provider without the owner's separate direct word. Stripe is sandbox
  only. Never enter or print secrets.
- No rebase, amend, reset, clean, force-push, CodeRabbit or bare `git stash`.
- One executor and one disposable PostgreSQL 18 cluster per run. Never use ports 51454, 51458, 51474,
  51511 or 49981. A race test only with an observed `pg_locks` wait (the `race` helper in
  `test_l8b2_finance_races.py`).
- Failing tests first. «Не скрывай ни одного сбоя»: every slip goes into `STATE.md` and the record's
  `FAILURES`.
- Do not edit `api/`, `web/` or `docs/runbooks/` while a test run is executing. Rebuild the web static
  export after any web change.
- Extra agents only with the owner's consent. Do not delete files you do not own (the
  `miami-elio-*` and `DiagOutputDir` Temp folders belong to another project).
- Commit trailer: `Co-Authored-By: <model name> <noreply@anthropic.com>`.
- Write to the owner in Russian, simply. The owner is they/them.

## 6. Known issues and traps

- **Disk:** C: has had between 3.4 and 31 GB free. O3b's full suite once failed with DiskFull. Always
  run `disk_monitor.ps1` beside the gates. The owner's earlier choice authorised cleaning only the npm
  and uv caches.
- **Flaky under load** (passes alone; record it, rerun it alone as dev-N, then rerun the gates):
  - `test_i4_browser`;
  - stock-documents pagination;
  - `test_l7b_visit_desk_browser` mobile axe `scrollable-region-focusable`. This one is also a real
    accessibility gap in older `.mgmt-table-container` tables, which the a11y task above is fixing.
- **GateGuard hook:**
  - the first Write or Edit of every file is refused once: state the facts and retry (writing a
    one-line placeholder first works);
  - the first Bash command of each turn may also be refused: state the request and what the command
    does, then retry.
- Windows paths inside regex substitutions in the record adapters break easily. Use plain string
  replacement for paths.
- FIN-03 drafts created by a domain must be added to `financial_documents._linked_to_visit`, so FIN-03
  refuses to edit them.
- The O4a measurement guard and the change-order decision guard have each been replaced twice (0091,
  0093). If O6 must replace one again, copy the latest body from 0093 and keep every earlier check.
