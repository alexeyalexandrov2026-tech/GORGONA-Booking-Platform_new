# Next agent — Package K after K1g, 2026-10-17

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k1g-guard-additions` (parent `af26f1d`), source `4401a2e7bcdc716eaa5664285c0ca383ddf77163`
  plus one docs commit. The branch contains K1f and K1g. Inspect HEAD and status first.
- **Not published.** Only `codex/package-k1e-http-ingress` is on GitHub (head `e5279cb`, CI
  run 38996263458 SUCCESS). `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0046 immutable; next **0047**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K1g adds

Closes review finding IR-05 ([validation](evidence/2026-10-17-k1g-guard-additions/VALIDATION.md)):
the receipt schema guard checks group membership topology, K table shape (ordinary, logged, no
rewrite rules), table/column/function ACLs and the RLS context functions.

## Open

1. `test_stock_scale` (package J) is near its timing limit in full runs (one failure in K1g
   full-1; passed alone and in full-2). Needs its own small slice: a steadier measurement or a
   justified threshold. Do not loosen it silently.
2. Remaining review follow-ups: IR-03 (runtime INSERT on the inbox, 0047), IR-07 (revocation
   author/time). Publishing K1f/K1g needs the owner's word.
3. K0 stays BLOCKED until separately authorized.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` needs the owner's word.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k1g-20261017-af26f1d`. Copy its scripts.
