# Package O, slice O3b — actual costs (2026-10-31)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decision 6. Architecture:
[ADR-0035](../adr/0035-construction-projects-and-estimates.md). Previous slice:
[O3a](PACKAGE_O3A_DESIGN_2026-10-31.md) (budget and commitments). Branch `codex/package-o3b-costs` from the
O3a docs commit `df6f84b`. Same process as O1-O3a: failing tests first, one executor, one disposable
PostgreSQL 18 cluster per run, gates, a source-bound record, code and docs commits, push for CI without a PR.

## What O3b adds

Actual costs are **links to facts that already exist** in other modules; construction never creates or edits
those facts. A link puts one fact on one budget line of a project. The budget view adds actual, remaining and
over-budget per line, per phase and in total, next to O3a's committed.

## Scope

- Migration **0090**: `construction_cost_links` (insert-only, numbered per project) and
  `construction_cost_reversals` (insert-only, one per link). No update or delete grant; module gate; tenant
  isolation; branch scope as the last section.
- Service `business/construction_costs.py`; routes under `/v1/businesses/{id}/construction/projects/{id}`:
  `GET costs`, `GET costs/{number}`, `POST costs` (link), `POST costs/{number}/reversal`; the existing
  `GET budget` gains the actual columns.

## Decisions (O3b)

1. **Three kinds of fact.** A link names exactly one:
   - `stock_write_off` — a line of a STOCK-01 write-off document (any reason) with its valuation. The
     document's branch must be the project's branch. Amount = the line's valuation; currency = the base
     currency of the ledger book the write-off was posted to. A zero-valued line has nothing to cost and is
     refused.
   - `payable` — a line of an **issued payable** FIN-03 invoice or manual accrual (not a credit note, not a
     receivable, not a draft). The link pins the issued revision and the line's stable `line_id`. Amount =
     the line amount; currency = the document currency.
   - `time_entry` — an **approved** WORK-01 time entry in the project's branch. The link pins the approved
     revision. Worked seconds = end − start − the breaks of that revision. WORK-01 has no labor cost rate, so
     the **rate per hour** (minor units of the project currency, 1 to 10^9) is entered with the link.
     Amount = worked seconds × rate / 3600, rounded half up to a whole minor unit; it must be at least 1.
2. **The database computes and checks.** The client sends the fact, the budget line, an optional note
   (1-500) and, for time, the rate. The guard trigger recomputes the amount from the fact and refuses a
   stored amount that differs; the fact's currency must equal the project currency
   (`CONSTRUCTION_COST_CURRENCY`). An unknown, invisible or ineligible fact, or an unknown budget line, is
   `INVALID_REFERENCE`. The budget line rule is O3a's (a contract line, or an added line of an approved change
   order); a link needs the contract.
3. **Each fact is linked once.** Across the whole company a fact has at most one link that is not reversed.
   Every link carries `attempt` = 1 + the number of earlier links of the same fact, and
   `(tenant, fact, attempt)` is unique; a new link needs every earlier link of that fact reversed. Two racing
   links of one fact in one project leave one after an observed `pg_locks` wait on the project lock; in two
   projects the unique `(tenant, fact, attempt)` lets only one commit. The loser gets
   `CONSTRUCTION_COST_ALREADY_LINKED`.
4. **A reversal instead of an edit.** A link is never changed. A reversal is one insert-only row per link with
   a reason (1-500); a reversed link no longer counts and its fact may be linked again (to another line or
   project). A second reversal is `CONSTRUCTION_COST_REVERSED`. Facts linked stay as they were: a stock
   valuation and an issued payable are final; a time entry approved again later keeps its link on the pinned
   revision — reverse and link again to take the new hours.
5. **Actual and the differences.** Actual = the sum of links not reversed, per budget line, per phase and in
   total. The budget view shows `actual_minor`, `remaining_minor` = budget − actual (may be negative) and
   `over_budget` = actual > budget, beside O3a's committed. Overruns are shown, not blocked.
6. **Rules as before.** `construction.manage` for writes (managers and owners, who also hold `finance.read`,
   `inventory.read` and `workforce.read`); idempotency scopes `construction.cost_link` and
   `construction.cost_reversal`; the project lock serialises writes within a project; module off refuses
   writes (`MODULE_DISABLED`); another company sees nothing; a branch-limited member sees and links only its
   branch's projects and, through the source modules' own branch scope, only its branch's write-offs and time
   entries.

## Not in O3b

Supplier credit notes netted against a linked payable (reverse the link and link the corrected document);
labor rate tables (the rate is entered per link); allocating one fact across several budget lines (one fact,
one line); facts in another currency; screens (O7).

## Acceptance of O3b — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| O3b-01 | A write-off line links at its valuation in the project's branch and currency; a receipt line, an unknown line, a project in another branch and another currency are refused | NOT TESTED |
| O3b-02 | A line of an issued payable invoice or manual accrual links at its amount; a draft, an issued receivable, an unknown line and another currency are refused | NOT TESTED |
| O3b-03 | An approved time entry links at worked seconds (breaks deducted) × the rate, rounded half up; open, proposed and declined entries and a project in another branch are refused | NOT TESTED |
| O3b-04 | A fact links once across projects; after its reversal it links again; two racing links of one fact leave one after an observed `pg_locks` wait | NOT TESTED |
| O3b-05 | A link is reversed once (racing reversals leave one); direct SQL updates and deletes are refused; a forged amount, currency or attempt is refused by the database | NOT TESTED |
| O3b-06 | Actual, remaining and over-budget per line, phase and total; reversed links do not count; budget, committed and actual reconcile; an overrun is not blocked | NOT TESTED |
| O3b-07 | Module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch; `construction.manage` needed for writes | NOT TESTED |
| O3b-08 | 0089 -> 0090 keeps every row; the full suite stays green | NOT TESTED |
