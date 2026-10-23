# L8b1 — package L review fixes R8-R15: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l8b1-review-fixes`, parent `02724a9`
([L8 design](../../PACKAGE_L8_DESIGN_2026-10-23.md), decisions 61-68; [review](../2026-10-23-l8-review/REVIEW.md)),
source commit `ee7fc1b`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every
source blob, command, exit code and log digest. No new route, no migration; readiness unchanged.

## What changed

| Finding | Fix |
|---|---|
| R8 | Replacing a visit's stages always sets `updated_at`, so the revision moves even when the total is the same or the stages are cleared |
| R9 | The site accepts up to 50 stages, the API's limit |
| R10 | Reschedule passes every further service of the visit (`_further_services`), so the new specialist must serve all of them |
| R11 | Commission plan save and accrual need the workforce module; a consumption needs the inventory module even with nothing to write off (reads stay open, decision 64) |
| R12 | A write-off place must be in the visit's branch (`VISIT_PLACE_OTHER_BRANCH`) |
| R13 | An unknown payee or service in a plan is refused (`InvalidReferenceError`); two racing first saves give one plan and a revision conflict instead of a raw unique violation |
| R14 | A package is sold only in its service's currency (`PREPAID_CURRENCY_MISMATCH`) |
| R15 | The visit desk stops offering a balance already used on this invoice |

## Proof

`tests/integration/test_l8b1_finance_fixes.py` (5, real PostgreSQL): a plan save and an accrual refused
without workforce; unknown payee and service refused; two first saves race (the second waits on a
`transactionid` lock, observed in `pg_locks`) and the loser gets a revision conflict; a EUR package for a USD
service refused. `test_l8b1_booking_fixes.py` (2): a same-total stage save bumps the revision; a visit of two
services cannot move to a specialist who serves only the first. `test_l8b1_stock_fixes.py` (1): a write-off
from another branch's place is refused. Web: `customer-visit.spec.ts` accepts 11 and 50 stages and refuses 51;
`prepaid.spec.ts` shows the used balance gone after a redemption (desktop and mobile, axe clean).

## Failures kept

- web red: `customer-visit.spec.ts` 1 failed (11 stages refused) — expected.
- red-1: 9 failed, each reproducing its finding (plan saved without workforce, empty consumption without
  inventory, raw foreign-key error, raw unique violation after an observed lock wait, EUR package sold,
  revision kept, used balance still offered). Two test bugs fixed: the R10 move ran past closing time
  (moved to 12:00) and the R12 test passed a UUID into JSON.
- red-2: R10 move and R12 write-off both accepted (200) — reproduced.
- dev-1: 71 passed, 1 failed — the prepaid browser spec expected the redemption form to stay, but the desk
  hides it with no usable balance left: test bug; the spec now expects the form gone.
- **L8a CI run 39971712190 FAILED** (api job, browser wrappers), in areas L8a did not touch:
  `management.spec.ts:121` [mobile] found 4 "Loading…" statuses besides "Business profile saved" (strict
  mode); `service-catalog.spec.ts:152` [desktop] the new equipment row did not show within 5 s. Both passed
  locally and in L7c CI. Fixed in a separate spec commit on this branch.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l8b1-20261023-02724a9`: **static-1** PASS; **focused-1** PASS,
**466 passed**; **full-1** PASS, **2543 passed, 4 skipped** (40 minutes locally).

## Remaining

L8b2: races with an observed `pg_locks` wait for consumption, accrual and redemption; the desk follows the
enabled modules; every step refuses without its module (L-10); a room stage against staff reservations (L-04).
L8c: the BEAUTY-01 acceptance record (readiness and `main` only on the owner's word). Next migration **0072**.
