# Next agent — Package K after K3b, 2026-10-19

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k3b-provider-links` (parent `199eada`), source
  `8bb2eb43e16a05092065a09bee8082733737fe1f` plus one docs commit. The branch contains K1f–K4b and K3b.
  Inspect HEAD and status first.
- **K3b not published.** On GitHub, CI only, no PR: `codex/package-k1e-http-ingress` (`e5279cb`),
  `codex/package-k4a-provider-screen` (`09d8187`, run 39185366331 SUCCESS) and
  `codex/package-k4b-provider-review` (`507e709`, run 39205753605 SUCCESS). The K3b design and
  decision commits (`22bfbd0`, `199eada`) are on the K3b branch only. `main` is `fedd0f1`.
- Migrations 0001–0054 immutable; next **0055**. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.

## What K3b adds

[Design](PACKAGE_K3B_DESIGN_2026-10-19.md), [validation](evidence/2026-10-19-k3b-provider-links/VALIDATION.md),
[runbook](../runbooks/PROVIDER_OPERATIONS.md).

- 0054 (H): `provider_payment_links`; `enforce_provider_payment_link`; the financial guard reads it;
  `schema_guard` definitions are 68; a test that drops `current_location_id()` restores its policy.
- States `needs_link` and `linked` in the SQL state; `PROVIDER_OPERATION_LINKED`,
  `PROVIDER_LINK_MISMATCH`; `PUT …/provider-operations/{id}/link`.
- H keeps one manual payment per alias and reference: test payments that name the same ID need
  different references.

## Open

1. K5 evidence plan: FIN-02 needs actual admitted Stripe test execution (K0, BLOCKED), an
   independent review and exact-head CI. Planned on 2026-10-19 in [K5](PACKAGE_K5_PLAN_2026-10-19.md);
   the owner answered the four questions on 2026-10-19 (all defaults).
2. A worker entry point and schedule, alerts and dashboards (infrastructure, owner's word).
3. Fees, payouts and bank reconciliation; other currencies (each needs the owner's word).
4. The manual H payment form still loses its input after a refusal (existing behaviour).
5. K2b and K0 BLOCKED; IR-03 and publishing K3b need the owner's word.

## Rules

Same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules); pushing any branch other
than the three listed above needs the owner's word. `gh` is not installed; read a published
branch's CI once through the public GitHub API.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k3b-20261019-199eada` (`STATE.md`, phase
logs, scripts). Copy them for the next slice; run with `api/.venv/Scripts/python.exe`; build `web`
before a focused run with a browser test.
