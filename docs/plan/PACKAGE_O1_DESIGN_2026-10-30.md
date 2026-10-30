# Package O, slice O1 — construction module, projects and estimate versions (2026-10-30)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md). Architecture:
[ADR-0035](../adr/0035-construction-projects-and-estimates.md). Branch `codex/package-o1-estimates` from the plan
commit `21f1a12`. Same process as packages L, M and N: failing tests first, one executor, one disposable
PostgreSQL 18 cluster per run, gates, a source-bound record, code and docs commits, push for CI without a PR.

## Scope

- Module `construction` registered (`implemented`, not enableable), depending on `counterparties` and
  `finance_documents`; registry version 5. Permissions `construction.read`, `construction.manage`,
  `construction.approve` for owners and managers; permissions version 11; nothing delegable.
- Migration **0087**: `construction_projects`, `construction_estimate_versions`, `construction_estimate_lines`;
  RLS, branch scope by the project's location, the module gate on project and version inserts, lines and
  versions insert-only (only the one-time proposal stamp may be set).
- Routes under `/v1/businesses/{business_id}/construction`:
  - `PUT/GET projects/{project_id}`, `GET projects` (50 a page, `after` cursor);
  - `POST projects/{project_id}/estimates` (next version), `GET projects/{project_id}/estimates`,
    `GET projects/{project_id}/estimates/{version}`;
  - `POST projects/{project_id}/estimates/{version}/proposal`.

## Decisions (O1)

1. Project ids are chosen by the client; a replacement needs the expected revision (0 to create); a stale one is
   `CONSTRUCTION_REVISION_CONFLICT`; a taken number is `CONSTRUCTION_NUMBER_TAKEN`; an unknown customer or
   branch is `INVALID_REFERENCE`; an unknown time zone is 422 `CONSTRUCTION_TIME_ZONE_UNKNOWN`.
2. Currency: three capital letters; after the first estimate version it cannot change
   (`CONSTRUCTION_CURRENCY_FIXED`).
3. An estimate save carries `based_on` (the latest version the client read, 0 for the first) and 1 to 500
   lines; quantity > 0 with at most 4 decimals and at most 999 999 999.9999; unit 1–16 characters; unit cost
   and unit price 0 to 10^12 minor units; phase label 1–64 characters; description 1–500 characters. A
   material id must name a STOCK-01 material of the business (`INVALID_REFERENCE`).
4. The view of a version lists its lines with derived `cost_minor` and `price_minor` (half up) and the
   version's `cost_total_minor`, `price_total_minor`, `proposed_at`; the list of versions returns the same
   without lines.
5. Proposal: only the latest version (`CONSTRUCTION_ESTIMATE_STALE` otherwise); a repeat of the proposal of
   the same version returns it unchanged; the database refuses any other change of a version or line.
6. Commands are idempotent with `Idempotency-Key` (same key and body: the stored result; other body:
   `IDEMPOTENCY_KEY_REUSED`).
7. Without the module enabled every write is `MODULE_DISABLED` and writes nothing; reads continue. With the
   module not accepted every write is `MODULE_NOT_READY`.

## Acceptance of O1 (all NOT TESTED)

| id | Requirement |
|---|---|
| O1-01 | The module is listed, `implemented`, not enableable, depends on counterparties and finance documents; writes refused `MODULE_NOT_READY`; reads empty |
| O1-02 | A project is saved and replaced with its revision; stale revision, taken number, unknown customer, unknown time zone refused |
| O1-03 | Estimate versions are insert-only: v1, then v2 on base 1; a stale base refused; old versions unchanged; totals derived half up |
| O1-04 | A proposal is stamped once on the latest version; an older version cannot be proposed; a later version may follow; direct SQL updates and deletes of lines and versions refused |
| O1-05 | The currency is fixed once an estimate exists |
| O1-06 | Module off: writes `MODULE_DISABLED`, nothing written; another company sees nothing; a branch-limited member sees only its branch's projects |
| O1-07 | Two racing saves on one base leave one version and one `CONSTRUCTION_ESTIMATE_STALE` after an observed `pg_locks` wait |
| O1-08 | 0086 -> 0087 keeps every row; the full suite stays green |
