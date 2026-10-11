# Shift-visibility setting: exact command and outcome ledger — 2026-10-11

API commands ran from `api` of the canonical checkout through the author's runner,
as in the [I4 ledger](../2026-10-11-i4-workforce-screens/COMMANDS.md): it sets
`PYTHONPATH`, `GBA_REQUIRE_POSTGRES=1`, with `--browser` also
`GBA_REQUIRE_BROWSER=1`, takes the connection from a private file, redacts it and
adds `-p no:cacheprovider --basetemp <new temporary folder>` to every pytest call.
PostgreSQL 18.6 was the author's own cluster on 127.0.0.1:51474, started with
`-o "-p 51474 -c max_connections=400 -c listen_addresses=127.0.0.1"`. Below,
`run` stands for that runner. No connection value or secret appears here.

Web commands ran from `web` with `C:/Program Files/nodejs` first on `PATH`.

## Start and publication

```text
git -C <checkout> rev-parse --abbrev-ref HEAD   -> codex/package-i4-workforce-screens
git -C <checkout> rev-parse HEAD                -> 5f0e58fe124e9668c94f3088fe3a660b5e476877
git -C <checkout> status --porcelain            -> empty
git ls-remote --heads origin "codex/package-i*" -> 0 refs
git push -u origin codex/package-i4-workforce-screens
```

The owner allowed publishing this branch on 2026-10-11. Before the push the
twelve commits above the published `codex/package-h-acceptance` (`9ef3734`) were
searched for secret patterns: 0 matches. Push: new branch, remote head equal to
the local one. `.github/workflows/ci.yml` runs on every push; run 38132277248 for
`5f0e58f` ended `success` (job `api`, 2026-10-11 10:31–10:48 UTC). No PR was
opened.

```text
run pytest -q tests/integration/test_workforce_desk.py tests/integration/test_workforce_desk_races.py tests/unit/test_workforce_desk_contracts.py tests/integration/test_timesheet_upgrade.py --tb=short
```

Baseline PASS 13 / 15.02s on the untouched tree.

## Schema and API: red, then green

```text
run pytest -q tests/integration/test_workforce_visibility.py --tb=line
```

FAIL 9 / 7.61s before the schema and routes existed (the relation did not exist).

```text
run pytest -q tests/integration/test_workforce_visibility.py tests/unit/test_workforce_desk_contracts.py tests/integration/test_workforce_desk.py --tb=short
```

After the migration and the routes: 1 failed, 18 passed / 17.97s. The failure was
in the test: it ordered audit events by a column that does not exist. Corrected
to order by id.

```text
run pytest -q tests/integration/test_workforce_visibility.py tests/unit/test_workforce_desk_contracts.py tests/integration/test_workforce_desk.py tests/integration/test_workforce_desk_races.py tests/integration/test_timesheet_upgrade.py tests/integration/test_location_access.py tests/integration/test_workforce.py tests/integration/test_workforce_guards.py --tb=short
```

PASS 83 / 60.74s, with the branch-policy restore and the I1 guard tests.

## Upgrade and race

```text
run pytest -q tests/integration/test_workforce_visibility.py tests/integration/test_workforce_visibility_upgrade.py tests/integration/test_timesheet_upgrade.py tests/integration/test_shift_changes_upgrade.py tests/integration/test_workforce_upgrade.py --tb=short
```

1 failed, 13 passed / 22.52s: the new upgrade test assumed one change request in
the fixture and found two. The assertion now requires at least one. Then PASS
14 / 15.01s with the contract tests. The I3 upgrade test was changed to apply
exactly `0034` and to expect that the current application, which also needs
`0035`, is not ready on that older schema; the new test upgrades a nonempty
`0034` database to `0035`.

The race test fails unless the second transaction is observed in `pg_locks`
waiting, not granted, for the advisory lock of exactly that business and branch.

## Static checks during the work

```text
run -m ruff check src tests
run -m ruff format --check src tests
run -m mypy src tests
```

Ruff first reported 4 findings in the new tests (two multi-statement
`pytest.raises` blocks, two unused imports); mypy reported 2 errors in a test
helper. All corrected. Then PASS 36 / 32.75s on the focused set.

## A participant reads the shifts of their own request

```text
run pytest -q tests/integration/test_workforce_visibility.py -k participants --tb=line
```

FAIL 1 / 2.77s before the route existed (404). After the route: 1 failed,
21 passed / 19.93s — the test created two overlapping shifts for one person. The
second shift was moved to another hour: PASS 23 / 24.23s.

## Web

```text
npx playwright test tests/workforce-contracts.spec.ts --project=desktop
npm run typecheck
npm run lint
npm run format:check
npm run build
```

Contracts: 1 failed, 6 passed — the desk sample of the existing test lacked the
new field. After the update and a new case: PASS 8. Typecheck, lint, format:
exit 0. Build: exit 0, 23 static pages.

## Real browser

```text
run --browser pytest -q -s tests/integration/test_i4_browser.py --tb=short
```

| Run | Result | Tree |
|---|---|---|
| 1 | **PASS 1 / 108.35s** — closed 2, enabled 2 (37.6s and 40.2s), switched off 2 Playwright tests; database counts asserted | the extended scenario at its first run, before the lookup-scope commit |
| 2 | **PASS 1 / 103.56s** | final code `419eda8` |

## The author's re-read: one more commit

```text
run pytest -q tests/integration/test_workforce_visibility.py tests/integration/test_workforce_desk.py tests/integration/test_workforce_visibility_upgrade.py tests/unit/test_workforce_desk_contracts.py --tb=short
```

PASS 24 / 26.70s after the colleague lookup returned to the caller's own scope
and a test for a company-wide member was added. That test was also run against
the earlier order: it passed there too, so no defect was demonstrated.

A first complete run was stopped by the author after a few minutes to make that
change; it produced no result and is not counted.

## Complete suite and gates on the final tree

```text
run --browser pytest -q -ra --tb=short
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

Complete suite on `419eda8`, with the web export built from the same web
sources: PASS 1500 passed / 4 skipped / 953.19s. The 4 skips are the three container checks and the
optional external tenant site; they are not counted as PASS.

Ruff: exit 0. Format: 263 files already formatted. Mypy: no issues in
263 source files. Typecheck, lint, format: exit 0. Unit: 102 passed.
Build: exit 0, 23 static pages. Audit: FAIL exit 1, 2 high in the inherited
production tree (`next`, `source-map-js`); no dependency file changed.

## Not run

Containers, the optional external tenant site, HawkScan (no scanner runtime or
key on this machine), load, soak, deployment and production. CI of the head that
carries this record starts on its push and is read on GitHub.
