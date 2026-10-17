# Next agent — Package K after K1k, 2026-10-17

Superseded on 2026-10-17 by [the K2a handoff](NEXT_AGENT_PACKAGE_K2A_2026-10-17.md). Kept below as history.

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k1k-truncate-guard` (parent `ae9e1e2`), source
  `a5f21e41f550d5d07e428c644e9f718082b3f619` plus one docs commit. The branch contains K1f–K1k.
  Inspect HEAD and status first.
- **Not published.** Only `codex/package-k1e-http-ingress` is on GitHub (head `e5279cb`, CI
  run 38996263458 SUCCESS). `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0049 immutable; next **0050**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K1k adds

Closes review findings IR-09 and the default part of IR-08
([validation](evidence/2026-10-17-k1k-truncate-guard/VALIDATION.md)): migration 0049 refuses
TRUNCATE, also `TRUNCATE … CASCADE`, of all six receipt tables for the owner and superusers, and
`provider_receipt_routes.ingress_id` defaults to `gen_random_uuid()`. A test must never try to
empty a receipt table; the shared test database keeps all rows.

## Open

1. Review items left: IR-03 (runtime INSERT on the inbox; reverses the K1b design, owner's
   decision), IR-08 remainder (per-route disable, listing routes), IR-10/IR-11 (test and
   observability notes).
2. K2 (bounded worker, fencing, operation identity, reconciliation) is the next plan slice; it
   needs its own design first, and the plan's decision 3 (ambiguity) is for the owner to confirm.
   K0 stays BLOCKED until separately authorized.
   Proposed in [the K2a design](PACKAGE_K2A_DESIGN_2026-10-17.md) (docs only, four owner questions).
3. Publishing K1f–K1k needs the owner's word.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` needs the owner's word.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k1k-20261017-ae9e1e2` (`STATE.md`, phase
logs, `runner.py`, `run_gates.py`, `write_record.py`). Copy its scripts for the next slice.
