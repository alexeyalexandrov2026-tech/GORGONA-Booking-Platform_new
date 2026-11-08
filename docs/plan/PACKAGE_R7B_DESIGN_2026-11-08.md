# Package R, slice R7b — damage charges and refunds of a rental agreement (2026-11-08)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decisions 5 and 8, acceptance R-07.
Previous slice: [R7a](PACKAGE_R7A_DESIGN_2026-11-07.md); handoff [NEXT_AGENT_PACKAGE_R7B_2026-11-08.md](NEXT_AGENT_PACKAGE_R7B_2026-11-08.md).
Branch `codex/package-r7b-rental-damage-refunds` from the R7a docs commit `2ef404e`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after each slice. R7a CI run 42449693704 on `2ef404e`: success.

FIN-03 has invoices and manual accruals but no credit note; R7b does not change FIN-03. A refund is therefore a FIN-03
**payable** invoice draft to the customer (what the business owes back) or a recorded external refund.

## Scope

- Migration **0107**: `rental_damage_charges` and `rental_refunds` (insert-only, numbered 1, 2, 3 per booking), each
  with its FIN-03 draft when it has one; guards under the class row lock; module gate; tenant isolation; branch scope
  last.
- Service `business/rental_charges.py`; routes `GET bookings/{id}/charges`, `POST bookings/{id}/damage-charges`,
  `POST bookings/{id}/refunds`; `financial_documents` keeps both drafts linked.

## Decisions (R7b, agent)

1. **A damage charge** needs `rental.approve`, a settled booking (R7a) and as its basis one or more marks of the
   return inspection that are new since the handover; each new mark is charged at most once. It has an amount above 0
   in the agreement currency, a reason, and one FIN-03 receivable invoice draft of the customer for that amount,
   written in the same request.
2. **A refund** needs `rental.approve` and a settled booking, an amount above 0 and a reason; all refunds of a booking
   never exceed the settlement total plus the damage charged. Its method is `payable` (a FIN-03 payable invoice draft
   to the customer for the amount, written in the same request) or `external` (a reference and the time it was made).
3. **Separate obligations.** A charge or a refund never edits the settlement, the security or another charge; a
   security capture never edits a charge (rental plan decision 5). Corrections are new records.
4. **The database rechecks** the settlement, the basis marks (of the return, new, not charged before), the numbering,
   the refund ceiling, and that each named document is the receivable (charge) or payable (refund) invoice of the
   booking's customer in the agreement currency for the amount. Records are never updated or deleted.
5. **Permissions and rules as before**: reading under the rental read rules, writing under `rental.approve`;
   idempotency scopes `rental.damage_charge` and `rental.refund`; module off writes nothing; branch scope by the
   booking's pickup branch; another company's booking or book is refused. Errors: `RENTAL_CHARGE_STATE` (not settled,
   a basis mark that is not new, of another inspection or already charged), `RENTAL_REFUND_EXCEEDS`.

## Acceptance of R7b — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R7b-01 | A damage charge on new return marks writes a receivable draft; a payable and an external refund are their own records; the view lists them | NOT TESTED |
| R7b-02 | Before settlement, a mark that is not new or already charged, and a refund over the ceiling are refused; both need `rental.approve` | NOT TESTED |
| R7b-03 | The settlement, the security and earlier charges are unchanged; FIN-03 keeps the drafts linked | NOT TESTED |
| R7b-04 | The database refuses updates, deletes and forged records or documents; module off writes nothing; scope holds | NOT TESTED |
| R7b-05 | 0106 -> 0107 keeps every row; the full suite stays green | NOT TESTED |

## Not in R7b

The reconciliation per agreement (R7c); paying, issuing or posting the drafts (FIN-03's own flows); a FIN-03 credit
note kind; screens (R8).
