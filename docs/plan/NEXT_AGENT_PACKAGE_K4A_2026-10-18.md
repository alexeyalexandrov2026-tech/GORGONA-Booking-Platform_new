# Next agent — Package K after K4a, 2026-10-18

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k4a-provider-screen` (parent `c1ff170`), source
  `374f60c2adb04060bd69c526dbf14b687c52698c` plus one docs commit. The branch contains K1f–K4a.
  Inspect HEAD and status first.
- **Not published.** Only `codex/package-k1e-http-ingress` is on GitHub (head `e5279cb`, CI
  run 38996263458 SUCCESS). `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0052 immutable; next **0053**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K4a adds

The first K4 slice ([design](PACKAGE_K4A_DESIGN_2026-10-18.md),
[validation](evidence/2026-10-18-k4a-provider-screen/VALIDATION.md)), by the owner's decisions of
2026-10-18: applying from the reserved settlement; clearing account registered in the screen after
a confirmation step; conflict marker only.

- API: `GET …/provider-operations?state=` (state computed in SQL; complete across pages), state
  `revoked`, `GET …/provider-connections` (no key material).
- Web: `components/provider-operations.tsx` (tab, clearing account form, apply form); command
  `settlement_provider_confirm`, recovered as `settlement_confirm`; refusals from code and reason
  (`ManagementApiError.details`).
- Browser evidence: `api/tests/integration/test_k4a_browser.py` runs
  `npm run test:management:provider` (desktop and mobile) on synthetic events signed in memory.

The finance workspace unmounts its panes while it reloads the book: a form that must keep its
input after a refusal keeps its draft in the workspace (as the provider form does).

## Open

1. K4b: conflict detail (which delivery disagrees), recovery views, redacted metrics and the
   operational runbook. Proposed on 2026-10-18 as [K4b](PACKAGE_K4B_DESIGN_2026-10-18.md);
   the owner answered the four questions the same day.
2. K3b: link an earlier manual payment to a provider operation (now refused as "needs linking").
3. The manual H payment form still loses its input after a refusal (existing behaviour).
4. Fees, payouts and bank reconciliation; other currencies (each needs the owner's word).
5. K2b and K0 stay BLOCKED; a worker entry point, IR-03 and publishing K1f–K4a need the owner.
6. Performance: the state filter and readiness scan per operation; an index is a candidate once
   volumes are known.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than `codex/package-k1e-http-ingress` needs the owner's word.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k4a-20261018-c1ff170` (`STATE.md`, phase
logs, `runner.py`, `run_gates.py`, `write_record.py`). Copy its scripts for the next slice; run
them with `api/.venv/Scripts/python.exe`. Build `web` before a focused run that includes a browser
test (the static gate builds it for the final gates).
