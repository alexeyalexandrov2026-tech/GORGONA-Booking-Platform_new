# Package O, slice O4a — schedule, daily reports and completed quantities (2026-11-01)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decision 7 and acceptance O-06.
Architecture: [ADR-0035](../adr/0035-construction-projects-and-estimates.md). Previous slice:
[O3b](PACKAGE_O3B_DESIGN_2026-10-31.md) (actual costs). Branch `codex/package-o4a-execution` from the O3b
docs commit `9557ae2`. Same process as O1-O3b: failing tests first, one executor, one disposable
PostgreSQL 18 cluster per run, gates, a source-bound record, code and docs commits, push for CI without a PR.

## Why O4 is split

Decision 7 of the plan holds four different things. Like O3 (budget, then costs), O4 is built in two
slices:

- **O4a (this slice, migration 0091):** the phase schedule (planned dates and dependencies), daily
  reports and completed quantities with a progress view. It carries O-06.
- **O4b (next, migration 0092):** inspections, defects and the punch list as items with states.

## Scope

- Migration **0091**: `construction_schedule_versions`, `construction_schedule_phases`,
  `construction_schedule_dependencies`, `construction_daily_reports`, `construction_daily_report_crew`,
  `construction_daily_report_photos` and `construction_progress_measurements`, all insert-only (select and
  insert grants only); module gate; tenant isolation; branch scope as the last section. The O2 decision
  guard is replaced so that an approved removal never takes a contract line below its completed quantity.
- Services `business/construction_schedule.py`, `business/construction_daily_reports.py` and
  `business/construction_progress.py`; routes under
  `/v1/businesses/{id}/construction/projects/{id}`: `GET schedule`, `PUT schedule`; `GET daily-reports`,
  `GET daily-reports/{date}`, `PUT daily-reports/{date}`; `GET progress`, `POST progress` (a
  measurement), `GET progress/measurements`.

## Decisions (O4a)

1. **Everything here needs the contract.** Phases, lines and their quantities come from the budget (the
   contract lines after approved removals, and the added lines of approved change orders, as in O3a);
   before the contract there is nothing to schedule or measure (`CONSTRUCTION_NO_CONTRACT`).
2. **The schedule is one versioned document per project.** A version replaces the whole schedule: for each
   phase it names a planned start and a planned finish (dates in the site's time zone, 2000-01-01 to
   2100-12-31, finish not before start) and the phases it depends on (finish-to-start). Versions are
   insert-only and numbered 1, 2, ...; the latest counts. Phases and dependencies are written with their
   version, in its transaction. A phase must be a phase of the budget (`INVALID_REFERENCE` otherwise), at
   most 200 phases and 1000 dependencies per version. The client sends the version it saw
   (`expected_revision`, 0 before the first); a stale one is `CONSTRUCTION_REVISION_CONFLICT`, so two
   racing revisions leave one after an observed `pg_locks` wait on the project lock.
3. **Dependencies never form a cycle.** A phase never depends on itself (a check) and the database refuses
   the dependency that closes a cycle: before a dependency is stored the guard walks the dependencies
   already stored in the same version and refuses it when the predecessor already depends, directly or not,
   on the phase (`CONSTRUCTION_SCHEDULE_CYCLE`). Both ends must be phases of that version.
4. **The schedule view derives, it does not store.** For each scheduled phase: planned dates, its
   predecessors, `conflict` = it starts on or before the planned finish of a predecessor (shown, not
   blocked: moving one phase must not force rewriting the others), `critical` = on the critical chain, and
   its progress (decision 9). The critical chain starts at the phase with the latest planned finish and
   follows, step by step, the predecessor with the latest planned finish (ties by phase name). Budget phases
   that the version does not name are listed as unscheduled. No dates are optimised.
5. **A daily report per site date, with revisions.** A report names its date in the site's time zone; the
   date is not after today there (the database computes "today" from the project's time zone) and not
   before 2000-01-01. A report has weather (optional, 1-200), notes (optional, 1-4000), crew lines (up to
   50: a label 1-64, a headcount 1-1000 and optionally the counterparty whose crew it was) and photos (up to
   50 stage-1 document versions whose file is a PNG or JPEG; anything else is `INVALID_REFERENCE`). A
   correction is a new revision of the same date; earlier revisions stay. Crew lines and photos are written
   with their revision. The client sends the revision of that date it saw (`expected_revision`, 0 for the
   first); a stale one is `CONSTRUCTION_REVISION_CONFLICT`. A report that is all empty is refused
   (`INVALID_REQUEST`).
6. **Completed quantities are cumulative measurements.** A measurement names a budget line (a contract
   line, or an added line of an approved change order), a site date (not after today there, not before the
   latest measurement of the same line), the **quantity completed to date** on that line (0 or more, 4
   decimals, the line's unit) and an optional note (1-500). Measurements are insert-only and numbered per
   project; the latest one of a line counts.
7. **Never above the contract.** The quantity to date is at most the line's contracted quantity: the
   contract quantity minus approved removals, or the quantity of the added line
   (`CONSTRUCTION_ABOVE_CONTRACT`). More work than the contract needs an approved change order first; a
   change order adds scope as a new line, which then has its own measurements. A lower value than the
   previous measurement is a correction and needs a note (`CONSTRUCTION_CORRECTION_NOTE`).
8. **A removal never goes below the work done.** The O2 approval guard is replaced: approving a change
   order whose removals would leave a contract line below its completed quantity is refused
   (`CONSTRUCTION_BELOW_COMPLETED`). Both guards take the project row lock themselves, so the invariant
   holds for direct SQL too; a measurement racing an approval leaves exactly one of the two outcomes the
   order allows, after an observed `pg_locks` wait.
9. **Progress is derived.** Per budget line: contracted quantity, completed to date, percent (rounded
   down to 0.01, so 100 means finished), the line's contract value and its **completed value**. A line's
   contract value is computed as O2 computes the contract sum (the original line amount minus the amounts
   of its approved removals, each rounded half up). Completed value = the line's contract value when the
   line is finished, otherwise completed × unit price rounded half up, never above the line's contract
   value. So a finished project's completed value equals the current contract sum exactly, which O5 bills
   against. Per phase and in total the values are sums; percent there is by value.
10. **Rules as before.** `construction.read` to read and `construction.manage` to write; idempotency scopes
    `construction.schedule`, `construction.daily_report` and `construction.measurement`; the project lock
    serialises writes within a project; module off refuses writes (`MODULE_DISABLED`) and nothing is
    written; another company sees nothing; a branch-limited member sees and writes only its branch's
    projects; direct SQL updates and deletes are refused.

## Not in O4a

Inspections, defects and the punch list (O4b); actual start and finish dates typed by hand (progress comes
from measurements); weather from a provider; resource levelling and date optimisation; upload of photos (the
existing stage-1 document upload is used); screens (O7).

## Acceptance of O4a — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| O4a-01 | Schedule versions are insert-only; a phase outside the budget, a finish before the start and a stale version are refused; two racing revisions leave one after an observed `pg_locks` wait | NOT TESTED |
| O4a-02 | A dependency on itself and one that closes a cycle are refused by the database; the view shows conflicts, the critical chain and unscheduled phases | NOT TESTED |
| O4a-03 | Daily reports: one per site date with revisions; a date after today in the site's time zone is refused; crew, weather, notes and image photos are kept; a non-image or unknown document is refused | NOT TESTED |
| O4a-04 | Measurements are cumulative; above the contracted quantity is refused; an added line of an approved change order is measurable; a lower value needs a note; a date before the line's latest measurement is refused | NOT TESTED |
| O4a-05 | An approved removal below the completed quantity is refused; a measurement racing that approval leaves one outcome after an observed `pg_locks` wait | NOT TESTED |
| O4a-06 | Progress per line, phase and total: contracted, completed, percent, contract value and completed value; a finished project's completed value equals the current contract sum | NOT TESTED |
| O4a-07 | Module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch; `construction.manage` needed for writes; direct SQL updates and deletes are refused | NOT TESTED |
| O4a-08 | 0090 -> 0091 keeps every row; the full suite stays green | NOT TESTED |
