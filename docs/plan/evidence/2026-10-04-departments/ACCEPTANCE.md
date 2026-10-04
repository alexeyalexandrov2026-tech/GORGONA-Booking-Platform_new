# Department drafts — acceptance evidence

Date: 2026-10-04. Branch: `codex/company-departments`.
Base: `b8647897cfa653e39f2e3188dbb9ad23c13e13fa`, selected-company fix plus handoff.
PR #3's code SHA `951708a` passed CI: 482 passed, one optional skip; both push
and PR CI of its documentation SHA `b864789` also completed successfully.
No pull request was merged, and the owner's foundation checkout is preserved.

## Implemented

Company-owned department identities and append-only draft versions under
[ADR-0017](../../../adr/0017-company-department-drafts.md), migration 0012.
Optional parent/branch/legal-entity links are constrained to the same company.
The current hierarchy cannot cycle; version inserts serialize through the existing
business-structure lock, including direct database inserts. Internal codes do not
change, and identical names do not imply duplicate identities.

GET collection/detail/history and PUT commands reuse existing business permissions,
transactions, idempotency, audit and typed versioned contracts. Forced RLS and four
restrictive policies deny branch/delegated reads and writes. The guard now checks
49 access-boundary definitions. No older migration was edited.

The business page supports create/edit, links, paginated choices, history, lost
response replay and stale-edit recovery. Publication and employee access are
unaffected by structural links.

## Observed checks

| Check | Exact observed outcome |
|---|---|
| Initial three workflow tests before implementation | Expected FAIL: 3 failed, 2.85 s, exit 1; endpoints returned 404 |
| Initial PostgreSQL + location tests after restoring only dropped policies | PASS: 23 passed, 8.02 s, exit 0 |
| Final focused contracts, PostgreSQL, location security and browser harness | PASS: 44 passed, 45.65 s, exit 0 |
| Reviewer snapshot regression before isolation-level protection | Expected FAIL: 1 failed, 13 deselected, 2.43 s; both stale Repeatable Read transactions committed |
| Department suite after snapshot protection | PASS: 15 passed, 6.25 s, exit 0 |
| Web typecheck, lint and build | PASS, exit 0; 14 exported pages |
| Web format check and unit tests | PASS, exit 0; 20 passed, 836 ms |
| Ruff format/check and strict mypy | PASS, exit 0; 140 source files |
| Final complete API suite with required PostgreSQL 18.6/browser after snapshot protection | PASS: 512 passed, 4 skipped, 215.30 s, exit 0 |

Local skips are the three container gates and the optional external-site gate.
CI of the new department code must independently execute the container gates.
Independent read-only review verified the final isolation-level fix and found no
further substantial issue; the reviewer did not run tests.

The real browser harness uses test-only FAKE OIDC with code/PKCE and real loopback
API/PostgreSQL. Desktop and mobile create a root, lose a committed response,
replay the same key and ID, edit, read history, detect a competing revision,
reload, create a child/branch link and reject a root-to-child cycle. Direct SQL
asserts four root versions and one child version per viewport, with no departments
in the other company. Axe WCAG 2 A/AA and horizontal-overflow checks pass in
the exercised browser states.

Tests also verify a manager belonging to both companies cannot link their foreign
parent or legal entity; rejected commands leave no partial identity, version or
receipt. Branch/delegated scopes deny data, and revoked membership cannot replay
an earlier command. Intentional changes to each of four restrictive policies
return 503; restoring it returns ready.

An early run exposed a test restoration bug: dropping the location function only
removed branch policies, while restoration attempted to recreate delegation
policies too (DuplicateObject). The restore now selects only the dropped branch
section; subsequent complete focused runs passed. A separate asynchronous test
context-manager error was fixed; it was not an application success.

Independent review identified a fixed-snapshot hazard. Two Repeatable Read
transactions pinned snapshots before either write and both committed opposite
parent links. A new regression reproduced it. The trigger now accepts only
READ COMMITTED, and the service converts the database constraint to an unavailable
error; the tested failing command leaves no identity, version or receipt.
See the [PostgreSQL 18 isolation documentation](https://www.postgresql.org/docs/18/transaction-iso.html).

## Unverified boundaries

These are technical draft records. Group consent/reporting, staff assignments,
multiple branches per department, configuration publication and shared occupancy
are still planned. No real IdP/provider, staging, production migration, load,
recovery or industry pilot was exercised. Full dependency audit retains the
development ESLint/braces finding recorded in the previous package.
