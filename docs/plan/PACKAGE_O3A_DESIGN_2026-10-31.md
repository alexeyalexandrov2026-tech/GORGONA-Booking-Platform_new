# Package O, slice O3a — the budget and commitments (2026-10-31)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), decision 6. Architecture:
[ADR-0035](../adr/0035-construction-projects-and-estimates.md). Branch `codex/package-o3a-budget` from the O2
docs commit `1f61f64`. Same process as O1 and O2: failing tests first, one executor, one disposable
PostgreSQL 18 cluster per run, gates, a source-bound record, code and docs commits, push for CI without a PR.

## Why O3 is split

Plan slice O3 has three parts: the budget, commitments and actual cost links to three existing facts (STOCK-01
write-offs, FIN-03 payables, WORK-01 time entries). Each of those facts has its own guards, currency and branch
rules. The slice is cut in two, as J5 was:

- **O3a** (this design, migration **0089**): the budget per line and phase, derived from the contract;
  commitments (subcontracts and supplier orders) against budget lines, versioned; budget vs committed.
- **O3b** (next, migration **0090**): actual cost links, each fact linked once, a reversal row instead of an
  edit; the budget view adds actual and the differences.

## Scope

- Migration **0089**: `construction_commitments` (the anchor: number, kind, counterparty),
  `construction_commitment_versions` and `construction_commitment_lines`; all insert-only (no update or delete
  grant); RLS, branch scope by the project's branch; the module gate on commitment and version inserts.
- Routes under `/v1/businesses/{business_id}/construction/projects/{project_id}`:
  - `GET budget` (`construction.read`);
  - `POST commitments` (`construction.manage`), `GET commitments`, `GET commitments/{number}`;
  - `PUT commitments/{number}` (`construction.manage`): the next version, on the revision the client read.

## Decisions (O3a)

1. **The budget is derived, never stored.** It exists once the project has a contract (`GET budget` without one
   is `CONSTRUCTION_NO_CONTRACT`). Its lines are the lines of the original contract (key: `change_order` null,
   `position` = the contract position) and the `add` lines of approved change orders (key: `change_order` =
   its number, `position` = its line position). A contract line's current quantity is its quantity less the
   quantities removed by approved change orders; its budget is the original line cost less the cost of those
   removals, each rounded as O2 rounds them, so **the budget total equals the contract's current cost**.
   A fully removed line stays, with budget 0. Proposed, rejected and withdrawn change orders do not count.
2. **Phases** are the phase labels of the budget lines, in the order they first appear (contract positions,
   then change orders by number and position). Each phase shows the sums of its lines. Planned dates and
   dependencies of phases belong to execution (O4, plan decision 7).
3. **A commitment** is a subcontract (`subcontract`, counterparty with the `contractor` role) or a supplier
   order (`purchase_order`, counterparty with the `supplier` role), numbered 1, 2, … per project (the database
   checks the sequence). The counterparty must be active at creation; kind and counterparty never change. It
   needs a contract (`CONSTRUCTION_NO_CONTRACT`).
4. **Commitment versions are insert-only.** Version 1 is written with the commitment; a revision needs the
   revision the client read (`CONSTRUCTION_REVISION_CONFLICT` otherwise). A version is `open` with a title
   (1–200), an optional reference (the counterparty's document number, 1–64), an optional note (1–1000) and 1 to
   200 lines; or `cancelled` with no lines, which is final (`CONSTRUCTION_COMMITMENT_CANCELLED` afterwards).
   A line names one budget line (at most once per version) and an amount in minor units (1 to 10^12). An unknown
   budget line is `INVALID_REFERENCE` (field `lines`); the database rechecks it.
5. **Committed** per budget line is the sum of the lines of the latest version of every open commitment. The
   view shows per line and phase: budget, committed, uncommitted (= budget − committed) and `over_committed`
   when committed > budget. **Overruns are shown, not blocked.**
6. All commands are idempotent with `Idempotency-Key`; module off is `MODULE_DISABLED`; module not accepted is
   `MODULE_NOT_READY`; another company sees nothing; a branch-limited member sees only its branch's projects.
   Two racing revisions of one commitment on the same revision leave one version after an observed `pg_locks`
   wait; two racing creations get numbers 1 and 2.

## Not in O3a

Actual costs and their links (O3b); phase dates and dependencies (O4); commitments in another currency (a
commitment is always in the project currency); a commitment as a FIN-03 document (the payable it produces is an
actual cost linked in O3b); retention on subcontracts (O5, O6).

## Acceptance of O3a — PASS 2026-10-31 (code `447ff4f`, [evidence](evidence/2026-10-31-o3a-budget/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| O3a-01 | No budget without a contract; the budget has the contract lines and the approved added lines, current quantity and cost after approved removals; the budget total equals the contract's current cost; unapproved change orders do not count | PASS |
| O3a-02 | Phases are the line phase labels with their sums, in first-appearance order | PASS |
| O3a-03 | A commitment needs a contract, a counterparty with the role of its kind, numbered in sequence; kind and counterparty fixed | PASS |
| O3a-04 | Versions are insert-only, need the read revision; cancelled is final; lines name a budget line once; direct SQL updates and deletes refused, unknown budget lines refused by the database | PASS |
| O3a-05 | Committed = latest version of open commitments; uncommitted and over-committed shown per line and phase; an overrun is not blocked | PASS |
| O3a-06 | Two racing revisions leave one after an observed `pg_locks` wait; two racing creations get 1 and 2 | PASS |
| O3a-07 | Module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch; `construction.manage` needed for writes | PASS |
| O3a-08 | 0088 -> 0089 keeps every row; the full suite stays green | PASS |
