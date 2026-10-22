# Package L, slice L6 — prepaid packages and gift certificates: design (2026-10-22)

**Status: design; decisions taken by the agent under the owner's full delegation** («Делай как
считаешь нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22; «continue»). Branch
`codex/package-l6-prepaid` from L5 (`ffddb66`). Builds package L decision 7
([plan](PACKAGE_L_PLAN_2026-10-22.md)) on FIN-03. A platform part: any direction that sells prepaid
sessions, passes or vouchers (fitness, spa, clinics, workshops, rentals) uses the same balance.

## What exists (inspected)

- FIN-03: a receivable invoice line may credit a liability account; a credit note against an issued
  invoice's line reduces it, and a counter account other than the line's needs a reason; a credit of
  an already paid part needs a refund obligation. Draft and issue are separate, both idempotent.
- L4: the visit invoice and its obligation; L5: the paid check.

## Decisions

34. **A prepaid balance is sold by an invoice line on a liability.** `POST /v1/salons/{id}/prepaid`
    saves a FIN-03 receivable draft to the customer with one line on the prepayment account the
    caller names (a liability), and records a `gba.prepaid_balances` row: a **package** of a number
    of units of one variant, or a **certificate** of an amount, its price, currency, customer and sale
    invoice. Nothing is revenue at sale. The balance becomes usable once the sale invoice is issued and
    fully paid (as in L5).
35. **What a unit is worth.** A package unit is worth its price divided by its units; the last unit
    takes the rounding remainder, so the units together use exactly the price and the liability
    returns to zero. A certificate is worth its price.
36. **Redemption is a FIN-03 credit note of the visit invoice.** `POST .../bookings/{booking}/redeem`
    names the prepaid balance, the credit date and number. The visit invoice must be issued, belong to
    the same customer and currency, and have that much still unpaid. A package credits the visit's
    line of its variant by one unit's value (at most that line's amount); a certificate credits the
    visit's lines in order up to its remaining value. The credit note's lines name the prepayment
    account (reason "Prepaid redemption") and it is issued at once: the liability moves to revenue
    exactly when the service is delivered.
37. **Never twice.** A balance's row is locked while redeeming; a package unit is used once per visit
    (`gba.prepaid_redemptions`, unique balance and visit); remaining units and value never go below
    zero (SQL checks); the same key repeats the answer.
38. **Rights.** Selling and redeeming need `finance.manage` of a company-wide member under the ledger
    lock.
39. **Later.** A catalog of package products, expiry and breakage (an unused remainder), refunds of an
    unused balance and partial units are later decisions (recorded).

## Acceptance for L6 (NOT TESTED)

| id | Requirement |
|---|---|
| L6-01 | Selling a package or certificate is a FIN-03 draft with one line on the prepayment liability; nothing is revenue; the balance is usable only after the sale invoice is fully paid |
| L6-02 | A package unit redeems the visit's line of its variant at price/units (the last unit takes the remainder); the credit note is issued with the prepayment account and the reason |
| L6-03 | A certificate redeems the visit's lines in order up to its remaining value |
| L6-04 | A unit is not used twice for one visit; a balance with no units or value left, another customer, another currency, an unpaid sale or a paid visit invoice is refused |
| L6-05 | After all units the prepayment liability of that sale is zero |
| L6-06 | Without finance rights nothing is written; another company sees nothing |
