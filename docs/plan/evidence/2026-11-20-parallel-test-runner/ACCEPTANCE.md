# Parallel full-suite test runner on gorgona-dev

**PASS on gorgona-dev (3/3 consecutive full parallel runs).** Full VM test execution drops from
~53 minutes (`3182.8 s` serial) to **~19.6 minutes** (`1191.4 s`, `1176.5 s`, `1197.1 s`) on
8 vCPUs (`Standard_D8as_v6`) with zero lost tests (`2975/2975`), zero duplicates, and zero failures
or flakes across three consecutive runs. Default serial `uv run pytest` and GitHub Actions CI
remain unchanged. [Checks](CHECKS.json)

## Architecture and quality guarantees

| Requirement | Implementation | Evidence |
|---|---|---|
| One disposable PostgreSQL, one DB per worker from a template DB | `create_template_and_clones()` runs `bootstrap()` (creating `gba_test_owner`, `gba_test_app`, `gba_test_receipt_writer`, `gba_test_receipt_worker`) and `apply_migrations()` once on `gba_test_tpl_<id>` (~2.8 s), then clones 7 databases via `CREATE DATABASE ... TEMPLATE` with identical `CONNECT` grants. `conftest.py`, `writer_pool`, and `worker_pool` use the pre-cloned DB when `GBA_TEST_PREBUILT_DB` is set and behave identically to serial pytest when unset. | Template + 7 clones created in `2.91 s`, `2.80 s`, `2.77 s` across the 3 runs. |
| Global-state and DDL-mutating tests isolated in serial lane | `SERIAL_FILES` (`14 files / 216 tests`) runs on its own fresh bootstrapped database after the parallel and browser lanes complete. Starts with `test_location_access.py` followed immediately by `test_delegations.py` and `test_r09_rental_problem_reports.py` in the same pytest session, plus all tests that mutate cluster roles (`pg_auth_members`) or drop shared functions. `test_all_cluster_role_and_function_drop_tests_are_in_serial_lane` statically enforces this invariant across `tests/integration/test_*.py`. | Diagnostic run v1 exposed `test_provider_receipt_decisions.py` temporarily granting `gba_receipt_worker`/`gba_receipt_writer` at cluster level; moving it and `test_provider_event_inbox.py` to `SERIAL_FILES` + adding the static unit test eliminated the race completely (`0` failures across all 3 consecutive runs). |
| Dedicated browser lane | All 41 `test_*_browser.py` files (`46 tests`) run sequentially in one dedicated browser lane against its own cloned DB while the 6 API workers run in parallel, preventing `web/test-results/` races and Chromium CPU starvation. | `46/46` browser tests passed in all 3 runs (`1089.6 s`, `1081.7 s`, `1102.5 s`), including `test_l7a_catalog_browser` (3/3 first-try passes). |
| Same test count (zero lost tests, zero duplicates) | `collect_suite()` runs `pytest --collect-only -q` (`2975` tests across `350` files), `partition_files()` asserts pairwise disjointness and exact union before running, and `main()` parses all JUnit XML files to verify `executed == expected == unique == 2975`. | `count_ok=True`, `expected=2975`, `tests=2975`, `duplicates=0` in all 3 consecutive runs. |

## Consecutive full parallel runs on gorgona-dev (`9c555f8`, tree `c94c5c2`)

| Run | Wall time | Template + 7 clones | 6 API workers (min–max) | Browser lane (46 tests) | Serial lane (216 tests) | Total result |
|---|---:|---:|---:|---:|---:|---|
| Diagnostic v1 (before moving `test_provider_receipt_decisions.py` to serial) | `1175.6 s` (19m 35s) | `2.82 s` | `508.0–614.6 s` | `1103.1 s` (46/46) | `61.3 s` (136/136) | `2974` collected (`+1` unit test): `2968 passed, 2 failed, 4 skipped` (`provider_receipt_guard` saw concurrent cluster-role grant) |
| **Consecutive Run 1** | **`1191.4 s` (19m 51s)** | `2.91 s` | `469.4–596.7 s` | `1089.6 s` (46/46) | `95.0 s` (216/216) | **`2975` tests: `2971 passed, 0 failed, 4 skipped, 0 duplicates`** |
| **Consecutive Run 2** | **`1176.5 s` (19m 36s)** | `2.80 s` | `454.2–589.9 s` | `1081.7 s` (46/46) | `88.1 s` (216/216) | **`2975` tests: `2971 passed, 0 failed, 4 skipped, 0 duplicates`** |
| **Consecutive Run 3** | **`1197.1 s` (19m 57s)** | `2.77 s` | `480.7–624.7 s` | `1102.5 s` (46/46) | `87.8 s` (216/216) | **`2975` tests: `2971 passed, 0 failed, 4 skipped, 0 duplicates`** |

Test count reconciliation against serial baseline:
- Previous combined R-10 serial full suite (`b2a6fac`): `2973` tests (`2969 passed, 4 skipped`).
- Parallel runner commit (`9c555f8`): adds 2 unit tests in `api/tests/unit/test_parallel_runner.py`
  (`2973 + 2 = 2975` tests: `2971 passed, 4 skipped`).
- The 4 VM skips are identical in every run: 3 container tests (`GBA_REQUIRE_CONTAINER=1`) and
  1 external tenant-site test (`GBA_REQUIRE_TENANT_SITE=1`).

## Usage

```bash
cd api
uv run --locked python -m tools.run_parallel_tests --workers 6 --out-dir /var/tmp/gba-parallel-run
```
