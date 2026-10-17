# Next agent — Package K after K1i, 2026-10-17

Superseded on 2026-10-17 by [the K1j handoff](NEXT_AGENT_PACKAGE_K1J_2026-10-17.md). Kept below as history.

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k1i-stock-plan-stability` (parent `0760553`), source
  `42ead59a3ff975d0daa6ee294af6b34b2b8ce5ff` plus one docs commit. The branch contains K1f, K1g, the
  K1h finding and K1i. Inspect HEAD and status first.
- **Not published.** Only `codex/package-k1e-http-ingress` is on GitHub (head `e5279cb`, CI
  run 38996263458 SUCCESS). `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0047 immutable; next **0048**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K1i adds

Fixes the [K1h finding](evidence/2026-10-17-k1h-stock-statistics/FINDING.md)
([validation](evidence/2026-10-17-k1i-stock-plan-stability/VALIDATION.md)): migration 0047 makes
`stock_movements_sequence_key` and `stock_valuations_sequence_key` unique indexes ending with
`(tenant_id::text)`, reads a return's source document by key and compares a document's lines by
`IS NOT DISTINCT FROM`. With a 100,016-row history and stale statistics one document's check reads
at most 1 row per stock-table node. `test_stock_scale` now checks the plan with `auto_explain` as
well as the time; its threshold is unchanged. Do not loosen it.

## Open

1. IR-07 (who and when revoked a verification configuration or a route binding; revocation cannot
   tell rotation from compromise). Next by the plan; needs migration 0048.
2. IR-03 (runtime INSERT on the inbox) reverses the K1b design and needs the owner's decision.
3. Publishing K1f–K1i needs the owner's word. K0 stays BLOCKED until separately authorized.
4. Other company-leading keys outside the stock document checks are unchanged (not shown to
   read a history).

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` needs the owner's word.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k1i-20261017-0760553` (`STATE.md`, phase
logs, `runner.py`, `run_gates.py`, `write_record.py`). Copy its scripts for the next slice; the
runner deletes each stopped cluster's `data` directory.
