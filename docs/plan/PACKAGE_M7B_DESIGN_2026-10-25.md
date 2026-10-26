# Package M, slice M7b — transport money on the screens (2026-10-25)

User 2026-10-25: "Continue with M7 the same way." and "First fix the two open defects (night-time workforce
test, silent refused grant offer), then M7b." Builds on [M7a](PACKAGE_M7A_DESIGN_2026-10-25.md) and
[ADR-0033](../adr/0033-transport-money.md). Branch `codex/package-m7b-money-screens` from `d6c3893` (defects).

## Scope

- **Web contracts** for the M7a routes: the rate with its versions, the order invoice (a FIN-03 invoice and its
  obligation), the trip's pay components with their accruals; wired into `managementResponseSchema`.
- **Who sees money:** a company-wide owner or manager (finance rights); a branch-limited member and a delegate
  never see the money panels (the server refuses them anyway).
- **Order money** (from the Orders table, "Money"): the current rate and its versions; a "Rate" form (fixed or
  per mile, amount, currency) saved with the expected revision; once there is a rate and no invoice, a
  "Customer invoice" form (book, receivable and revenue accounts, date, number, billed miles for a per-mile
  rate, named extras with their accounts) that creates the FIN-03 draft; afterwards the invoice's lines, total,
  state and what is paid and open. Issuing and payment stay on the finance screens.
- **Trip pay** (on the trip page): the components with recipient, role, formula and, once accrued, the
  accrual's total, state and what is paid and open; a "Pay component" form (recipient from active
  counterparties, role, currency and formula) registered once; an "Accrue" form (component, book, expense and
  payable accounts, date, number, miles for a per-mile component).
- Refusals (no rate, still open, invoiced, already accrued, missing miles) are shown in words; a form keeps
  its record id and key until the save succeeds. No migration (next stays **0080**).

## Acceptance of M7b (PASS locally in `f44db22`)

| id | Requirement |
|---|---|
| M7b-01 | An owner sets a per-mile rate, sees its version and creates the customer invoice draft with an extra; the screen shows its lines, total and open amount |
| M7b-02 | An owner registers a driver's per-mile pay and a dispatch fee on the trip and accrues the driver's pay; the screen shows each component's accrual |
| M7b-03 | Refusals are shown in words: an invoice without miles for a per-mile rate |
| M7b-04 | A branch-limited member and a delegate never see the money panels |
| M7b-05 | Real browser, desktop and mobile: axe clean, no horizontal scroll; the database holds exactly what the screens did; strict contracts; the full suite stays green |
