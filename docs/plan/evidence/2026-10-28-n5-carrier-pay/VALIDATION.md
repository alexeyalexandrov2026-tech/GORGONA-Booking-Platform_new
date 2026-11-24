# N5 — carrier pay per accepted tender and margin per order: local validation

**PASS for this bounded local, synthetic slice (package N, N5).** Branch `codex/package-n5-carrier-pay`, parent
`f55ad07` ([N5 design](../../PACKAGE_N5_DESIGN_2026-10-28.md)), source commit `5dd4700`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit code
and log digest; the eight committed blobs were checked against it. Owner 2026-10-28: "continue" under full
delegation («Делай как считаешь нужным я доверяю тебе»).

## What changed

- Migration **0085**: `transport_tender_accruals` — one insert-only row per tender with the rate confirmation
  revision in force, the miles of a per-mile rate and its FIN-03 manual accrual document; module gate; tenant
  isolation; company-wide.
- `POST tenders/{tender}/accrual` (`transport.broker`): an accepted, not withdrawn tender with a version in force
  and closed tendered legs accrues once as a FIN-03 payable to its carrier — the fixed amount, or the rate times
  the miles (ADR-0033 rounding and bounds). A repeat key replays it. `GET tenders/{tender}/accrual` reads it.
- `GET orders/{order}/margin` (`transport.broker`), derived and never stored: the order's invoice total less the
  accrued pay of tenders whose legs carry only this order's loads; a tender that also carries another order is
  listed as shared and not subtracted; no margin without revenue or with mixed currencies.

## Proof

| id | Result | Test |
|---|---|---|
| N5-01 | PASS | `test_an_accepted_tender_accrues_once_for_the_version_in_force` (900.00 fixed; 2.10 × 412.5 = 866.25) |
| N5-02 | PASS | `test_open_legs_and_closed_tenders_are_refused`; missing miles and a second accrual in N5-01 |
| N5-03 | PASS | `test_the_margin_of_an_order_is_derived_from_its_own_tenders` (1500.00 − 900.00 = 600.00; shared listed) |
| N5-04 | PASS | `test_carrier_pay_is_a_broker_task_only` (another company, module off, SQL update and delete) |
| N5-05 | PASS | `test_n5_upgrade.py` (0084 → 0085); full suite below |

## Failures kept

- red-1: 5 failed, routes 404, no migration 0085 — intended RED.
- dev-1 (4 failed, 19 passed): "Accrual not found" — `load_invoice` reads kind `invoice` by default and the
  accrual is a `manual_accrual`; the kind is now passed. dev-2: 5 passed.

## Not tested

- Quick pay and factoring stay later (plan decision 6).

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-n5-20261028-f55ad07`: **static-1** PASS; **focused-1** PASS,
**831 passed**; **full-1** PASS, **2652 passed, 4 skipped** (0:43:54 locally).

## Remaining

N6 screens, N7 acceptance. Readiness and enabling transport wait for the owner's word. Next migration **0086**.
