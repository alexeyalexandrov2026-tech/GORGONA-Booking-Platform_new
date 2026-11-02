# Package O, slice O6a — stage and final acceptance, retainage release (2026-11-02)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decisions 8-9 and 11, acceptance O-08
(BUILD-01: "stage acceptance, retainage and the invoice reconcile with the budget"). Architecture:
[ADR-0035](../adr/0035-construction-projects-and-estimates.md). Previous slice:
[O5](PACKAGE_O5_DESIGN_2026-11-01.md) (pay applications with retainage). Branch
`codex/package-o6a-acceptance` from the O5 docs commit `47ba8bd`, in the O5 worktree
(`.codex/worktrees/package-o5`). Same process as O1-O5: failing tests first, one executor, one
disposable PostgreSQL 18 cluster per run, gates, a source-bound record, code and docs commits, push for
CI without a PR.

## O6 is split in two

O6 is split like O3 and O4. **O6a** (this slice, migration **0094**): stage and final acceptance, what
an acceptance closes, and the release of retainage. **O6b** (next, migration **0095**): warranty
claims with their repair cost linked to actual costs, and the reconciliation view per project. O6a
already records the warranty period with the final acceptance, so O6b only adds the claims.

## Scope

- Migration **0094**: `construction_acceptances` and `construction_retainage_releases`, both
  insert-only (select and insert grants only); functions `construction_budget_line_phases` (every budget
  line with its phase) and `construction_phase_retained` (the retainage held on one phase); new guards
  that close accepted work for measurements, change-order approvals and pay applications; module gate;
  tenant isolation; branch scope as the last section. No earlier guard body is replaced: the closing
  checks are separate triggers, so the O4a measurement guard and the change-order decision guard of
  0093 stay as they are.
- Service `business/construction_acceptance.py`; routes under
  `/v1/businesses/{id}/construction/projects/{id}`: `GET acceptances`, `GET acceptances/{number}`,
  `POST acceptances`, `POST acceptances/{number}/release`.
- FIN-03 is not changed (decision 9).

## Decisions (O6a, agent, under the owner's delegation)

1. **Everything here needs the contract** (`CONSTRUCTION_NO_CONTRACT`).
2. **An acceptance is the customer's recorded answer**, insert-only and numbered per project. Its
   scope is `phase` (one phase of the budget; an unknown one is `INVALID_REFERENCE`) or `final` (the
   whole project); the client names the scope explicitly, so a missing phase never becomes a final
   acceptance by accident. It has a site date (not after today on the site,
   `CONSTRUCTION_FUTURE_DATE`; not before 2000-01-01), the customer's signatory (1-200, one line), the
   source (`paper` or `email`) and an optional note (1-1000). As with the contract and change-order
   answers (O2), recording it needs `construction.approve`; a customer answering on the platform through
   a grant (plan decision 11) is not built yet, so the source `platform` is reserved and refused by the
   API, exactly as in O2.
3. **Each scope is accepted once.** A phase is accepted at most once and the project at most once
   finally; after the final acceptance nothing more is accepted (`CONSTRUCTION_ACCEPTED`). Phase
   acceptances are not required before the final one: the final acceptance accepts the whole project.
4. **Only finished work is accepted.** Every budget line in the scope (the phase's lines, or all lines
   for the final acceptance) must be finished: its contracted quantity (after approved changes) is 0, or
   its latest measurement reaches it and is dated on or before the acceptance date. Otherwise
   `CONSTRUCTION_NOT_COMPLETED`.
5. **Open defects and punch items block an acceptance** (the question O4b left to O6). A quality item
   whose state is `open` or `fixed` (fixed but not yet verified) blocks the acceptance of its phase;
   every such item of the project, with or without a phase, blocks the final acceptance
   (`CONSTRUCTION_OPEN_ITEMS`). Items without a phase do not block a phase acceptance. `closed` and
   `void` items do not block.
6. **The final acceptance closes billing and starts the warranty.** It needs the whole contract
   billed: the latest pay application's billed to date equals the current contract sum
   (`construction_contract_minor`), otherwise `CONSTRUCTION_NOT_FULLY_BILLED` (the business bills the
   last period first). It records the warranty end date, after the acceptance date and not after
   2100-12-31 and not more than 10 years after it; the warranty period runs from the acceptance date to
   that date (O6b records claims against it). A phase acceptance has no warranty date.
7. **Accepted work is closed.** After a phase acceptance, a measurement of a line of that phase is
   refused, and so is the approval of a change order that adds a line to that phase or removes from a
   line of it. After the final acceptance every measurement, every change-order approval and every pay
   application is refused. All of these answer `CONSTRUCTION_ACCEPTED`. A rejection or a withdrawal of a
   change order stays possible (it changes no scope). New quality items stay possible (a problem found
   after acceptance is recorded; in the warranty period O6b adds claims).
8. **Retainage is released once per acceptance, by the amount it frees** (O-08). A release names an
   acceptance, a site date (on or after the acceptance date and not after today on the site) and an
   optional note, and needs `construction.manage`. The server computes the amount; the client never
   sends it:
   - for a **phase** acceptance, the retainage held on that phase: for every pay application, the
     change of the phase's billed value from the previous application times that application's rate,
     rounded down, summed over the applications (`construction_phase_retained`); it needs the phase
     billed in full (in the latest application every line of the phase is billed at its contracted
     quantity), otherwise `CONSTRUCTION_NOT_FULLY_BILLED`;
   - for the **final** acceptance, everything still held: retained to date minus everything released.
   The amount is never above what is still held (retained to date minus released). An amount of 0 is
   `CONSTRUCTION_NOTHING_TO_RELEASE`. A second release of one acceptance is `CONSTRUCTION_RELEASED`;
   after the final release no phase release is recorded (`CONSTRUCTION_RELEASED`). Two racing releases of
   one acceptance leave one after an observed `pg_locks` wait.
9. **Release is a construction fact; FIN-03 is not changed.** The retained amounts are the receivable
   accruals without a due date that O5 drafted, one FIN-03 obligation each. FIN-03 obligations have no
   due date and settlements allocate money to obligations with no domain gate, so O6a does not block
   collection: refusing money a customer actually pays would make FIN-03 wrong. The release records
   when retainage became due; O6b's reconciliation shows released, paid and any retainage paid before
   its release as a difference, derived.
10. **The database rechecks everything** under the project lock: the acceptance's sequence, its date,
    its phase, that its scope was not accepted and that no final acceptance exists, that the work is
    finished, that no open or fixed item blocks it, and for the final one that the contract is billed
    in full and the warranty date; for a release its acceptance, its date, that it is the first for the
    acceptance and that no final release exists, the phase billed in full and the exact amount; and the
    closing rules of decision 7.
11. **Views derive.** `GET acceptances` lists the acceptances (each with its release, if any), every
    phase of the budget (finished or not, open items, billed in full or not, retainage held, its
    acceptance and release), the final acceptance with the warranty period, and the totals: retained to
    date, released and still held. `GET acceptances/{number}` shows one acceptance with its release.
12. **Rules as before.** `construction.read` to read; `construction.approve` to record an acceptance;
    `construction.manage` to record a release; idempotency scopes `construction.acceptance` and
    `construction.retainage_release`; module off refuses writes (`MODULE_DISABLED`) and nothing is
    written; another company sees nothing; a branch-limited member sees and writes only its branch's
    projects; direct SQL updates and deletes are refused.

## Not in O6a

Warranty claims and their repair cost, and the reconciliation view (O6b); a signed copy of the
acceptance as a document version (as for the contract in O2, a later screen slice may add it); customers
answering on the platform (plan decision 11, with the grant); blocking FIN-03 collection of retainage
(decision 9); revoking an acceptance (it is a fact; a later problem is a quality item or a warranty
claim); screens (O7).

## Acceptance of O6a — PASS 2026-11-02 (code `c06ec73`, [evidence](evidence/2026-11-02-o6a-acceptance/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| O6a-01 | A phase or final acceptance is numbered and insert-only, with its signatory, source and site date; a date after today on the site, an unknown phase, the source `platform`, a missing contract and a member without `construction.approve` are refused; each scope is accepted once and nothing after the final acceptance | PASS |
| O6a-02 | Only finished work is accepted (lines below their contracted quantity or measured after the acceptance date are refused); open or fixed items of the phase block a phase acceptance and any open or fixed item blocks the final one; the final one needs the contract billed in full and records the warranty period | PASS |
| O6a-03 | Accepted work is closed: measurements and change-order approvals touching an accepted phase, and after the final acceptance every measurement, approval and pay application, are refused; rejections and withdrawals stay possible | PASS |
| O6a-04 | Retainage is released once per acceptance by the amount the server derives (a phase's held retainage once it is billed in full; the rest at the final acceptance); nothing more than is held, nothing twice, nothing after the final release (O-08) | PASS |
| O6a-05 | Two racing releases of one acceptance, and an acceptance racing a measurement of its phase, each leave one outcome after an observed `pg_locks` wait | PASS |
| O6a-06 | The database refuses forged acceptances and releases (sequence, date, scope, unfinished work, open items, not billed, wrong amount, second release) and direct SQL updates and deletes; module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch | PASS |
| O6a-07 | 0093 -> 0094 keeps every row; the full suite stays green | PASS |
