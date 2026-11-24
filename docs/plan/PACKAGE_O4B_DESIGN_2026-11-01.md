# Package O, slice O4b — inspections, defects and the punch list (2026-11-01)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decision 7 (last sentence).
Architecture: [ADR-0035](../adr/0035-construction-projects-and-estimates.md). Previous slice:
[O4a](PACKAGE_O4A_DESIGN_2026-11-01.md) (schedule, daily reports, completed quantities). Branch
`codex/package-o4b-quality` from the O4a docs commit `852c117`. Same process as O1-O4a: failing tests
first, one executor, one disposable PostgreSQL 18 cluster per run, gates, a source-bound record, code and
docs commits, push for CI without a PR.

## Scope

- Migration **0092**: `construction_inspections`, `construction_inspection_photos`,
  `construction_quality_items`, `construction_quality_item_events` and `construction_quality_item_photos`,
  all insert-only (select and insert grants only); module gate; tenant isolation; branch scope as the last
  section.
- Service `business/construction_quality.py`; routes under
  `/v1/businesses/{id}/construction/projects/{id}`: `GET inspections`, `GET inspections/{number}`,
  `POST inspections`; `GET quality-items` (optional filters `kind`, `state`, `phase`),
  `GET quality-items/{number}`, `POST quality-items`, `POST quality-items/{number}/events`.

## Decisions (O4b, agent, under the owner's delegation)

1. **Everything here needs the contract** (`CONSTRUCTION_NO_CONTRACT`), as in O4a. A phase named by an
   inspection or an item must be a phase of the budget (`INVALID_REFERENCE`); it is optional, and without
   it the record is about the whole project.
2. **An inspection is a recorded check, insert-only and numbered per project.** It has a site date (not
   after today in the site's time zone, `CONSTRUCTION_FUTURE_DATE`; not before 2000-01-01), a kind
   (`internal`, `customer`, `authority`, `third_party`), an optional phase, the inspector's name (1-64, one
   line) and optionally the inspector's counterparty, a result (`passed`, `passed_with_items`, `failed`),
   optional notes (1-4000) and up to 50 photos (stage-1 document versions with a PNG or JPEG file, as in
   O4a; anything else is `INVALID_REFERENCE`). Photos are written with their inspection. A wrong inspection
   is not edited; a later inspection records the correction in its notes.
3. **Defects and punch items are one kind of record with states.** A quality item is numbered per project
   and has a kind (`defect`: work that does not conform; `punch`: work left to finish before acceptance),
   a title (1-120, one line), an optional description (1-4000), an optional phase, an optional location
   (1-200, one line), a severity (`minor`, `major`, `critical`), the site date it was raised (not after
   today there), an optional due date (not before the raised date, not after 2100-12-31), an optional
   responsible counterparty (for example the subcontractor who must fix it) and optionally the inspection
   that found it. Up to 20 photos go with the item. The item row itself never changes.
4. **An inspection that passed raises nothing.** An item may name only an inspection of the same project
   whose result is `passed_with_items` or `failed`; naming a `passed` one is refused by the database
   (`CONSTRUCTION_INSPECTION_PASSED`), naming an unknown one is `INVALID_REFERENCE`.
5. **States move by insert-only events.** A new item is `open`. Each later change is an event numbered 1,
   2, ... per item, with the new state, an optional note (1-1000) and up to 20 photos. Allowed moves:
   `open` -> `fixed` (the responsible party says the work is done), `open` -> `void` (raised in error),
   `fixed` -> `closed` (the fix is verified), `fixed` -> `open` (verification failed: reopened). `closed`
   and `void` are final; a problem found later is a new item. Voiding and reopening need a note. A move
   that the current state does not allow is `CONSTRUCTION_ITEM_TRANSITION`; the database refuses it too,
   under the project lock. The client sends the number of events it saw (`expected_sequence`, 0 for a new
   item); a stale one is `CONSTRUCTION_REVISION_CONFLICT`, so two racing moves of one item leave one after
   an observed `pg_locks` wait.
6. **The views derive, they do not store.** An item's state is its latest event's state (`open` when it
   has none); the item view lists its events and photos. `overdue` = the item is `open` and its due date
   is before today in the site's time zone. The item list carries a summary per phase (the whole project
   is its own row) and kind: open, fixed, closed, void and overdue counts. Whether open items block a
   stage acceptance is decided in O6, which reads this view.
7. **Rules as before.** `construction.read` to read and `construction.manage` to write; idempotency scopes
   `construction.inspection`, `construction.quality_item` and `construction.quality_event`; the project
   lock serialises writes within a project; module off refuses writes (`MODULE_DISABLED`) and nothing is
   written; another company sees nothing; a branch-limited member sees and writes only its branch's
   projects; direct SQL updates and deletes are refused.

## Not in O4b

Reassigning an item or moving its due date (a new item replaces it); notifications to the responsible
party; customers answering on the platform (O6 with the grant of decision 11); the link of a repair's cost
to actual costs (warranty claims in O6 link through O3b); screens (O7).

## Acceptance of O4b — PASS 2026-11-01 (code `6b6124f`, [evidence](evidence/2026-11-01-o4b-quality/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| O4b-01 | Inspections are insert-only and numbered; a date after today on the site, a phase outside the budget, an unknown counterparty and a non-image photo are refused; without the contract nothing is written | PASS |
| O4b-02 | Defect and punch items are numbered with their references checked; an item naming a passed inspection is refused by the database; a due date before the raised date is refused | PASS |
| O4b-03 | Moves open -> fixed -> closed, fixed -> open (with a note) and open -> void (with a note) are kept as events; closed and void are final; a move the state does not allow is refused by the database too; a stale expected sequence is refused | PASS |
| O4b-04 | Two racing moves of one item leave one after an observed `pg_locks` wait | PASS |
| O4b-05 | Views: state from the latest event, history with photos, overdue in the site's time zone, summary per phase and kind | PASS |
| O4b-06 | Module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch; `construction.manage` needed for writes; direct SQL updates and deletes are refused | PASS |
| O4b-07 | 0091 -> 0092 keeps every row; the full suite stays green | PASS |
