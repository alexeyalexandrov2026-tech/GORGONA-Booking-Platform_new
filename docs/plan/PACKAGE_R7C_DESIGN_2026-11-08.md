# Package R, slice R7c — the reconciliation per rental agreement, derived (2026-11-08)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 8, slice R7.
Previous slice: [R7b](PACKAGE_R7B_DESIGN_2026-11-08.md); handoff [NEXT_AGENT_PACKAGE_R7C_2026-11-08.md](NEXT_AGENT_PACKAGE_R7C_2026-11-08.md).
Branch `codex/package-r7c-rental-reconciliation` from the R7b docs commit `6f20a26`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after each slice. R7b CI run 42511820796 on `6f20a26`: success.

## Scope

- No migration (next stays **0108**): every figure is derived on read and never stored.
- Service `business/rental_reconciliation.py`; route `GET bookings/{id}/reconciliation`.

## Decisions (R7c, agent)

1. **Inputs only.** The R7a settlement, the R7b damage charges and refunds, the FIN-03 obligation balances
   (`gba.obligation_balance`: principal, paid, credited, reserved) of their documents and of the refund obligations that
   FIN-03 creates when a credit note is issued, and the R5a security figures. No new record, no new rule.
2. **Charged** is the settlement total plus every damage charge. Each of those documents shows its state: `draft`
   while FIN-03 has not issued it (nothing paid, nothing open), `issued` with its principal, paid, credited and the open
   amount (principal minus paid, credited and reserved).
3. **Refunded** shows each refund: an external one is refunded when recorded; a credit one shows its credit note's
   state and, once issued, the refund obligation FIN-03 made (its principal and how much of it is paid back).
4. **Totals**: charged, invoiced (issued principal), paid, credited, open, refunded externally, refund owed (unpaid
   refund obligations) and the security (requested, held, captured, released, expired, remaining), each in minor
   units of the agreement currency; a booking without a security shows none.
5. **Read only**, under the rental read rules and branch scope; a booking without a settlement is not found
   (`NOT_FOUND`); another company's booking is not found.

## Acceptance of R7c — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R7c-01 | A settled booking shows its charged documents as drafts, then issued with principal and open; a payment lowers open | NOT TESTED |
| R7c-02 | Damage charges add to charged; credit and external refunds show their state, the refund obligation and its payment | NOT TESTED |
| R7c-03 | The security figures appear when recorded and not otherwise; totals equal the sums of their rows | NOT TESTED |
| R7c-04 | Before settlement, branch scope and another company give not found; the full suite stays green | NOT TESTED |

## Not in R7c

New money records; changing FIN-03; screens (R8).
