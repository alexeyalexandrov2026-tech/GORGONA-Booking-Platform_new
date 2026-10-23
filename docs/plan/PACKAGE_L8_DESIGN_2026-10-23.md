# Package L, slice L8 — BEAUTY-01 acceptance and review fixes: design (2026-10-23)

**Status: design; decisions taken by the agent under the owner's full delegation** («Делай как
считаешь нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22; «Делай как считаешь нужным,
я доверяю тебе», 2026-10-23). The one independent review ran with the owner's consent
([REVIEW.md](evidence/2026-10-23-l8-review/REVIEW.md)). Readiness changes and the fast-forward of `main`
still need the owner's word.

## Slices

| Slice | Deliverable |
|---|---|
| L8a | Review fixes of money and visit lifecycle: R1-R7 (decisions 54-60) |
| L8b | Review fixes R8-R15 and acceptance gaps: races with an observed `pg_locks` wait for consumption, accrual and redemption; module gates (L-10); a room stage (L-04) |
| L8c | BEAUTY-01 acceptance record: L-01..L-12 against the evidence, every gap named; readiness only on the owner's word |

## L8a decisions

54. **Commission of a confirmed visit only (R1).** Accrual refuses a booking that is not `CONFIRMED`
    (`VISIT_NOT_COMMISSIONABLE`, 409, nothing written). A cancelled visit's fee earns no commission.
55. **Catalog prices are hundredths (R2).** `price_cents` keeps its meaning everywhere (hundredths of the
    currency's main unit, as every screen shows it). Billing and commissions convert it exactly to the
    currency's minor units: `price_cents * 10**units / 100`; a price that is not exact in that currency
    (e.g. 123.45 of a 0-decimal currency) is refused (`VISIT_PRICE_NOT_EXACT`, 422) instead of rounded.
56. **A free line is not billed (R6).** A quote line priced at zero gets no invoice line; the visit invoice
    holds the priced lines of the quote in quote order, then the fee lines.
57. **Prepaid finds its line by meaning (R5).** A package is redeemed only on a `CONFIRMED` visit; its
    service's invoice line is the priced quote line of that variant mapped through decision 56, and must
    still carry the quote line's name and converted price; otherwise `PREPAID_NO_MATCHING_SERVICE`.
58. **A unit is spent only for its whole worth (R4).** A package unit credits exactly its worth (the last
    unit: the remaining value). If the visit's line or the invoice's open amount is smaller than that worth,
    the redemption is refused (`PREPAID_UNIT_EXCEEDS_LINE`, 409) and finance handles it by hand, so the
    liability always reaches zero with the last unit.
59. **Linked drafts are frozen (R7).** The generic draft save refuses a document that is a visit invoice,
    a commission accrual or a prepaid sale (`FINANCIAL_DOCUMENT_LINKED`, 409). Issue, settlement and credit
    notes stay as they are.
60. **A recorded visit stays put (R3).** Reschedule and cancel refuse a booking that has a completion, an
    invoice, a commission or a prepaid redemption (`VISIT_ALREADY_RECORDED`, 409); a later correction goes
    through the finance documents.

| id | Requirement (L8a, NOT TESTED) |
|---|---|
| L8-01 | A paid fee-only invoice of a cancelled visit accrues no commission; nothing is written |
| L8-02 | A visit in a 0-decimal currency priced 5000.00 is billed 5000 and its commission is computed on 5000; a 3-decimal currency is billed at the same main-unit price; an inexact price is refused |
| L8-03 | A visit with a free add-on is billed without a zero line; commission and redemption still work |
| L8-04 | A package is refused on a cancelled visit's fee invoice and on a line whose content differs |
| L8-05 | A unit worth more than the line or than the open amount is refused; three units worth exactly their lines bring the liability to zero |
| L8-06 | Saving a linked draft (visit invoice, commission, prepaid sale) is refused; unlinked drafts save as before |
| L8-07 | Rescheduling or cancelling a completed, invoiced, commissioned or redeemed visit is refused; an untouched confirmed visit reschedules and cancels as before |
| L8-08 | The full suite and the L1-L7c browser tests still pass |
