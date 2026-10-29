# Package N slice N7 — acceptance of brokerage (design)

"continue" of 2026-10-29 after N6, under the owner's full delegation («Делай как считаешь нужным я доверяю
тебе»). Branch `codex/package-n7-acceptance` from `e9ac854` (N6 docs). Plan:
[PACKAGE_N_PLAN_2026-10-26.md](PACKAGE_N_PLAN_2026-10-26.md), slice N7.

## Scope

- One end-to-end test, `api/tests/integration/test_n7_acceptance.py`, of a brokered two-leg load through the
  API and PostgreSQL: no broker authority refuses the tender; the authority is recorded; a carrier without a
  profile is refused; leg 1 goes to one carrier and leg 2 to another (decision 8, the 3PL flow); a second
  acceptance on a covered leg is refused; the second carrier's rate confirmation changes to version 2, both
  versions kept; the broker closes the second leg with stop events, and a repeated event changes nothing; each
  carrier's pay accrues once (the second accrual refused); the order's margin is the invoice less both
  accruals, and no table stores a margin.
- An acceptance record `docs/plan/evidence/2026-10-29-n7-acceptance/ACCEPTANCE.md`: TMS-01..03 for brokered
  loads and N-01..N-09, each with its proof from N1–N7 and its limits; slices with code commits, suites and CI.
- No migration (next stays 0086), no screen change.

## Not in this slice

- The independent review (one extra agent) needs the owner's consent; it stays open in the record.
- Readiness, enabling transport, `main`, PR, deployment: only on the owner's word.

## Acceptance of N7

| id | Requirement |
|---|---|
| N7-01 | The end-to-end test passes on PostgreSQL with the rows read back |
| N7-02 | The record maps TMS-01..03 and N-01..N-09 to proofs and limits, with the review open |
| N7-03 | The full suite stays green; one executor, one disposable cluster |
