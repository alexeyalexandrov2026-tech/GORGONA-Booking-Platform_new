# L4 — visit billing: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l4-billing`, parent `c45607f`
([L4 design](../../PACKAGE_L4_DESIGN_2026-10-22.md)), source commit `0738b4a12e8163b86698eec0bf6722c095d0b13e`. [CHECKS.json](CHECKS.json) was
written before the source commit and binds every source blob, command, exit code and log digest. No
network; readiness unchanged (BEAUTY-01 stays partial until L8).

## What changed

| Area | Change |
|---|---|
| Invoice | `POST .../bookings/{id}/invoice` saves a FIN-03 receivable draft: the quote lines of a confirmed visit (name and price, on the named revenue account), then fee lines (description, amount, account); a cancelled visit only fee lines; a hold or an expired booking is refused; the quote's currency |
| Link (0069) | `visit_invoices`: one invoice per visit, permanent (select and insert only), tenant and branch scope; the same key repeats the answer, another key is `VISIT_ALREADY_INVOICED` |
| Payments | Issue, a deposit and the rest are the unchanged FIN-03 routes; `GET .../bookings/{id}/invoice` shows the invoice and, once issued, the obligation (paid, available) — tested with a 20.00 deposit and the 50.00 rest |
| Rights | `finance.manage` of a company-wide member under the ledger lock; reading needs `finance.read`; front desk is refused and nothing is written |

## Failures kept

- **red-1**: 7 failed (route 404, migration 0069 missing) — expected.
- My first draft of the tests reached the booking world through the payment fixture, which cannot
  work; rewritten before any run.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l4-20261022-c45607f`: **static-1** PASS; **focused-1** PASS, **378
passed**; **full-1** PASS, **2494 passed, 4 skipped**.

## Remaining

Fees and deposits computed from a structured published policy are a later decision (the policy has
text only; fee lines are named by a finance user). No screen yet (L7). Migrations 0001–0068 unchanged;
the next is **0070**.
