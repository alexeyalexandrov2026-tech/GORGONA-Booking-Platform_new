# Package O, slice O6b — warranty claims, repair cost and the reconciliation view (2026-11-02)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decisions 9-10, acceptance O-05 and
BUILD-01 ("stage acceptance, retainage and the invoice reconcile with the budget"). Architecture:
[ADR-0035](../adr/0035-construction-projects-and-estimates.md). Previous slice:
[O6a](PACKAGE_O6A_DESIGN_2026-11-02.md) (acceptance and retainage release), handoff
[NEXT_AGENT_PACKAGE_O6B_2026-11-02.md](NEXT_AGENT_PACKAGE_O6B_2026-11-02.md). Branch
`codex/package-o6b-reconciliation` from the O6a docs commit `04d0329`, in the O5 worktree. Same process
as O1-O6a: failing tests first, one executor, one disposable PostgreSQL 18 cluster per run, gates, a
source-bound record, code and docs commits, push for CI without a PR. From this slice on the heavy runs
(red, dev, gates) run on the Google Cloud VM `gorgona-dev` (Linux), as the owner asked.

## Scope

- Migration **0095**: `construction_warranty_claims`, `construction_warranty_claim_events` and
  `construction_warranty_repairs`, all insert-only (select and insert grants only); their guards; module
  gate; tenant isolation; branch scope as the last section. No earlier guard body is replaced; the O3b
  cost-link guard stays as it is.
- Service `business/construction_warranty.py` (claims, repairs and the reconciliation view); routes
  under `/v1/businesses/{id}/construction/projects/{id}`: `GET warranty-claims`,
  `GET warranty-claims/{number}`, `POST warranty-claims`, `POST warranty-claims/{number}/events`,
  `POST warranty-claims/{number}/repairs`, `GET reconciliation`.
- FIN-03 is not changed.

## Decisions (O6b, agent, under the owner's delegation)

1. **Everything here needs the contract** (`CONSTRUCTION_NO_CONTRACT`).
2. **A warranty claim** is the customer's report of a problem after the final acceptance, insert-only and
   numbered per project: a title (1-120, one line), an optional description (1-4000), an optional phase
   of the budget (an unknown one is `INVALID_REFERENCE`), an optional place (1-200, one line), who
   reported it (1-200, one line) and the site date it was raised. A claim exists only inside the
   warranty period: without the final acceptance it is refused (`CONSTRUCTION_NO_WARRANTY`, 409); a
   date before the final acceptance or after the warranty end is refused
   (`CONSTRUCTION_OUTSIDE_WARRANTY`, 422); a date after today on the site is refused
   (`CONSTRUCTION_FUTURE_DATE`). The database rechecks all of it under the project lock.
3. **States move by insert-only events**, as quality items in O4b: a claim starts `open`; `open` moves
   to `repaired` or `rejected`; `repaired` moves to `closed` or back to `open` (reopened); `closed` and
   `rejected` are final. Rejecting and reopening carry a note. Any other move is
   `CONSTRUCTION_CLAIM_TRANSITION` (409). The database checks the move against the latest event under
   the project lock; two racing moves of one claim leave one after an observed `pg_locks` wait. A move
   is not limited to the warranty period (a claim raised in time is finished after it).
4. **Repair cost is a label on an O3b cost link.** The repair is paid like any cost: a STOCK-01
   write-off line, a FIN-03 payable line or approved WORK-01 time is linked to the budget line it
   repairs (O3b), and that link is then assigned to the claim. So each fact still counts once (the O3b
   guard is unchanged) and the repair cost is part of actual cost, shown apart. A link is assigned to at
   most one claim (`CONSTRUCTION_REPAIR_ASSIGNED`, 409); a reversed link is refused
   (`CONSTRUCTION_COST_REVERSED`); a claim that is closed or rejected takes no new cost
   (`CONSTRUCTION_CLAIM_CLOSED`, 409). If a link is reversed after its assignment, it stops counting
   for the claim (derived; the assignment row stays).
5. **The reconciliation view derives everything**, nothing is stored: the contract sum (original plus
   approved changes) and the completed value (O4a); the budget, committed and actual cost (O3), actual
   split into warranty repair cost and the rest; billed, retained and due (O5); released and still held
   (O6a); and for the FIN-03 obligations of the pay-application invoices and the retainage accruals
   (through `settlements.load_obligation`), paid and credited; a document not issued yet has no
   obligation and counts as nothing settled. The differences: contract minus billed, completed minus
   billed, billed minus settled (paid and credited), retained minus released (held), retainage settled
   before its release (settled on the retainage obligations above what was released, never below 0),
   budget minus actual and contract minus actual. The claims are summarised by state with their repair
   cost.
6. **Rules as before.** `construction.read` to read; `construction.manage` to record claims, events and
   repairs; idempotency scopes `construction.warranty_claim`, `construction.warranty_event` and
   `construction.warranty_repair`; module off refuses writes (`MODULE_DISABLED`) and nothing is written;
   another company sees nothing; a branch-limited member sees and writes only its branch's projects;
   direct SQL updates and deletes are refused.

## Not in O6b

Photos of a claim (a later screen slice may add them as for quality items); customers raising claims on
the platform (plan decision 11, with the grant); blocking FIN-03 collection of retainage before release
(O6a decision 9; the view reports it); a warranty extension; screens (O7).

## Acceptance of O6b (all NOT TESTED)

| id | Requirement | Result |
|---|---|---|
| O6b-01 | A warranty claim is numbered and insert-only with its title, phase, place, reporter and site date; without the final acceptance, before it, after the warranty end, after today on the site, with an unknown phase, without the contract and for a member without `construction.manage` it is refused | NOT TESTED |
| O6b-02 | A claim moves only open to repaired or rejected and repaired to closed or open; closed and rejected are final; rejecting and reopening need a note | NOT TESTED |
| O6b-03 | A cost link of the project is assigned to a claim once; a reversed link, a link already assigned and a closed or rejected claim are refused; a link reversed later stops counting for the claim; each fact still counts once | NOT TESTED |
| O6b-04 | The reconciliation view derives contract, completed, budget, committed, actual (warranty repair apart), billed, retained, due, released, held, paid and credited on the FIN-03 obligations, and the differences, including retainage settled before its release (O-05) | NOT TESTED |
| O6b-05 | Two racing moves of one claim leave one outcome after an observed `pg_locks` wait | NOT TESTED |
| O6b-06 | The database refuses forged claims, events and repairs (sequence, period, date, phase, move, note, link, claim state) and direct SQL updates and deletes; module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch | NOT TESTED |
| O6b-07 | 0094 -> 0095 keeps every row; the full suite stays green | NOT TESTED |
