# Package R, slice R7b — damage charges and refunds of a rental agreement (2026-11-08)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decisions 5 and 8, acceptance R-07.
Previous slice: [R7a](PACKAGE_R7A_DESIGN_2026-11-07.md); handoff [NEXT_AGENT_PACKAGE_R7B_2026-11-08.md](NEXT_AGENT_PACKAGE_R7B_2026-11-08.md).
Branch `codex/package-r7b-rental-damage-refunds` from the R7a docs commit `2ef404e`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after each slice. R7a CI run 42449693704 on `2ef404e`: success.

A refund uses the existing FIN-03 credit note (H3, migration 0027): a credit note against the issued obligation of the
settlement or damage-charge invoice; at its issue FIN-03 itself turns the paid part into a separate refund obligation.
Correction 2026-11-08 before red: the first design commit `0453d6a` said FIN-03 has no credit note and proposed a payable
invoice; that was wrong (a slip, recorded).

## Scope

- Migration **0107**: `rental_damage_charges` and `rental_refunds` (insert-only, numbered 1, 2, 3 per booking), each
  with its FIN-03 draft when it has one; guards under the class row lock; module gate; tenant isolation; branch scope
  last.
- Service `business/rental_charges.py`; routes `GET bookings/{id}/charges`, `POST bookings/{id}/damage-charges`,
  `POST bookings/{id}/refunds`; `financial_documents` keeps a charge invoice linked and `credit_notes` keeps a refund
  credit note linked (`FINANCIAL_DOCUMENT_LINKED`).

## Decisions (R7b, agent)

1. **A damage charge** needs `rental.approve`, a settled booking (R7a) and as its basis one or more marks of the
   return inspection that are new since the handover; each new mark is charged at most once. It has an amount above 0
   in the agreement currency, a reason, and one FIN-03 receivable invoice draft of the customer for that amount,
   written in the same request.
2. **A refund** needs `rental.approve` and a settled booking, an amount above 0 and a reason; all refunds of a booking
   never exceed the settlement total plus the damage charged. Its method is `credit` (a FIN-03 credit note draft, in
   the same request, against the issued obligation of the settlement or a damage-charge invoice of the booking, reducing
   its lines in order up to the amount; refused while that invoice is not issued) or `external` (a reference and the
   time it was made).
3. **Separate obligations.** A charge or a refund never edits the settlement, the security or another charge; a
   security capture never edits a charge (rental plan decision 5). Corrections are new records.
4. **The database rechecks** the settlement, the basis marks (of the return, new, not charged before), the numbering,
   the refund ceiling, and that a charge names the receivable invoice of the booking's customer in the agreement
   currency for its amount and a credit refund a credit note of an obligation of the booking's settlement or charges for
   its amount. Records are never updated or deleted.
5. **Permissions and rules as before**: reading under the rental read rules, writing under `rental.approve`;
   idempotency scopes `rental.damage_charge` and `rental.refund`; module off writes nothing; branch scope by the
   booking's pickup branch; another company's booking or book is refused. Errors: `RENTAL_CHARGE_STATE` (not settled,
   a basis mark that is not new, of another inspection or already charged), `RENTAL_REFUND_EXCEEDS`.

## Acceptance of R7b — PASS 2026-11-08 (code `b174d1b`, [evidence](evidence/2026-11-08-r7b-rental-damage-refunds/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R7b-01 | A damage charge on new return marks writes a receivable draft; a credit-note and an external refund are their own records; the view lists them | PASS |
| R7b-02 | Before settlement, a mark that is not new or already charged, and a refund over the ceiling are refused; both need `rental.approve` | PASS |
| R7b-03 | The settlement, the security and earlier charges are unchanged; FIN-03 keeps the drafts linked | PASS |
| R7b-04 | The database refuses updates, deletes and forged records or documents; module off writes nothing; scope holds | PASS |
| R7b-05 | 0106 -> 0107 keeps every row; the full suite stays green | PASS |

## Not in R7b

The reconciliation per agreement (R7c); paying, issuing or posting the drafts (FIN-03's own flows); a FIN-03 credit
note kind; screens (R8).
