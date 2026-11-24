# N2 — tenders: local validation

**PASS for this bounded local, synthetic slice (package N, N2).** Branch `codex/package-n2-tenders`, parent
`d82bc5d` ([N2 design](../../PACKAGE_N2_DESIGN_2026-10-27.md), on `main` `590a8f3`), source commit `80183b5`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit code
and log digest; the eight committed blobs were checked against it. Owner 2026-10-27: «Делай как считаешь нужным
я доверяю тебе», then «Ок» to N2.

## What changed

- Migration **0082**: `transport_tenders` (an insert-only offer of some legs of a trip to one carrier, with a
  carrier rate, terms and an expiry) and `transport_tender_answers` (`accepted`, `declined`, `withdrawn`, each
  with a source and a time); module gate; tenant isolation; company-wide; select and insert only.
- The state is derived: offered, accepted, declined, withdrawn or expired. An accepted tender can only be
  withdrawn; a closed one refuses more answers (409 `TRANSPORT_TENDER_CLOSED`).
- Offering and accepting need an eligible broker authority and carrier (N1) on the date in the time zone of the
  trip's first stop (409 `TRANSPORT_BROKER_NOT_ELIGIBLE` / `TRANSPORT_CARRIER_NOT_ELIGIBLE` with the reasons).
- A leg has at most one accepted tender (409 `TRANSPORT_LEG_TENDERED`): the trip-tender advisory lock and the
  answer trigger; a withdrawn acceptance frees the legs.
- Routes: `GET trips/{trip}/tenders`, `GET/PUT tenders/{tender}`, `POST tenders/{tender}/answers`, all under
  `transport.broker`.
- Change to the plan: the broker records every answer; a carrier answering in its own company is decided with N4.

## Proof

| id | Result | Test |
|---|---|---|
| N2-01 | PASS | `test_a_tender_is_offered_for_some_legs_and_read_back` |
| N2-02 | PASS | `test_answers_move_the_state_and_a_closed_tender_refuses_more` |
| N2-03 | PASS | `test_offering_and_accepting_need_an_eligible_broker_and_carrier` |
| N2-04 | PASS | `test_a_leg_has_at_most_one_accepted_tender`; `test_two_racing_accepts_on_overlapping_legs_leave_one` (an advisory wait observed in `pg_locks`) |
| N2-05 | PASS | `test_only_owners_and_managers_with_the_broker_right_tender` |
| N2-06 | PASS | `test_n2_upgrade.py` (0081 → 0082); full suite below |

## Failures kept

- red-1: 7 failed (routes 404, no migration 0082) — intended RED.
- dev-2 static: ruff I001, E501 and S101 ×3; fixed.
- **gates-1:** static passed; focused **5 failed, 809 passed** — `test_inventory_upgrade` and
  `test_stock_upgrade` keep a set of known tables that lacked the two 0082 tables. Added; rerun as gates-2.

## Gates (suffix 2)

Run folder `GorgonaBookingTests/package-n2-20261027-d82bc5d`: **static-2** PASS; **focused-2** PASS,
**814 passed**; **full-2** PASS, **2635 passed, 4 skipped** (0:42:05 locally).

## Remaining

N3 rate confirmations, N4 tracking (and carrier answers in its own company), N5 carrier pay, N6 screens, N7
acceptance. Readiness and enabling transport wait for the owner's word. Next migration **0083**.
