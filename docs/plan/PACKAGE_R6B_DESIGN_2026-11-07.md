# Package R, slice R6b — overdue time and meter excess, derived (2026-11-07)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), slice R6, acceptance R-06.
Previous slice: [R6a](PACKAGE_R6A_DESIGN_2026-11-07.md); handoff [NEXT_AGENT_PACKAGE_R6B_2026-11-07.md](NEXT_AGENT_PACKAGE_R6B_2026-11-07.md).
Branch `codex/package-r6b-rental-usage` from the R6a docs commit `18470ae`. Same process: failing tests first, gates
on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner asked to go
on to the next stage right after each slice. R6a CI run 42426865948 on `18470ae`: success.

## Scope

- No migration (next stays **0106**): the figures are derived on read and never stored.
- Pure function `business/rental_usage.py` `derive_usage`; route `GET bookings/{id}/usage`.

## Decisions (R6b, agent)

1. **Inputs.** The latest agreement version (its period, its whole rental days and its rate card's included meter
   allowance per day and excess rate, all frozen by R4a-R4c) and the R6a inspections. Nothing else is read; no price
   or allowance is looked up again.
2. **State.** `not_handed_over` before the handover, `out` between handover and return, `returned` after the return.
3. **Overdue.** The end is the return time, or the time of the read while out. Overdue seconds are the end minus the
   agreement period end, never below 0; overdue hours are the whole hours started (a second over is one hour).
   No grace and no price: R7 settles the overdue time.
4. **Meter excess.** For a class with a meter, the distance is the return reading minus the handover reading (while
   out, none). The allowance is the allowance per day times the agreement's rental days; the excess is the distance
   over the allowance, never below 0, and its amount is the excess times the excess rate in the card's currency.
   Without an allowance on the card there is no excess (null); without an excess rate the amount is null.
5. **Read only.** The view states the `as_of` time it used; it creates no charge, invoice, security event or
   payment. Permissions and scope as for the other rental reads; another company's booking is not found.

## Acceptance of R6b — PASS 2026-11-07 (code `010692f`, [evidence](evidence/2026-11-07-r6b-rental-usage/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R6b-01 | Before handover, out and returned give the right state; distance, allowance, excess and its amount follow the card and the agreement days | PASS |
| R6b-02 | A return after the period end gives the overdue seconds and started hours; a return before it gives 0; while out the read time counts | PASS |
| R6b-03 | No allowance gives no excess; no rate gives no amount; a class without a meter gives no distance; an extension's latest version counts | PASS |
| R6b-04 | Branch scope and another company give not found; the full suite stays green | PASS |

## Not in R6b

Pricing the overdue time, damage charges, refunds and settlement (R7); swaps after handover and one-way returns;
screens (R8).
