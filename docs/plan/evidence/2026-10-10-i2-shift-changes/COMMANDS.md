# I2 exact test command ledger

Commands recovered from this executor's own recorded tool calls. Counts are
per invocation and source snapshot; later PASS never changes an earlier FAIL.
Repeated identical commands are listed once; their red/green outcomes are noted.
Runner configuration and non-test gates are recorded in [VALIDATION.md](VALIDATION.md).

## 1. i2-initial-red

FAIL:4 failed/5.67s; missing routes and duplicate-head acceptance.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-initial-red --tb=short
```

## 2. i2-basic-green

FAIL:4 errors/6.59s; schema approval setup.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-basic-green --tb=short
```

## 3. i2-guard-diagnosis

FAIL:1 failed/2.43s; wrong CHECK deparse approvals.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_workforce.py::test_packaged_workforce_schema_passes_guard -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-guard-diagnosis --tb=long
```

## 4. i2-basics-02

PASS:5 passed/5.51s.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_workforce.py::test_packaged_workforce_schema_passes_guard tests/integration/test_shift_changes.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-basics-02 --tb=short
```

## 5. i2-reuse-regression

FAIL:1 failed/66 passed/46.42s; policy restoration.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_upgrade.py tests/integration/test_workforce.py tests/integration/test_workforce_guards.py tests/integration/test_workforce_upgrade.py tests/integration/test_location_access.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-reuse-regression --tb=short
```

## 6. i2-contracts-guar

FAIL:5 failed/27 passed/29.89s; assertion expected409 rather than422 and missing sql import.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_upgrade.py tests/integration/test_location_access.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-contracts-guar --tb=short
```

## 7. i2-cross-role-red

FAIL:1 failed/1 passed/4.12s; cross-home manager consent.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_guards.py::test_own_cross_home_consent_and_company_wide_approval -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-cross-role-red --tb=short
```

## 8. i2-cross-decline-red

FAIL:2 failed/2 passed/5.20s; cross-home decline.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_guards.py::test_own_cross_home_consent_and_company_wide_approval tests/integration/test_shift_changes_guards.py::test_cross_home_recipient_can_decline_own_request -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-cross-decline-red --tb=short
```

## 9. i2-cross-guard-green

PASS:31 passed/27.17s.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_guards.py tests/integration/test_location_access.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-cross-guard-green --tb=short
```

## 10. unit-contracts

FAIL:3 failed/12 passed/0.22s before strict revision fields; later15 PASS.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/unit/test_shift_change_contracts.py -p no:cacheprovider --tb=short
```

## 11. i2-consent-red

FAIL:1 failed/15 passed/3.66s; proposer consent used stale-conflict status instead of403.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_guards.py::test_proposer_cannot_forge_the_other_employees_consent tests/unit/test_shift_change_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-consent-red --tb=short
```

## 12. i2-races-01

PASS:24 passed/10.55s.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_guards.py::test_proposer_cannot_forge_the_other_employees_consent tests/unit/test_shift_change_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-races-01 --tb=short
```

## 13. i2-races-02

PASS:11 passed/12.59s.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_guards.py::test_unrequired_snapshot_cannot_be_forged_in_the_creation_transaction -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-races-02 --tb=short
```

## 14. i2-schema-mutants

PASS:9 passed/7.93s.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_schema.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-schema-mutants --tb=short
```

## 15. i2-history-red

FAIL:2 failed/4.13s; missing event projection and manager history route.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes_guards.py::test_change_history_exposes_exact_event_actor_and_timestamp -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-history-red --tb=short
```

## 16. i2-all-focused-01

PASS:63 passed/47.88s.

```powershell
& 'C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1' -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_schema.py tests/integration/test_shift_changes_upgrade.py tests/unit/test_shift_change_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-all-focused-01 --tb=short
```

## 17. i2-all-focused-02

FAIL:1 failed/69 passed/60.87s; invalid cancellation test fixture.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_schema.py tests/integration/test_shift_changes_upgrade.py tests/unit/test_shift_change_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-all-focused-02 --tb=short
```

## 18. i2-home-focused

PASS:1 passed/4.21s.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_open_shifts_and_directory_use_home_and_active_memberships -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-home-focused --tb=short
```

## 19. i2-regression-focused-01

PASS:151 passed/95.53s.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_schema.py tests/integration/test_shift_changes_upgrade.py tests/unit/test_shift_change_contracts.py tests/integration/test_workforce.py tests/integration/test_workforce_guards.py tests/integration/test_workforce_upgrade.py tests/integration/test_resource_kind_boundaries.py tests/integration/test_location_access.py tests/unit/test_workforce_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-regression-focused-01 --tb=short
```

## 20. i2-permissions-focused

PASS:1 passed/3.21s.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_foreign_company_and_platform_support_cannot_use_change_routes -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-permissions-focused --tb=short
```

## 21. i2-review-red

FAIL:4 failed/4.49s; pickup reproduced, release fixture keyword still incorrect.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_self_pickup_cannot_discover_an_open_shift_outside_home tests/integration/test_shift_changes_guards.py::test_raw_branch_sql_cannot_leave_a_hidden_prior_allocation_active -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-review-red --tb=short
```

## 22. i2-review-release-red

FAIL:2 failed/3.16s; hidden release defect confirmed.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_raw_branch_sql_cannot_leave_a_hidden_prior_allocation_active -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-review-release-red --tb=short
```

## 23. i2-review-fixes-green

PASS:19 passed/19.82s.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_self_pickup_cannot_discover_an_open_shift_outside_home tests/integration/test_shift_changes_guards.py::test_raw_branch_sql_cannot_leave_a_hidden_prior_allocation_active tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py::test_conflicting_swap_rolls_back_both_sides_event_audit_and_key tests/integration/test_shift_changes_races.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-review-fixes-green --tb=short
```

## 24. i2-regression-focused-02

PASS:156 passed/114.89s; before four additional skill cases.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes.py tests/integration/test_shift_changes_guards.py tests/integration/test_shift_changes_races.py tests/integration/test_shift_changes_schema.py tests/integration/test_shift_changes_upgrade.py tests/unit/test_shift_change_contracts.py tests/integration/test_workforce.py tests/integration/test_workforce_guards.py tests/integration/test_workforce_upgrade.py tests/integration/test_resource_kind_boundaries.py tests/integration/test_location_access.py tests/unit/test_workforce_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-regression-focused-02 --tb=short
```

## 25. i2-review-skills-focused

PASS:6 passed/7.48s.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q tests/integration/test_shift_changes_guards.py::test_approval_repeats_effective_skill_validation_in_sql -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-review-skills-focused --tb=short
```

## 26. i2-full-local-01

PASS:1380 passed/4 skipped/738.66s, exit0; required PostgreSQL/browser.
Three container checks and one external-site check remain NOT TESTED.

```powershell
& C:\Users\alexa\AppData\Local\Temp\gorgona-i2-check.ps1 -m pytest -q -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i2-full-local-01 --tb=short 2>&1 | Tee-Object -FilePath C:\Users\alexa\AppData\Local\Temp\gorgona-i2-full-local-01.log; exit $LASTEXITCODE
```
