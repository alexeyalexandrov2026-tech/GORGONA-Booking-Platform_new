# GORGONA department acceptance — 2026-10-04

CORE-03 step A is technically verified on commit `5b3c00b11e2bb2e844a3183bbd840ca36d764895`, branch `codex/universal-business-foundation`, repository `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. Later documentation commits do not extend this acceptance to changed application code.

The business owner can create departments inside the existing business, link an own parent department, legal entity and location, archive them, read saved history and retry an uncertain save without creating a duplicate. Cycles, foreign links and premature archiving are rejected. Employee assignment, access rights, groups and delegation are outside this increment. See [ADR-0016](../../../adr/0016-tenant-owned-departments.md).

## Direct evidence

| Check | Exact outcome |
|---|---|
| Full GitHub PR CI | **PASS**: [run 37235035509](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37235035509), job `111532331832`, exact commit above; every step succeeded, including web build/unit, PostgreSQL 18, production image, Ruff, mypy and pytest |
| GitHub push CI | **PASS**: [run 37235032875](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37235032875), same commit |
| CI test counts | Not retrieved: job logs require authentication and `gh` was unavailable. Step conclusions were read through the public GitHub API |
| Local full Python suite, PostgreSQL 18.6, required browsers | **445 passed, 4 skipped, 215.10 s**. Skips: three container gates (no Docker locally; covered by CI) and the optional external tenant-site gate, which is not a passed check |
| Local focused PostgreSQL | **PASS: 69** — departments, legal entities, location access, roles/migrations, identity schema, tenant isolation |
| Management browser harnesses | **PASS: 2** Python harness tests; Playwright 7 passed / 1 intentional skip (company-wide), 2 passed (branch-limited); desktop and mobile |
| Saved browser results | SQL asserts per project an OPS department at revision 3 and a TEAM department at revision 2 under OPS with a location, both archived; no department rows in the other tenant |
| Browser failure handling | Lost response after real persistence keeps the same ID/key; a cycle and premature archive are rejected without locking the form; a competing revision gives 409, preserves the edit and requires explicit reload; Axe WCAG 2 A/AA and no horizontal overflow |
| API unit / static | API unit **218**; Ruff and strict mypy PASS; web typecheck, ESLint, Prettier, unit **16**, 14-page build PASS |

Local runs used a separate disposable cluster on 127.0.0.1:51455 created from the official EDB PostgreSQL 18.6 archive (SHA256 `fbe23da234ee31547bf8a36d29dfd81e82b849df2d2b78d2eecb43d360252f8c`); it was stopped afterwards.

Tests and source: [contracts](../../../../api/tests/unit/test_department_contracts.py), [PostgreSQL/API](../../../../api/tests/integration/test_departments.py), [management browser](../../../../web/tests/management.spec.ts), [harness/SQL assertions](../../../../api/tests/integration/test_management_browser.py), [response boundaries](../../../../web/tests/management-contracts.spec.ts), [migration 0011](../../../../api/src/gorgona_booking/db/migrations/0011_departments.sql).

## Boundaries

No independent reviewer examined this step. Azure, staging, production migration, live providers, load and industry pilots were not verified. CORE-03 remains partial until delegation (step B) and the group model (step C) are accepted.
