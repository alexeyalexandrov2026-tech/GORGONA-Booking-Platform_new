# N4 — a carrier answering in its own company, and tracking of tendered work: local validation

**PASS for this bounded local, synthetic slice (package N, N4).** Branch `codex/package-n4-tracking`, parent
`1f5a333` ([N4 design](../../PACKAGE_N4_DESIGN_2026-10-28.md)), source commit `cd301f1`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit code
and log digest; the fifteen committed blobs were checked against it. Owner 2026-10-28: "continue" under full
delegation («Делай как считаешь нужным я доверяю тебе»).

## What changed

- Migration **0084**: `transport_carrier_companies` (insert-only versions linking a carrier counterparty to its
  own company on the platform, or unlinking it; one carrier per company at a time; never the broker itself);
  `servicer_business_id` on `transport_tender_answers` and `transport_rate_confirmation_answers`, set exactly
  when the source is `platform`; grant terms may name `transport.tender`.
- `transport.tender` is held by owners and managers of their own company and works only through a grant
  (ADR-0017): the linked company's delegates accept or decline the tenders addressed to their carrier and answer
  rate confirmation versions. The broker's own staff are refused on these routes; the broker still records an
  external carrier's answers with their source (N2, N3).
- Tracking (ADR-0030): a linked carrier's delegate records stop events only at stops of its accepted, not
  withdrawn tendered legs, and quantities only for them; a repeat of a source event id changes nothing. The
  broker and an M4 dispatcher that is not a linked carrier keep their rights.
- Routes: `GET/PUT carriers/{counterparty}/company` (`transport.broker`), `POST tenders/{tender}/carrier-answers`
  and `POST tenders/{tender}/rate-confirmation/{revision}/carrier-answers` (`transport.tender` through a grant).

## Proof

| id | Result | Test |
|---|---|---|
| N4-01 | PASS | `test_the_broker_links_a_carrier_to_its_company_in_versions` |
| N4-02 | PASS | `test_the_linked_company_answers_its_tender_through_its_grant` |
| N4-03 | PASS | `test_the_linked_company_answers_a_rate_confirmation_version` |
| N4-04 | PASS | `test_a_linked_carrier_tracks_only_its_accepted_legs` |
| N4-05 | PASS | `test_links_are_insert_only_and_need_the_module` and the refusal of the broker's staff in N4-02 |
| N4-06 | PASS | `test_n4_upgrade.py` (0083 → 0084); full suite below |

## Failures kept

- red-1: 6 failed, routes 404, no migration 0084 — intended RED.
- dev-1 (8 failed, 31 passed): a delegate also needs the right by role in its own company, so `transport.tender`
  became an owner and manager right used only through a grant (design updated); the location-access restore
  re-ran 0084 from its branch-scope marker and re-added the columns (the section moved to the end); the upgrade
  copy met N4 rows an older schema cannot hold (older schemas now omit grants naming `transport.tender` and
  `platform` answers).
- dev-2 (1 failed, 33 passed): the upgrade test compared row digests of the two answer tables, which change with
  the added empty column; those two now compare row counts.
- **gates-1:** static passed; focused **1 failed, 825 passed** — the unit test of delegable rights listed them
  without `transport.tender` (added; `transport.broker` added to the never-delegable list). Full not run.

## Not tested

- A carrier company answering an expired tender through its grant: only the N2 rules cover expiry.

## Gates (suffix 2)

Run folder `GorgonaBookingTests/package-n4-20261028-1f5a333`: **static-2** PASS; **focused-2** PASS,
**826 passed**; **full-2** PASS, **2647 passed, 4 skipped** (1:39:05 locally).

## Remaining

N5 carrier pay, N6 screens, N7 acceptance. Readiness and enabling transport wait for the owner's word. Next
migration **0085**.
