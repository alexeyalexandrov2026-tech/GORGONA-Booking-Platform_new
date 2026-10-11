# I3 exact command and outcome ledger — 2026-10-11

Commands ran in the root disposable environment. The runner changes cwd to the
canonical checkout/api and enforces PostgreSQL/browser. It selects PG18.6 at
127.0.0.1:51480, not another cluster. No secrets are included here.

## Feature and protection TDD

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheets.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-initial-red --tb=short
```

FAIL2/4.19s before routes existed.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_workforce.py::test_packaged_workforce_schema_passes_guard tests/integration/test_timesheets.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-basic-green --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/unit/test_timesheet_contracts.py -p no:cacheprovider --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheets.py tests/unit/test_timesheet_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-dst-green --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheets.py tests/integration/test_timesheet_guards.py tests/unit/test_timesheet_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-guards-first --tb=short
```

Respectively: PASS3/4.45s; FAIL2 with12 passes/0.23s; PASS16/3.80s after UTC
ordering fix; PASS41/26.85s.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_schema.py -k missing_exclusion -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-missing-exclusion-red --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_schema.py tests/integration/test_timesheet_guards.py tests/unit/test_timesheet_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-schema-green --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_races.py tests/integration/test_timesheet_upgrade.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-races-upgrade-first --tb=short
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_guards.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-guard-extra-first --tb=short
```

Respectively: FAIL1/9 deselected/4.84s (read200 despite missing exclusion);
PASS49/31.44s after guard correction; PASS13/16.00s; FAIL1 with36 passes/38.53s
(wrong test ledger table name). The schema-green command followed qualification
of advisory/hash names with pg_catalog in the new migration in the same shell.

## Independent findings: reproduce, then correct

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_guards.py::test_branch_manager_cannot_decide_another_home_entry_with_wide_sql_context -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-review-home-red --tb=short
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_races.py -k 'rr_shift_link or rr_module_disable' -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-review-rr-red --tb=short
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_races.py tests/integration/test_timesheet_guards.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-review-fixes-green --tb=short
```

Respectively: FAIL2/2 passed/6.30s; FAIL5/12 deselected/6.45s; PASS58/52.57s.
Observed pg_locks waits are mandatory in all17 corrected race cases.

## Final local suites

```powershell
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheets.py tests/integration/test_timesheet_guards.py tests/integration/test_timesheet_schema.py tests/integration/test_timesheet_races.py tests/integration/test_timesheet_upgrade.py tests/unit/test_timesheet_contracts.py tests/integration/test_workforce.py tests/integration/test_workforce_guards.py tests/integration/test_workforce_upgrade.py tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_upgrade.py tests/integration/test_location_access.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-focused-final --tb=short
```

PASS204/171.18s. Subsequent changes only correct test annotations/explicit
arguments; production files remain unchanged.

```powershell
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_guards.py::test_original_clockin_and_correction_receipts_replay_after_later_approval tests/integration/test_timesheet_guards.py::test_branch_manager_cannot_decide_another_home_entry_with_wide_sql_context tests/integration/test_timesheet_upgrade.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-annotations-final --tb=short
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_guards.py::test_clock_in_replay_and_correction_replay_keep_original_immutable_response tests/integration/test_timesheet_guards.py::test_branch_manager_cannot_decide_another_home_entry_with_wide_sql_context tests/integration/test_timesheet_upgrade.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-annotations-final-green --tb=short
```

FAIL: first selector has no matching node, exit1, zero tests/0.97s.
Corrected command PASS6/9.43s.

```powershell
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q -ra -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-full-final --tb=short
```

PASS1467/4 skipped/944.47s on the pre-break-limit snapshot. This is retained
historical evidence; it does not validate the later correction below.

```powershell
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_guards.py -k 'break_limit or hundredth_break' -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-break-limit-red --tb=short
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q tests/integration/test_timesheet_guards.py tests/integration/test_timesheet_schema.py tests/integration/test_timesheet_races.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-break-limit-focused-final --tb=short
```

First FAIL4/2 passed/43 deselected/8.07s (API/raw SQL admitted break101).
Second PASS76/67.46s after early refusal prevents the unclosable state.

```powershell
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m pytest -q -ra -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i3-full-break-final --tb=short
```

PASS1473/4 skipped/832.46s on the final source after all four fixes.
Three container checks and one optional external-site check skipped; their exact
requirements are recorded in VALIDATION.md, not counted as PASS.

## Static and web gates

```powershell
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m ruff check src tests
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m ruff format --check src tests
& C:/Users/alexa/AppData/Local/Temp/gorgona-i3-check.ps1 -m mypy src tests
```

Final PASS: exit0 each; format254 files; mypy254 source files. Prior failures
were Ruff line lengths/imports and mypy6 test-annotation errors, corrected.

Each web command ran from canonical checkout/web with
`$env:PATH='C:/Program Files/nodejs;'+$env:PATH`:

```powershell
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
npm audit --omit=dev --json
```

First five PASS exit0; unit94/1.8s, build20 static pages. Audit FAIL exit1,
2 high nodes in the inherited production dependency tree (next, source-map-js).
No dependency file was changed or npm audit fix executed.

## Source approval helper / operational checks

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 C:/Users/alexa/AppData/Local/Temp/i3-pin-source-approvals.py
& C:\Users\alexa\AppData\Local\Temp\gorgona-i3-check.ps1 C:/Users/alexa/AppData/Local/Temp/i3-pin-cleanup.py
```

First helper compiled reviewed source in its own new scratch DB and pinned
11 new CHECKs,2 exclusions and3 policies, but ended FAIL exit1 in cleanup because
its database variable was overwritten. The exact own scratch DB was identified
and cleanup helper PASS; other DBs untouched. Old approval literals unchanged.

Read-only Git/GitHub, raw SHA256 copying/comparison and final docs/commit checks
are specified in VALIDATION.md. No secrets or command DSNs are printed here.

```powershell
& 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/postgres-18.6/pgsql/bin/pg_ctl.exe' status -D 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/i3-root-20261011'; $taskPgStatus=$LASTEXITCODE; Write-Output ('Native pg_ctl status exit: '+$taskPgStatus); exit $taskPgStatus
```

PASS: native exit3 and no server running, following own-target-verified stop
exit0. The initial plain PowerShell status wrapper returned1; the explicit
native-code command above distinguishes the expected pg_ctl3 result.
