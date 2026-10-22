# L6 — prepaid packages and gift certificates: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l6-prepaid`, parent `7c7230a`
([L6 design](../../PACKAGE_L6_DESIGN_2026-10-22.md)), source commit `affdaf327c3904695876b2296c99aadfdad92b4a`. [CHECKS.json](CHECKS.json) was
written before the source commit and binds every source blob, command, exit code and log digest. No
network; readiness unchanged (BEAUTY-01 stays partial until L8).

## What changed

| Area | Change |
|---|---|
| Sale | `POST .../prepaid`: a FIN-03 receivable draft with one line on the named prepayment liability (a non-liability account is refused) and a `prepaid_balances` row — a package (units of one service) or a certificate (an amount); nothing is revenue; usable once the sale invoice is issued and fully paid |
| Redemption | `POST .../bookings/{id}/redeem`: a FIN-03 credit note of the visit invoice, issued at once, its lines on the prepayment account (reason "Prepaid redemption"); a package unit is worth price/units, the last takes the remainder (100.00 / 3 = 33.33, 33.33, 33.34); a certificate credits the visit lines in order (60.00 of a 70.00 visit: 50.00 and 10.00); at most the unpaid amount |
| Refusals | Unpaid sale, no unit or value left, the same balance twice on one visit, another customer, no matching service, nothing unpaid |
| Schema (0071) | `prepaid_balances`, `prepaid_redemptions`; used units and amount only grow, by exactly the redemption of the same transaction, never past what was sold; tenant policies, branch scope for redemptions |
| Rights | `finance.manage` of a company-wide member under the ledger lock; front desk is refused and nothing is credited |

## Failures kept

- **red-1**: 6 failed (routes 404, migration 0071 missing) — expected.
- **dev-1**: 2 failed — test bugs: the replay sent a fresh credit number under the same key
  (`IDEMPOTENCY_KEY_REUSED` was the right answer), and visits of one test shared an hour and artist.
- **dev-2**: 1 failed — 75-minute visits at hourly starts overlapped; spaced two hours apart.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l6-20261022-7c7230a`: **static-1** PASS; **focused-1** PASS, **427
passed**; **full-1** PASS, **2510 passed, 4 skipped**.

## Remaining

A catalog of package products, expiry and breakage, refunds of an unused balance and partial units are
later decisions; a line already credited in part is refused by FIN-03 rather than capped. No screen yet
(L7). Migrations 0001–0070 unchanged; the next is **0072**.
