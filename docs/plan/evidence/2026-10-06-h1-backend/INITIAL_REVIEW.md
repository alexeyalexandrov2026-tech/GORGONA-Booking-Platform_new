# Independent H1 backend review — ac7726e

Status: **FAIL / changes required** for the bounded backend slice. One concrete readiness/lineage defence gap remains. This is not FIN-03 acceptance.

## Finding

**H1-R01 (P2): H CHECK drift does not fail readiness.** `api/src/gorgona_booking/db/financial_guard.py` validates triggers/functions, policies, keys, foreign keys, columns and privileges, but its CHECK approval is limited to the G journal source-kind constraint (lines 186–198). It does not approve the H CHECK inventory, predicate or validated status.

Independently reproduced against this exact snapshot: in a throwaway fixture database on the reviewer's private PostgreSQL 18.6 cluster, remove `gba.financial_obligations.financial_obligations_source_kind_check`, then call `GET /health/ready`. Actual result: HTTP **200**, `{"status":"ready","checks":{"database":"ok"}}`; required result: 503. The external negative regression failed with **1 failed in 2.75s**. Its `finally` restored the constraint, fixture teardown dropped the database, and the reviewer stopped the owned cluster.

The coupled assertion in `0021_invoice_accrual.sql:366–378` compares most obligation fields but omits `source_kind` and `component`; its operation-link lookup omits `component`. Those semantics depend on CHECKs that readiness does not verify. Wrong-money execution was not claimed or reproduced by this probe.

Required closure: approve the complete repository-owned H CHECK inventory, literal-preserving predicates and `convalidated` status; reject missing, weakened, substituted or unvalidated constraints. Independently require obligation `source_kind = 'invoice'`, obligation `component = 'principal'` and link `component = 'principal'` in the coupled assertion. Add negative regressions and rerun on the corrected exact SHA. The implementer has acknowledged this finding; no corrected source was reviewed here.

## Reviewed behavior

Read the 18 changed code/test files between `18e3f5e53b24a7590ef035df7fe3ae41521dc740` and `ac7726e769c739f2fa94de644763159d1350ef70` in the separate, clean checkout `C:\Users\alexa\.codex\worktrees\package-g-final-review\Gorgona Booking`, branch `codex/package-h1-backend-review`.

No other concrete correctness defect found in this bounded review. The deferred assertions are attached to H versions/lines/anchors/obligations/links and G headers/lines, so late balanced G-line insertion and same-transaction draft→issue→late draft-line insertion recheck the final graph. Private transaction defaults prevent later-transaction filling. Exact issued copies and journal-line multisets, current period/scope/currency/account checks, invoice-origin linkage and generic reversal refusal preserve G balance invariants. Permanent receipts, replay after ordinary receipt expiry, cancellation sealing and recovery are finite and keep actor/operation/key/subject checks. Current readiness withdrawal blocks new H commands while existing G remains usable. V1 journal reads require explicit upgrade when invoice entries exist, and V2 reads/trial balance retain those entries.

## Independent checks

Python executable: `C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe`. `PYTHONPATH` pointed exclusively to the review checkout's `api\src`; bytecode/cache writes were disabled or redirected outside source.

| Check | Result |
|---|---|
| `python -m pytest tests/unit/test_financial_documents.py tests/unit/test_configuration_contracts.py tests/unit/test_ledger_contracts.py tests/unit/test_document_contracts.py -q -p no:cacheprovider` | PASS: 109 tests, 0.94s |
| Scoped `python -m ruff check --no-cache`, `python -m ruff format --check --no-cache` on the 13 changed Python files | PASS: all checks; 13 files formatted |
| Scoped `python -m mypy --no-incremental --cache-dir <owned-external-cache>` on those 13 files, repository strict configuration | PASS: no issues in 13 source files |
| `git diff --check 18e3f5e53b24a7590ef035df7fe3ae41521dc740..ac7726e769c739f2fa94de644763159d1350ef70` | PASS |
| `python -m pytest -c <review-api/pyproject.toml> tests/integration/test_invoice_issue.py tests/integration/test_ledger.py tests/integration/test_configurations.py tests/integration/test_location_access.py <external-negative-probe> -q -p no:cacheprovider --basetemp <owned-temp> --tb=short` | 107 normal tests PASS in 54.67s; initial external probe setup ERROR due to missing fixture aliases |
| Corrected external probe only, same pytest options | FAIL: missing obligation source CHECK leaves readiness 200; 1 failed in 2.75s |

The fixture alias repair touched only the external probe, not repository code. The earlier setup error is a harness failure and is not counted as a source finding. The 107 ordinary PostgreSQL tests were not needlessly rerun after that repair.

Private cluster: new target `%LOCALAPPDATA%\GorgonaBookingTests\package-h1-independent-review-51460`, loopback port **51460**, verified absent/free before creation. Credentials were generated privately outside Git and not printed or copied. Test fixtures ran sequentially. Stop returned 0; final PID file absent and port listener count 0. Historical 51458 and root 51456 were not accessed for SQL or changed. Prior review branches and reports were preserved; review checkout is clean at the reviewed SHA.

## Boundaries

Independent full suite, browser execution, web build/type/lint/test execution and exact-SHA remote CI: **NOT TESTED** in this review. Web journal V2 changes were reviewed statically. Implementer results are not used as independent proof.

H invoice UI, payment/reserve/release/refund/credit/provider execution and full FIN-03: **NOT IMPLEMENTED / NOT TESTED** here. `finance_documents` remains planned and closed in the real registry; positive enablement exists only in isolated development integration fixtures. This report approves neither owner product rules nor FIN-03 promotion, publishing, merge, deployment or production migration.
