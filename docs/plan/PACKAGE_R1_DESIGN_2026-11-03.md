# Package R, slice R1 — rental module, item classes and units (2026-11-03)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), slice R1 and acceptance R-01.
Architecture: [ADR-0036](../adr/0036-rental-classes-and-units.md). Branch `codex/package-r1-rental-catalog` from the
O7b docs commit `506f12c`, in the O5 worktree. Same process as package O: failing tests first, one executor, one
disposable PostgreSQL 18 cluster per run, gates on the VM `gorgona-dev`, a source-bound record, code and docs
commits, push for CI without a PR.

## Scope

- Registry: module `rental` (implemented, not enableable), registry version 6; permissions `rental.read`,
  `rental.manage`, `rental.approve` for owners and managers, permissions version 12.
- Migration **0096**: `rental_classes`, `rental_class_attributes`, `rental_units`, `rental_unit_values`; guards that
  raise `check_violation` with a named constraint; module gate; tenant isolation; select and insert grants (update
  only on the mutable head columns); the `-- Rental branch scope:` section last.
- Service `business/rental.py` and routes in `api/rental.py` under `/v1/businesses/{id}/rental`: `GET classes`,
  `GET classes/{id}`, `PUT classes/{id}`, `GET units` (optionally `?class_id=`), `GET units/{id}`, `PUT units/{id}`;
  lists paged by `?after=` (50 a page, `next_cursor`).

## Decisions (R1, agent)

1. **Class** body: `expected_revision`, `code` (1-32: capital letters, digits, `-` or `_`), `name` (1-200, one line),
   `meter_kind` (`none`, `odometer`, `hours`) and `attributes` (0-50, unique keys: `key` `^[a-z][a-z0-9_]{0,31}$`,
   `label` 1-100, `type` `text`, `number` or `boolean`, `required`). A taken code is `RENTAL_CODE_TAKEN` (409); a
   code is fixed after creation (`RENTAL_CODE_FIXED`, 409). Writing a class needs a company-wide member.
2. **Unit** body: `expected_revision`, `class_id`, `identifier` (1-64, one line), `location_id`, `state` (`active` or
   `retired`) and `values` (key to string; a number is a decimal string up to 12 digits and 6 places, a boolean is
   `true` or `false`). An unknown class or branch is `INVALID_REFERENCE`; a taken identifier is
   `RENTAL_IDENTIFIER_TAKEN` (409); a changed class or identifier is `RENTAL_UNIT_FIXED` (409); a retired unit takes
   no new revision (`RENTAL_UNIT_RETIRED`, 409); an unknown key, a value of the wrong type or a missing required
   value is `RENTAL_VALUE_INVALID` (422). The database rechecks all of it.
3. **Revisions**: a stale `expected_revision` is `RENTAL_REVISION_CONFLICT` (409); the first save uses 0. Each save
   keeps its Idempotency-Key (scopes `rental.class` and `rental.unit`).
4. **Rules as before.** `rental.read` to read, `rental.manage` to write; module off refuses writes
   (`MODULE_NOT_READY` before acceptance, `MODULE_DISABLED` in the database) and nothing is written; another company
   sees nothing; direct SQL updates of insert-only rows and deletes are refused.

## Acceptance of R1 — PASS 2026-11-03 (code `15a884d`, [evidence](evidence/2026-11-03-r1-rental-catalog/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R1-01 | The module is registered implemented and cannot be enabled; with it off every write is refused and nothing is written; reads answer | PASS |
| R1-02 | A class is replaced whole with its revision and its full attribute set per revision; a taken or changed code, a stale revision and a bad attribute set are refused | PASS |
| R1-03 | A unit is replaced whole with its revision and typed values; unknown key, wrong type, missing required, taken identifier, changed class or identifier and a retired unit are refused | PASS |
| R1-04 | Owners and managers read and write; front desk is refused; a branch-limited manager sees and writes only its branch's units and writes no class; another company sees nothing | PASS |
| R1-05 | The database refuses forged values, attribute rows outside their revision, updates of insert-only rows and deletes | PASS |
| R1-06 | 0095 -> 0096 keeps every row; the full suite stays green | PASS |

## Not in R1

Bookings (R2), assignment and occupancy (R3), rates and agreements (R4), security (R5), inspections (R6),
settlement (R7), screens (R8).
