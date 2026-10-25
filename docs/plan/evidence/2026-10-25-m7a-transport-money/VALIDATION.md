# M7a — transport money through FIN-03: local validation

**PASS for this bounded local, synthetic slice (package M, money).** Branch `codex/package-m7-transport-money`,
parent `00470fc` ([M7a design](../../PACKAGE_M7A_DESIGN_2026-10-25.md),
[ADR-0033](../../../adr/0033-transport-money.md)), source commit `b2998d5`. [CHECKS.json](CHECKS.json) was
written before the source commit and binds every source blob, command, exit code and log digest. User
2026-10-25: "Continue with M7 the same way."

## What changed

- Migration **0079**: `transport_order_rates` (insert-only versions of an order's agreed rate, fixed or per
  mile, with the expected revision; frozen by the invoice under the order's lock), `transport_order_invoices`
  (one per order), `transport_pay_components` (registered once; one per trip, recipient and role) and
  `transport_pay_accruals` (one per component); module gate; RLS; trip money follows the trip's branch.
- Routes: `GET/PUT orders/{id}/rate`, `GET/POST orders/{id}/invoice`, `GET trips/{id}/pay`,
  `PUT trips/{id}/pay/{component}`, `POST trips/{id}/pay/{component}/accrue`. Writes need
  `finance.manage`, reads `finance.read`; never a delegate; invoice and accrual take the ledger lock.
- The customer invoice is a FIN-03 receivable draft: the freight line (per mile × billed miles, half up to the
  currency's minor units) and up to 20 named extras, only when every load is planned and nothing is open.
- Each pay component (driver, owner-operator, dispatch fee, other; fixed, per mile or a percentage of an agreed
  base) accrues once as a FIN-03 payable manual accrual on a closed trip: its own obligation. FIN-03 keeps every
  payment within the open balance (checked when a settlement is reserved).

## Proof

`test_m7a_transport_money.py` (M7a-01..06, real PostgreSQL through the API): rate versions, a stale revision and
the freeze after invoicing; no rate, open legs, unplanned loads and missing miles refused; 2.35 × 412.5 = 969.38
plus a 75.00 extra; one invoice per order with a replayed key; issue and payment through FIN-03 and an
over-payment refused; components once per id and per recipient and role, invalid formulas refused; accruals
refused on an open trip, then 226.88 (per mile), 93.75 (7.5% of 1250.00) and 40.00 (fixed) as three
obligations; a partial payment of 100.00 leaves 126.88 and a reservation of 130.00 is refused; a front desk, a
carrier dispatcher with every transport right and another company are refused and nothing is written; with the
module off a rate is refused. `test_m7_upgrade.py` (M7a-07): 0078 → 0079 keeps every row.

## Failures kept

- red-1: 7 failed — money routes 404, no money tables, no migration 0079 (expected RED).
- Before dev: ruff E501, S608, RUF001, RUF100 and a mypy arg-type in the new code.
- dev-1: **code** — accruals were loaded as invoices (the `manual_accrual` kind was missing); test — settlements
  were prepared for the finance fixture's counterparty, not the customer or payee; the inventory and stock
  upgrade table lists needed the 0079 tables. dev-2: test data — the accrual was dated after the payment that
  settles it. dev-3: test expectation — FIN-03 checks the open balance at reservation, not at preparation.
- full-1: **1 failed**, 2611 passed — `test_agreement_browser` on desktop lost its Chromium session ("Protocol
  error … session closed") while waiting for the contracts region; mobile passed, it passed alone (dev-5) and
  M7a changes no web or agreement code. Gates were rerun as suffix 2.

## Gates (suffix 2)

Run folder `GorgonaBookingTests/package-m7a-20261025-00470fc`: **static-2** PASS; **focused-2** PASS,
**730 passed**; **full-2** PASS, **2612 passed, 4 skipped** (0:54:56 locally).

## Remaining

M7b (money on the order and trip screens), then M8 (acceptance). Advances, deductions, fuel surcharge formulas,
factoring and quick pay are their own later decisions. Open defects: the time-of-day-dependent workforce
browser test (M6a), the silent refused grant offer (M6b). Transport stays not enableable until package M's
acceptance and the owner's word. Next migration **0080**.
