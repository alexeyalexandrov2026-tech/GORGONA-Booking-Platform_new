# Package N, slice N3 — rate confirmations (2026-10-27)

Owner 2026-10-27: "continue" after N2 (full delegation: «Делай как считаешь нужным я доверяю тебе»). Plan:
[PACKAGE_N_PLAN_2026-10-26.md](PACKAGE_N_PLAN_2026-10-26.md) decision 3; builds on N2
([design](PACKAGE_N2_DESIGN_2026-10-27.md)). Branch `codex/package-n3-rate-confirmations` from `7926d9c` (N2).

## Scope

- Migration **0083**:
  - `transport_rate_confirmations` — insert-only versions per tender: revision, basis, amount, terms and an
    optional signed copy (a stage-1 document of the same business); the currency stays the tender's;
  - `transport_rate_confirmation_answers` — one answer per version: `agreed` or `declined`, with a source and a
    time.
- **Accepting a tender writes version 1** with the tender's rate and terms and its `agreed` answer (the
  acceptance's source and time) in the same transaction; tenders accepted before 0083 are backfilled.
- **A change is a new version both sides accept:** the broker proposes version n + 1 with the expected revision;
  it is in force only after the carrier's `agreed` answer is recorded; a `declined` answer leaves the previous
  agreed version in force. At most one open proposal; nothing is edited.
- Refused: a proposal on a tender that is not accepted or was withdrawn (409 `TRANSPORT_TENDER_CLOSED`), a stale
  revision or an open proposal (409 `TRANSPORT_RATE_CONFIRMATION_CONFLICT`), an answer to a version that is
  already answered or not the latest (409), a time before the proposal (422), amounts with the M7a bounds and
  precision (422), a document of another business (422).
- Routes under `/v1/businesses/{id}/transport`: `GET/PUT tenders/{tender}/rate-confirmation`,
  `POST tenders/{tender}/rate-confirmation/{revision}/answers`; all need `transport.broker` and the module.
- **Kept from N2:** a carrier on the platform answering in its own company is decided with N4 (the plan put it in
  N3); here the broker records the carrier's answer with its source.
- Next migration after this slice: **0084**.

## Acceptance of N3 (PASS, 2026-10-27)

| id | Requirement |
|---|---|
| N3-01 | Accepting a tender writes version 1 (the tender's rate and terms, agreed by the acceptance); a declined or withdrawn tender has none |
| N3-02 | A proposal is a new version; it is in force only after the carrier agrees; a declined proposal leaves the previous one in force; versions are never edited |
| N3-03 | A stale revision, a second open proposal, a proposal after the tender was withdrawn, an answer to an answered or older version, a time before the proposal and an over-precise amount are refused |
| N3-04 | A signed copy refers to a document of the same business; another business's document is refused |
| N3-05 | Only owners and managers with `transport.broker` read or write; the module off and direct SQL updates and deletes are refused |
| N3-06 | Upgrade 0082 → 0083 keeps every row and backfills version 1 for accepted tenders; the full suite stays green |
