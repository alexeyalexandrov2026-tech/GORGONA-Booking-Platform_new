# L9b — commission reversal after a refund: local validation

**PASS for this bounded local, synthetic slice (BEAUTY-01 gap L-07).** Branch
`codex/package-l9b-commission-reversal`, parent `c87d5c8` ([L9 design](../../PACKAGE_L9_DESIGN_2026-10-23.md),
decisions 81-85), source commit `00aadee`. [CHECKS.json](CHECKS.json) binds every source blob, command, exit code
and log digest; **it was written after the code commit** (see Failures kept). Readiness and `main` untouched.

## What changed

- Migration **0073**: `gba.visit_commission_reversals`, one permanent row per refund credit of the visit
  invoice, naming the FIN-03 credit note of the accrual that reversed its share (none, amount 0, when the refund
  touched no service line); RLS, branch scope, insert-only.
- `business/commission_reversals.py`: a refund is an issued, unvoided credit note of the visit invoice that is
  not a prepaid redemption. Per commission line the cumulative reversal is the line times the refunded share of
  its service (service line with its add-ons), half up; each refund takes what the target adds, so rounding
  never drifts. Accrual lines are matched to services in quote order by name.
- `POST /v1/salons/{id}/bookings/{booking}/commission/reversal` (finance rights, ledger lock): one FIN-03 credit
  note of the accrual, issued at once; the accrual must be issued (`VISIT_COMMISSION_NOT_ISSUED`); nothing left
  is `VISIT_NOTHING_TO_REVERSE`; a part already paid to the payee needs the refund control account (FIN-03). The
  commission read adds `reversals` and `to_reverse`.
- **Decision 85 (a defect found while writing these tests):** L5 refused a commission on any credited visit
  invoice, so a visit settled by a prepaid unit never earned its specialist's commission. The accrual now
  counts redemptions as settlement; a refund no longer blocks it and is reversed afterwards.
- Desk: "Reverse commission" shows the amount to reverse and records it; the list shows each reversal.

## Proof

`tests/integration/test_l9b_commission_reversal.py` (6, real PostgreSQL): a full refund reverses 7.00 (same key
answers the same, a second call has nothing to reverse, the accrual is credited 7.00); a refund of the massage
reverses its share 2.00; a fee-only refund records 0.00, then 10.01 and 25.02 reverse 1.00 and 2.50 (cumulative
3.50, no drift); a redemption credit is no refund (a visit settled by prepaid plus payment earns the commission;
nothing to reverse), a draft accrual is refused; a paid commission needs the refund account; two racing
reversals leave one after an observed `pg_locks` wait, lineage rows are insert-only and company scoped.
`test_l9b_upgrade.py`: 0072 -> 0073 keeps every row. Browser (`visit-billing.spec.ts`, desktop and mobile,
keyboard, axe): after a full refund the desk reverses 5.00 and lists it.

## Failures kept

- red-1: 6 failed — `to_reverse` missing and the route 404 (expected); a test bug (refund lines must use the
  account of the credited line); and the defect above (decision 85).
- dev-2: 3 failed, 21 passed — test bugs: a replay sent a new number (correct key-reuse refusal), the plan was
  saved twice, the commission payment used the customer's counterparty.
- dev-4: static failed — the web unit contract example lacked the new fields; the browser then ran on a stale
  build ("incomplete information").
- **dev-7: 8 passed but proved nothing about the reversal screen** — the edit script that added the refund
  fixture and spec steps had failed on CRLF line endings and the chained run continued; found, fixed, dev-9 ran
  the real steps (2 passed).
- **Slip: the record was written after the code commit.** `write_record.py` first failed (red-1 ran on the
  earlier base `78e5df2`, before the decision-85 design commit) and a pipe to `tail` hid the failure, so
  `00aadee` was committed first. The record was then adapted (history runs may carry the red base; HEAD~1 must be
  the base) and written; it still binds exactly the committed sources.
- **Slip: the docs commit `90289c2` carried a one-line placeholder of this file** (an edit hook blocked the
  write); the full text follows in the next commit.
- **npm audit (static-1): 1 high in `zod` <4.6.6 (GHSA-mrhx-c7xc-m3w5)**, a new advisory; the lockfile is
  unchanged by L9b (the L9a audit was 0). Fixed in its own commit (zod 4.6.7).

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l9b-20261023-78e5df2`: **static-1** PASS; **focused-1** PASS,
**486 passed**; **full-1** PASS, **2563 passed, 4 skipped** (58 minutes locally).

## Remaining

The zod 4.6.7 security commit with its own gates; the owner's word on readiness and `main`. Next migration
**0074**.
