# K1b guard review — local validation

**PASS for this bounded local correction.** Source `db96f005442201428700995c09f028e1b6da08c0`, parent `84d4177e97ebc16e1743dcb995abf54c1b81269d`,
branch `codex/package-k1b-guard-review`. [CHECKS.json](CHECKS.json) was written before the source commit;
it binds source blobs, all phase commands, exits, log hashes and test evidence.
No K publication. This is inline self-review, not independent acceptance.

Changed source files:

- `api/src/gorgona_booking/db/ledger_guard.py`
- `api/src/gorgona_booking/db/provider_receipt_guard.py`
- `api/tests/integration/test_provider_receipt_guard_review.py`

The receipt guard now rejects a shadow trigger function, conditional or argument-bearing
trigger, changed shared immutable function, foreign-schema FK parent, and PUBLIC column
grants. It reuses the ledger/financial guard pattern and packaged immutable-history source.
No SQL migration, dependency, role, public ingress, worker or financial effect was added.

| Check | Exact observed outcome |
|---|---|
| RED, original production sources | FAIL expected:6 failed in 5.93s; all six DID NOT RAISE DatabaseUnavailableError |
| Smallest GREEN | PASS:6 passed in 4.81s; healthy before damage, restored after, no receipts written |
| Focused fresh PostgreSQL18.6 | PASS:316 passed in 106.89s (0:01:46) |
| Complete fresh PostgreSQL18.6/browser suite | PASS:1890 passed, 4 skipped in 1454.00s (0:24:14) |
| Ruff check/format, strict mypy | PASS:required exit0; mypy304 source files |
| Web typecheck/lint/format/unit/build | PASS:required exit0;114 web unit tests |
| Runtime npm audit | PASS:0 vulnerabilities |
| Existing development npm audit | FAIL:5 high; unchanged lock/dependencies, nonrequired existing limitation |
| Actual container image | NOT TESTED:Docker CLI unavailable;3 container skips |
| Historical optional external site | NOT TESTED:1 optional skip; not a current product dependency |
| K publication / exact-commit CI / independent review | NOT TESTED |
| Actual provider admission/execution | BLOCKED:separate direct owner authorization and actual evidence required |

All six new cases passed in the full JUnit. Complete K1 and K-01–K-14 remain NOT TESTED.
Runtime-writable facts remain **receipt_only_not_admitted**, without cryptographic database
attestation. Do not use them for money; see [reuse](ARCHITECTURE_REUSE.md) and [review](REVIEW.md).
No HTTP commit-before-ack, power-loss durability, quotas/retention or provider availability
is established by these tests. Existing receipt concurrency tests use real pg_locks waits;
this slice introduces no new race or performance claim.

Exact gate entry commands (PowerShell; cwd `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`):

```powershell
& 'C:\Users\alexa\.codex\worktrees\package-j-review2-fixes\Gorgona Booking\api\.venv\Scripts\python.exe' 'C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1b-review-20261015-84d4177\runner.py' static-1 static
& 'C:\Users\alexa\.codex\worktrees\package-j-review2-fixes\Gorgona Booking\api\.venv\Scripts\python.exe' 'C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1b-review-20261015-84d4177\runner.py' full-1 full
```

The focused subprocess command recorded by the runner, including all selected regressions
(the runner supplies its private disposable-cluster environment):

```powershell
Set-Location -LiteralPath 'C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking/api'
& 'C:\Users\alexa\.codex\worktrees\package-j-review2-fixes\Gorgona Booking\api\.venv\Scripts\python.exe' '-m' 'pytest' '-p' 'no:cacheprovider' '--basetemp' 'C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1b-review-20261015-84d4177\focused-1\focused-tmp' '-q' '-ra' '--tb=short' '--capture=tee-sys' '--junitxml=C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1b-review-20261015-84d4177\focused-1\focused.xml' 'tests/integration/test_location_access.py' 'tests/integration/test_provider_event_inbox.py' 'tests/integration/test_provider_receipt_guard_review.py' 'tests/integration/test_roles_and_migrations.py' 'tests/integration/test_ledger.py' 'tests/integration/test_provider_receipt_upgrade.py' 'tests/unit/test_migration_files.py' 'tests/unit/test_stripe_event_boundary.py' 'tests/unit/test_provider_admission_contracts.py' 'tests/unit/test_settlement_contracts.py' 'tests/unit/test_payment_correction_contracts.py' 'tests/integration/test_provider_admission.py' 'tests/integration/test_external_payments.py'
```

RED/GREEN commands are the same runner with `red-guard focused` / `green-guard focused`
and `tests/integration/test_provider_receipt_guard_review.py`. Each phase uses a fresh
owned disposable cluster; all were stopped and temporary password files removed.
Synthetic/local credentials were never printed. Full exact commands/log hashes are in CHECKS.

Run folder `C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1b-review-20261015-84d4177` contains runner.py, run_gates.py, write_record.py, update_docs.py,
validate_docs.py, redacted logs, JUnit, results and STATE.md. Record helper expects BASE;
docs updater expects its source child. Do not rerun those against a later HEAD.

No readiness changes. FIN-02/STOCK-01 planned, ADR0026/0027 Proposed, remote main=fedd0f1,
published J=df88c20. Migrations0001–0044 unchanged; next0045. K remains local only.

Documentation files in the following docs commit:

- `docs/plan/evidence/2026-10-15-k1b-guard-review/CHECKS.json`
- `docs/plan/evidence/2026-10-15-k1b-guard-review/VALIDATION.md`
- `docs/plan/evidence/2026-10-15-k1b-guard-review/REVIEW.md`
- `docs/plan/evidence/2026-10-15-k1b-guard-review/ARCHITECTURE_REUSE.md`
- `docs/plan/NEXT_AGENT_PACKAGE_K1B_REVIEW_2026-10-15.md`
- `docs/plan/NEXT_AGENT_PACKAGE_K1B_REVIEW_PROMPT_2026-10-15.md`
- `docs/plan/GORGONA_MASTER_PLAN.md`
- `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md`
- `CLOUD_CODE_HANDOFF.md`
- `docs/plan/PACKAGE_K_PLAN_2026-10-15.md`
- `docs/adr/0027-provider-events-and-reconciliation.md`
- `docs/plan/NEXT_AGENT_PACKAGE_K1B_2026-10-15.md`
