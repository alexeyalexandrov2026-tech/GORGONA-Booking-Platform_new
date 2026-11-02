# Package O, slice O5 — pay applications with retainage (2026-11-01)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decision 8 and acceptance O-07
(BUILD-01, part 2: "retainage and the invoice reconcile with the budget"). Architecture:
[ADR-0035](../adr/0035-construction-projects-and-estimates.md). Previous slice:
[O4b](PACKAGE_O4B_DESIGN_2026-11-01.md). Branch `codex/package-o5-pay-applications` from the O4b docs
commit `88cf16e`, in its own worktree (`.codex/worktrees/package-o5`). Same process as O1-O4b: failing
tests first, one executor, one disposable PostgreSQL 18 cluster per run, gates, a source-bound record,
code and docs commits, push for CI without a PR.

## Scope

- Migration **0093**: `construction_retainage_rates`, `construction_pay_applications` and
  `construction_pay_application_lines`, all insert-only (select and insert grants only); function
  `construction_contract_minor`; module gate; tenant isolation; branch scope as the last section. The O4a
  measurement guard and the O2/O4a change-order decision guard are replaced to keep billed periods and
  billed amounts whole (decisions 7-8).
- Service `business/construction_billing.py`; routes under
  `/v1/businesses/{id}/construction/projects/{id}`: `GET retainage`, `PUT retainage`;
  `GET pay-applications`, `GET pay-applications/{number}`, `POST pay-applications`.
- FIN-03 is reused, not copied: a pay application drafts its documents through
  `financial_documents.save_draft`, and FIN-03 refuses to edit a draft that belongs to a pay application,
  as it does for visits, prepaid sales and transport.

## Decisions (O5, agent, under the owner's delegation)

1. **Everything here needs the contract** (`CONSTRUCTION_NO_CONTRACT`).
2. **The retainage rate is versioned on the contract.** A version holds a rate in basis points from 0 to
   5000 (0% to 50%); versions are insert-only and numbered 1, 2, ...; the client sends the revision it
   saw (`expected_revision`, 0 before the first; stale: `CONSTRUCTION_REVISION_CONFLICT`). Before the
   first version the rate is 0. A pay application records the rate and the revision it used; later
   versions never change an earlier application.
3. **A pay application closes a billing period.** Applications are numbered per project. Each names its
   period end, a site date not after today there (`CONSTRUCTION_FUTURE_DATE`) and strictly after the
   previous application's period end (`CONSTRUCTION_PERIOD_BILLED`): one application per period, and two
   racing applications for one period leave one after an observed `pg_locks` wait on the project lock.
4. **It bills completed value to date minus earlier billing.** For every budget line (contract lines
   after approved removals and added lines of approved change orders) the application stores the
   quantity completed as of its period end (the line's latest measurement dated on or before it, 0 when
   none) and that quantity's completed value under O4a decision 9 (a finished line is worth its contract
   value, otherwise quantity times unit price rounded half up, never above the line's contract value).
   **Billed to date** is their sum; **billed this period** = billed to date minus the previous
   application's billed to date, and must be above zero (`CONSTRUCTION_NOTHING_TO_BILL`). A line may bill
   less than before (a measurement corrected down after a period); only the total must grow.
5. **Retainage is held from each billed amount.** Retained = billed this period times the rate, rounded
   down to the minor unit; **due** = billed this period minus retained. With the rate at most 50%, due is
   always above zero.
6. **Two FIN-03 documents, never mixed.** The application drafts a FIN-03 **receivable invoice** for the
   amount due (the project's customer and currency, the receivable control account the client names, one
   line to the revenue account) and, when retained is above zero, a separate **receivable manual
   accrual** for the retained amount on the retainage account the client names (an asset account other
   than the receivable control account), with **no due date**: it becomes due only on a recorded
   acceptance or release (O6). Revenue is the whole billed amount across the two. The accrual's number is
   the invoice number with `-R`. Both are drafts the business issues through FIN-03, as with transport
   invoices; each becomes its own obligation there. FIN-03 refuses to edit them
   (`FINANCIAL_DOCUMENT_LINKED`).
7. **A billed period is closed for measurements.** The O4a measurement guard is replaced: a measurement
   dated on or before the latest application's period end is refused (`CONSTRUCTION_PERIOD_BILLED`), so
   every application's stored quantities stay the measurements of its period. Corrections are dated
   after it.
8. **Billed never exceeds the contract sum** (BUILD-01). Completed value never exceeds a line's contract
   value, so billed to date is at most the current contract sum (a finished project bills exactly it);
   the database rechecks it with `construction_contract_minor` (the O2 sum: original line amounts less
   approved removal amounts plus approved added lines, each rounded half up). The change-order decision
   guard is replaced so that an approval that would take the contract sum below billed to date is
   refused (`CONSTRUCTION_BELOW_BILLED`), besides its O2 and O4a checks.
9. **The database rechecks the whole application** under the project lock: number order, period order,
   site date, the previous billed amount, the arithmetic of this period, retained and due, the rate
   version, billed to date against the contract sum, both documents (kind, receivable, customer,
   currency, amount, the accrual present exactly when retained is above zero), lines written with their
   application and each line's quantity equal to its latest measurement as of the period end; at commit,
   the lines add up to billed to date.
10. **Views derive.** `GET pay-applications` lists the applications (period end, billed to date, this
    period, retained, due, the FIN-03 state of each document) with totals: contract sum, billed to date,
    retained to date, due to date and still to bill. `GET pay-applications/{number}` shows the lines
    (contracted quantity and value, completed to date, value to date, previously billed, this period),
    the rate and both FIN-03 documents. Release of retainage, acceptance and reconciliation are O6.
11. **Rules as before.** `construction.read` to read and `construction.manage` to set the rate and bill
    (issuing and settling stay FIN-03 operations with their own rights); idempotency scopes
    `construction.retainage` and `construction.pay_application`; module off refuses writes
    (`MODULE_DISABLED`) and nothing is written; another company sees nothing; a branch-limited member sees
    and writes only its branch's projects; direct SQL updates and deletes are refused.

## Not in O5

Release of retainage, stage and final acceptance, warranty and the reconciliation view (O6); credit
notes against a pay application (FIN-03 credit notes stay available but are not linked here); taxes,
percentage-of-completion revenue recognition and lien waivers (plan, "Not in this package"); stored
materials billed before installation; screens (O7).

## Acceptance of O5 — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| O5-01 | Retainage rate versions are insert-only, 0-5000 basis points, a stale revision is refused; an application keeps the rate it used | NOT TESTED |
| O5-02 | An application bills completed value as of its period end minus earlier billing, per line; retained is rounded down and due is the rest; a FIN-03 receivable invoice (due) and a separate receivable accrual without a due date (retained) are drafted, frozen, and issue as two obligations | NOT TESTED |
| O5-03 | One application per period: a period not after the previous one, a period after today on the site, nothing to bill and no contract are refused; a measurement dated in a billed period is refused | NOT TESTED |
| O5-04 | Billed to date never exceeds the contract sum: a finished project bills exactly the contract sum; an approval below billed is refused; the database refuses a forged application (over the sum, wrong arithmetic, wrong rate, wrong document, lines not adding up) | NOT TESTED |
| O5-05 | Two racing applications for one period leave one after an observed `pg_locks` wait | NOT TESTED |
| O5-06 | Module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch; `construction.manage` needed for writes; direct SQL updates and deletes are refused | NOT TESTED |
| O5-07 | 0092 -> 0093 keeps every row; the full suite stays green | NOT TESTED |
