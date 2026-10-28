# Package N, slice N5 — carrier pay and margin per order (2026-10-28)

Owner 2026-10-28: "continue" after N4 (full delegation: «Делай как считаешь нужным я доверяю тебе»). Plan:
[PACKAGE_N_PLAN_2026-10-26.md](PACKAGE_N_PLAN_2026-10-26.md) decision 6; builds on N4
([design](PACKAGE_N4_DESIGN_2026-10-28.md)) and the money of M7a (ADR-0033). Branch `codex/package-n5-carrier-pay`
from `7cde106` (N4).

## Scope

- **The carrier's pay is one FIN-03 payable per accepted tender.** Migration **0085**:
  `transport_tender_accruals` — one row per tender (its stable id: the broker company, the tender, hence the
  carrier), the rate confirmation revision in force, the miles for a per-mile rate, and the FIN-03 manual
  accrual document. Insert only; module gate; tenant isolation; company-wide.
- `POST tenders/{tender}/accrual` (`transport.broker`) books the accrual once: the tender is accepted and not
  withdrawn, a rate confirmation version is in force (N3), and every tendered leg is closed (nothing open, the
  M7a rule). The amount is the version in force: fixed, or the rate times the miles (required exactly then). The
  payable goes to the tender's carrier with the expense and payable accounts given. Refused: a second accrual
  (409 `TRANSPORT_ALREADY_ACCRUED`), open legs (409 `TRANSPORT_TRIP_NOT_CLOSED`), a tender not accepted or
  withdrawn (409 `TRANSPORT_TENDER_CLOSED`), missing miles (422). `GET tenders/{tender}/accrual` reads it.
- **Margin per order, derived and never stored:** `GET orders/{order}/margin` (`transport.broker`) — revenue is
  the order's FIN-03 invoice total (none before it is invoiced); carrier cost is the total of the accrued
  tenders whose legs all carry this order's loads; a tender whose legs also carry another order's loads is
  listed as shared and not subtracted. The margin is revenue less cost, given only with revenue and one currency.
- Quick pay and factoring stay later (plan decision 6). Next migration after this slice: **0086**.

## Acceptance of N5

| id | Requirement |
|---|---|
| N5-01 | An accepted tender with closed legs accrues once as a FIN-03 payable to its carrier for the version in force (fixed or per mile); a repeat key replays it |
| N5-02 | Open legs, a withdrawn or declined tender, missing miles and a second accrual are refused |
| N5-03 | The margin of an order is its invoice total less the accrued carrier pay of its own tenders; a shared tender is listed and not subtracted; nothing is stored |
| N5-04 | Only owners and managers with `transport.broker`; the module off and direct SQL updates and deletes are refused |
| N5-05 | Upgrade 0084 → 0085 keeps every row; the full suite stays green |
