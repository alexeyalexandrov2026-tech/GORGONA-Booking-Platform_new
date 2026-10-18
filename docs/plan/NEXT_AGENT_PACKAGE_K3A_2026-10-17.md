# Next agent — Package K after K3a, 2026-10-17

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k3a-provider-money` (parent `1476108`), source
  `2f91368271458d6f20030e43ab9409751c3fa62d` plus one docs commit. The branch contains K1f–K3a.
  Inspect HEAD and status first.
- **Not published.** Only `codex/package-k1e-http-ingress` is on GitHub (head `e5279cb`, CI
  run 38996263458 SUCCESS). `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0052 immutable; next **0053**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K3a adds

The first K3 slice ([design](PACKAGE_K3A_DESIGN_2026-10-17.md),
[validation](evidence/2026-10-17-k3a-provider-money/VALIDATION.md)), by the owner's decisions of
2026-10-17: a finance user applies; one registered clearing account per connection; USD only;
manual voids and corrections allowed.

- 0051 (K): the runtime reads its company's operations and decisions and locks an operation row.
- 0052 (H): `provider_observed` payments with `external_payment_provenance` (one per operation),
  `provider_clearing_accounts`, and `gba.assert_provider_payment` checked in the applying
  transaction. The command receipt stays `settlement_confirm`.
- `business/provider_payments.py`, `settlements.confirm_provider`; routes
  `GET …/provider-operations`, `PUT …/provider-connections/{id}/clearing-account`,
  `POST …/settlements/{id}/provider-confirmations/{payment}`. The web payment contract accepts
  the provenance.

Tests that copy the shared database into older schemas must leave out companies with provider
payments (`copy_fixture_data`). A test that drops `current_location_id()` must restore the 0052
company policies. Never revoke the runtime's decision read in a drift repair.

## Open

1. K3b: link an earlier manual payment to a provider operation (now refused as "needs linking").
2. K4: finance UI for operations and "applied with conflict", recovery and runbook. Its first
   part is proposed on 2026-10-18 as [K4a](PACKAGE_K4A_DESIGN_2026-10-18.md); waits for three
   owner answers.
3. Fees, payouts and bank reconciliation; other currencies (each needs the owner's word).
4. K2b and K0 stay BLOCKED; a worker entry point, IR-03 and publishing K1f–K3a need the owner.
5. Performance: readiness scans the connection's inbox per operation; an expression index is a
   candidate once volumes are known.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` needs the owner's word.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k3a-20261017-1476108` (`STATE.md`, phase
logs, `runner.py`, `run_gates.py`, `write_record.py`). Copy its scripts for the next slice; run
them with `api/.venv/Scripts/python.exe`.
