# Package N, slice N1 — broker authority and carrier profiles (2026-10-26)

User 2026-10-26: "Continue with N1 the same way." Plan: [PACKAGE_N_PLAN_2026-10-26.md](PACKAGE_N_PLAN_2026-10-26.md);
decision [ADR-0034](../adr/0034-broker-authority-and-carrier-profiles.md). Branch
`codex/package-n1-broker-carriers` from `ca2653e` (package N plan).

## Scope

- Migration **0080**: `transport_broker_authorities` and `transport_carrier_profiles`, insert-only versions
  with a revision guard; module gate; RLS; select and insert only.
- Routes under `/v1/businesses/{id}/transport`: `GET/PUT broker-authority`, `GET broker-authority/eligibility
  ?on=`, `GET/PUT carriers/{counterparty_id}/profile`, `GET carriers/{counterparty_id}/eligibility?on=`; all
  need `transport.broker` (owners and managers, never delegated in N1).
- Permissions version 10.
- Change to the plan: `transport.broker` is not delegable in N1 (ADR-0034 decision 4).
- Next migration after this slice: **0081**.

## Acceptance of N1 (NOT TESTED)

| id | Requirement |
|---|---|
| N1-01 | The broker authority is kept as versions with the expected revision; a stale revision is refused |
| N1-02 | Broker eligibility on a date: withdrawn, not yet effective, expired and stale (checked over 90 days ago) are refused with their reasons; a current authority is eligible |
| N1-03 | A carrier profile is kept as versions; carrier eligibility names every failing reason (no profile, unknown authority, unknown or expired liability or cargo insurance, unsatisfactory rating, stale check) |
| N1-04 | Only owners and managers with `transport.broker` read or write; a front desk, a carrier's dispatcher with every transport right, another company and a business with the module off are refused; direct SQL updates and deletes are refused |
| N1-05 | Upgrade 0079 -> 0080 keeps every row; the full suite stays green |
