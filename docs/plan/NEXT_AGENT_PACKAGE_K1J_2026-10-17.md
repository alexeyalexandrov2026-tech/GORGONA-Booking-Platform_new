# Next agent — Package K after K1j, 2026-10-17

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k1j-revocation-record` (parent `84bc4d7`), source
  `201847856aa768bbeb25751d5b219e154383c293` plus one docs commit. The branch contains K1f–K1j.
  Inspect HEAD and status first.
- **Not published.** Only `codex/package-k1e-http-ingress` is on GitHub (head `e5279cb`, CI
  run 38996263458 SUCCESS). `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0048 immutable; next **0049**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K1j adds

Closes review finding IR-07 ([validation](evidence/2026-10-17-k1j-revocation-record/VALIDATION.md)):
migration 0048 makes every new revocation of a receipt connection or verification config name its
reason (`rotation`, `compromise`, `retired`; connections without `rotation`) and records when and
by which login (`session_user`). The record is permanent; rows revoked before 0048 keep an empty
record (revoked, record unknown). Revoke with
`UPDATE … SET revoked=true, revoked_reason='…'`; a bare `SET revoked=true` is now refused.

## Open

1. Low review findings: IR-08 (no random default for `ingress_id`), IR-09 (no TRUNCATE guard on
   the K tables; the "permanent" claim covers UPDATE/DELETE only).
2. IR-03 (runtime INSERT on the inbox) reverses the K1b design and needs the owner's decision.
3. K2 (bounded worker, fencing, operation identity, reconciliation) is the next plan slice; it
   needs its own design first. K0 stays BLOCKED until separately authorized.
4. Publishing K1f–K1j needs the owner's word. A revoked connection still cannot be re-provisioned
   in the same namespace (K2 constraint).

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` needs the owner's word.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k1j-20261017-84bc4d7` (`STATE.md`, phase
logs, `runner.py`, `run_gates.py`, `write_record.py`). Copy its scripts for the next slice.
