# Package O, slice O7b — construction screens: budget, commitments, schedule, daily reports and completed quantities (2026-11-02)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), slice O7 and acceptance O-10. The O7 split is in
[O7a](PACKAGE_O7A_DESIGN_2026-11-02.md); handoff [NEXT_AGENT_PACKAGE_O7B_2026-11-02.md](NEXT_AGENT_PACKAGE_O7B_2026-11-02.md).
Branch `codex/package-o7b-construction-screens` from the O7a docs commit `dec2b58`, in the O5 worktree. Same process
as O7a: failing tests first, gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI
without a PR.

## The O7b part is split again

Linking an actual cost needs a fact from another module: a STOCK-01 write-off line, a FIN-03 payable line or an
approved WORK-01 time entry. Construction has no read that offers those facts, and a form that asks for their ids
is not usable. So **O7b2** builds the cost links (the list, the pickers over the facts and the reversal), after a
check of which reads of STOCK-01, FIN-03 and WORK-01 it can use. O7b (this) builds everything else of O3a-O4a.

## Scope of O7b

- Web only; **no API change and no migration** (next migration stays 0096).
- `web/components/construction-budget.tsx` (budget per line and phase, commitments), `web/components/construction-execution.tsx`
  (schedule, daily reports, completed quantities), strict contracts and API calls for every O3a and O4a response
  and command they use, added to `construction-contracts.ts` and `construction-api.ts`; the project page
  (`construction.tsx`) shows them once the project has a contract.
- Tests: `web/tests/construction-contracts.spec.ts` (new cases), `web/tests/construction-execution.spec.ts` (real browser,
  desktop and mobile, `test:management:construction-execution`) and `api/tests/integration/test_o7b_construction_browser.py`.

## Decisions (O7b, agent, under the owner's delegation)

1. **The budget** shows each line (contract line or change-order line), its phase, description, budget, committed,
   uncommitted, actual and remaining, and the flags "over committed" and "over budget"; the same per phase and in
   total. All figures are the server's (O3a decision 1); actual comes from the cost links (O7b2 adds the screen).
2. **Commitments** are listed with number, kind, counterparty, title, state, revision and total. A new one has a kind
   (subcontract or purchase order), an active counterparty with the role of its kind (contractor or supplier;
   the server checks it), a title, optional reference and note, and lines that each name a budget line and an
   amount. An open commitment is revised as a whole with the revision the screen read; cancelling is a revision
   with the state "cancelled", final on the server.
3. **The schedule** shows the latest version: each phase with its planned start and finish (site dates), its
   predecessors, the server's conflict and critical flags and percent complete, the planned finish and the budget
   phases not yet scheduled. The editor has one row per budget phase (planned or not); a phase is planned when both
   dates are given; predecessors are chosen among the other planned phases. It saves the next version with the
   revision it read; the server refuses a cycle or a finish before a start.
4. **Daily reports** are listed by site date (revision, weather, headcount, photos). The form takes a site date,
   weather, notes and crew rows (label, headcount); it reads the report of that date first so it sends that
   revision (0 for a new date). Photos are not added on this screen (they are document versions; a later screen).
5. **Completed quantities**: the progress view per line and phase (contracted, completed, percent, contract and
   completed value) and the measurements. A measurement names a line, a site date and the cumulative quantity to
   date; the server refuses one above the contracted quantity, after today on the site or before the line's latest
   measurement. A measurement keeps its Idempotency-Key until saved, so a retry after a lost answer records once.
6. Accessibility and times as in O7a (named forms, tables in focusable regions, site dates, axe, no horizontal
   scroll at 375 px).

## Acceptance of O7b — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| O7b-01 | Strict contracts accept every O3a and O4a response the screens read and refuse unknown fields and bad values | NOT TESTED |
| O7b-02 | In a real browser (desktop and mobile) an owner sees the budget, creates a subcontract and revises it above the line's budget; the budget shows committed and over committed as the server derived them; the database holds both versions | NOT TESTED |
| O7b-03 | The owner saves a schedule with a dependency and sees the planned finish; saves a daily report by keyboard; records a completed quantity after a lost answer once and sees the progress; the database holds them | NOT TESTED |
| O7b-04 | Axe finds no violation on the budget and execution parts; no horizontal scroll on mobile | NOT TESTED |
| O7b-05 | Web static checks and the full suite stay green | NOT TESTED |

## Not in O7b

Cost links (O7b2); photos of daily reports; schedule history browsing beyond the latest version; O7c screens.
