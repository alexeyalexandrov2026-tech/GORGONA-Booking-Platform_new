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
| L8b1 | Review fixes R8-R15 (decisions 61-68) |
| L8b2 | Acceptance gaps: races with an observed `pg_locks` wait for consumption, accrual and redemption; module gates (L-10); a room stage (L-04) |
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

## L8b1 decisions (added 2026-10-23, same delegation)

Branch `codex/package-l8b1-review-fixes` from the L8a head (`ef71142`). All of R8-R15 were confirmed against
the code before this design.

61. **A stage save always bumps the revision (R8).** Replacing a service's stages touches the variant row
    (`updated_at = clock_timestamp()`), so the revision grows even when the total minutes stay the same or
    the stages are cleared; a stale save is refused (`SERVICE_REVISION_CONFLICT`).
62. **The customer site takes every visit's stages (R9).** The web quote contract accepts up to 50 stages
    (five services of at most ten stages), still strict.
63. **Reschedule keeps one specialist for the whole visit (R10).** The further services of the stored quote
    (each variant line with its own add-ons) are passed to the availability check, so the new specialist must
    serve every service (L2 decision 14).
64. **Module gates (R11).** Saving a commission plan and accruing a commission need the workforce module
    (plan decision 8); reads continue, as for every module that is turned off. Posting a consumption needs
    the inventory module even when nothing is written off. A missing module answers `MODULE_DISABLED` and
    writes nothing.
65. **The write-off place is the visit's branch (R12).** The storage place of a consumption must belong to the
    branch of the completed visit (`VISIT_PLACE_OTHER_BRANCH`, 422).
66. **Plan refusals are readable (R13).** An unknown payee or service in a plan is `INVALID_REFERENCE` (422);
    two first saves racing end with one plan and one `COMMISSION_PLAN_REVISION_CONFLICT` (409), never a 500.
67. **A package is sold in its service's currency (R14).** Otherwise `PREPAID_CURRENCY_MISMATCH` (422).
68. **The desk forgets a used balance (R15).** After a redemption the desk reloads the customer's balances and
    no longer offers a balance already used on this visit; after a page reload the server's refusal
    (`PREPAID_ALREADY_USED`) is shown in its own words.

| id | Requirement (L8b1, NOT TESTED) |
|---|---|
| L8-09 | Replacing stages with the same total, or clearing them, bumps the revision; the old revision is refused |
| L8-10 | The web quote contract parses an 11-stage version 2 quote and refuses 51 |
| L8-11 | A two-service visit cannot be moved to a specialist who does not serve the second service |
| L8-12 | With workforce off, saving a plan and accruing answer `MODULE_DISABLED` while the plan read continues; with inventory off, posting an empty consumption answers `MODULE_DISABLED`; nothing is written |
| L8-13 | A write-off place of another branch is refused |
| L8-14 | A plan naming an unknown payee or service is refused with 422; two racing first saves leave one plan and one 409 |
| L8-15 | A package in another currency than its service is refused |
| L8-16 | After a redemption the desk no longer offers that balance (browser) |


## L8b2 decisions (added 2026-10-23, same delegation)

Branch `codex/package-l8b2-acceptance-gaps` from the L8b1 head. Closes the acceptance gaps L-03, L-04 and
L-10 named in the review and in the L-01..L-12 mapping.

69. **Once under a race, observed (L-03).** Two concurrent consumptions of one visit, two concurrent accruals
    of one visit's commission and two concurrent redemptions of a one-unit package (two visits) each leave
    exactly one write; each race is proven with an observed `pg_locks` wait behind a barrier transaction that
    holds the row the service locks.
70. **The desk follows the modules (L-10).** The visit desk reads the business configuration once
    (`effective_module_ids`) and shows each step only when its modules are on: materials with `inventory`,
    billing and prepaid redemption with `finance_documents`, the commission with `workforce`. A missing
    module shows one plain line ("Materials are turned off in this business's configuration") instead of
    the form. If the configuration cannot be read, the desk shows the steps as before and the server's
    refusal speaks.
71. **Every step refuses without its module (L-10).** Billing, prepaid sale and redemption without
    `finance_documents`, consumption without `inventory`, plan and accrual without `workforce` answer
    `MODULE_DISABLED` (or the module's own refusal) and write nothing; completing a visit needs only booking.
72. **A room is a stage resource (L-04).** A stage that needs a `room` holds a room in the shared occupancy;
    a staff reservation of that room for an overlapping time is refused, and the specialist stays free during
    processing.

| id | Requirement (L8b2, PASS locally in `1e4368a`) |
|---|---|
| L8-17 | Consumption, accrual and redemption races each leave one write after an observed `pg_locks` wait |
| L8-18 | With workforce off the desk shows no commission form; with inventory off no materials form; real browser desktop and mobile, keyboard, axe |
| L8-19 | Each step without its module is refused and writes nothing |
| L8-20 | A room stage holds the room; an overlapping staff reservation of it is refused |
