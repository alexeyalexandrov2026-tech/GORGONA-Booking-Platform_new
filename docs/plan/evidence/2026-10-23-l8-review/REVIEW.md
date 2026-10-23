# Package L — independent review (2026-10-23)

One independent review agent, started with the owner's consent («Да, запускай одного независимого
проверяющего для пакета L.»). Read-only over `0591d3a..11f5674` (package L, L1-L7c): no file changed, no test,
database or browser run. 15 findings survived the reviewer's own refutation pass. Each was then re-read
by the implementing agent against the code; the column "Checked" says what that check found.

| id | Severity | Where | Defect | Checked | Fixed in |
|---|---|---|---|---|---|
| R1 | high | `business/commissions.py` `accrue_commission` | No booking status check and the booked quote is the base: a cancelled visit whose fee-only invoice is paid accrues the full service commission | Confirmed: only the invoice's paid state is checked | L8a `e3d45de` |
| R2 | high | `business/visit_billing.py` `_lines`, `business/commissions.py` | Catalog `price_cents` is hundredths everywhere (screens `cents/100`), but billing and commissions read it as the currency's own minor units: a 0-decimal currency is billed 100x, a 3-decimal one 1/10 | Confirmed: `_money(price_cents, units)` | L8a `e3d45de` |
| R3 | medium | `api/salons.py` reschedule and cancel | A completed, consumed, invoiced or commissioned visit can still be rescheduled (old booking cancelled, new one with the same quote) or cancelled; the new booking can be completed, consumed, billed and commissioned again | Confirmed: only the booking status is checked | L8a `e3d45de` |
| R4 | medium | `business/prepaid.py` `_credits` | A package unit's credit is capped at the line and at the open amount, yet the whole unit is used: value worth more than the line stays in the liability forever | Confirmed: `min(worth, line, available)` with one unit used | L8a `e3d45de` |
| R5 | medium | `business/prepaid.py` `_credits` | The package's service is found by its quote position and used as an index into the invoice lines; on a cancelled visit's fee-only invoice the unit is spent on a fee | Confirmed | L8a `e3d45de` |
| R6 | medium | `business/visit_billing.py` `_lines` | A zero-priced quote line (allowed by the catalog) makes the visit unbillable: invoice lines must be at least 1 minor unit | Confirmed: `amount_minor between 1 and ...` | L8a `e3d45de` |
| R7 | medium | `api/financial_documents.py` draft save | A visit invoice, commission accrual or prepaid sale is an ordinary draft that any finance manager may rewrite before issue; package L keeps trusting its first content | Confirmed: `save_draft` has no link check | L8a `e3d45de` |
| R8 | medium-low | `api/salons.py` stage replace | Replacing stages with the same total (or clearing them) changes no column, so the revision is not bumped and a stale save is not detected | Confirmed: `bump_revision` fires only on a real row change | L8b1 `ee7fc1b` |
| R9 | low | `web/lib/contracts.ts` | The site caps a quote at 10 stages; a visit may have up to 50 | Confirmed: `.max(10)` | L8b1 `ee7fc1b` |
| R10 | low | `api/salons.py` reschedule | Rescheduling a visit of several services checks the new specialist against the first service only | To verify in L8b | L8b1 `ee7fc1b` |
| R11 | low | commissions, `business/visits.py` | Commission plan and accrual never check the workforce module; a consumption with nothing to write off skips the inventory check | To verify in L8b | L8b1 `ee7fc1b` |
| R12 | low | `business/visits.py` | The write-off place may be in another branch | To verify in L8b | L8b1 `ee7fc1b` |
| R13 | low | `business/commissions.py` | An unknown service or payee in a plan, or two racing first saves, is a raw database error (500) | To verify in L8b | L8b1 `ee7fc1b` |
| R14 | low | `business/prepaid.py` | A package may be sold in a currency other than its service's and can then never be redeemed | To verify in L8b | L8b1 `ee7fc1b` |
| R15 | low | `web/components/visit-billing.tsx` | After a redemption the desk does not reload the balances | To verify in L8b | L8b1 `ee7fc1b` |

## Found sound by the reviewer

RLS enabled and forced on all 10 new tables, `tenant_id` in every key and join, branch policies; finance
routes company-wide, no delegation on new routes; once-only writes (idempotency claim, primary key, row
lock, ledger lock, guard triggers); lock order without a cycle; stage occupancy and its mirror; migrations
0066-0071 safe on existing rows; commission rounding; strict web contracts and kept idempotency keys.

## Acceptance gaps named by the reviewer

L-04 (no room stage, no staff reservation against a staged visit), L-06 (R6, R7; fees by published policy
not built), L-07 (R1), L-08 (R4), L-10 (essentially untested; workforce not gated, R11), L2-14 on
reschedule (R10), L7-01 (R8), L-12 pending.
