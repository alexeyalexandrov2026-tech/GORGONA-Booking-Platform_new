# Package I, slice I3 — local evidence, 2026-10-11

PASS: implementation and final full local validation complete:
1473 passed / 4 skipped / 832.46s, with mandatory PostgreSQL and browser.
The earlier1467/4 skipped/944.47s result is retained as pre-break-limit evidence.
WORK-01/CORE-04 are not accepted or promoted by this slice.

## Repository and execution boundary

- Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
- Checkout: C:/Users/alexa/Documents/ChatGPT/gorgona-package-i.
- Branch: codex/package-i3-timesheets, base I2
  49276bf800eb929589785e192db489e17ac77fa7.
- Only root edits this checkout or executes its disposable PostgreSQL suite.
  The independent reviewer reads a separate checkout and runs no database tests.
- One forward migration: 0034_timesheets.sql. Migrations0001–0033 are preserved.
  WORK-01, CORE-04, modules/readiness, API/web dependency locks are unchanged.
  Workforce writes remain closed outside fixture-only readiness overrides.
- No push, PR, merge, force-push, rebase, amend, reset, clean, deployment,
  production migration, Azure, provider, real money or credential operation.
  No CodeRabbit. The independent FIN-03 acceptance check remains a separate task.

Live read-only checks on2026-10-11:

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git remote get-url origin
git ls-remote origin refs/heads/codex/package-i2-shift-changes refs/heads/codex/package-i3-timesheets
```

PASS: base/branch and expected origin verified, no published I2/I3 refs.
GitHub connector search_issues with
`repo:alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new is:pr head:codex/package-i3-timesheets`
returned zero PRs. fetch_commit_workflow_runs for the I2 base returned zero
PR-triggered runs; the wrapper does not establish absence of all workflow events.
I3 exact-commit CI remains NOT TESTED because this branch is unpublished.

## Implemented flow and working policies

Three relations hold an immutable clock-in head, immutable revision snapshots,
and an exactly derivable current projection. Commands record start, break start,
break end, clock-out, correction, approve and decline. Each event keeps actor,
server time and reason. A correction can replace only a closed snapshot and
requires a reason; three consecutive corrections preserve the entire chain.

The last approved revision remains effective while a newer correction awaits
approval or is declined. Only a new approval replaces its effective interval.
Pending entries may overlap; approved full half-open intervals cannot. Breaks
deduct elapsed worked microseconds but do not release an overlap interval.
Clock-out automatically closes an active break and preserves the start/history.
Starting another break after100 completed breaks is refused before opening it,
so the limit cannot strand the entry or prevent closure, including module-off.

Identity is the stable tenant/user, including after a same-home reinvitation.
There can be one open entry for that identity. Revoked old profile memberships
do not hide the employee's history or prevent their new active membership from
closing an already open own entry. Every accounting row belongs to the employee
home; an optional work-branch shift link captures its immutable original bounds.
Later correction changes reported work, not that original shift association.

Clock-in may have no shift. The explicit out_of_schedule flag compares actual
revision start with the captured optional shift interval; no shift is flagged.
A linked shift must be the employee's current published assignment, checked
again in SQL. Times are reported inputs, not proof from a clock/device/location.
Durations/order use UTC instants, including repeated wall hours at a DST fold.

Employees clock/correct only their own entries. Manager read/decision scope is
the employee home, with company-wide management covering all homes. SQL checks
the actual membership home even when the trusted runtime branch GUC is empty.
A manager cannot approve their own stable user identity. An owner may do so with
an immutable, visible self_approved flag. Delegates, platform support and another
company receive refusal. Audit reuses the existing identifier-only workforce flow.

Disabling workforce or revoking application readiness refuses new actions.
Own history remains readable, and only closing an existing open own entry is
allowed. The SQL off-switch exception is confined to clock_out; it cannot also
replace start/break snapshot or approve another entry.

Commands reuse claim/complete/audit and WorkforceReceipt. Replay loads the exact
original immutable revision and its effective approved state as of that revision,
even after later approval. A changed payload under the same key is refused.
Native SQL40001 maps to WORKFORCE_CONFLICT and rolls back the claimed key. The
API mapping test injects a real SQL exception; real old-snapshot conflicts are
also exercised separately through direct REPEATABLE READ transactions.

## SQL protection and concurrency

Locks begin with shared business-configuration advisory/physical module-row
locks, then the stable resource and entry/shift head. The module lock-read alone
temporarily widens the branch GUC for the already tenant-readable config row;
it restores the scope before any staff/entry access. FOR SHARE detects a module
publication after a REPEATABLE READ snapshot. Linked clock-in also locks its
existing confirmed shift allocation, whose physical release detects replaced
assignments under an old snapshot. This creates no resource occupancy.

Two immediate GiST exclusions protect one-open and approved full intervals on
tenant/user. They protect old snapshots independently of application advisory
locks. The projection requires its exact latest immutable source in the current
transaction, INSERT only at revision1, and UPDATE advancing exactly one revision
without changing identity. DELETE/forgery/orphan histories are rejected, including
deferred completeness at transaction end.

The combined guard checks14 tables, exact packaged functions/triggers/WHEN,
forced tenant/home policies, input column grants, defaults, keys, FKs and CHECKs.
For exclusions it also checks existence, nondeferrability, predicate, index
valid/ready/live flags, GiST and UUID/range opclasses. Approvals are packaged
reviewed SQL, never learned from a target database. Five actual catalogue queries
remain sufficient. Location-policy restoration includes forward0034.

Primary mechanism references:
[PostgreSQL18 CREATE TABLE](https://www.postgresql.org/docs/18/sql-createtable.html)
and [transaction isolation](https://www.postgresql.org/docs/18/transaction-iso.html).
Runtime evidence comes from the tests below, not documentation alone.

The projection is actual-work accounting, not a resource reservation table.
No shared allocations, journal entries or journal lines are created by timesheet
start/close/approval. There are no payroll amounts, legal break/overtime rules,
geolocation, device verification, notifications or I4 screens.

## Acceptance mapping

Test names below are in api/tests/integration unless marked unit.

| Requirement | Direct evidence |
|---|---|
| I-07: versions, authors/reasons, last approved, three corrections | test_timesheets.py workflows; test_pending_and_declined_correction_keep_the_previous_approved_interval; immutable/orphan/projection tests in test_timesheet_guards.py |
| I-08: one open, stale corrections, effective overlap, original receipt |12 races × API/raw RC/raw RR modes in test_timesheet_races.py; full-interval overlap tests; reinvite and original clock/correction replay tests |
| I-09: self/manager/home/owner/delegate/support/foreign scope | test_timesheet_guards.py own-user refusal, four branch-manager decision cases, scoped-manager success, real active delegation refusal and owner-tag preservation |
| I-10: raw SQL and damaged protections |10 schema mutation cases refuse reads and writes503 and restore exact definitions; orphan/projection/grant/array checks; combined guard five-query regression |
| I-11: off/readiness and booking regression | four API/raw closure cases; off snapshot/user refusal; three real RR module-disable races; historical I1/I2/location checks and full suite |
| Current optional link under RR | two cancellation/reassignment races after observed resource wait reject stale links; normal cross-work-branch link remains valid |
| UTC and strict contracts |14 unit cases including two fail-before-fix DST ordering regressions |
| Nonempty upgrade | populated0033 shift/change data preserve every old row digest/checksum, add only0034, empty new tables, repeat application no-op, guard passes |
| No money or reservation | counts of resource_allocations, journal_entries and journal_lines unchanged |
| I-12 package acceptance | NOT TESTED: I4 screens, exact-commit CI and independent runtime acceptance remain |

All17 I3 races require observed waiting advisory locks in pg_locks before release;
none is credited solely for task timing. The reviewer did not execute these tests.

## Validation commands and results

Exact commands, including retained FAIL outcomes, are in [COMMANDS.md](COMMANDS.md).
The local runner sets PYTHONPATH to this checkout/api, requires PostgreSQL/browser,
and selects only the root disposable PG18.6 cluster on127.0.0.1:51480. It borrows
Python3.14.6 from the existing package-g-ledger-review venv; Node24.18.0 and
npm11.16.0 are the existing local tools. No dependency was added.

| Check | Outcome |
|---|---|
| Earlier I3 SQL guards/races before final break-limit fix | PASS58/52.57s |
| Earlier expanded I1/I2/I3/location suite | PASS204/171.18s |
| Earlier test-annotation/replay/upgrade checks | PASS6/9.43s |
| Final I3 guards/schema/17 races after break-limit fix | PASS76/67.46s |
| Ruff check | PASS, exit0 |
| Ruff format check | PASS254 files, exit0 |
| mypy src tests | PASS254 source files, exit0 |
| Web typecheck/lint/format | PASS, each exit0 |
| Web unit | PASS94/1.8s |
| Production web build | PASS20 static pages, exit0 |
| npm audit --omit=dev --json | FAIL2 high nodes: next and source-map-js, inherited unchanged tree |
| Corrected-source independent review | final PASS14 files/14 SHA matches/0 mismatches after all four fixes; reviewer runtime0 runs |
| Full pytest with mandatory PostgreSQL/browser, final source | PASS1473/4 skipped/832.46s |

## Red evidence retained

Feature TDD:2 failures/4.19s, routes404 before implementation. Two DST ordering
cases failed with12 passes/0.23s, then UTC comparisons corrected. Dropping the
approved-overlap exclusion initially still admitted an API read200:
1 failure/9 deselected/4.84s; exact exclusion-set verification fixed it.

Independent findings were reproduced before fixes: raw home-foreign approve and
decline accepted (2 failures/2 API passes/6.30s); replaced shift cancellation and
reassignment still linked under RR, and three actions bypassed disabled state
under RR (5 failures/12 deselected/6.45s). Forward0034 fixes all three mechanisms.
Final green results do not retroactively accept the earlier source.

A fourth source finding appeared during final self-review: starting a101st
break after100 completed breaks stranded the open entry. Its pre-fix tests:
FAIL4/2 passed/43 deselected/8.07s. Refusal now precedes opening that break;
tests cover no revision/state/audit/key effect and successful closure with100
breaks even after module disable, plus both ways to finish the100th break.
The first full green run1467/4 skipped/944.47s was on the earlier source and
does not validate this final fix.

Test/tool errors are also retained: no-money check referred to a nonexistent
ledger_entries fixture table (1 failed/36 passed/38.53s), corrected to real
journal_entries/journal_lines; mypy6 test annotation errors corrected; an
incorrect final pytest node selector ran zero tests and was corrected, then6 PASS.
The source-approval compilation helper succeeded but its first cleanup attempt
used an overwritten variable and exited1. Its own scratch DB was subsequently
identified and removed; no other DB was touched. Approvals were not re-learned.

## Changed files and boundaries

[SOURCE_SHA256.md](SOURCE_SHA256.md) lists all14 changed API source/test files:
new timesheet API/contracts/service, forward0034, five integration modules and
one unit module; routing/combined guard/policy restoration/I2 upgrade adaptation.
Six current project documents and these four evidence documents complete I3.

The six existing documentation files are CLOUD_CODE_HANDOFF.md,
docs/adr/0025-workforce-shifts-and-timesheets.md,
docs/plan/GORGONA_IMPLEMENTATION_STATUS.md,
docs/plan/NEXT_AGENT_PACKAGE_I_2026-10-09.md,
docs/plan/PACKAGE_I_PLAN_2026-10-09.md and
docs/plan/PROJECT_PROGRESS_2026-10-09.md. The four new evidence files are
VALIDATION.md, COMMANDS.md, SOURCE_SHA256.md and INDEPENDENT_REVIEW.md in this
directory. Total24 files:14 API/test and10 documentation files.

Final independent source review is recorded in [INDEPENDENT_REVIEW.md](INDEPENDENT_REVIEW.md).
It is separate from root's PostgreSQL/browser execution. All remaining checks
are refreshed after the final evidence/document edits.

Post-full SHA256 comparison PASS: all14 API/test files and14 review copies match
the final pre-full snapshot. Historical migrations0001–0033, readiness/modules,
API/web locks and all web sources have empty diffs. Only the root disposable
cluster was stopped after live data-directory/port verification; its files remain.

```powershell
& 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin/psql.exe' -h 127.0.0.1 -p 51480 -U postgres -d postgres -At -c "select current_setting('data_directory')||'|'||current_setting('port');"
& 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin/pg_ctl.exe' stop -D 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/i3-root-20261011' -m fast -w
& 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin/pg_ctl.exe' status -D 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/i3-root-20261011'
```

Verified data directory exactly i3-root-20261011 and port51480; stop PASS exit0,
status confirms no server. Explicit native status exit3 confirms that result;
the initial PowerShell wrapper reported exit1 for that expected nonzero status.

Final scope check PASS: all24 intended staged files have normalized Git blobs
matching the working tree. Fresh git diff --check and git diff --cached --check
PASS exit0;150 local Markdown links in10 changed documents PASS, zero missing
targets. These checks are repeated after this evidence edit before local commit.
No push is authorized; the commit SHA and clean-tree result are read from Git
after committing, not invented inside a self-referencing evidence file.

```powershell
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 C:/Users/alexa/AppData/Local/Temp/i3-check-doc-links.py
git diff --check
git diff --cached --check
git commit -m "feat(workforce): add versioned timesheets with SQL guards"
git show --format= --check HEAD
git status --porcelain
git rev-parse HEAD
```

Four skipped checks are NOT TESTED: three container checks require
GBA_REQUIRE_CONTAINER=1, one external-site check requires GBA_REQUIRE_TENANT_SITE=1.
Neither optional boundary is silently counted as PASS.

NOT TESTED: I4 screens, exact-commit CI, containers, external-site embedding,
industrial load/soak, deployment, production data and labour/payroll compliance.
Docker CLI is not available on PATH (read-only Get-Command docker check).
WORK-01 requires the remaining I4 and package acceptance evidence, exact-commit
CI, independent acceptance review and the owner's separate readiness decision.
