# L7b2b — prepaid screen and redemption on the desk: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l7b2b-prepaid-screens`, parent `fa30344`
([L7 design](../../PACKAGE_L7_DESIGN_2026-10-22.md), decisions 45-47), source commit `3d2658a`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No migration; readiness unchanged.

## What changed

| Area | Change |
|---|---|
| Prepaid screen | Lists the business's balances (customer, package of a service or certificate, remaining, sale invoice, usable or waiting for payment), filters by customer, and sells one as a draft invoice line on a prepayment liability |
| Visit desk | While the issued visit invoice is open, the usable balances of its customer in its currency are offered; one is redeemed with a credit number and date; the desk shows "Credited X" |
| API | `GET .../prepaid` (`finance.read`): creation order, at most 50 a page with an `after` cursor, optionally of one customer |
| Contracts | Strict schemas for a balance (a package names a service and units, a certificate neither; remaining never above units), the list and a redemption (an issued FIN-03 credit note) |

## Proof

API: three balances list in creation order, page with the cursor, filter by customer; a front-desk member
is refused (403), a member of another business sees nothing, bad parameters are refused (422).

Real Chromium through the actual OIDC/PKCE sign-in, desktop and mobile: a package of one base visit for
50.00 is sold to the project's FAKE customer, shown "Waiting for payment"; finance issues and settles its
invoice through the FIN-03 routes; after a reload it is "Usable"; the desk of the customer's issued visit
invoice shows "Paid 0.00 of 50.00", redeems the package, and shows "Credited 50.00"; keyboard-only close,
axe without violations, no horizontal scroll. The database then holds, per customer, one balance with one
used unit (5000 minor units) and one redemption of that visit.

## Failures kept

- Web contract spec red (2 failed, 4 passed); API and browser red (list route 405, no Prepaid page) — expected.
- dev-1: a test bug (the payment helper settles only for the fixture customer; that sale now stays unpaid)
  and a **real accessibility bug** on mobile — the scrollable balances table was not keyboard reachable
  (axe `scrollable-region-focusable`); it is now a labelled region with `tabIndex=0`, as on the finance and
  ledger screens.
- dev-2: the database check grouped by `b.id` instead of the key `(tenant_id, id)` — test SQL bug.
- gates-1: static web-format failed — the new browser spec was not prettier-formatted (a slip).

## Gates (final, suffix 2)

Run folder `GorgonaBookingTests/package-l7b2b-20261023-fa30344` (worktree `package-l7b2b`): **static-2**
PASS; **focused-2** PASS, **442 passed**; **full-2** PASS, **2520 passed, 4 skipped** (42 minutes locally).

## Remaining

L7c: the customer site — several services in one visit and the stages of a staged service. Then L8
(BEAUTY-01 acceptance). The next migration is **0072**.
