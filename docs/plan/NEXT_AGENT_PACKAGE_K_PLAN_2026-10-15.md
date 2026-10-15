# Next agent — Package K planning checkpoint, 2026-10-15

Current scope: **local planning only** for K / FIN-02 after Package J technical
acceptance. No K functional implementation or provider execution is claimed.
Read [plan](PACKAGE_K_PLAN_2026-10-15.md), [ADR-0027 (Proposed)](../adr/0027-provider-events-and-reconciliation.md),
[reuse evidence](evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md),
[validation](evidence/2026-10-15-package-k-plan/VALIDATION.md), then
[stage-2 plan](STAGE2_PLAN_2026-10-06.md), ADR-0024 and current entry documents.

## Exact state and inherited evidence

- Checkout: `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`.
- New local branch: `codex/package-k-plan`, based on
  `df88c20687333668d39fe76a26eabca691e62cb0`. The planning commit is above this base;
  inspect actual HEAD/status. This checkout is now on K, despite its directory name.
- Published J branch remains `codex/package-j-review2-fixes` at that base; exact
  [CI 158](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38697747829) PASS.
- Main remains `fedd0f115f24aad52f6256298296e8c5123fb427`. Do not switch or move main.
- Inherited code commit: `7b96feca22b430d0ea98ef8081ac89cf7e292fc6`; local full
  1748 passed/4 skipped, focused 141, web unit 114. These are Package J source results,
  not new K tests. J-01–J-14 technical evidence PASS; STOCK-01 remains planned.
- Five existing development npm audit findings remain FAIL; runtime audit 0.
  Local container/optional external-site skips and J review limits remain recorded
  in the [J acceptance](evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md).

## Implementation blockers and reuse

K-01–K-14 are NOT TESTED; FIN-02 remains planned. K0 real test admission is BLOCKED
by the owner's separate provider/credential authorization rule. H4's submitted
metadata and all-false capabilities are not admission evidence. There is no Booking
inbox/outbox/webhook/Stripe adapter to reuse; implement only the bounded components
defined by the selected K slice. Preserve G/H accounting and manual-attestation labels.

The plan offers three concrete recommendations: events only for merchant-owned
payments/refunds; one selected test merchant/book/currency before expansion; explicit
bindings and reconciliation rather than guessing financial allocations. Get the
owner's selection before treating the proposal as accepted. Any authenticated test
access or provider object creation needs a separately bounded direct authorization.
Do not ask for secrets in chat or documents.

Run folder:
`C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-k-plan-20261015-df88c20`.
It holds STATE.md and validate_plan.py, plus validation receipts. Use this checkout's
`api/.venv/Scripts/python.exe`. The validator compares against df88c20 and binds all
inspected source candidates. Do not reuse the J final validator against K HEAD: its
exact-head guard intentionally expects the published J commit.

## Standing boundaries

No K push is authorized: the publication exception is only for Package J branches
without PRs. No PR/merge/rebase/amend/reset/clean/force-push; readiness change,
CodeRabbit, Azure, deployment, production migration, provider/funds/credential action
requires separate direct owner authorization. No actual provider account was accessed
for this plan. FIN-02/STOCK-01 stay planned; ADR-0026/0027 Proposed.
Published migrations 0001–0043 are immutable; next 0044, recheck before code.
One executor per checkout/cluster; work inline without extra agents. Do not touch
other checkouts/processes or ports 51454/51458/51474/51511. Future race claims require
an observed pg_locks wait. Credentials are generated privately and never printed.
Use they/them for the owner. Update this handoff/prompt after the next verified slice.
