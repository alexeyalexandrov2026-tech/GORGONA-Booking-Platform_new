# L5 — commissions and tips: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l5-commissions`, parent `12b64c9`
([L5 design](../../PACKAGE_L5_DESIGN_2026-10-22.md); decision 30 revised in dev-1), source commit `7ff9249f967e4f3a91dd6ff9dca9c6aa88f5782e`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No network; readiness unchanged (BEAUTY-01 stays partial until L8).

## What changed

| Area | Change |
|---|---|
| Plan (0070) | `commission_plans` (payee, currency, revision) and `commission_rules` (per service or default; percentage in basis points with two decimals at most, or a fixed amount; one rule per service including the default); `PUT .../staff/{resource}/commission` replaces the whole plan with the expected revision |
| Accrual | `POST .../bookings/{id}/commission`: only when the visit invoice is issued and fully settled (nothing available, reserved or credited); per service line with its add-ons, the service rule else the default, a percentage rounded half up (33.35 % of 70.00 = 23.35); fee lines never in the base; one FIN-03 payable manual-accrual draft to the payee; once per visit; issue and payment are FIN-03 |
| Tips | A tip is a visit invoice line on a liability account (never revenue). FIN-03 refuses a liability line on a payable document, so the tips are recorded and reported with the commission (`visit_commissions.tips_minor`); a revenue tips account is refused |
| Rights | `finance.manage` of a company-wide member; front desk is refused; another company sees nothing |

## Failures kept

- **red-1**: 10 failed (routes 404, migration 0070 missing) — expected.
- **dev-1**: 1 failed — the database refused the planned tips line on the payable accrual ("invoice
  needs an open counter account": a payable document names only expense or asset lines). Decision 30
  was revised (the design records it): tips stay a liability and are recorded with the commission.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l5-20261022-12b64c9`: **static-1** PASS; **focused-1** PASS, **388
passed**; **full-1** PASS, **2504 passed, 4 skipped**.

## Remaining

Paying the tips out to the person is a ledger entry for now (a payable to the person is a later
decision). A credited visit invoice refuses the commission; reversing an issued commission is a FIN-03
credit note. No screen yet (L7). Migrations 0001–0069 unchanged; the next is **0071**.
