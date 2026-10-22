# Package L, slice L5 — commissions and tips: design (2026-10-22)

**Status: design; decisions taken by the agent under the owner's full delegation** («Делай как
считаешь нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22; «continue»). Branch
`codex/package-l5-commissions` from L4 (`0904f2f`). Builds package L decision 6
([plan](PACKAGE_L_PLAN_2026-10-22.md)) on FIN-03. A platform part: any direction that pays its
people a share of what they sold uses the same plan and accrual.

## What exists (inspected)

- FIN-03 manual accruals (`kind = manual_accrual`, route `.../accruals`): a payable or receivable
  draft with a counterparty, a control account and counter lines, issued once; issuing posts one
  balanced journal (source `accrual`) and creates an obligation that settlements pay. No new ledger
  source kind is needed.
- L4: the visit invoice and its obligation (principal, paid, credited, reserved, available).
- A booking is shown under its specialist (the first `artist` allocation, L2a).

## Decisions

28. **A commission plan per specialist.** `gba.commission_plans` names, for one `artist` resource, the
    payee counterparty (the person's card) and the currency; `gba.commission_rules` lists per service,
    or as the default for every other service, either a percentage (two decimals at most) of the
    service's price with its add-ons, or a fixed amount per service. The plan is replaced whole with
    the expected revision; `finance.manage` of a company-wide member.
29. **Accrued only when the visit is paid.** `POST .../bookings/{id}/commission` (with the expense,
    the payable and optionally the tips account, the accrual date and a number) requires the visit
    invoice issued and fully settled: nothing available, nothing reserved, nothing credited. The
    commission of each service line of the quote (with its add-ons) uses the specialist's rule for
    that service, else the default; a percentage rounds half up to the currency's minor units. One
    payable manual-accrual draft to the payee holds the commission lines on the expense account.
    Issuing it (the existing route) posts expense and the payable once; the obligation is paid out by
    the existing settlements. Fee lines are never part of the base.
30. **Tips are a payable, never revenue.** A tip is a line of the visit invoice (L4 fee line) on a
    liability account; when the commission names that account as the tips account, the accrual adds
    one line moving the tips from that liability to the payee's payable. A tips account that is not
    a liability is refused.
31. **Once per visit.** `gba.visit_commissions` links a visit to its accrual once, permanently; the
    same key repeats the answer, another key `VISIT_ALREADY_COMMISSIONED`.
32. **Refunds.** A credited visit invoice refuses the commission (`VISIT_INVOICE_CREDITED`); an issued
    commission is reversed with a FIN-03 credit note on its accrual (existing route). Automatic
    reversal from a refund is a later decision (recorded).
33. **No payroll.** Paying the payable is a settlement like any other; no payroll, tax or payslip.

## Acceptance for L5 (NOT TESTED)

| id | Requirement |
|---|---|
| L5-01 | A plan is replaced whole with its revision; a percentage with three decimals, both or neither of percentage and amount, a second default and a foreign resource are refused |
| L5-02 | An unpaid, partly paid, reserved or credited visit invoice refuses the commission; a fully paid one accrues it |
| L5-03 | The accrual has one line per service line at the service rule, else the default, rounded half up; fees are not in the base |
| L5-04 | Tips on a liability account move to the payee's payable in the same accrual; a revenue tips account is refused |
| L5-05 | Once per visit; issuing posts expense and payable once; the obligation is paid by a settlement |
| L5-06 | Without finance rights nothing is written; another company sees nothing |
