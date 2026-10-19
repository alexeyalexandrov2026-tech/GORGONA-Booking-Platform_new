# Next agent — Package K after K4b, 2026-10-18

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k4b-provider-review` (parent `45f15df`), source
  `60a12e14d461ef3d9a9b6dbca8e35c25f402055d` plus one docs commit. The branch contains K1f–K4b.
  Inspect HEAD and status first.
- **K4b not published.** On GitHub: `codex/package-k1e-http-ingress` (`e5279cb`, CI SUCCESS) and,
  since 2026-10-18 (the owner answered the publish question "do as you see fit"),
  `codex/package-k4a-provider-screen` (`09d8187`, CI run 39185366331 SUCCESS). No PR. `main` is
  `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0053 immutable; next **0054**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K4b adds

The second K4 slice ([design](PACKAGE_K4B_DESIGN_2026-10-18.md),
[validation](evidence/2026-10-18-k4b-provider-review/VALIDATION.md),
[runbook](../runbooks/PROVIDER_OPERATIONS.md)).

- 0053: `provider_event_acknowledgements`, one per decision without an operation; the receipt
  guard reads it. A test that drops `current_location_id()` restores its company policy.
- `business/provider_review.py`; routes `GET …/provider-operations/{id}`,
  `GET …/provider-attention`, `PUT …/provider-attention/{event}/acknowledgement`.
- Counters `gorgona.provider_receipt_decisions` and `gorgona.provider_applications` (with
  `tenant_id`); tests replace the counter objects instead of setting a global meter provider.
- The browser harness `test_k4a_browser.py` covers K4a and K4b; `tests/unit/test_provider_runbook.py`
  fails when a state or a `PROVIDER_` refusal code is missing from the runbook.

## Open

1. K3b: link an earlier manual payment to a provider operation (now `PROVIDER_PAYMENT_LINK_REQUIRED`).
2. The manual H payment form still loses its input after a refusal (existing behaviour).
3. A worker entry point and schedule, alerts and dashboards (infrastructure, owner's word).
4. Fees, payouts and bank reconciliation; other currencies (each needs the owner's word).
5. K2b and K0 stay BLOCKED; IR-03 and publishing K4b need the owner's word.
6. K5: FIN-02 evidence needs actual admitted Stripe test execution (K0), an independent review and
   exact-head CI.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` and `codex/package-k4a-provider-screen` needs the owner's
word. `gh` is not installed here; a published branch's CI can be read once through the public
GitHub API.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k4b-20261018-45f15df` (`STATE.md`, phase
logs, `runner.py` (also hashes `docs/runbooks`), `run_gates.py`, `write_record.py`). Copy its
scripts for the next slice; run them with `api/.venv/Scripts/python.exe`; build `web` before a
focused run with a browser test.
