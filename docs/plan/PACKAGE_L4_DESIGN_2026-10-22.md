# Package L, slice L4 — visit billing: design (2026-10-22)

**Status: design; decisions taken by the agent under the owner's full delegation** («Делай как
считаешь нужным и правильным! Я полностью даю тебе право выбора», 2026-10-22; «continue»). Branch
`codex/package-l4-billing` from L3 (`ef83b91`). Builds package L decision 5
([plan](PACKAGE_L_PLAN_2026-10-22.md)) on FIN-03. A platform part: any direction bills a visit,
appointment or job the same way.

## What exists (inspected)

- FIN-03 invoices: a draft (book, counterparty and its revision, direction, currency, dates, control
  account, title, number, lines with a counter account and an amount) is saved and then issued once;
  issuing posts a balanced journal and creates one obligation. Both need `finance.manage` of a
  company-wide member under the ledger lock.
- Payments are settlements: a payment always applies to obligations (manual attestation or an observed
  provider payment); there is no open advance. An obligation reports principal, paid, credited,
  reserved and available.
- The published cancellation policy is a text summary only (`{version, summary}`); it names no fee.

## Decisions

22. **The visit invoice is a FIN-03 invoice.** `POST /v1/salons/{id}/bookings/{booking}/invoice`
    saves a receivable draft whose lines are the visit's quote lines in order (each variant and
    add-on: its name and price), all on the revenue account the caller names, plus optional fee
    lines (description, amount, account). The caller names the book, counterparty, control account,
    revenue account, invoice date, optional due date and number. Issuing, credit notes, payments and
    their idempotency stay the existing FIN-03 routes, unchanged.
23. **One invoice per visit.** `gba.visit_invoices` links a booking to its document once; another
    request is `VISIT_ALREADY_INVOICED`, the same key repeats the answer. The link is permanent.
24. **Which visits.** A CONFIRMED booking is billed for its quote lines (and any fee lines); a
    CANCELLED booking only for fee lines (cancellation or no-show), at least one; a hold or an
    expired booking is refused. The currency is the quote's.
25. **Deposit and the rest are payments of that invoice.** A deposit is a partial settlement of the
    issued visit invoice through FIN-03 (manual or provider), the rest likewise; no new money path.
    `GET .../bookings/{booking}/invoice` shows the link, the invoice state and, once issued, the
    obligation's principal, paid, credited and available amounts — L5 reads "fully paid" from it.
26. **Fees are named by staff for now.** The published policy has no fee amounts, so a fee line is
    entered by a finance user; computing fees and deposits from a structured policy is a later
    decision (recorded, not built).
27. **Rights.** Billing needs `finance.manage` of a company-wide member under the ledger lock, like
    any invoice; reading the visit invoice needs `finance.read`.

## Acceptance for L4 (NOT TESTED)

| id | Requirement |
|---|---|
| L4-01 | A confirmed visit's draft invoice has one line per quoted variant and add-on with their prices, in the quote's currency; fee lines are added after them |
| L4-02 | A cancelled visit is billed for fee lines only; a hold or expired booking, and a cancelled one without fee lines, are refused |
| L4-03 | One invoice per visit; the same key repeats the answer; another key is `VISIT_ALREADY_INVOICED` |
| L4-04 | After issue a partial payment (deposit) and the rest settle the obligation; the visit invoice view reports paid and available exactly |
| L4-05 | Without `finance.manage` (front desk, branch-scoped member) nothing is written; another company sees nothing |
