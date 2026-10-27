# N3 — rate confirmations: local validation

**PASS for this bounded local, synthetic slice (package N, N3).** Branch `codex/package-n3-rate-confirmations`,
parent `1b18dcf` ([N3 design](../../PACKAGE_N3_DESIGN_2026-10-27.md)), source commit `526189e`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit code
and log digest; the nine committed blobs were checked against it. Owner 2026-10-27: «Делай как считаешь нужным
я доверяю тебе», then "continue" to N3.

## What changed

- Migration **0083**: `transport_rate_confirmations` (insert-only versions per accepted tender: basis, amount,
  terms, an optional signed copy that must be a document of the same business) and
  `transport_rate_confirmation_answers` (`agreed` or `declined`, once per version); backfill of version 1 for
  tenders accepted before 0083; module gate; tenant isolation; company-wide; select and insert only.
- Accepting a tender writes version 1 with the tender's rate and terms, agreed by the acceptance.
- A change is a new version the broker proposes; it is in force only once the carrier's agreement is recorded. A
  declined proposal leaves the previous version in force. The version in force is derived, never stored.
- Order: a version follows the answered previous one on an accepted, not withdrawn tender, under the
  rate-confirmation advisory lock; an answer answers the latest version once and never before its proposal.
- Routes: `GET/PUT tenders/{tender}/rate-confirmation`, `POST tenders/{tender}/rate-confirmation/{revision}/answers`,
  all under `transport.broker`.

## Proof

| id | Result | Test |
|---|---|---|
| N3-01 | PASS | `test_accepting_a_tender_writes_version_one` |
| N3-02 | PASS | `test_a_change_is_in_force_only_once_the_carrier_agrees` |
| N3-03 | PASS | `test_stale_open_closed_and_bad_changes_are_refused` |
| N3-04 | PASS (partial) | `test_a_signed_copy_must_be_a_document_of_this_business` — an unknown document is refused |
| N3-05 | PASS | `test_only_brokers_read_or_change_rate_confirmations` |
| N3-06 | PASS | `test_n3_upgrade.py` (0082 → 0083); full suite below |

## Failures kept

- red-1: routes 404, no migration 0083 — intended RED.
- dev-1..dev-6: a second carrier for the declined-tender case, the documents module gate for a signed copy, E501
  line lengths; fixed (STATE.md in the run folder).
- **gates-1:** static and focused passed; full **4 failed, 2637 passed** outside transport
  (`test_k6a_event_permutations`, `test_l7b2_billing_browser`, `test_materials_browser`,
  `test_provider_receipt_processes`). The four alone passed (recheck-1); treated as load-dependent and rerun in
  full as gates-2.

## Not tested

- A signed copy that is the business's own document (needs the documents module enabled).
- The 0083 backfill on accepted tenders: the upgrade test ran it on a database without them.

## Gates (suffix 2)

Run folder `GorgonaBookingTests/package-n3-20261027-1b18dcf`: **static-2** PASS; **focused-2** PASS,
**820 passed**; **full-2** PASS, **2641 passed, 4 skipped** (1:09:24 locally).

## Remaining

N4 tracking (and carrier answers in its own company), N5 carrier pay, N6 screens, N7 acceptance. Readiness and
enabling transport wait for the owner's word. Next migration **0084**.
