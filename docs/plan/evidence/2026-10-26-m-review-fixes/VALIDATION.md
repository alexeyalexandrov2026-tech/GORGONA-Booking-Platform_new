# Package M review fixes R-01..R-09: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-m-review-fixes`, parent `b9b76ee`
([fix design](../../PACKAGE_M_REVIEW_FIXES_2026-10-26.md), amendments to
[ADR-0030](../../../adr/0030-transport-stop-events.md) and [ADR-0033](../../../adr/0033-transport-money.md)),
source commit `44b8505`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every source
blob, command, exit code and log digest; the twelve committed blobs were checked against it. Owner 2026-10-26: one
independent review of package M by one extra agent, fix the findings, then propose the `main` update.

## What changed

- **R-01** FIN-03 refuses to edit a transport order invoice draft or a pay accrual draft
  (`FINANCIAL_DOCUMENT_LINKED`); they issue through their own documents.
- **R-02** A leg is open for its planned quantity until its pickup stop is departed, then for loaded minus
  delivered, refused and damaged; a leg loaded short closes, so the order bills and the trip's pay accrues.
- **R-03** Migration **0081**: a trigger on `transport_loads` refuses adding, enlarging or removing a load of an
  invoiced order under the order-rate advisory lock (409 `TRANSPORT_ORDER_INVOICED`); an unchanged load passes,
  so the order can still be renamed.
- **R-04** Stop windows carry an explicit end date on the screen; a missing one closes on the next local day.
- **R-05, R-06** Money lines are bounded below 10^15 minor units (422 `TRANSPORT_AMOUNT_TOO_LARGE`) and exact to
  the currency (422 `TRANSPORT_AMOUNT_PRECISION`); per-mile rates keep their precision.
- **R-07** A concurrent pay component on the same id waits and is compared: identical 200, different 409.
- **R-08, R-09** Module text, the M7a-06 wording and the grant label "Plan trips (API only)".

## Proof

| id | Result | Test |
|---|---|---|
| RF-01 | PASS | `test_transport_drafts_are_not_edited_through_fin03` |
| RF-02 | PASS | `test_a_leg_loaded_short_closes_once_its_pickup_is_departed`; web `legOpen` unit test |
| RF-03 | PASS | `test_an_invoiced_order_keeps_its_loads`; `test_m_review_upgrade.py` (0080 → 0081) |
| RF-04 | PASS | web unit test "a stop window survives editing exactly" |
| RF-05, RF-06 | PASS | `test_amounts_are_bounded_and_exact` |
| RF-07 | PASS | `test_a_concurrent_pay_component_on_the_same_id_waits_and_compares` (both cases; a `transactionid` wait observed in `pg_locks`) |
| RF-08 | PASS | full suite below |

## Failures kept

- red-1: 6 failed, 1 passed (the different-rate race case already answered 409); web unit failed because
  `transport-rules` was missing — intended RED.
- dev-1 static: ruff E501 ×4 and tsc TS2345 in the stop-window test; fixed.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-mreview-20261026-b9b76ee`: **static-1** PASS; **focused-1** PASS,
**807 passed**; **full-1** PASS, **2628 passed, 4 skipped** (1:00:23 locally).

## Remaining

Package M with its review fixed is ready for the owner's decision on the `main` fast-forward. Readiness and
enabling transport wait for the owner's word. Then N2..N7. Next migration **0082**.
