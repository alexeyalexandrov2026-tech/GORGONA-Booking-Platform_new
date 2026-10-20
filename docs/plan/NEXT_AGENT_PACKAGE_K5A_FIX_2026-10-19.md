# Next agent — Package K after K5a-fix, 2026-10-19

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k5a-review-fixes` (parent `59c54a0`), source `76f776447b0b4fcb1699047aa2fa496531ee6b34` plus one docs commit. The
  branch contains K1f–K4b, K3b, the K5 plan, the K5a review and K5a-fix. Inspect HEAD and status
  first.
- **K5a-fix not published.** On GitHub, CI only, no PR: `codex/package-k1e-http-ingress`,
  `codex/package-k4a-provider-screen` (SUCCESS), `codex/package-k4b-provider-review` (SUCCESS) and
  `codex/package-k3b-provider-links` (`c2a891d`, run 39296081078 SUCCESS). The K5 plan, decisions
  and review commits after `c2a891d` are local. `main` is `fedd0f1`.
- Migrations 0001–0056 immutable; next **0057**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K5a-fix adds

[Review](evidence/2026-10-19-k5a-review/REVIEW.md), [validation](evidence/2026-10-19-k5a-review-fixes/VALIDATION.md),
[runbook](../runbooks/PROVIDER_OPERATIONS.md), [K5 plan](PACKAGE_K5_PLAN_2026-10-19.md).

- 0055 (K): refund failure/success conflict; revocation guards take the ledger advisory key
  directly (the receipt roles cannot call `gba.lock_ledger`; keep the two keys equal).
- 0056 (H): `provider_reference_ids`, `effective_payment_amount`, `provider_manual_payment`,
  `provider_operation_payment`; trigger `external_payments_provider_identity`; the provider
  assertion and link checks replaced. Use these helpers for any new "names the ID" or amount rule.
- Only a `compromise` revocation of a verification config blocks money (owner decision).
- The overview names the business `timezone`; the web contract requires it.
- A test that records a manual payment naming an already applied or linked operation is now
  refused by design; H also refuses correcting a payment an issued credit depends on and voiding a
  refund payment.

## Open

1. K0a/K0b/K0c of the K5 plan: an owner-recorded admission (migration 0057+), ingress and worker
   entry points with the secret read by name from a local environment variable, then the owner's
   own Stripe test run. Each provider step is the owner's.
2. Review findings 6, 8, 9 (IR-03), 12 and 15 (see the review).
3. The manual financial editors still default to the UTC date.
4. Publishing K5a-fix or any other branch needs the owner's word.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than the four listed above needs the owner's word. `gh` is not installed; read a published
branch's CI once through the public GitHub API.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k5a-fix-20261019-59c54a0` (`STATE.md`,
phase logs, scripts). Copy them for the next slice; run with `api/.venv/Scripts/python.exe`; build
`web` before a focused run with a browser test.
