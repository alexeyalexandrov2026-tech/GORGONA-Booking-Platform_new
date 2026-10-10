# Package I, slice I2 — local evidence, 2026-10-10

PASS: implementation and full local validation complete. This record does not
accept WORK-01, promote readiness or claim industrial deployment readiness.

## Repository and execution boundary

- Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
- Checkout: C:/Users/alexa/Documents/ChatGPT/gorgona-package-i.
- Branch: codex/package-i2-shift-changes, based on I1 commit
  69270cc8bfdfb763cc8f5fc9b7892b13db987bce.
- The unrelated primary checkout was preserved. One executor owns this checkout
  and its disposable PostgreSQL cluster. The independent reviewer reads a
  separate checkout and runs no PostgreSQL suite.
- Only forward migration 0033_shift_changes.sql is added. Migrations 0001–0032,
  readiness_registry.py, modules.py and the web dependency lockfile are unchanged.
- WORK-01 and CORE-04 remain planned. Workforce writes remain closed outside
  fixture-only readiness overrides. I3 timesheets and I4 screens are not implemented.
- No push, PR, merge, rebase, amend, reset, clean, force-push, deployment,
  production migration, Azure, provider, real money or credential operation.
  No CodeRabbit. The separate FIN-03 acceptance-commit check was not undertaken.

Live read-only checks on 2026-10-10:

```powershell
git branch --show-current
git rev-parse HEAD
git remote get-url origin
git ls-remote origin refs/heads/codex/package-i1-workforce refs/heads/codex/package-i2-shift-changes
```

PASS: branch/base and expected origin verified; ls-remote returned no published
I1/I2 refs. GitHub connector search_issues, with query
`repo:alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new is:pr head:codex/package-i1-workforce`
and the corresponding I2 head query, returned zero PRs. Its
fetch_commit_workflow_runs for the I1 base returned zero PR-triggered runs;
that tool does not establish the absence of all workflow event types.
The attempted gh read-only commands failed because gh is not installed; the
connector supplied the bounded results above. I2 exact-commit CI is NOT TESTED
while the branch remains unpublished.

## Implementation and working policies

Three immutable relations hold change requests, the exact participant × required
skill snapshot, and consent/decision events. Requests reference immutable I1
shift and assignment revisions. Events carry their actor and timestamp. Handover,
swap and pickup require an explicit accept event before a manager approval.

For pickup there is no outgoing employee: the requester accepts their own pickup,
then a different manager user approves. Handover/swap approval may be performed
by a manager who is also a participant, after the other employee's explicit
consent. Timesheet self-approval rules belong to I3 and are not implemented here.

Self pickup is limited to an open shift in the employee's home branch, including
direct SQL. Own handover/swap consent and history work for existing cross-home
assignments. Company-wide management approves cross-home changes; branch
management must cover both shifts and both staff homes. The colleague projection
contains only active home-branch profiles and display names. Open-shift reads
exclude draft, cancelled, assigned and other-home shifts.

The existing I1 manager manual reassignment path is retained. SQL gba.user_id is
trusted application context, not cryptographic authentication for an arbitrary
database client. I2 enforces actor/role/consent on its request/event workflow; it
does not claim employee consent is required for every raw I1 version insertion.

Commands reuse business claim/complete/audit and WorkforceReceipt. Replay loads
the exact original immutable event revision, including its actor/time, after
later acceptance/approval. A changed payload under the same key is refused.
Failure rolls back events, versions, assignments, occupancy, audit and receipt.

Locks use sorted resource advisory IDs, sorted shift heads, sorted skill catalogue
heads FOR SHARE, then the request head. Catalogue locks precede snapshot revision
comparison, so even a harmless rename invalidates an approval that waited for it.

Swap inserts both next shift versions in one statement. A transition-table AFTER
STATEMENT trigger releases every old allocation before creating the new ones;
the shared immediate exclusion constraint remains authoritative. It refuses
multiple revisions of one shift per statement, hidden prior resources under a
narrow RLS scope, and a release count different from the prior assignment count.
There is no new occupancy table, deferred exclusion or new dependency.

Primary mechanism references: PostgreSQL18
[CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html)
for statement transition tables and
[explicit locking](https://www.postgresql.org/docs/18/explicit-locking.html)
for resource/row lock ordering. Runtime correctness is established by the tests
above, not inferred from documentation alone.

The combined I1/I2 package guard approves all eleven tables, forced tenant/branch
RLS, columns/defaults/grants/keys/FKs/CHECKs and exact function/trigger definitions,
including transition aliases, statement mode and WHEN. It still uses five real
catalog queries. Approval values come from packaged SQL, never from the target
database. Location-access restoration includes migration 0033 and drops each
restored policy explicitly because indirect child dependencies may survive CASCADE.

## Acceptance mapping for this slice

All test names below are in api/tests/integration unless identified as unit.

| Requirement | Direct checks |
|---|---|
| I-04: explicit consent, manager decision, atomic three workflows | test_shift_changes.py::test_change_needs_explicit_consent_and_manager_and_applies_atomically (handover/swap/pickup); pickup different-manager test |
| I-04: changed shift/assignment/catalogue/staff skill refuses approval | test_shift_changes_guards.py::test_approval_refuses_any_changed_expected_fact; manual-race test |
| I-03: effective skill check repeated by SQL | test_approval_repeats_effective_skill_validation_in_sql: missing/future/revoked replacement × API/raw SQL (six cases); inherited I1 assignment regressions |
| I-05: two pickups, approval/withdraw, approval/manual, opposite swaps | test_shift_changes_races.py::test_i05_ordered_races_have_one_winner_without_deadlock: eight API/raw SQL cases |
| Catalogue change during approval | test_catalogue_rename_is_locked_before_the_stale_snapshot_comparison: two API/raw SQL cases |
| I-06: immutable event/snapshot/request and terminal history | test_all_change_history_is_immutable_for_owner; terminal decline/withdraw refusal; actor/time history |
| Exact snapshots; construction-only, no forged extra rows | old-request and same-transaction unrequired-snapshot tests, complete rollback |
| I-09: own/home/company/manager/support boundaries | trusted-participant/history, active-home directory/open shifts, cross-home consent/approval/decline, scope-restoration, same-user re-invite, forged consent, foreign/support route tests |
| Pickup cannot discover a foreign open shift | test_self_pickup_cannot_discover_an_open_shift_outside_home: API/raw SQL403/42501 and zero residual rows/receipt |
| I-10: raw SQL narrow scope cannot keep old occupancy active | test_raw_branch_sql_cannot_leave_a_hidden_prior_allocation_active: open/cancel refusal and whole rollback |
| I-10: damaged schema fails closed | test_shift_changes_schema.py: nine damaged policy/function/default/FK/trigger/WHEN/transition metadata cases return503 on read and write |
| I-11: module off/readiness revoked | new events refused, history readable; module-off raw SQL GBM01; inherited booking/reservation/resource-kind tests |
| Populated upgrade and repeat | test_shift_changes_upgrade.py: nonempty0032→0033 preserves every old row digest/checksum; repeat no-op; combined guard PASS |
| Versioned strict input | unit/test_shift_change_contracts.py:15 invalid shape/version/extra/boolean/float/string revision cases |

I-07/I-08 and timesheet parts of I-09/I-11 remain NOT TESTED (I3). I-12 workforce
screens, exact-SHA CI and final package acceptance remain NOT TESTED (I4/release).
Existing generic browser regressions are a separate full-suite gate.

## Environment and exact commands

The [command ledger](COMMANDS.md) retains26 distinct exact pytest commands from
the executor's own recorded calls, including earlier red evidence.

Python3.14 environment:
C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv.
The runner C:/Users/alexa/AppData/Local/Temp/gorgona-i2-check.ps1 sets PYTHONPATH
to this checkout's api/src and api, changes cwd to api and sets
GBA_REQUIRE_POSTGRES=1 and GBA_REQUIRE_BROWSER=1. Only the own disposable PG18.6
cluster i2-root-20261009, loopback51479/max_connections400, is used. Its creation
date in the directory name remains unchanged. DSNs/secrets are not recorded.

From the repository root:

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m ruff check .
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m ruff format --check .
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m mypy
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_schema.py tests/integration/test_shift_changes_upgrade.py tests/unit/test_shift_change_contracts.py tests/integration/test_workforce.py tests/integration/test_workforce_guards.py tests/integration/test_workforce_upgrade.py tests/integration/test_resource_kind_boundaries.py tests/integration/test_location_access.py tests/unit/test_workforce_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-regression-focused-02 --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-full-local-01 --tb=short 2>&1 | Tee-Object -FilePath C:\Users\alexa\AppData\Local\Temp\gorgona-i2-full-local-01.log; exit $LASTEXITCODE
```

- Ruff/format: PASS;248 files formatted.
- Strict mypy: PASS;248 source files after the last test-only edit.
- Before independent fixes, combined focused set: PASS151/95.53s.
- Independent fixes plus workflows/rollback/all ten lock-wait races: PASS19/19.82s.
- Combined focused after the two independent fixes: PASS156/114.89s. Four
  additional future/revoked replacement cases were then added; their complete
  six-case effective-skill group PASS6/7.48s. Final full suite covers their union.
- Full project suite: PASS,1380 passed / 4 skipped / 738.66s, exit0, required
  PostgreSQL/browser. Three container checks skipped because GBA_REQUIRE_CONTAINER
  was unset (Docker unavailable); one external-site check skipped because
  GBA_REQUIRE_TENANT_SITE was unset. These boundaries remain NOT TESTED.
- Independent corrected-source review: PASS,16 API files;
  [separate evidence](INDEPENDENT_REVIEW.md). Independent runtime/CI NOT TESTED.

From web, Node24.18.0/npm11.16.0, unchanged package-lock:

```powershell
npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
npm audit --omit=dev --json
```

PASS: install (361 added/362 audited), typecheck, lint, formatting,94 unit tests
(1.3s), build20 static pages. Production dependency audit: FAIL, exit1,2 high
nodes (next and source-map-js),0 critical; install reports7 high for the full
tree. These are inherited and no dependency was changed by I2. An audit finding
is not an observed exploit. No industrial readiness is claimed.

## Red evidence retained

Initial feature TDD: FAIL4/5.67s (three missing routes and duplicate-head SQL
statement accepted). Subsequent pre-fix setup/check failures were retained in
the [exact command ledger](COMMANDS.md): incorrect compiled CHECK deparse, policy restoration,
cross-home manager self-consent/decline, strict revisions, actor refusal and
history projection. Final green counts do not retroactively accept those trees.

Fresh late failures with exact commands:

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_schema.py tests/integration/test_shift_changes_upgrade.py tests/unit/test_shift_change_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-all-focused-02 --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_self_pickup_cannot_discover_an_open_shift_outside_home tests/integration/test_shift_changes_guards.py::test_raw_branch_sql_cannot_leave_a_hidden_prior_allocation_active -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-review-red --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_raw_branch_sql_cannot_leave_a_hidden_prior_allocation_active -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-review-release-red --tb=short
```

- FAIL1/69 passed/60.87s: test attempted to create a cancelled shift directly;
  fixed to append cancellation to an existing shift, PASS1/4.21s.
- FAIL4/4.49s: foreign pickup API200/raw SQL accepted; release test initially
  used an unsupported fixture keyword and did not yet prove the release defect.
- FAIL2/3.16s after correcting the fixture: both published/open and cancelled
  narrow SQL changes committed without refusal, confirming the release defect.
- Corrections are only in forward0033. Both foreign pickup paths and both hidden
  release paths now fail closed; the19-case focused result above includes them.
- Ruff previously FAIL19 (line lengths/assertions), then FAIL3 after adding new
  regressions; corrected, fresh Ruff/format PASS as recorded above.

## Changed files

The [source snapshot](SOURCE_SHA256.md) names all sixteen API files and their raw
SHA256. They include the new shift_changes API/service/contracts, forward0033,
five integration modules and one unit module; app routing, workforce listing,
package guard, location-policy restoration and I1 regression adaptations changed.

Six existing documentation files changed: CLOUD_CODE_HANDOFF.md,
docs/adr/0025-workforce-shifts-and-timesheets.md,
docs/plan/GORGONA_IMPLEMENTATION_STATUS.md,
docs/plan/NEXT_AGENT_PACKAGE_I_2026-10-09.md,
docs/plan/PACKAGE_I_PLAN_2026-10-09.md,
docs/plan/PROJECT_PROGRESS_2026-10-09.md. Four evidence files are new:
VALIDATION.md, INDEPENDENT_REVIEW.md, SOURCE_SHA256.md and COMMANDS.md in this
directory. All26 files belong to this slice.

## Remaining boundaries

Post-full SHA256 comparison PASS: all16 API source/test files match the captured
pre-full snapshot and the independent review checkout. Historical migration,
readiness/modules, api/uv.lock and web diffs are empty. All26 staged files belong
to this slice and their normalized Git blobs match the working copy. Fresh
git diff --check and git diff --cached --check both PASS, exit0;140 local Markdown
file links across10 changed documents PASS. These checks are refreshed after
this final evidence edit. No push is authorized.

Own PostgreSQL target was checked against data directory and port51479 before
stopping. Only that disposable cluster stopped successfully; status exit3
confirmed no server. Its files are preserved, and no owner/shared cluster changed.

```powershell
& 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\postgres-18.6\pgsql\bin\pg_ctl.exe' stop -D 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\i2-root-20261009' -m fast -w
& 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\postgres-18.6\pgsql\bin\pg_ctl.exe' status -D 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\i2-root-20261009'
git diff --check
git diff --cached --check
```

CI, container runtime, external-site embedding, industrial load/soak, deployment
and production data are NOT TESTED. No external tenant site is required for this
universal platform.
WORK-01 acceptance requires I3/I4, complete I-01–I-12 evidence, independent
acceptance review, exact-commit CI and the owner's separate readiness decision.
