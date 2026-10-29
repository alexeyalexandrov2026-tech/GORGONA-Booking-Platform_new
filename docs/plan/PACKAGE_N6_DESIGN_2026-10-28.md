# Package N, slice N6 — brokerage on the screens (2026-10-28)

Owner 2026-10-28: "Start N6" (full delegation: «Делай как считаешь нужным я доверяю тебе»). Plan:
[PACKAGE_N_PLAN_2026-10-26.md](PACKAGE_N_PLAN_2026-10-26.md) slice N6; builds on N1–N5 and the screens of M7b
([design](PACKAGE_M7B_DESIGN_2026-10-25.md)). Branch `codex/package-n6-screens` from `234194b` (N5).

## Scope

- **Web contracts** for the N1–N5 routes: broker authority and its eligibility, carrier profiles and their
  eligibility, tenders with their answers, rate confirmations with their versions, the tender accrual and the
  order margin; strict schemas wired into `managementResponseSchema`.
- **Who sees brokerage:** a company-wide owner or manager (`transport.broker`, company-wide tables). A
  branch-limited member and a delegate never see the brokerage panels (the server refuses them anyway).
- **Broker authority** panel: the current version and its history; a form (jurisdiction, number, bond, status,
  effective from, expires on, source, checked on) saved with the expected revision; today's eligibility in words.
- **Carriers** panel: active counterparties with their current profile and today's eligibility in words (missing
  authority, expired or unknown insurance); a profile form saved with the expected revision.
- **Board — loads to cover:** each trip's legs without an accepted tender, with their tenders; a "Tender" form
  (carrier, legs, basis, amount, currency, terms, expiry) that keeps its tender id and key until it succeeds.
- **Tender** panel: state and answers; an answer form for an external carrier (accepted, declined, withdrawn,
  with its source); the rate confirmation versions with the one in force; a proposal form (new version) and an
  answer form per proposed version; once accepted with closed legs, an "Accrue carrier pay" form (book, expense
  and payable accounts, date, number, miles for a per-mile rate) and afterwards the accrual's total and open
  amount.
- **Margin** on the order money panel: revenue, carrier cost, margin and shared tenders.
- Refusals (no current authority, ineligible carrier, a leg already covered, open legs, missing miles, already
  accrued) are shown in words. The carrier company link and the carrier's own answers through a grant stay on
  the API (N4) and come to the screens later. No migration (next stays **0086**).

## Acceptance of N6

| id | Requirement |
|---|---|
| N6-01 | An owner records the broker authority and a carrier profile; the screen shows the versions and eligibility in words |
| N6-02 | An owner tenders an uncovered leg to an eligible carrier and records its acceptance; the board no longer lists the leg |
| N6-03 | An owner proposes a changed rate confirmation version and records its agreement; the version in force changes, old versions stay |
| N6-04 | An owner accrues the carrier's pay on closed legs and sees the order margin; refusals are shown in words |
| N6-05 | A branch-limited member and a delegate never see the brokerage panels |
| N6-06 | Real browser, desktop and mobile: axe clean, no horizontal scroll; the database holds exactly what the screens did; strict contracts; the full suite stays green |
