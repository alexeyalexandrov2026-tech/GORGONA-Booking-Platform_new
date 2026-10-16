# K1c isolated receipt verifier — local validation

**PASS for this bounded local foundation.** Source `0c72a719cb9743a1f3cd7d60ea26bc46e9e2638c`, parent `f5f7987a534a518f3019b7aced28be970f18ad0d`,
branch `codex/package-k1c-receipt-attestations`. [CHECKS.json](CHECKS.json) was generated before the source commit.
It binds all source blobs, exact commands/cwd/exits, logs, final gates and earlier failures.
No K publication or operational acceptance is claimed.

Changed source/test files:

- `api/src/gorgona_booking/db/bootstrap.py`
- `api/src/gorgona_booking/db/pool.py`
- `api/src/gorgona_booking/db/provider_receipt_guard.py`
- `api/src/gorgona_booking/db/migrations/0045_provider_receipt_attestations.sql`
- `api/src/gorgona_booking/providers/authenticated_receipts.py`
- `api/tests/integration/test_location_access.py`
- `api/tests/integration/test_provider_receipt_upgrade.py`
- `api/tests/integration/test_provider_attestation_upgrade.py`
- `api/tests/integration/test_provider_receipt_attestations.py`
- `api/tests/unit/test_receipt_writer_bootstrap.py`
- `api/tests/integration/test_h3_upgrade.py`
- `api/tests/integration/test_fixture_copy_budget.py`
- `web/components/my-shifts.tsx`
- `web/tests/workforce-situations.spec.ts`

Migration0045 adds an append-only attestation linked to one exact archived delivery,
with opaque verification-config UUID, derived connection/book, verifier version,
writer role and timestamp. Ordinary runtime has SELECT only. A dedicated non-owner
writer group/login has receipt-table privileges and no unrelated business/finance
table rights. Existing archive remains ordinary-runtime-writable and untrusted.
The raw-body entry point verifies K1a before DB access, refuses unsafe current/session/
parent roles, owns the outer transaction and returns only after commit. Archive and
attestation roll back together. Existing manual financial attestation is unchanged.
The required full suite also exposed an existing MyShifts stale-response race.
A deliberately delayed real response reproduces it;only the newest load may publish
screen data,and effect cleanup invalidates pending loads. No timeout increase or retry.

| Gate | Exact observed outcome |
|---|---|
| New cases | PASS:40 pytest cases in full JUnit;2 browser response-ordering cases |
| Narrow integration/upgrade/role/guard set | PASS:57 passed in32.02s before final journal assertion |
| Copy-budget regression / real scale and upgrades | PASS:1 passed in10.51s;5 passed in130.84s |
| Final focused PostgreSQL18.6 | PASS:369 passed in 322.44s (0:05:22) |
| Full disposable PostgreSQL18.6/browser suite | PASS:1930 passed, 4 skipped in 1685.52s (0:28:05) |
| Ruff check/format, strict mypy | PASS:exit0;309 source files |
| Web typecheck/lint/format/unit/build | PASS:exit0;114 unit tests |
| Runtime npm audit | PASS:0 vulnerabilities |
| Existing development npm audit | FAIL:5 high;unchanged dependencies/lock,nonrequired limitation |
| Container image / optional external site | NOT TESTED:3 container skips +1 optional historical site skip |
| Exact K CI / independent security review | NOT TESTED:no K publication;inline work only |
| Actual provider account/keys/admission | BLOCKED:separate direct owner authorization and actual evidence required |

Two races observed actual transaction-ID waits in pg_locks on the attestation INSERT,
then checked leader commit and rollback. Deferred COMMIT failure rolls back archive
and attestation before return; nested outer transactions are refused. This is not
process-kill/power-loss or raw HTTP acknowledgement proof. Nonempty0044 upgrade
preserves all prior rows and44 checksums and creates zero attestations; reapply is a no-op.
Tests also cover runtime SQL/SET ROLE denials, NOINHERIT dangerous ancestry, signature-
before-DB, company/tenant RLS, revoked bindings, scope mismatch, duplicates/conflicts,
legacy archive poisoning and writer privilege/schema drift. No financial journal added.

Preserved failures:initial missing-module RED;dev2 had8 failed/33 passed (early nested
result,2 misplaced test assertions,old upgrade bound,4 cascading policy-restoration
failures). Separate role RED had2 expected failures for SET ROLE/session and dangerous
NOINHERIT parent. Repr RED had1 failed/7 passed with source-declared FAKE unit values;
actual generated credentials were not printed. Static-1 had1 mypy error in the test
override mapping;TypedDict fixed it.

Full-2 was interrupted with1 failed,940 passed,3 skipped in2380.26s(39:40):a historical
test-fixture copy query became pathologically slow after the100000-row scale fixture.
Only the owned pytest/source SQL was diagnosed and canceled;normal teardown stopped
its own cluster. LIVE_STACK/LIVE_QUERY_PLAN/FULL2_INTERRUPTION are preserved externally.
The fresh estimated EXPLAIN was not the already-running plan. The historical-copy
correction changed test SQL only.
The diagnostic scripts target historical PIDs;never rerun them at a later state.
A new real-PostgreSQL minimal synthetic regression forced nested loops and a2s per-query
source budget:RED1 failed by statement timeout;GREEN1 passed in10.51s after computing
incompatible tenant IDs once. Ordinary journals are preserved and incompatible stock
rows excluded as before. The minimal fixture is not product migration proof. Separate
scale-upgrade-green verified100016 movements+valuations and real upgrades:5 passed
in130.84s.

Full-3 was stopped after an observed actual failure:1 failed,488 passed,3 skipped
in974.10s. The old Workforce pagination scenario showed zero open shifts after a date
change. A natural narrow repeat passed(1 pytest/16 browser cases),so it did not establish
a correction. A controlled delayed-old-response browser regression was then added before
the production fix. Three harness prototypes failed before valid synchronization:
the first blocked the initial form(54.51s),the second timed out then cleanup reported a closed page(279.64s),
the third waited for global networkidle(278.85s). These are harness failures,not
product RED evidence. The final control waits only concrete workforce requests
and the completed load's paint. Red-stale-response4 then failed the final expected12
with actual0(1 failed in73.65s),after initially showing12. MyShifts now invalidates obsolete loads before publishing any state;
2 new desktop/mobile response-ordering cases pass in final full. No wait increase or skip was used.
Focused-4 then passed the forced desktop case but failed the mobile harness assertion
that the old list was entirely empty:prior desktop scenarios legitimately added2 other
shifts. The corrected precondition checks zero selected-date-tag matches;the final12
selected shifts and exact old-load completion barrier remain required.
Only the validated own full-3 pytest child received a normal pytest stop;its cluster
was stopped by the runner. FULL3_FAILURE and its historical PID script are preserved
as evidence;never rerun that script. Final gates did not ignore or skip earlier failures.

Exact PowerShell gate entry commands;cwd
`C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`:

```powershell
& 'C:\Users\alexa\.codex\worktrees\package-j-review2-fixes\Gorgona Booking\api\.venv\Scripts\python.exe' 'C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1c-20261016-f5f7987\runner.py' static-5 static
& 'C:\Users\alexa\.codex\worktrees\package-j-review2-fixes\Gorgona Booking\api\.venv\Scripts\python.exe' 'C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1c-20261016-f5f7987\runner.py' focused-5 focused 'tests/integration/test_i4_situations_browser.py' 'tests/integration/test_fixture_copy_budget.py' 'tests/integration/test_h3_upgrade.py' 'tests/integration/test_stock_upgrade.py' 'tests/integration/test_provider_admission_upgrade.py' 'tests/integration/test_workforce_upgrade.py' 'tests/integration/test_location_access.py' 'tests/integration/test_provider_event_inbox.py' 'tests/integration/test_provider_receipt_guard_review.py' 'tests/integration/test_provider_receipt_attestations.py' 'tests/integration/test_provider_attestation_upgrade.py' 'tests/unit/test_receipt_writer_bootstrap.py' 'tests/integration/test_roles_and_migrations.py' 'tests/integration/test_ledger.py' 'tests/integration/test_provider_receipt_upgrade.py' 'tests/unit/test_migration_files.py' 'tests/unit/test_stripe_event_boundary.py' 'tests/unit/test_provider_admission_contracts.py' 'tests/unit/test_settlement_contracts.py' 'tests/unit/test_payment_correction_contracts.py' 'tests/integration/test_provider_admission.py' 'tests/integration/test_external_payments.py'
& 'C:\Users\alexa\.codex\worktrees\package-j-review2-fixes\Gorgona Booking\api\.venv\Scripts\python.exe' 'C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1c-20261016-f5f7987\runner.py' full-5 full
```

The runner sets its private disposable-cluster environment and uses api as pytest cwd.
Use a new phase name on a fresh cluster;these names already exist. All owned clusters
were stopped and temporary password files removed. No other checkouts/processes or
ports51454/51458/51474/51511 were changed. Run folder `C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1c-20261016-f5f7987` has runner.py, run_gates.py,
write_record.py, update_docs.py, validate_docs.py, STATE.md, redacted logs/results/JUnit.
Record expects BASE before source commit;docs updater expects its source child. Do not
rerun state-bound helpers against later HEAD.

Full K1/K-01–K-14 NOT TESTED. FIN-02/STOCK-01 planned,ADR0026/0027 Proposed.0001–0044
unchanged,new0045,next0046. Remote main=fedd0f1,published J=df88c20. No K push/PR/deploy.
[Architecture/reuse](ARCHITECTURE_REUSE.md),[self-review and limits](SELF_REVIEW.md).

Documentation files in the following docs commit:

- `docs/plan/evidence/2026-10-16-k1c-receipt-attestations/CHECKS.json`
- `docs/plan/evidence/2026-10-16-k1c-receipt-attestations/VALIDATION.md`
- `docs/plan/evidence/2026-10-16-k1c-receipt-attestations/ARCHITECTURE_REUSE.md`
- `docs/plan/evidence/2026-10-16-k1c-receipt-attestations/SELF_REVIEW.md`
- `docs/plan/NEXT_AGENT_PACKAGE_K1C_2026-10-16.md`
- `docs/plan/NEXT_AGENT_PACKAGE_K1C_PROMPT_2026-10-16.md`
- `CLOUD_CODE_HANDOFF.md`
- `docs/plan/GORGONA_MASTER_PLAN.md`
- `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md`
- `docs/plan/PACKAGE_K_PLAN_2026-10-15.md`
- `docs/adr/0027-provider-events-and-reconciliation.md`
- `docs/plan/NEXT_AGENT_PACKAGE_K1B_REVIEW_2026-10-15.md`
