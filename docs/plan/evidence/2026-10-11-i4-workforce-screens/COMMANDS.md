# I4 exact command and outcome ledger — 2026-10-11

API commands ran from `api` of the canonical checkout through the author's runner.
The runner sets `PYTHONPATH` to this checkout's `api/src` and `api`,
`GBA_REQUIRE_POSTGRES=1`, with `--browser` also `GBA_REQUIRE_BROWSER=1`, takes the
connection from a private file and redacts it from the output. It adds
`-p no:cacheprovider --basetemp <new temporary folder>` to every pytest call.
PostgreSQL 18.6 was the author's own cluster on 127.0.0.1:51474, started with
`-o "-p 51474 -c max_connections=400 -c listen_addresses=127.0.0.1"`. Below,
`run` stands for that runner. No connection value or secret appears here.

Web commands ran from `web` with `C:/Program Files/nodejs` first on `PATH`.

Versions: Python 3.14, Node 24, PostgreSQL 18.6, as in I3.

## Start

```text
git -C <checkout> rev-parse --abbrev-ref HEAD   -> codex/package-i3-timesheets
git -C <checkout> rev-parse HEAD                -> d22b61cf53612ab85c157c00ecd75fd1630ba1c2
git -C <checkout> status --porcelain            -> empty
git -C <checkout> switch -c codex/package-i4-workforce-screens
run pytest -q tests/integration/test_timesheets.py tests/unit/test_timesheet_contracts.py --tb=short
```

Baseline PASS 16 / 5.18 s on the untouched I3 tree.

## API support: red, then green

```text
run pytest -q tests/integration/test_workforce_desk.py --tb=line
```

FAIL 7 / 6.56 s before the routes existed (404 from every new route).

```text
run pytest -q tests/integration/test_workforce_desk.py --tb=short
run pytest -q tests/unit/test_workforce_desk_contracts.py tests/integration/test_workforce_desk.py --tb=short
```

PASS 7 / 8.57 s after the implementation; PASS 10 / 8.73 s with the contract unit
tests. Commit `e480a4e`.

## Web library: red, then green

```text
npx playwright test tests/workforce-contracts.spec.ts --project=desktop
```

FAIL: the spec could not be loaded, because `lib/workforce-recovery` did not exist
("No tests found"). After the recovery module and the client: 6 passed, 1 failed —
the test expected an unknown workforce route to return a failing schema, while
`managementResponseSchema` throws for it. The test was corrected to expect the
throw. PASS 7 / 0.76 s. Commit `ae8501e`.

## Screens

```text
npm run typecheck
npm run lint
npm run build
```

Exit 0 each; 23 static pages (20 before I4). Commit `b7caec8`.

## Real browser: every run, in order

```text
run --browser pytest -q -s tests/integration/test_i4_browser.py --tb=short
```

| Run | Result | Cause and correction |
|---|---|---|
| 1 | FAIL 1 / 2.65 s | Fixture: display labels with spaces produced an invalid test e-mail. Labels changed to `i4-…` |
| 2 | FAIL 1 / 34.28 s; closed phase 2 passed | Test: a select wrapped by its label is not found by label text. Selects are located by role and name |
| 3 | FAIL 1; closed phase 2 passed (pytest time not captured: the runner's own log line failed to encode) | **Product:** "Versions" listed 1 version instead of 2, because the success message appeared before the list was reloaded. The message now follows the reload |
| 4 | FAIL 1 / 49.55 s; desktop enabled phase passed in 30.6 s | Test: on the phone run the colleague of the desktop run already held a skill, so a text matched twice. The assertion is scoped to the skill |
| 5 | **PASS 1 / 93.40 s** | closed 2, enabled 2 (31.0 s and 34.3 s), switched off 2 Playwright tests; database counts asserted. Commit `7442ff7` |
| 6 | **PASS 1 / 92.97 s** | After the author's review corrections and a rebuild. Commit `f4a7395` |

## Cancel races

```text
run pytest -q tests/integration/test_workforce_desk_races.py tests/integration/test_workforce_desk.py tests/unit/test_workforce_desk_contracts.py --tb=short
```

PASS 12 / 10.26 s. Both races fail unless the second transaction is observed
waiting in `pg_locks` (`locktype='transactionid'`, not granted) for the first
one's uncommitted receipt key.

## Complete suites

```text
run --browser pytest -q -ra --tb=short
```

First complete run, on `7442ff7` with the web export built from it: PASS
1484 passed / 4 skipped / 931.53 s. It does not cover the later corrections.

Final complete run, on `f4a7395` with the web export rebuilt from it: PASS
1486 passed / 4 skipped / 907.37 s.

The four skips are the three container checks (`GBA_REQUIRE_CONTAINER=1`) and the
optional external tenant site (`GBA_REQUIRE_TENANT_SITE=1`). They are not counted
as PASS.

## Static and web gates on the final tree

```text
run -m ruff check src tests
run -m ruff format --check src tests
run -m mypy src tests
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
npm audit --omit=dev --json
```

Ruff: exit 0. Format: 261 files already formatted. Mypy: no issues in 261 source
files. Typecheck, lint, format: exit 0. Unit: 101 passed / 1.4 s (94 before I4 and
7 new). Build: exit 0, 23 static pages. Audit: FAIL exit 1, 2 high in the
inherited production tree (`next`, `source-map-js`); no dependency file changed
and `npm audit fix` was not run.

Earlier static failures during the work, all corrected: Ruff format wanted two new
files reformatted; mypy reported three annotation errors in `test_i4_browser.py`.

## Not run

Exact-commit CI (the branch is local), containers, the optional external tenant
site, HawkScan (no scanner runtime or key on this machine), load, soak,
deployment and production.
