# Handoff — package R, slice R9 in progress (acceptance of RENT-01); how to work on the server (2026-11-13)

This file replaces [NEXT_AGENT_PACKAGE_R9_2026-11-12.md](NEXT_AGENT_PACKAGE_R9_2026-11-12.md). Read it whole before
doing anything. The ready-to-paste prompt is
[NEXT_AGENT_PACKAGE_R9_PROMPT_2026-11-13.md](NEXT_AGENT_PACKAGE_R9_PROMPT_2026-11-13.md).

## 0. In one paragraph

GORGONA is one business platform for **all 39 directions of the master plan, launched together**; never plan or
estimate a one-industry launch. Package R (rental, RENT-01, master plan stage 4) is build order. R1..R8c are done and
pushed (each with design, failing tests first, VM gates, a source-bound record, a code commit, a docs commit and a push
for CI without a PR). **R9, the acceptance of RENT-01, is in progress on the VM**:
- the design is committed (`a323b58`);
- a real defect of R-09 was found (staff can record the answer source `platform`);
- the failing tests are written and red-1 failed as intended;
- the code fix, the gates, the record and the commits are next.

**All work happens on the server (the VM `gorgona-dev`), not on the laptop.**

## 1. The owner and their words (verbatim where it matters)

- Write to the owner in **Russian, simply**, short sentences, numbers exact; the owner is **they/them**. Report
  PASS / FAIL / BLOCKED / NOT TESTED with exact numbers. Hide no failure: «Не скрывай ни одного сбоя».
- Full delegation of packages O and R: «Делай как считаешь нужным я доверяю тебе». It covers designing, building and
  pushing each slice branch for CI **without a PR**. Nothing else.
- 2026-11-13: «Нет, мы работаем на сервере. Мы не работаем локально.» Edits, runs, the record, the commits and the
  push all happen on the VM. The laptop only runs `gcloud`, `ssh`, `scp` and `curl`.
- 2026-11-13: «Готовь, пожалуйста, хенд-офф и полную инструкцию следующему агенту…» — this file.
- Hard rules (no exception without the owner's separate direct word):
  «никаких PR, merge, изменений в main, readiness, включения transport, деплоя или боевых провайдеров без отдельного
  прямого слова владельца». The same holds for enabling rental or construction, Azure and any production migration.
- No rebase, amend, reset, clean, force-push, CodeRabbit or bare `git stash`.
- Stripe sandbox only; never enter or print a secret.
- An independent review (one extra read-only agent) only with the owner's consent; **for R9 it has not been asked yet.**
- Extra agents of any kind only with the owner's consent.

## 2. Working on the server — the full how-to

### 2.1 The machine

- Google Cloud VM `gorgona-dev`, project `gorgona-one-ai`, zone `us-central1-a`: 8 CPUs, 31 GB RAM, 145 GB disk
  (6 % used on 2026-11-13).
- **Each start has needed the owner's word.** On 2026-11-13 the owner said work is on the server; if the VM is stopped
  when you begin, ask once in one short Russian sentence, and write the word into the run's `STATE.md`.
- Start it and read the IP from the laptop (Git Bash). **Every start gives a new external IP.**

  ```bash
  gcloud compute instances start gorgona-dev --zone us-central1-a --project gorgona-one-ai
  gcloud compute instances describe gorgona-dev --zone us-central1-a --project gorgona-one-ai --format="value(status,networkInterfaces[0].accessConfigs[0].natIP)"
  ```

- SSH needs the alias `gorgona-dev` from the laptop's `~/.ssh/config`, the new IP and the stored host key:
  `ssh -o HostName=<IP> -o HostKeyAlias=34.30.251.0 gorgona-dev '<command>'`. The host key has never changed. If it
  does, stop and tell the owner.
- Right after a start, sshd needs about a minute. Add `-o ConnectionAttempts=90 -o ConnectTimeout=10` to the first
  call instead of sleeping.
- **An idle cron stops the VM after 60 minutes without an SSH session.** Keep one open in the background for the
  whole work, and start it again whenever it ends:

  ```bash
  ssh -o HostName=<IP> -o HostKeyAlias=34.30.251.0 -o ServerAliveInterval=60 gorgona-dev "sleep 14400"
  ```

- Copy results back before the VM can stop. In R8c it stopped after the gates, and starting it again just to copy the
  results needed a second word from the owner. Since 2026-11-13 the record is written on the VM, so nothing needs
  copying to the laptop.
- Last IP: `35.192.116.237` (started 2026-11-13).

### 2.2 What is on the VM

| Item | Where |
|---|---|
| Repository | `~/gorgona`, remote `origin` = `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`; fetch over https; **push over SSH with the deploy key** `~/.ssh/github_gorgona` (works, checked 2026-11-13) |
| Git author | repo config `user.name Alex`, `user.email` as in the whole history (already set) |
| Python | `~/gorgona/api/.venv/bin/python`; `ruff` and `mypy` in the same `.venv/bin` |
| Node | `/usr/bin/node`, `/usr/bin/npm`; `~/gorgona/web/node_modules` installed; `npx prettier` works |
| PostgreSQL 18 | `/usr/lib/postgresql/18/bin` (a disposable cluster per run, made by `runner.py`) |
| Run folders | `~/gba-runs/<package>-<date>-<design sha>/` (R1..R8c, R9) |
| `gh` | installed, **not logged in**; do not log in. Read CI with `curl` (2.6) |

### 2.3 Editing files on the VM

- Short plain text: from Git Bash, `ssh … 'cat > ~/gorgona/<path>' <<'EOF' … EOF` (the R9 design was written so).
- Long files or code with many quotes: the heredoc broke once in the tool ("unexpected EOF while looking for matching
  quote"). Instead:
  1. write the file in the session scratchpad (a transport copy only, never run anything locally);
  2. `scp -o HostName=<IP> -o HostKeyAlias=34.30.251.0 <file> gorgona-dev:<path>`;
  3. compare `sha256sum` on both sides.
- Edits to existing files: a small Python patch script with exact anchors (`assert text.count(anchor) == 1`), copied
  by `scp` into the run folder and run there with `python3`. Example: `~/gba-runs/package-r9-20261113-a323b58/patch_tests.py`.
- Lint on the VM before any run:

  ```bash
  cd ~/gorgona/api && .venv/bin/ruff check <files> && .venv/bin/ruff format --check <files> && .venv/bin/mypy <files>
  cd ~/gorgona/web && npx prettier --check <files>
  ```

  Python lines are at most 100 characters (E501 also counts docstrings).

### 2.4 The laptop's hook (GateGuard)

In this desktop setup the first Bash call of each turn and the first Write/Edit of each file are refused once. State
the facts it asks for, then retry the same call:
- the request in one sentence and the user's words verbatim;
- what the command does;
- who calls or imports the file.

For a new file, a one-line placeholder first, then the real content, works.

### 2.5 Running tests on the VM (the harness)

- `runner.py <phase> <static|focused|full> [pytest files]`, started in `~/gorgona` with `GBA_ROOT=~/gorgona`:
  - one executor and one disposable PostgreSQL 18 cluster per phase;
  - it never uses the forbidden ports 51454, 51458, 51474, 51511 and 49981;
  - it writes `<phase>/results.json` and logs, and checks that sources and the built site did not change during the
    run;
  - `static` runs the web lint, typecheck, unit tests and **build** (browser tests use the built `web/out`, so rebuild
    with a static phase after any web change).
- `run_gates.py N` runs `static-N`, then `focused-N` (a list written in the script), then `full-N`. It never advances
  after a failure. Start it with nohup so an SSH drop cannot kill it:

  ```bash
  R=~/gba-runs/package-r9-20261113-a323b58
  cd ~/gorgona && (GBA_ROOT=~/gorgona nohup api/.venv/bin/python $R/run_gates.py 1 > $R/gates-1.out 2>&1; echo exit=$? > $R/gates-1.done) > /dev/null 2>&1 &
  ```

  Timing on the VM for R8c: focused about 32 minutes (1101 tests) and full about 65 minutes (2845 passed,
  4 skipped). Watch `gates-1.out` and `gates-1.done`; the last line of a pass is `GATE PASS full-1`.
- **No edits to `api/`, `web/` or `docs/runbooks/` while a run executes** (the runner would fail on changed sources,
  and the evidence would be void).
- A race test needs an observed `pg_locks` wait. Failing tests come first: red-1 runs before any code.
- The 4 skipped tests need outside services and are named in every CHECKS.json.

### 2.6 Git, push and CI (from the VM)

- Branch per slice from the previous slice's docs commit, named `codex/package-<slice>-<topic>`.
- Two commits per slice after the gates:
  - **code** (sources and tests only), message `feat(rental): …`;
  - **docs** (design PASS line, `GORGONA_IMPLEMENTATION_STATUS.md` and `GORGONA_MASTER_PLAN.md` checkpoints,
    evidence, next handoff), message `docs(plan): … accepted … PASS; … handoff`.

  Every message ends with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Push the branch for CI only: `git push origin <branch>`. Never open a PR. Never touch `main` (still `590a8f3`).
- Read CI without signing in (the repository is readable anonymously):

  ```bash
  curl -s "https://api.github.com/repos/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs?branch=<branch>&per_page=3" | python3 -c "import json,sys; [print(r['id'], r['head_sha'][:7], r['status'], r['conclusion']) for r in json.load(sys.stdin)['workflow_runs']]"
  ```

  A failed run's annotations are readable the same way (`/check-runs/<id>/annotations`). A rerun needs GitHub
  credentials, which are not on the VM: when a browser check fails with no web change, say so in the record (R5a,
  R5b and R8a did) instead of rerunning.
- `CLOUD_CODE_HANDOFF.md` at the repository root stopped at N8 (2026-10-30). The live checkpoints are the tops of
  `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md` and `docs/plan/GORGONA_MASTER_PLAN.md` ("Current", "Previous",
  "Earlier" checkpoint sections; rotate them, as `r8c-record/r8c_docs.py` did).

### 2.7 The laptop (only for reference)

- The old worktree `C:/Users/alexa/.codex/worktrees/package-o5/Gorgona Booking` is at `7eafa7b` (R8c docs) with an
  untracked `.claude/`. Do not work there any more; leave `.claude/` alone.
- Never touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.
- Never touch the worktree `package-l7b2b`: another session uses it (branch `codex/a11y-table-regions`).
- The old local run folders are under `C:/Users/alexa/AppData/Local/GorgonaBookingTests/`. Files written there
  physically sit in `Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/`. The evidence of R1..R8c names those paths.

## 3. State on 2026-11-13

| Slice | Branch | Design | Code | Docs | Migration | Full suite | CI |
|---|---|---|---|---|---|---|---|
| R1 | `codex/package-r1-rental-catalog` | `889c69a` | `15a884d` | `101e3ad` | 0096 | 2756 passed | 41590287564 success |
| R2 | `codex/package-r2-rental-bookings` | `d423d7e` | `e34ac3f` | `e96e8fc` | 0097 | 2763 passed | 41606651336 success |
| R3a | `codex/package-r3-rental-assignment` | `ce29972` | `ab98936` | `cf9ff3f` | 0098 | 2771 passed | 41627679283 success |
| R3b | `codex/package-r3b-rental-blocks` | `427b8f0` | `b5cff95` | `90fb28f` | 0099 | 2777 passed | 41708625225 success |
| R4a | `codex/package-r4a-rental-rates` | `281d3f6` | `79d678f` | `4902f23` | 0100 | 2787 passed | 41900546592 success |
| R4b | `codex/package-r4b-rental-agreements` | `7e793ea` | `a098477` | `86d2cad` | 0101 | 2793 passed | 42291512691 success |
| R4c | `codex/package-r4c-rental-extensions` | `0cb38f2` | `c38efe8` | `63b2318` | 0102 | 2799 passed | 42394185544 success |
| R5a | `codex/package-r5a-rental-security` | `5d25694` | `ffe05b8` | `7129d83` | 0103 | 2805 passed | 42404010560 failed: flaky `visit-desk.spec.ts:65`, no web change |
| R5b | `codex/package-r5b-rental-provider-holds` | `58391fd` | `e4efe63` | `fc1c378` | 0104 | 2811 passed | 42413235532 failed: flaky `service-catalog.spec.ts:137`, no web change |
| R6a | `codex/package-r6a-rental-inspections` | `7d5dec6` | `78db1a8` | `18470ae` | 0105 | 2818 passed | 42426865948 success (contains R5a, R5b) |
| R6b | `codex/package-r6b-rental-usage` | `af3f01f` | `010692f` | `0432c98` | none | 2828 passed | 42438106172 success |
| R7a | `codex/package-r7a-rental-settlement` | `5f968b9` | `31cf73d` | `2ef404e` | 0106 | 2834 passed | 42449693704 success |
| R7b | `codex/package-r7b-rental-damage-refunds` | `0453d6a`, `00c7dc0` | `b174d1b` | `6f20a26` | 0107 | 2839 passed | 42511820796 success |
| R7c | `codex/package-r7c-rental-reconciliation` | `c16edcf` | `6876fee` | `a2bfc54` | none | 2842 passed | 42558093855 success |
| R8a | `codex/package-r8a-rental-screens` | `eef91e1` | `06b3c25` | `454c70f` | none | 2843 passed | 43058107935 failed (browser install); rerun 43061387414 success |
| R8b | `codex/package-r8b-rental-agreement-screens` | `bf5dd55` | `b3528b8` | `977a96f` | none | 2844 passed | 43128481780 success |
| R8c | `codex/package-r8c-rental-settlement-screens` | `bc54650` | `c45d3da` | `7eafa7b` | none | 2845 passed | 43368792577 success |
| **R9** | `codex/package-r9-rental-acceptance` (on the VM; pushed with this handoff) | `a323b58` | — | — | none | — | — |

- Every full suite: 4 skipped.
- **Next migration: 0108.** Migrations 0001..0107 are immutable.
- Each slice's acceptance table is in its design file `docs/plan/PACKAGE_R*_DESIGN_*.md`, and each record is
  `docs/plan/evidence/<date>-r*/CHECKS.json`.
- The VM's `~/gorgona` is on `codex/package-r9-rental-acceptance` at this handoff commit, with two **uncommitted**
  test files (2.2 above; checksums in 4.2).
- **Construction:** there is no O8 (acceptance of BUILD-01) on GitHub or in any history, though an earlier note said
  "O done through O8". BUILD-01 acceptance is still open. Say so if the owner asks.

## 4. R9 — what is done and the exact next steps

Design: [PACKAGE_R9_DESIGN_2026-11-13.md](PACKAGE_R9_DESIGN_2026-11-13.md). Run folder on the VM:
`~/gba-runs/package-r9-20261113-a323b58` (`STATE.md` is the log; keep adding one line per step).

### 4.1 The defect found (R-09)

- `AcceptInput.source` in `api/src/gorgona_booking/business/rental_agreements.py:60` is
  `Literal["platform", "paper", "email"]`. `ChangeInput` and the period change's `PeriodInput`
  (`rental_extensions.py`) inherit it.
- The screen `web/components/rental-agreement.tsx:465` offers "Platform".
- No customer answers on the platform yet (that needs a grant, plan decision 9), so staff can record a platform answer
  that never happened.
- Construction refuses the same source in the API (`construction_contracts.py:73`: `Source = Literal["paper",
  "email"]`) and keeps `platform` allowed in the database for the future grant path (0094:
  `check (source in ('platform', 'paper', 'email'))`).
- The model for that future path is transport N4 (0084): `platform` is allowed only together with the company that
  answered through its grant (`(source = 'platform') = (servicer_business_id is not null)`).

### 4.2 Done

1. Design commit `a323b58`.
2. Tests (uncommitted in `~/gorgona`; copies in `$R/wip/`, checksums in `$R/wip/sha256.txt`):
   - `api/tests/integration/test_r9_rental_acceptance.py` (new; sha256 `ca51ed30…`): one end-to-end test of a whole
     rental, commented per R-row; ruff, format and mypy clean.
   - `web/tests/rental-agreement.spec.ts` (modified; sha256 `7c662885…`): the Source options are exactly Paper and
     Email.
3. red-1 (focused: the R9 test and `test_r8b_rental_agreement_browser.py`): 2 failed as intended in 28.5 s:
   - `assert 200 == 422` (the platform source was accepted);
   - `toHaveText` failed (three options).

   **Everything after the platform refusal in the R9 test has never run.** Expect test-data slips there; fix the test
   data, never the expectations of RENT-01, and record each slip.

### 4.3 Next steps, in order

1. **Code fix.** Use a patch script on the VM with exact anchors:
   - `rental_agreements.py:60` → `source: Literal["paper", "email"]`, with a comment: `platform` is reserved for a
     customer's own answer through a grant (plan decision 9, not built), as construction O2/O6a; the database check
     keeps it.
   - `web/lib/rental-api.ts:206` → `source: "paper" | "email";`
   - `web/components/rental-agreement.tsx`: the state type at line 381 and the cast at line 462 become
     `"paper" | "email"`; remove `<option value="platform">Platform</option>` (line 465).
   - Keep `web/lib/rental-contracts.ts:180` (the view may read the reserved value).
   - Check that no other test sends `"platform"` to rental. `test_o2` and `test_o6a` send it to construction and must
     keep passing.
2. **dev-1** `static` (rebuilds `web/out`; required steps must pass; `web-audit-all` of development dependencies is not
   required and exits 1).
3. **dev-2** `focused`: `test_r9_rental_acceptance.py`, `test_r8b_rental_agreement_browser.py`,
   `test_r4b_rental_agreements.py`, `test_r4c_rental_extensions.py`. Repeat as dev-3 and so on after each fix, writing
   every failure into `STATE.md`.
4. **Gates.** Add `'tests/integration/test_r9_rental_acceptance.py',` at the top of the focused list in
   `$R/run_gates.py`, then start gates-1 with nohup (2.5). Expected full: **2846 passed, 4 skipped**.
5. **Record (on the VM).**
   - Adapt `$R/r8c-record/write_record.py` into `$R/write_record.py`, the way `adapt_r8c_record.py` adapted R8b's
     (that adapter reads a Windows path; point it at `$R/r8c-record/write_record.py`). Change:
     - `ROOT = Path.home() / 'gorgona'`;
     - `BASE = 'a323b58'`;
     - `BRANCH = 'codex/package-r9-rental-acceptance'`;
     - `EVIDENCE = ROOT / 'docs/plan/evidence/2026-11-13-r9-acceptance'`;
     - `SOURCES` = the five changed files (`rental_agreements.py`, `test_r9_rental_acceptance.py`,
       `rental-agreement.tsx`, `rental-api.ts`, `rental-agreement.spec.ts`), also listed in `$R/sources.txt`;
     - `NEW_MODULES = ('tests.integration.test_r9_rental_acceptance',)`, `NEW_CASES = 1`;
     - `REQUIRED` gets `tests.integration.test_r9_rental_acceptance.test_a_whole_rental_keeps_rent_01`;
     - `REGRESSION` gets `tests.integration.test_r8c_rental_settlement_browser`;
     - `ARCHITECTURE` names the owner's words of 2026-11-13, the VM and the IP;
     - `FAILURES` holds red-1, every dev run and every slip;
     - `REMAINING` holds the open review, readiness on the owner's word and the limits of section 5.
   - Run `api/.venv/bin/python $R/write_record.py 1`. It refuses if a source changed after the gates.
6. **Code commit:** the five files only, for example `feat(rental): R9 agreement source paper or email (R-09); RENT-01
   end-to-end acceptance test (package R)` with the trailer.
7. **Docs commit:**
   - the R9 design's acceptance section → `PASS <date> (code <sha>, evidence)` with each R9-0x row PASS;
   - `docs/plan/evidence/2026-11-13-r9-acceptance/CHECKS.json` (from `write_record.py`) and `ACCEPTANCE.md` (from the
     draft in section 5, in the style of `docs/plan/evidence/2026-10-29-n7-acceptance/ACCEPTANCE.md`);
   - rotated checkpoints in `GORGONA_IMPLEMENTATION_STATUS.md` and `GORGONA_MASTER_PLAN.md` (`$R/r8c-record/r8c_docs.py`
     is the R8c example);
   - the next handoff.
8. **Push** `codex/package-r9-rental-acceptance`, read CI (2.6), add the CI line to `STATE.md`.
9. **Report to the owner in Russian:**
   - what R9 found and fixed;
   - the numbers;
   - CI;
   - that rental is technically accepted on the VM with R-09 partial and the review open;
   - ask for consent to the one independent review of package R (one read-only agent), then fix what it finds (as N8
     did for package N);
   - readiness of rental and `main` only on their word.

## 5. Draft of ACCEPTANCE.md (check every claim against the design files before writing it)

RENT-01: "A class booking is separate from the assignment of a unit; a double issue is impossible; the payment
security, damage and refund are recorded separately." Proofs: R-02 and R-03 for the first two parts, R-05 and R-07 for
the last; R9 shows all three in one rental.

| id | Proof | Limit or gap |
|---|---|---|
| R-01 | R1-01 implemented and not enableable (`MODULE_NOT_READY`); every slice: module off writes nothing (`MODULE_DISABLED`), branch scope and another company refused, direct SQL updates and deletes refused (`InsufficientPrivilege`), forged rows refused by named checks; R9 end to end | Tests switch the module on only through the `accepted` fixture; the registry stays `implemented` |
| R-02 | R2-01..R2-05 (R2-04 racing bookings for the last unit leave one after an observed `pg_locks` wait); R8a browser; R9: two bookings take both cars, a third is `RENTAL_UNAVAILABLE`, no unit hold before an assignment | — |
| R-03 | R3a-02..R3a-05 (database exclusion; racing assignments leave one after an observed wait; replacement releases and keeps history); R3b-01..R3b-04 (blocks never overlap an assignment, counted in availability); R9: `RENTAL_UNIT_BUSY` for a second booking, a block refuses an extension | Check in the R3b design how moves between branches work; plan decision 7 says in transit, R3b-03 describes a move without a hold. State the truth |
| R-04 | R4a-01..R4a-04 versioned cards, quote from the card in force; R4b-01..R4b-04 frozen agreement with source, who and when; R4c-01..R4c-04 extensions as versions checked against occupancy; R9: a later card version leaves the agreement, an extension into a block is refused, a fitting one is version 2 | Extensions and extras are API-only (not on screen) |
| R-05 | R5a-01..R5a-04 states, capture in parts with a basis and `rental.approve`, one release or expiry; R5b sandbox provider receipts; R7b-03 charges leave the security; R9: capture without a basis 422, the settlement leaves the security, a second release refused | Sandbox only; no live card holds |
| R-06 | R6a-01..R6a-04 meters, levels, marks with photos (PNG or JPEG document versions); R6b-01..R6b-04 overdue and excess derived; R8c browser; R9: a distance of 500 against 300 allowed, 2 started hours late | Photos on marks are API-only; check plan decision 6 (checklist items, fuel) against R6a and state what is not built |
| R-07 | R7b-01..R7b-04 damage charge on new return marks needs `rental.approve`, refunds are their own records within the ceiling; R8c browser; R9: front desk 403, an old mark refused, the settlement unchanged | No built-in role has `rental.manage` without `rental.approve`; the refusal is shown with a member without rental rights |
| R-08 | R7a-01..R7a-04 one receivable draft from frozen terms (rental, excess, late); R7c-01..R7c-04 the reconciliation derives documents, refunds, security and totals; R9: 150.00 + 50.00 + 6.00 = 206.00, damage 80.00, refunded 10.00, totals equal | Check plan decision 8 (fuel, extras) against R7a and state what is not charged; FIN-03 documents are issued and paid on FIN-03 screens |
| R-09 | R4b source, who and when recorded; **R9 fix**: `platform` refused on acceptance, change and period change, the screen offers Paper and Email | **PARTIAL**: a customer's own answer through a grant is not built (as construction) |
| R-10 | R8a, R8b and R8c real browser desktop and mobile through the management login, axe clean, no horizontal scroll; R8a cancels a booking by keyboard (Enter); the full suite green in every slice | No full keyboard-only walk of the rental screens |

Verdict to expect: technically accepted on the VM, **without** the independent review (open), R-09 partial. This does
not change readiness, does not make rental enableable and does not touch `main`.

## 6. Traps and lessons (all happened)

- **Time zones in test data:** a booking that crosses a daylight-saving change counts an extra rental day (R8c mobile,
  2031-11-02 in America/New_York). Keep test periods away from DST changes; the API tests use June 2031 in UTC.
- **Late returns in tests** are made by moving the recorded return as the owner (`returned_at` in
  `test_r6b_rental_usage.py`); the API records the real time.
- **The first booking period** lives on `rental_bookings`; `rental_booking_periods` starts at sequence 2 with the
  first extension.
- **Availability** is the peak, at each instant, of overlapping bookings plus active blocks (`gba.rental_booking_peak`,
  0102). An extension inserts the new period, releases the old assignment and inserts a new one. Exclusion on the
  unit's resource gives `RENTAL_UNIT_BUSY`; the deferred availability check gives `RENTAL_UNAVAILABLE`.
- **Writing a migration before red-1** happened once (O5); it was moved aside for an honest red-1 and recorded.
- **The VM stopped idle** after the R8c gates before the copy-back; keep the SSH session open.
- **Windows-only details** (`tar --force-local`, Windows paths in record scripts) no longer apply on the VM. Adapt
  any script you bring over.
- **Browser checks fail now and then** and pass alone: `test_i4_browser`, `test_l7b_visit_desk_browser`,
  `service-catalog.spec.ts:137`, `visit-desk.spec.ts:65`. Name them in the record, never retry silently.

## 7. After R9

- The owner decides: the one independent review of package R, then the fixes; then readiness of rental and `main`.
- The next package in the master plan is PROPERTY-01 (real estate, §9.2). Its plan is not written; write it like
  `PACKAGE_RENT_PLAN_2026-11-03.md` and give the decisions to the owner.
- BUILD-01 (construction) acceptance is still open (section 3).
