# K1h finding — stock posting plans under misleading statistics (deferred)

**Diagnosed, not fixed; no code changed.** Branch `codex/package-k1h-stock-scale-timing` from
`8b30a3b`, docs only. Run folder `C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k1h-20261017-8b30a3b`
(`STATE.md`, phase logs, `K1H_ATTEMPT.patch`, `0047_stock_history_keys.sql.attempt`).

## Question and answer

The owner asked to make `test_stock_scale` robust to load without weakening it. The test is
right and the measurement is not load noise: postings after a 100k history become slow when the
planner's statistics do not describe the company (gathered before the company existed or before
a burst). Every index that starts with `tenant_id` is then estimated at one row, so PostgreSQL
may reach one document's rows through another index and read the whole history.

## Evidence

| Observation | Source |
|---|---|
| No checkpoint or autovacuum in the test window of K1e/K1f/K1g full runs | server logs vs junit timing |
| After the stock tests: after 134–178 ms vs 55–77 ms before (tight; deterministic) | diag-1 |
| `gba.assert_stock_document` (0040): the line anti join used `stock_movements_sequence_key` and filtered 100,016 rows | diag-2 auto_explain |
| Stale statistics: `reltuples` 1, `tenant_id` `n_distinct` −1 → both indexes cost 8.45 | probe-1 |
| Deterministic reproduction (ANALYZE on a short history first): 100,031 rows in one plan node; after 386.8 vs 45.3 ms | red-1 |
| Same hazard in the line/movement/valuation triggers: source-document join scanned 100,017 documents | diag-5 |

## Attempts (all reverted)

1. Rewrites of `assert_stock_document` (`IS NOT DISTINCT FROM`, `ORDER BY` the document key): no
   plan change — equal-cost choice, redundant pathkeys.
2. `tenant_id` `n_distinct = -0.01` on seven stock tables: passed alone and with the stock tests
   (after 43.3 vs 43.0 ms), **failed in the full order** (gates-1; diag-4: 1 failed, 1045 passed):
   a company absent from the most-common-values list still looks tiny.
3. Owner-approved key change: running-total keys material-first/company-last plus lateral source
   lookups in three triggers: passed the stock group (after 43.8 vs 47.9 ms), **failed in the full
   order** (gates-2: 1 failed, 2051 passed): the count by company and document again used the
   reordered key, probably through PostgreSQL 18 skip scan (not verified).

## Conclusion and next slice

While another index contains `tenant_id`, key changes cannot guarantee the document key under
misleading statistics; removing `tenant_id` from those keys would weaken company isolation and
was rejected. A robust fix rewrites the document checks to read movements and valuations only by
their full primary keys, line by line, without "company + document" predicates — a larger change
to a financial-integrity function that needs careful, preferably independent, review. Until then
`test_stock_scale` stays unchanged and can fail now and then in full runs; that failure is this
finding, not noise. STOCK-01 readiness is unchanged.
