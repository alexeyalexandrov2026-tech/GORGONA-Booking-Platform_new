# Package M, slice M7a — transport money through FIN-03 (2026-10-25)

Owner's word 2026-10-23 for package M; 2026-10-24 «Делай как считаешь нужным я доверяю тебе»; 2026-10-25
"Continue with M7 the same way." Plan: [PACKAGE_M_PLAN_2026-10-23.md](PACKAGE_M_PLAN_2026-10-23.md) slice M7,
split like L4/L5 then L7: **M7a** (this) the money API, **M7b** money on the order and trip screens.
Decision: [ADR-0033](../adr/0033-transport-money.md). Branch `codex/package-m7-transport-money` from `c61de57`.

## Scope

- Migration **0079**: `transport_order_rates` (insert-only versions), `transport_order_invoices` (one per
  order), `transport_pay_components` (registered once; unique per trip, recipient and role) and
  `transport_pay_accruals` (one per component); module gate; RLS; trip money follows the trip's branch.
- Routes under `/v1/businesses/{id}/transport`: `GET/PUT orders/{id}/rate`, `GET/POST orders/{id}/invoice`,
  `GET trips/{id}/pay`, `PUT trips/{id}/pay/{component_id}`, `POST trips/{id}/pay/{component_id}/accrue`.
  Writes `finance.manage` (never delegated), reads `finance.read`; invoice and accrual under the ledger lock.
- Next migration after this slice: **0080**.

## Acceptance of M7a (PASS locally in `b2998d5`)

| id | Requirement |
|---|---|
| M7a-01 | An order's rate is kept as versions with the expected revision; after the invoice it never changes |
| M7a-02 | An order is invoiced once, only when all its loads are planned and nothing is open; fixed and per-mile freight lines (half up to minor units) and named extras |
| M7a-03 | The invoice is issued and paid through FIN-03; paying beyond the open balance is refused |
| M7a-04 | Pay components are registered once per id; one recipient has one component per role on a trip |
| M7a-05 | Each component accrues once, only on a closed trip, as its own payable obligation (per mile, percent of base, fixed); a repeat answers the same accrual and nothing is paid twice |
| M7a-06 | Without finance rights, as a carrier's dispatcher or in another company nothing is written or read; with the module off nothing is written and reads continue (corrected 2026-10-26, package M review R-08) |
| M7a-07 | Upgrade 0078 → 0079 keeps every row; the full suite stays green |
