# K1i stock posting plans independent of statistics — local validation

**PASS for this bounded local slice.** Branch `codex/package-k1i-stock-plan-stability`, parent
`0760553`, source commit `42ead59a3ff975d0daa6ee294af6b34b2b8ce5ff`. [CHECKS.json](CHECKS.json) was
generated before the source commit and binds source blobs, commands, exit codes and log digests.
Not published. Fixes the [K1h finding](../2026-10-17-k1h-stock-statistics/FINDING.md). Executor:
Claude, inline, after the owner's «Сначала исправь ошибку».

## What changed

- `api/src/gorgona_booking/db/migrations/0047_stock_document_plan_stability.sql` (new):
  `stock_movements_sequence_key` and `stock_valuations_sequence_key` become unique indexes of the
  same names ending with `(tenant_id::text)`; `guard_stock_document_line`, `apply_stock_movement`
  and `apply_stock_valuation` read a return's source document by `LEFT JOIN LATERAL … LIMIT 1` on
  its full key; `assert_stock_document` compares a line with its movement and valuation by
  `IS NOT DISTINCT FROM` (all columns NOT NULL, same meaning)
- `api/src/gorgona_booking/db/inventory_guard.py`: lists 0047, accepts constraints that a later
  migration drops, approves both unique indexes by exact `pg_get_indexdef` text
- `api/tests/integration/test_stock_scale.py`: `ANALYZE` of the stock tables on a short history
  before timing; a load-independent `auto_explain` check of `gba.assert_stock_document` as the
  runtime role (at most 100 rows of a stock table per plan node); threshold 3× + 50 ms unchanged
- `api/tests/integration/test_stock_plan_keys.py` (new, 4 cases); `test_stock_upgrade.py` and
  `test_inventory_upgrade.py` reach the latest migration and name the K tables of 0044–0046

Migrations 0001–0046 unchanged (next 0048). No dependency, rule, row, grant, threshold, receipt
code or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| I-01 | One document's check reads at most 100 rows per stock-table node with stale statistics | `test_posting_time_does_not_grow_with_a_long_history` (100,016 movements and valuations): full-2 at most **1** row per node | PASS |
| I-02 | Timing passes with the unchanged threshold alone, in the stock group and in the full order | dev-1, dev-2, focused-2, full-2: before 51.8 ms, after 47.0 ms (median) in full-2 | PASS |
| I-03 | Missing or altered history index, or the old constraint, refuses inventory work; repaired schema passes | `test_stock_plan_keys.py` ×4 (no movements index, no valuations index, company-first movements index, old valuations constraint) | PASS |
| I-04 | Existing stock, guard and upgrade tests and the full suite | focused-2, full-2 | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 473 passed in 329.46s (0:05:29) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2056 passed, 4 skipped in 1556.26s (0:25:56); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 317 source files |
| Web typecheck, lint, format, unit, build | PASS (web unchanged) |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop (`data_removed: true`); no `postmaster.pid` left |
| K CI | NOT TESTED (not published) |

New cases 5, regression cases 34 (see CHECKS.json).

## Failures kept in the record

**red-1, product RED** on `0760553`: 1 failed, 5 passed in 78.44s. The check of one document read
**100,031** rows through `stock_valuations_sequence_key`; median after 405.1 ms against 49.7 ms
before.

**dev-1** (keys and lateral lookups only): 129 passed in 251.81s; 46.2 → 41.1 ms.

**gates-1, full-1 FAIL**: focused-1 473 passed in 392.71s, then full-1 **1 failed**, 2055 passed,
4 skipped in 2168.09s (0:36:08). In the full order the line check of `assert_stock_document` read
100,031 rows through the **new** `stock_movements_sequence_key`: its join compared material,
place and owner by equalities, which a key that starts with the material can serve, and a
material absent from the statistics again looked like one row. Not counted as green.

**diag-1** (the full order up to the scale test, same code): 1 failed, 1049 passed, 3 skipped in
1524.96s. The index in the database was the packaged one; the heavy node was the anti join of the
line check. This led to decision 2a in the [K plan](../../PACKAGE_K_PLAN_2026-10-15.md)
(comparisons by `IS NOT DISTINCT FROM`).

**dev-2** (with 2a): 96 passed in 174.12s; 41.9 → 37.4 ms. Then gates-2 above.

## Limits

Other company-leading keys and joins outside the stock document checks are unchanged; they were
not shown to read a history. The `auto_explain` check covers `assert_stock_document`, the check
named by the finding, not every trigger. STOCK-01 readiness unchanged; ADR-0026 Proposed.
