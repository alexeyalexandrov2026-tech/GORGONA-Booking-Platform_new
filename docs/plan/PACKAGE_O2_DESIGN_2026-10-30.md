# Package O, slice O2 — the contract and change orders (2026-10-30)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decisions 4 and 5. Architecture:
[ADR-0035](../adr/0035-construction-projects-and-estimates.md). Branch `codex/package-o2-contract` from the O1
docs commit `3b80a13`. Same process as O1: failing tests first, one executor, one disposable PostgreSQL 18
cluster per run, gates, a source-bound record, code and docs commits, push for CI without a PR.

## Scope

- Migration **0088**: `construction_contracts`, `construction_change_orders`,
  `construction_change_order_lines`, `construction_change_order_decisions`; all insert-only (no update or
  delete grant); RLS, branch scope by the project's branch; the module gate on contract, change order and
  decision inserts. The 0087 guards are replaced (`create or replace`) so that after a contract no new
  estimate version is written and the project's customer does not change.
- Routes under `/v1/businesses/{business_id}/construction/projects/{project_id}`:
  - `POST contract` (`construction.approve`), `GET contract` (`construction.read`);
  - `POST change-orders` (`construction.manage`), `GET change-orders`, `GET change-orders/{number}`;
  - `POST change-orders/{number}/decision`: `approved` and `rejected` need `construction.approve` (the
    customer's answer, recorded by the business); `withdrawn` needs `construction.manage`.

## Decisions (O2)

1. **The contract is the accepted proposal.** It names an estimate version that is proposed and is the
   latest; one contract per project. It records the customer's signatory (1–200 characters), the source of
   the answer (`paper` or `email` through these routes; `platform` is kept for the customer's own answer
   through a grant, which comes with decision 11 in a later slice), an optional note and who recorded it at
   server time. The accepted version is the **original contract**; nothing changes it. Once a contract
   exists, a new estimate version is refused (`CONSTRUCTION_CONTRACT_EXISTS`) and the project's customer
   cannot change (`CONSTRUCTION_CUSTOMER_FIXED`); the database rechecks both.
2. Accepting a version that was never proposed is `CONSTRUCTION_NOT_PROPOSED`; an older version is
   `CONSTRUCTION_ESTIMATE_STALE`; a second contract is `CONSTRUCTION_CONTRACT_EXISTS`. Two racing
   acceptances leave one contract after an observed `pg_locks` wait.
3. **Change orders** need a contract (`CONSTRUCTION_NO_CONTRACT`), are numbered 1, 2, … per project
   (the database checks the sequence), have a title (1–200), an optional reason (1–1000), a change of days
   (−3650 to 3650) and 1 to 200 lines, written with the header and never changed.
   - `add` adds scope: kind, description, phase, quantity, unit, unit cost, unit price, optional material
     (the O1 line rules).
   - `remove` removes a quantity of a line of the original contract, named by its position, at that line's
     unit cost and price; the quantity is never above the line's quantity less the quantities removed by
     approved change orders (`CONSTRUCTION_SCOPE_EXCEEDED`, rechecked by the database at approval).
   - A **reprice** is a `remove` of a contract quantity and an `add` of the same scope at the new price in
     one change order; its effect is the difference, derived on read.
4. **States** are derived from one decision row per change order: none = `proposed`; `approved`,
   `rejected` or `withdrawn` are final. A decision on a decided change order is
   `CONSTRUCTION_CHANGE_ORDER_DECIDED` with the state it has. `approved` and `rejected` carry the source of
   the customer's answer (`paper` or `email`); `withdrawn` has none. Two racing approvals, or an approval
   racing a withdrawal, leave one decision after an observed `pg_locks` wait.
5. **The contract view** derives: the original cost and price totals (from the accepted version), the
   approved changes (cost, price, days), the **current contract sum** = original + approved changes, and the
   list of change orders with their state and effect. Nothing of this is stored.
6. All commands are idempotent with `Idempotency-Key`; module off is `MODULE_DISABLED`; module not
   accepted is `MODULE_NOT_READY`; another company sees nothing; a branch-limited member sees only its
   branch's projects.

## Not in O2

The customer's own answer on the platform (decision 11, with a grant); a signed copy as a document
version; removing scope that an earlier change order added (a later change order removes only
original-contract scope); retainage and warranty terms on the contract (O5, O6); budget and costs (O3).

## Acceptance of O2 (all NOT TESTED)

| id | Requirement |
|---|---|
| O2-01 | Only the latest proposed version becomes the contract; never-proposed and older versions refused; one contract per project; the contract records signatory, source and who recorded it |
| O2-02 | After the contract no estimate version is added and the customer cannot change; direct SQL updates and deletes of contracts, change orders, lines and decisions refused |
| O2-03 | Change orders need a contract, are numbered in sequence, insert-only; remove names a contract line and never exceeds its remaining quantity |
| O2-04 | The current contract sum = original + approved changes (add, remove, reprice); rejected, withdrawn and proposed change orders do not count; the original never changes |
| O2-05 | A decided change order refuses another decision; approve and reject need `construction.approve` |
| O2-06 | Two racing approvals, and an approval racing a withdrawal, leave one decision after an observed `pg_locks` wait; two racing acceptances leave one contract |
| O2-07 | Module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch |
| O2-08 | 0087 -> 0088 keeps every row; the full suite stays green |
