# Package J — J5/J6 review fixes, part 2, completed 2026-10-15 (started 2026-10-14)

PASS locally on the source bytes of `7b96feca22b430d0ea98ef8081ac89cf7e292fc6`. Branch `codex/package-j-review2-fixes`,
base `abbdfeb06bedb6632317f1427a59f8b9e8ecbf47`. No migration or dependency changed.
STOCK-01 remains `planned`; ADR-0026 remains Proposed. Technical acceptance J-01–J-14
is the next separate step; readiness needs the owner's explicit word.

## Changes and architecture reuse

- M1: both screens follow every cursor for materials, places and balances; Materials
  follows every cost cursor too. Each page still uses the existing typed response
  contract, authentication and tenant check. A repeated cursor fails closed and a
  partial catalogue is never installed. Document history retains its existing Show more.
- M1: a return line is refused when its material is not loaded; no assumed scale 0.
- L2: a separate exact-decimal document total supports up to 999,999,999,999,999,999
  minor units, without floating point or expansion of the line-amount bound. Malformed
  text is rejected before BigInt conversion. Boundary tests cover JPY, USD and KWD text.
- L3: executeInventoryCommand compares item_id, place_id, book_id or document_id with
  the sent subject after the existing schema and business checks. A mismatched response
  retains uncertain-command recovery, never presents success.
- Race gap 2: two transfers leave different source balances for one new destination.
  pg_locks shows an ungranted transaction-id lock on the leader, pg_blocking_pids names
  that leader, and pg_stat_activity shows the movement INSERT whose inbound trigger
  inserts the destination balance. With distinct sources, no source-row wait can satisfy
  the assertion. Both destination history links and both source histories reconcile.

Acceptance coverage J-13 now directly revokes the fixture readiness after posting: new material/place/rules and all four document kinds are refused; history and committed/cancelled command recovery remain readable. It passed on first run; no server fix was necessary. The real readiness registry is untouched.

No server data-contract shape, tenant policy, constraint, index or migration was changed. The client total bound now matches the existing server bound. The existing
0042 inbound trigger and ordered balance locking are reused; 0043 stays intact.
PostgreSQL lock interpretation: [official pg_locks documentation](https://www.postgresql.org/docs/18/view-pg-locks.html).

## Verification

[CHECKS.json](CHECKS.json) was written with write_record.py **before the code commit**.
It binds all 9 changed source files by SHA-256 and Git blob oid,
records exact commands, tool versions, phase results and log hashes. Both sources and
built site stayed unchanged during focused and full runs. Every completed database phase used a
new disposable PostgreSQL 18.6 cluster; its runner stopped it, with no postmaster.pid left.
The interrupted full-1 has a stale pidfile and preserved data; its recorded processes were absent on resumption.

| Check | Result |
|---|---|
| red-l2.log, new total boundary test before fix | FAIL as expected: legal JPY total rejected |
| red-browser, old build | FAIL as expected: first 100 materials only, unknown return material enabled, wrong item/document subject accepted; two incorrect test locators were corrected before green |
| red-race, strengthened assertion with old same-source setup | FAIL as expected: follower never reached destination insert |
| static-1 | FAIL: 1 failed, 113 passed web tests; malformed total reached BigInt; corrected, existing rejection test preserved |
| focused-3 | FAIL: 1 failed, 140 passed; mobile test navigated before its save finished because desktop had saved the same name; unique per-device names and exact success/row waits fix the test |
| focused-2 | PASS: 140 passed in 204.21s; before adding J-13 coverage |
| acceptance-j13 | PASS: 1 passed, 5 deselected in 5.07s, no server change |
| focused-1 | FAIL: repeated-cursor test locator matched both the error and Next route announcer; scoped to Materials, 139 Python and 12 new browser cases passed |
| static-5 | PASS: Ruff check/format, strict mypy, tsc, ESLint, Prettier, 114 web tests, production build |
| npm audit --omit=dev --json | PASS: 0 vulnerabilities |
| npm audit --json | FAIL: existing 5 high development-only findings (eslint-config-next chain), unchanged dependencies |
| focused-4, fresh PostgreSQL | PASS: 141 passed in 212.19s (0:03:32) |
| full-1 | NOT TESTED to completion: interrupted at 61%, test and cluster PIDs absent on 2026-10-15, no final summary; original evidence/data preserved |
| full-2, fresh PostgreSQL | PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08) |
| predecessor CI run 156 on abbdfeb | completed / success; observed via public GitHub REST API |
| exact part-2 commit CI | NOT TESTED at this pre-publication record; publish branch without PR, then read CI |
| local container, external site | NOT TESTED / skipped; exact four skips are in the full log |
| Azure, production, readiness promotion | NOT TESTED; not authorized |

Existing M2 regression, same current schema before/after loading history (no new
optimization claim and not a rerun of the historical pre-0042 960-to-43 ms comparison):

```text
M2 history: 100016 movements and 100016 valuations of one material, place and owner (seeded in 3.5 s)
before: median 54.9 ms, min 46.6 ms, max 70.3 ms, n=15
after: median 128.7 ms, min 123.7 ms, max 161.4 ms, n=15
```

Run folder: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-jr2p2-20261014-abbdfeb`. Commands (from the supplied checkout, use its own
`api/.venv/Scripts/python.exe`, installed with `uv sync --frozen`):

```text
python <run-folder>/runner.py static-5 static
python <run-folder>/runner.py focused-4 focused tests/integration/test_stock_running_totals.py tests/integration/test_stock_documents_browser.py tests/integration/test_materials_browser.py tests/integration/test_stock_acceptance.py tests/integration/test_stock_guards.py tests/integration/test_inventory_commands.py tests/unit/test_stock_contracts.py tests/unit/test_inventory_contracts.py
python <run-folder>/runner.py full-2 full
python <run-folder>/write_record.py full-2 red-browser red-race static-1 static-2 static-3 static-4 static-5 focused-1 focused-2 focused-3 acceptance-j13 focused-4 full-1
```

## Limits and rollback

L1: intermediate balance_after/quantity_after/value_after values backfilled by 0042 are approximate: transaction ids order transaction starts, not commit order; final totals remain the authoritative reconciliation. L4: cancellation tombstones expire after 24 hours with idempotency keys; a late command after expiry can be executed. These are recorded limits, not fixes. Earlier review L6: migrations 0037 and 0042 require a maintenance window and coordinated application/schema deployment; no deployment is authorized. The platform-wide current-user/current-tenant function body guard remains outside Package J. Review-2 gaps 3–5 remain unmeasured or untested as described in REVIEW.md; no new claim closes them. Additional pre-existing UI follow-up, confirmed by code inspection only: DocumentForm filters archived materials and places out of outbound selectors too, although the API permits supported outbound operations. This slice preserves that UI behavior; browser validation of that gap is NOT TESTED (web/components/stock-documents.tsx, open/usable selectors).

No independent reviewer was spawned for these changes: the owner asked to work inline.
The prior independent reviews and their findings are preserved; self-review and tests
are direct evidence here. Before deployment, reverting this code commit restores prior
client behavior; no database rollback is required. No PR, merge, rebase, amend, reset, clean, force-push, readiness changes, CodeRabbit, Azure, production migrations, deployment, provider, funds or credential actions. Only publishing Package J branches without a PR for CI is authorized. Migrations 0001–0043 are immutable; the next is 0044. One executor per checkout and cluster; do not touch other checkouts, processes or ports 51454/51458/51474/51511. Credentials are generated in memory and never printed. Races require a wait observed in pg_locks. Use they/them for the owner. Work inline; no extra agents.

Tools: the existing Python/uv lockfile, PostgreSQL 18.6 disposable harness, Playwright
desktop/mobile and axe checks, TypeScript/Zod/Next.js build, Ruff/mypy, git and public
read-only GitHub REST API. Evidence Engineering and GORGONA successor-handoff skills
guided source binding and handoff structure; no extra reviewer agent was started.
