# M7b — transport money on the order and trip screens: local validation

**PASS for this bounded local, synthetic slice (package M, money screens).** Branch
`codex/package-m7b-money-screens`, parent `745bac9` ([M7b design](../../PACKAGE_M7B_DESIGN_2026-10-25.md),
[ADR-0033](../../../adr/0033-transport-money.md)), source commit `f44db22`. [CHECKS.json](CHECKS.json) was
written before the source commit and binds every source blob, command, exit code and log digest. User
2026-10-25: "First fix the two open defects (night-time workforce test, silent refused grant offer), then M7b."

## What changed

- Strict web contracts for the M7a routes: the rate and its versions, the order invoice (a FIN-03 invoice and
  its obligation), the trip's pay components with their accruals.
- **Money for an order** (the "Money" button in the Orders table, a company-wide owner or manager only): the
  current rate and version; a rate form saved with the expected revision; once there is a rate, the customer
  invoice form (book, receivable and revenue accounts, date, number, billed miles, named extras) creating the
  FIN-03 draft; afterwards its lines, total, state and what is paid and open.
- **Trip pay** on the trip page: the components with recipient, role, formula and accrual; register a
  component (fixed amount, per mile, percent of an agreed base); accrue one with its book and accounts.
- Refusals in words; a branch-limited member and a delegate never see money; every select in the money panels
  has an explicit accessible name. No migration.

## Proof

`test_m7b_money_browser.py` (real Chromium, desktop and mobile, axe, no horizontal scroll): a per-mile rate of
2.35 (version 1); an invoice without miles refused with "billed miles"; with 412.5 miles and a 75.00 extra the
draft shows 969.38 and 75.00, total 1044.38 USD; a driver's 0.55 per mile and a 7.5% of 1250.00 dispatch fee
registered; the driver's pay accrued as 226.88 USD (draft); read back through the API and the rate row from the
database. `transport-forms.spec.ts`: a carrier's dispatcher sees no "Money" button and no "Trip pay".
`transport-contracts.spec.ts` (+1): strict money responses and their routing.

## Failures kept

- red-1: no "Money" button and no money schemas (intended RED).
- Before dev: eslint set-state-in-effect in the books hook; ruff E501 in the test docstring.
- dev-1: the Formula select inside its label took every option's text into its accessible name, so "Percent"
  matched two fields — fixed by naming every select explicitly (an accessibility fix, not only a test fix).
- Gates passed on the first run.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-m7b-20261025-745bac9`: **static-1** PASS; **focused-1** PASS,
**734 passed**; **full-1** PASS, **2615 passed, 4 skipped** (0:54:20 locally).

## Remaining

M8: package M acceptance (TMS-01..03) with one independent review — that review needs the owner's consent for
an extra agent; readiness only on the owner's word. Later: advances, deductions, fuel surcharges, factoring and
quick pay; planning for a delegate; fleet corrections. Next migration **0080**.
