# Next agent — Package K after K2a, 2026-10-17

Superseded on 2026-10-17 by [the K3a handoff](NEXT_AGENT_PACKAGE_K3A_2026-10-17.md). Kept below as history.

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k2a-receipt-decisions` (parent `b6c8040`), source
  `6e9bbfc74a09a5d472aaff25328356d6f71e8706` plus one docs commit. The branch contains K1f–K1k and
  K2a. Inspect HEAD and status first.
- **Not published.** Only `codex/package-k1e-http-ingress` is on GitHub (head `e5279cb`, CI
  run 38996263458 SUCCESS). `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0050 immutable; next **0051**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K2a adds

The first K2 slice ([design](PACKAGE_K2A_DESIGN_2026-10-17.md),
[validation](evidence/2026-10-17-k2a-receipt-decisions/VALIDATION.md)), by the owner's decisions of
2026-10-17: a separate NOLOGIN `gba_receipt_worker` group; every conflict to manual review; direct
payments and refunds only; unattested events never processed.

- Bootstrap creates the group and, from `GBA_RECEIPT_WORKER_ROLE`/`GBA_RECEIPT_WORKER_PASSWORD`,
  an optional worker login; migrate refuses without the group.
- Migration 0050: `provider_operations`, `provider_event_leases`, `provider_event_decisions`. The
  database decides: the worker inserts only its lease; the trigger derives outcome, reason and
  operation from the stored facts and refuses a stale or forged lease.
- `gorgona_booking.providers.receipt_worker.process_batch(pool, *, limit, lease_seconds,
  tenant_id)`; no process entry point or schedule.

Tests that read decisions as the worker must filter by company: the worker may discover every
company's decisions. A test that drops `current_location_id()` must restore the 0050 company
policies and the worker's grant (see `test_location_access.py`).

## Open

1. K3 (money): apply observed successes to G/H with provider provenance, after rechecking
   deliveries (a conflicting variant may arrive after a decision). Needs its own design and the
   owner's review before code. Proposed on 2026-10-17 as
   [K3a](PACKAGE_K3A_DESIGN_2026-10-17.md); waits for four owner answers.
2. K2b (provider retrieval for ambiguous facts) and K0 stay BLOCKED until separately authorized.
3. A process entry point for the worker, and the Azure bootstrap job passing the worker variables,
   need the owner's word (infrastructure).
4. IR-03 (runtime INSERT on the inbox) and publishing K1f–K2a need the owner's word.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` needs the owner's word.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k2a-20261017-b6c8040` (`STATE.md`, phase
logs, `runner.py`, `run_gates.py`, `write_record.py`). Copy its scripts for the next slice.
