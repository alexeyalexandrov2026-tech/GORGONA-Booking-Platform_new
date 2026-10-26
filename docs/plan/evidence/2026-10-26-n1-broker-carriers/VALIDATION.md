# N1 — broker authority and carrier profiles: local validation

**PASS for this bounded local, synthetic slice (package N, N1).** Branch `codex/package-n1-broker-carriers`,
parent `23b62a7` ([N1 design](../../PACKAGE_N1_DESIGN_2026-10-26.md),
[ADR-0034](../../../adr/0034-broker-authority-and-carrier-profiles.md)), source commit `a3d85d3`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit code
and log digest; the twelve committed blobs were checked against it. User 2026-10-26: "Continue with N1 the same
way."

## What changed

- Migration **0080**: `transport_broker_authorities` (a business's broker authority) and
  `transport_carrier_profiles` (one carrier's profile, a counterparty), insert-only versions with a source and a
  check date; a revision guard under an advisory lock; module gate; tenant isolation; company-wide (a
  branch-limited session sees none); select and insert only.
- Eligibility is computed for a date and never stored. The broker needs an active, effective, unexpired authority
  checked within 90 days; a carrier needs a known authority, known and unexpired liability and cargo insurance, a
  rating other than unsatisfactory and a check within 90 days. Every failing condition is a named reason.
- Right `transport.broker` (permissions version **10**) for owners and managers; not delegable in N1 (ADR-0034).
- Routes: `GET/PUT broker-authority`, `GET broker-authority/eligibility?on=`,
  `GET/PUT carriers/{counterparty_id}/profile`, `GET carriers/{counterparty_id}/eligibility?on=`.

## Proof

| id | Result | Test |
|---|---|---|
| N1-01 | PASS | `test_the_broker_authority_is_versioned` |
| N1-02 | PASS | `test_broker_eligibility_names_every_reason` |
| N1-03 | PASS | `test_carrier_profiles_are_versioned_and_eligibility_names_every_reason` |
| N1-04 | PASS | `test_only_owners_and_managers_with_the_broker_right_read_or_write` |
| N1-05 | PASS | `test_n1_upgrade.py`; full suite below |

## Failures kept

- red-1: 5 failed and 3 unit pins (routes 404, no migration 0080, permissions version 9) — intended RED.
- Before dev: a `ProfileInput` name clash with the clearance module (renamed `CarrierProfileInput`); ruff E501
  and I001.
- **M7a slip found in N1:** the 0079 branch-scope section was missing from the restore list of
  `test_location_access`, so after its damage test later tests in the same database ran without the pay-component
  branch policies (test database only). 0079 and 0080 are restored now.
- **gates-1 failed:** static passed; focused **1 failed, 799 passed** —
  `test_l7a_catalog_browser` (`service-catalog.spec.ts:137`: the equipment row was not visible within 15 s after
  the add). N1 changes no web or catalog code; this is the test's first failure since L7a development; no page
  snapshot was kept, so the cause is unknown. Rerun unchanged as gates-2.

## Gates (suffix 2)

Run folder `GorgonaBookingTests/package-n1-20261026-23b62a7`: **static-2** PASS; **focused-2** PASS,
**800 passed**; **full-2** PASS, **2621 passed, 4 skipped** (0:42:24 locally).

## Remaining

The independent review of package M ran on 2026-10-26 (owner's word); its fixes come next, before N2. Then N2
tenders (refused without an eligible broker and carrier on the tender date), N3 rate confirmations, N4 tracking,
N5 carrier pay, N6 screens, N7 acceptance. Readiness and `main` wait for the owner's word; transport stays not
enableable. Next migration **0081**.
