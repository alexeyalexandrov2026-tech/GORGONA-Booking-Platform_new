# Package R, slice R6a — handover and return inspections (2026-11-07)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), slice R6, acceptance R-06.
Previous slice: [R5b](PACKAGE_R5B_DESIGN_2026-11-07.md); handoff [NEXT_AGENT_PACKAGE_R6_2026-11-07.md](NEXT_AGENT_PACKAGE_R6_2026-11-07.md).
Branch `codex/package-r6a-rental-inspections` from the R5b docs commit `fc1c378`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after each slice.

R6 is split: **R6a** records the inspections; **R6b** derives overdue time and meter excess from them. By the rental
plan, damage charges and refunds belong to R7 (settlement); the R5b design and the R6 handoff named them under R6 by
mistake.

R5b CI run 42413235532 on `fc1c378`: FAIL, job api, a browser check that fails now and then
(`tests/service-catalog.spec.ts:137`, equipment added as a resource kind); R5b changes no web code and the full suite
passed on the VM; a rerun needs GitHub credentials this agent does not have.

## Scope

- Migration **0105**: `rental_inspections` (insert-only, one handover and one return per booking) and
  `rental_inspection_marks` (insert-only damage marks, each optionally with a photo); guards under the class row lock;
  module gate; tenant isolation; branch scope last.
- Service `business/rental_inspections.py`; routes `GET bookings/{id}/inspections`,
  `POST bookings/{id}/inspections`.

## Decisions (R6a, agent)

1. **What is inspected.** A handover is recorded for a booking that is not cancelled, has an agreement and a current
   (not released) unit assignment; it names that assignment. A return names the same assignment and needs the
   handover. One of each per booking; the time is the database time of the record, never a client time.
2. **Meters.** When the class counts a meter (`odometer` or `hours`), each inspection records a whole reading from 0
   to 10,000,000; the return reading is not below the handover reading. A class without a meter records none.
3. **Condition and damage.** Each inspection records a fuel or charge level from 0 to 100 per cent (optional), a note
   (optional), and up to 50 damage marks written with it: position 1..n, an area (1..100 characters), a severity
   (`minor`, `major`) and a note (optional). A mark may cite a photo: a document version whose file is PNG or JPEG.
   A return mark says whether it is new since the handover; a handover mark is never new.
4. **Permanent history.** Inspections and marks are never updated or deleted; a correction is a note on the return or
   an R7 settlement decision. Recording an inspection changes no assignment, booking, agreement, security or payment.
5. **Permissions and rules as before**: `rental.manage`; idempotency scope `rental.inspection`; module off writes
   nothing; branch scope by the booking's pickup branch; another company's booking, unit or photo is refused; direct
   SQL updates and deletes refused. Errors: `RENTAL_INSPECTION_STATE` (wrong order, missing agreement, assignment or
   handover, a second one), `RENTAL_INSPECTION_INVALID` (meter or mark rules).

## Acceptance of R6a — PASS 2026-11-07 (code `78db1a8`, [evidence](evidence/2026-11-07-r6a-rental-inspections/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R6a-01 | A handover and a return of the current assignment record meters, level, note and marks with photos; the view shows both | PASS |
| R6a-02 | A return before the handover, a second handover or return, no agreement, no assignment or a cancelled booking are refused | PASS |
| R6a-03 | A missing, extra or lower return meter, a level or mark out of range, a new mark at handover and a non-image photo are refused | PASS |
| R6a-04 | The database refuses updates, deletes and forged inspections or marks; module off writes nothing; scope holds | PASS |
| R6a-05 | 0104 -> 0105 keeps every row; the full suite stays green | PASS |

## Not in R6a

Overdue time and meter excess (R6b); swaps after handover and one-way returns (R6b or later); signed copies; damage
charges, refunds and settlement (R7); screens (R8).
