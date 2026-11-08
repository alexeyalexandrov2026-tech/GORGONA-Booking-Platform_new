# Package R, slice R7a — final settlement invoice for a rental agreement (2026-11-07)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 8, slice R7.
Previous slice: [R6b](PACKAGE_R6B_DESIGN_2026-11-07.md); handoff [NEXT_AGENT_PACKAGE_R7_2026-11-07.md](NEXT_AGENT_PACKAGE_R7_2026-11-07.md).
Branch `codex/package-r7a-rental-settlement` from the R6b docs commit `0432c98`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after each slice. R6b CI run 42438106172 on `0432c98`: success.

R7 is split: **R7a** the final settlement invoice; **R7b** damage charges with approval and refunds (credit notes or
external refunds, each its own record); **R7c** the reconciliation per agreement. The FIN-03 pattern is the one of
package O (O5 pay applications): the business record and its FIN-03 receivable invoice draft are written together.

## Scope

- Migration **0106**: `rental_settlements` (insert-only, one per booking) with the figures and the FIN-03 invoice it
  names; a guard that recomputes every figure under the class row lock; module gate; tenant isolation; branch scope
  last.
- Service `business/rental_settlements.py`; routes `GET`/`POST bookings/{id}/settlement`.

## Decisions (R7a, agent)

1. **When.** A booking with an agreement that is not cancelled is settled once, after its return inspection (R6a).
2. **Lines**, all in the agreement currency and from frozen terms only: (a) the rental and extras, the latest agreement
   version's total (R4b/R4c); (b) the meter excess, the R6b excess amount when above 0; (c) the late return, the R6b
   started overdue hours times the card's hour rate, or, without an hour rate, the started overdue days times the day
   rate; an overdue return on a card with neither is refused (`RENTAL_SETTLEMENT_UNPRICED`). Fuel is not priced (the
   card has no fuel term); a later slice adds it with its own term.
3. **The invoice** is one FIN-03 receivable invoice draft for the booking's customer in the given book, control
   (receivable) account and revenue account, with one line per figure above 0, written in the same transaction as the
   settlement. Issuing, posting and paying it stay FIN-03's own flows; corrections are R7b credit notes.
4. **The database rechecks** the return, the latest version and its total, the excess and the late amount from the
   card and the inspections, the sum, and that the named document is a receivable invoice of the booking's customer in
   the agreement currency for that sum. A settlement is never updated or deleted.
5. **Permissions and rules as before**: `rental.manage`; idempotency scope `rental.settlement`; module off writes
   nothing; branch scope by the booking's pickup branch; another company's booking or book is refused; direct SQL
   updates and deletes refused. Errors: `RENTAL_SETTLEMENT_STATE` (no return, no agreement, cancelled, settled),
   `RENTAL_SETTLEMENT_UNPRICED`.

## Acceptance of R7a — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R7a-01 | A returned booking settles once into a FIN-03 receivable draft with the rental, excess and late lines; the view shows the figures and the document | NOT TESTED |
| R7a-02 | Before the return, without an agreement, a cancelled booking and a second settlement are refused; an overdue return on a card without hour or day rate is unpriced | NOT TESTED |
| R7a-03 | An extension's latest total counts; a return on time and within the allowance gives the rental line only; a day-rate card prices started days | NOT TESTED |
| R7a-04 | The database refuses updates, deletes and forged figures or documents; module off writes nothing; scope holds | NOT TESTED |
| R7a-05 | 0105 -> 0106 keeps every row; the full suite stays green | NOT TESTED |

## Not in R7a

Damage charges and refunds (R7b); the reconciliation per agreement (R7c); fuel; screens (R8).
