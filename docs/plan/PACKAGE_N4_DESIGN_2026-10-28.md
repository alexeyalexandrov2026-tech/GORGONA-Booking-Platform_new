# Package N, slice N4 — a carrier answering in its own company, and tracking of tendered work (2026-10-28)

Owner 2026-10-28: "continue" after N3 (full delegation: «Делай как считаешь нужным я доверяю тебе»). Plan:
[PACKAGE_N_PLAN_2026-10-26.md](PACKAGE_N_PLAN_2026-10-26.md) decisions 4 and 5; builds on N3
([design](PACKAGE_N3_DESIGN_2026-10-27.md)). Branch `codex/package-n4-tracking` from `724b3fa` (N3).

## Scope

- **A carrier on the platform is a company of its own** (ADR-0017): the broker links a carrier counterparty to
  that company. Migration **0084**: `transport_carrier_companies`, insert-only versions per counterparty
  (revision, the carrier's business or none to unlink). A company is linked to at most one carrier of a broker
  at a time; the broker's own business is refused.
- **The carrier answers through its grant**, never through the broker's rights: a new delegable right
  `transport.tender` (never given to a role). A delegate of the linked company accepts or declines a tender
  addressed to its carrier and agrees to or declines a rate confirmation version. The answer is stored with the
  source `platform` and the carrier's business; the broker still records an external carrier's answer with its
  source (N2, N3). A delegate of a company that is not the tender's carrier is refused (403).
- **Tracking of tendered work uses the same stop events** (ADR-0030). A delegate of a linked carrier company
  records events only at stops of legs tendered to its carrier and accepted (not withdrawn), and quantities only
  for those legs (403 otherwise). A repeat of a source event id changes nothing (unchanged). The broker and a
  dispatcher of M4 (a company that is not a linked carrier) keep their rights.
- Columns added: `servicer_business_id` on `transport_tender_answers` and `transport_rate_confirmation_answers`;
  the source `platform` holds exactly when it is set.
- Routes under `/v1/businesses/{id}/transport`: `GET/PUT carriers/{counterparty}/company` (`transport.broker`),
  `POST tenders/{tender}/carrier-answers` and `POST tenders/{tender}/rate-confirmation/{revision}/carrier-answers`
  (`transport.tender` through a grant). All need the module.
- Next migration after this slice: **0085**.

## Acceptance of N4

| id | Requirement |
|---|---|
| N4-01 | The broker links and unlinks a carrier's company in versions; a stale revision, a company linked to another carrier and the broker's own business are refused |
| N4-02 | A delegate of the linked company accepts or declines its tender; the answer has the source `platform` and the company; a company that is not the carrier is refused; the rules of N2 hold |
| N4-03 | A delegate of the linked company agrees to or declines a rate confirmation version; the rules of N3 hold |
| N4-04 | A linked carrier's delegate records stop events only on its accepted tendered legs; a repeat changes nothing; after a withdrawal it is refused |
| N4-05 | `transport.tender` is never a role right; the module off and direct SQL updates and deletes are refused |
| N4-06 | Upgrade 0083 → 0084 keeps every row; the full suite stays green |
