# Next agent handoff — H3 settlement guards, 2026-10-07

Copyable prompt: [NEXT_AGENT_PROMPT_H3_GUARDS_2026-10-07.md](NEXT_AGENT_PROMPT_H3_GUARDS_2026-10-07.md).
Evidence: [validation](evidence/2026-10-07-h3-settlement-guards/VALIDATION.md).
Review that started this slice:
[independent H2 money/state review](evidence/2026-10-07-h2-settlements/INDEPENDENT_MONEY_STATE_REVIEW_e93ca5c.md).
Read [the H2 handoff](NEXT_AGENT_H2_2026-10-07.md) for everything not changed here.

## 1. State at handoff

| Item | Value |
|---|---|
| Repository | `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new` |
| Branch | `codex/package-h3-settlement-guards` |
| Checkout | `C:\Users\alexa\Documents\ChatGPT\gorgona-h3-guards` (a git worktree; the stash stack is shared with other worktrees) |
| Parent | published H2 head `e93ca5cae9400b7e9c2207089dda0ee101b7517d` (`codex/package-h2-settlements`, draft PR16) |
| Code commits | `24ee21bf1d141479af5e18c83fa42431a80d6d8b` (0025, service, guard, tests, docs) and `372da57e4a50bf97be13a533784e34c78e1ae509` (0026 self-review corrections). This handoff is a later docs-only commit; read the actual HEAD. |
| Pull request | [Draft PR17](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/17): base `codex/package-h2-settlements`, OPEN, DRAFT, unmerged. One owner comment describes `372da57`. |
| Stack | PR15 (H1) ← PR16 (H2) ← PR17 (H3 guards). Nothing is merged. |
| CI on `24ee21b` | `api` push run [37645658564](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37645658564) success; pull_request run [37649981128](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37649981128) success. |
| CI on `372da57` | push run [37654684082](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37654684082) success; pull_request run [37654689990](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37654689990) success. Test counts inside CI were not read (logs need an authenticated client). One annotation: Node 20 deprecation of `astral-sh/setup-uv@v6` in the workflow, unrelated. |
| Local evidence on the code of `372da57` | full suite with mandatory PostgreSQL and browser **1053 passed / 4 skipped / 429.52s**; ruff, format and strict mypy on 211 files PASS; web unchanged; upgrade 0024 → 0026 on a populated H2 database PASS. |
| Other trees | H2 checkout `C:\Users\alexa\Documents\ChatGPT\gorgona-h2-settlements` is clean at `e93ca5c`. Owner, E2, G, H1 and review worktrees were not touched. |
| Test cluster | private PostgreSQL 18.6 on `127.0.0.1:51470`, stopped. Clusters 51454, 51455, 51458, 51456, 51460 and 51462 were not touched. |

## 2. Authority

The owner gave this session full decision authority for the slice on
2026-10-07 and approved commit, push and one draft PR. Still **not authorized**:
merge or auto-merge, force-push, rebase or amend of published commits,
reset/clean, deployment, production migration, Azure/provider/funds/credentials
actions, FIN-03/FIN-02 readiness promotion. Keep all secrets outside Git and
output. Do not open a second PR for this slice; push to PR17's branch.

## 3. What the slice does

Forward migrations `0025_settlement_guards.sql` and
`0026_settlement_guard_corrections.sql` (both published in PR17 and now frozen)
plus `business/settlements.py` close the review's findings:

- **F1, one identity per external fact.** `gba.external_identity_key(value,
  rule)`: invisible (default-ignorable) code points removed first, then NFKC,
  Unicode lowercase via `pg_c_utf8`, NFKC again, ends trimmed. Interior
  whitespace follows the source's rule; `preserve` is the only rule (manual
  attestations have no provider contract) and an unknown rule raises
  `invalid_parameter_value`. Raw alias and reference are stored unchanged.
  Enforced under the ledger lock in `enforce_external_payment`
  (`unique_violation`) and first in the service
  (`FINANCIAL_SOURCE_ALREADY_RECORDED` with the existing `payment_id`).
- **F2, accounts.** A cash account is never an issued control account in the
  same book, in either order (payment trigger, document-version trigger,
  service).
- **F3, dates.** `entry_date` on or after `issued_on` of every allocated
  obligation (service 422 `LEDGER_DATE_INVALID`, SQL at commit).
  `actual_external_date` not after today in the business time zone:
  `gba.business_timezone(tenant)` returns, of the business's location zones,
  the one whose local date is the latest (ties by name); UTC only without any
  location. A location-scoped session sees fewer locations and can only get an
  earlier date. Service and trigger use the same SQL at the same transaction
  instant; the 422 carries `timezone` and `today`.
- **F4, readiness.** `financial_guard` approves column-level `references` and
  both new helpers (the latest packaged `create or replace` wins).
- The review's four test gaps (table-level FK drift, `opening` legacy entry,
  recovery while finance is OFF, settlement-row deletes) have tests.

## 4. How the work went (chronological)

1. Received the H2 handoff package (`GORGONA_ALL_DOCS_AND_HANDOFF_H2_2026-10-07.zip`;
   `Downloads.zip` was a byte-identical subset). Owner chose: verify H2
   delivery read-only, then review H2 money/state independently.
2. Verified PR16/H2 delivery state, then wrote the static review: no break of
   `P + C + R <= A`; F1 identity bypass by case/Unicode variants; F2 cash
   account equal to another obligation's control account (H and G balances
   drift); F3 payment posted before its accrual and future external dates; F4
   guard blind to column-level FKs; four test gaps.
3. Created the branch and checkout from `e93ca5c`. Red run of the new tests
   against unmodified source in a throwaway detached checkout: 6 failed / 12
   passed, each for the intended reason. Implemented `0025`, service and guard
   changes, tests. Full suite 1049 passed / 4 skipped.
4. Owner policy corrections: never remove all interior whitespace (rule made
   explicit and source-aware, conservative `preserve`); "today" from the
   business time zone, UTC only as a documented fallback, no global UTC+14.
   Boundary tests for midnight in UTC+14 and UTC−11, UTC rollover, legitimate
   local today, real future date. Full suite 1053 passed / 4 skipped.
5. Found that `0025` held 22 literal invisible characters instead of `\uXXXX`
   escapes (tool inputs decode JSON escapes). Rewrote it as pure ASCII and
   proved on PostgreSQL that both classes remove the same 4174 of all
   1,112,063 non-surrogate code points.
6. Upgrade check 0024 → 0025 on a database populated by H2's own suites.
7. Owner approved publication: commit `24ee21b`, push, draft PR17. `gh` is not
   installed; the GitKraken connector needs `gk auth login`; Claude in Chrome
   was not connected; the owner signed in to GitHub in the app's browser pane
   and the PR was created there as a draft. CI green.
8. High-effort self-review of the diff found five issues. Fixed two in forward
   `0026` (invisible characters were stripped after NFKC; several zones fell
   back to UTC), the third became fail-safe, two are documented follow-ups.
   Red on `24ee21b`, green with `0026`, full suite and upgrade 0024 → 0026
   again. Commit `372da57`, PR comment, CI green. Cluster stopped.

## 5. Next steps, in order

1. Read the actual HEAD, origin and PR17 state and the current-head CI; if a
   run failed, diagnose and report before changing source.
2. Independent review of `0025`, `0026` and the `confirm` changes by someone
   other than the author. CodeRabbit is installed on the repository but skips
   drafts; triggering it (`@coderabbitai review` on PR17) needs the owner's OK.
3. Owner decisions (validation file, "Decisions"): above all the
   latest-local-date rule for a business whose locations span time zones;
   interior whitespace `preserve`; look-alike punctuation not unified.
4. Not yet run: HawkScan (no `hawk` runtime or API key locally) and local Docker
   gates. Record exact CI test counts from an authenticated client.
5. Documented follow-ups, not urgent: the identity check is a linear scan under
   the ledger lock (an `IMMUTABLE` key plus a unique expression index and a
   guard extension would remove it); the guard's inline-FK pattern does not
   cover `alter table … add column … references` (extend it in the first
   migration that uses that form).
6. Merge order when the owner decides: PR15, then PR16, then PR17. Deploy the
   migrations together with the application: the H2 application fails closed
   against a `0025` database.
7. Then the rest of H3 on top of this branch (credits, refund obligations,
   guarded immutable corrections), as described in the H2 handoff, with new
   migrations from `0027`. `gba.obligation_balance` still returns
   `credited_minor = 0`; replace it in a new forward migration.

## 6. Environment and runbook

All paths are on the owner's Windows machine. Never print the DSN or password.

- Python 3.14 venv (editable source points to G; always set `PYTHONPATH`):
  `C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe`.
- PostgreSQL 18.6 binaries: `%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\pgsql\bin`.
- Private cluster: data `%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007\data`,
  port 51470, `max_connections=400`, superuser password in `pwfile` next to
  `data` (outside Git). Start without waiting on `pg_ctl` (it hangs under
  `Start-Process -Wait`):

  ```powershell
  $bin = "$env:LOCALAPPDATA\GorgonaBookingTests\postgres-18.6\pgsql\bin"
  $root = "$env:LOCALAPPDATA\GorgonaBookingTests\h3-guards-20261007"
  Start-Process -FilePath "$bin\pg_ctl.exe" -ArgumentList @('start','-D',"`"$root\data`"",'-l',"`"$root\server.log`"") -WindowStyle Hidden
  & "$bin\pg_isready.exe" -h 127.0.0.1 -p 51470   # repeat until accepting connections
  & "$bin\pg_ctl.exe" stop -D "$root\data" -m fast -w -t 60   # when done
  ```
- Test environment (from `api/`): `GBA_TEST_ADMIN_DSN` = superuser DSN of the
  private cluster built from `pwfile`; `PYTHONPATH=<checkout>\api\src`;
  `PYTHONDONTWRITEBYTECODE=1`; `GBA_REQUIRE_POSTGRES=1`; for the full suite
  also `GBA_REQUIRE_BROWSER=1` (needs the built `web/out` and Node 24 on
  `PATH`, `C:\Program Files\nodejs`). Run
  `python -m pytest -q -p no:cacheprovider --basetemp <short path under the cluster root>`.
  The handoff package's `tools/h3test.ps1` does exactly this.
- Affected suites: `tests/integration/test_external_payments.py`,
  `test_settlements.py`, `test_manual_accruals.py`, `test_invoice_issue.py`
  and `tests/unit` (633 passed). Full suite: no path arguments (1053/4).
- Static gates (from `api/`): `python -m ruff check --no-cache .`,
  `python -m ruff format --check --no-cache .`,
  `python -m mypy --no-incremental --cache-dir=nul .` (strict from pyproject).
- Web gates (from `web/`, only if web changes): `npm run typecheck`,
  `npm run lint`, `npm run format:check`, `npm run test:unit`, `npm run build`.
- Upgrade check: run the H2 checkout's finance suites with `GBA_TEST_KEEP_DB=1`
  (`tools/h2keep.ps1`), then `tools/upgrade_check.py guard|upgrade|drop` with
  `PYTHONPATH` pointing at the code under test. It resets the test roles'
  passwords to fresh random values, applies pending migrations as the owner
  role, compares every `gba` table's row count and content hash, reports rows
  that conflict with the new rules, stages rolled-back variant confirmations
  on the old data and runs the readiness guard.
- Red checks: `git worktree add --detach <short path> <old commit>`, copy the
  new test file in, run the selected tests, then `git worktree remove --force`.
  Use a short path such as `%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007\red2`
  (the scratchpad path is too long for Git).
- CI without `gh`: anonymous `https://api.github.com/repos/<repo>/commits/<sha>/check-runs`
  and `/actions/runs/<id>` (60 requests per hour per IP), or the PR's Checks
  tab in the app's signed-in browser pane.

## 7. Pitfalls met in this slice

- Tool inputs decode JSON escapes: typing `\u00ad` into an edit writes the
  invisible character itself. Write escapes with a script (`chr(92)` or
  `<U+XXXX>` placeholders) and scan with `tools/nonascii.py`. Keep SQL and
  Python sources ASCII.
- Windows text-mode writes produce CRLF; `.gitattributes` is `eol=lf`. Write
  bytes or use `UTF8Encoding($false)` and `\n`.
- `git commit -F <long scratchpad path>` fails with "Filename too long"; copy
  the message to a short path first.
- PowerShell strips double quotes when passing `-c` code to native programs;
  put Python in a file.
- Test roles `gba_test_owner`/`gba_test_app` are cluster-wide: never run two
  fixture suites on one cluster at the same time.
- A published migration is frozen even while its PR is a draft (as 0022–0024
  in PR16): fix forward with a new number.
- The GateGuard hooks ask for facts before the first command and the first edit
  of each file; state them and retry.

## 8. Decisions taken (owner may revise)

See the validation file. In short: interior whitespace preserved; look-alike
punctuation not unified; only issued obligations lock an account as control;
"today" is the latest local date among the business's location zones, else
UTC; the identity check stays a linear scan for now.

## 9. Working notes for the code

- Same rules as H2: add each migration to `_MIGRATIONS` in
  `db/financial_guard.py`; the latest packaged function wins; restore damaged
  functions in drift tests with `packaged_function` from `test_invoice_issue.py`.
- `0025` and `0026` create no table, so they have no scope footer and the
  definition count stays 63 in `test_document_contracts.py`.
- Every packaged H CHECK needs one `CHECK_APPROVAL` line; keep table-specific
  `new.<field>` references in nested PL/pgSQL ifs.
