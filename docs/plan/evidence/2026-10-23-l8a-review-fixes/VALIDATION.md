# L8a — package L review fixes R1-R7 (money and visit lifecycle): local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l8a-review-fixes`, parent `5839c03`
([L8 design](../../PACKAGE_L8_DESIGN_2026-10-23.md), decisions 54-60; [review](../2026-10-23-l8-review/REVIEW.md)),
source commit `e3d45de`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every
source blob, command, exit code and log digest. No new route, no migration; readiness unchanged.

## What changed

| Finding | Fix |
|---|---|
| R1 | Commission accrual refuses a booking that is not `CONFIRMED` (`VISIT_NOT_COMMISSIONABLE`); a cancelled visit's paid fee earns nothing |
| R2 | `catalog_minor` converts the catalog's hundredths exactly to the currency's minor units for billing and commissions; an inexact price is refused (`VISIT_PRICE_NOT_EXACT`) |
| R6 | A zero-priced quote line gets no invoice line (`priced_lines`) |
| R5 | A package unit is redeemed only on a `CONFIRMED` visit, on its service's priced line mapped through `priced_lines`, which must still carry the quote's name and amount |
| R4 | A unit credits exactly its worth; a smaller line or open amount is refused (`PREPAID_UNIT_EXCEEDS_LINE`), so the liability ends at zero |
| R7 | The generic draft save refuses a visit invoice, commission accrual or prepaid sale (`FINANCIAL_DOCUMENT_LINKED`) |
| R3 | Reschedule and cancel refuse a visit with a completion, invoice, commission or redemption (`VISIT_ALREADY_RECORDED`), before any time check |

## Proof

`tests/unit/test_visit_money.py` (6): exact conversions for 2, 0 and 3 decimals and the refusal of 123.45 in a
0-decimal currency. `tests/integration/test_l8a_review_fixes.py` (8, real PostgreSQL): a paid fee of a
cancelled visit accrues nothing and writes no row; JPY 5000.00 is billed `5000`, KWD 10.000 `10.000`, JPY
123.45 refused; a free add-on gets no line and the base line is still redeemed; a package is refused on a
fee-only invoice; units worth more than the line or the open amount are refused and stay unused; linked
drafts (visit invoice, prepaid sale) are refused while an unlinked draft saves; an invoiced visit cannot be
cancelled or rescheduled while an untouched one is cancelled.

## Failures kept

- red-1: collection error (`catalog_minor` missing) — expected.
- red-2: 7 failed, each reproducing its finding (commission accrued, JPY billed 500000, free add-on 422,
  package on a fee, oversized unit redeemed, linked drafts rewritten); the first R3 test was weak (the move was
  refused by another check) and was split.
- red-3: cancelling an invoiced visit succeeded (defect reproduced); the move was refused only by this test
  world's date window, so the new check runs before every time check.
- dev-1: before the run, mypy flagged `10**units` as `Any` and ruff a long comment line — fixed; 95 passed.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l8a-20261023-5839c03`: **static-1** PASS; **focused-1** PASS,
**458 passed**; **full-1** PASS, **2535 passed, 4 skipped** (37 minutes locally).

## Remaining

L8b: findings R8-R15; races with an observed `pg_locks` wait for consumption, accrual and redemption; module
gates (L-10); a room stage (L-04). L8c: the BEAUTY-01 acceptance record (readiness and `main` only on the
owner's word). The next migration is **0072**.
