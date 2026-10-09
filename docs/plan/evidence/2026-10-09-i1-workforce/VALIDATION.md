# Package I, slice I1 — local evidence, 2026-10-09

PASS: implementation and required full local validation complete. This is slice
evidence, not WORK-01 acceptance or production readiness.

## Repository and boundaries

- Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
- Checkout: C:/Users/alexa/Documents/ChatGPT/gorgona-package-i.
- Branch: codex/package-i1-workforce; base I0: 14190730db62680e743f7bf34371f5bff12ff774.
- Initial tree clean; unrelated primary checkout preserved.
- Read-only live checks: remote H acceptance head 9ef373489f1e6c9bb37cc8b2929143484afdc461;
  no published I branch from git ls-remote; no I0 PR from the GitHub connector.
  No PR-triggered workflow runs returned for I0 (not a claim about all workflow
  types). PR22 still open/draft, head319f144.
- No push, PR, merge, history rewrite, production migration, deployment, Azure,
  provider, credentials or actual money operation. No CodeRabbit.
- Only forward0032 is added; migrations0001–0031 are unchanged. WORK-01 and CORE-04
  readiness and the production workforce module remain planned/closed.

## Implementation and reuse

Membership-specific immutable profiles share one tenant/user staff resource
through staff_resource_owners, including revoke/re-invite. This is resource
ownership, not another person record. Skills have immutable catalogue versions
and dated grant/revoke events. Single-seat shifts have immutable draft,
published and cancelled versions and explicit assignment history.

The version trigger creates the assignment and its shift allocation in the
existing resource_allocations table, releasing the prior allocation in the same
transaction. Existing GiST exclusion remains authoritative. API and SQL take
resource locks in id order, then the shift row. Profile creation locks the target
membership FOR SHARE against concurrent revoke/home moves.

Version-one API contracts; permission-map6: workforce.self/read/manage, not
delegable and unavailable to platform support. Only company-wide managers edit
the company skill catalogue; branch managers manage staff skills and shifts in
scope. Existing business claim/complete/audit helpers are reused. Receipts contain
ids/revisions and audits exclude staff names/free text. Fixtures alone override
readiness.

The package guard covers eight tables, forced tenant/branch RLS, columns,
defaults/grants, keys/FKs/CHECKs, complete trigger metadata and exact function
bodies, plus the changed shared kinds/source CHECKs and allocation trigger.
PG18 deparse approvals are pinned from reviewed packaged SQL compiled on a NEW
disposable database; runtime never learns approval from its target. Literals
and quoted identifiers are preserved; function prosrc compares exactly.

## Required I1 acceptance mapping

| Requirement | Direct test evidence |
|---|---|
| Atomic profile/resource; version/assignment/occupancy/audit/receipt; replay and rollback | test_workforce.py atomic/idempotent, rollback, revision/cancellation tests |
| One person, including cross-branch and re-invite | test_workforce_guards.py I-02 API/rawSQL and stable-resource reinvite |
| Observed pg_locks waiting | Two advisory waiters in I-02; transaction-id waiter in profile/home race |
| Effective skills and SQL repetition | Required/future/revoked tests and rawSQL GBW02 |
| Tenant/branch/self/support/delegation boundaries | Branch/own-cross-branch tests, foreign/support denial, permissions unit test |
| Immutable history | UPDATE/DELETE rejection for all new tables; old versions readable and old allocations released |
| Module disabled / readiness revoked | API refusal, SQL GBM01, history readable |
| All I0 staff boundaries | Customer/management lookalike, management POST, service/holds/reservations, list/count/setup, standalone creation refusal; detailed mapping below |
| SQL staff-booking/reservation and artist-shift refusal | DirectSQL source-boundary tests |
| Booking fingerprint and concurrency regression | Fingerprint unchanged; artist booking during an overlapping staff shift succeeds |
| Fail-closed schema damage | Policy/function/trigger/WHEN/default/CHECK/quoted-helper/shared-literal/source-kind mutation ->503 |
| Nonempty forward upgrade | Private0031 ->0032 preserves every old row digest and checksum; repeat is no-op |
| F/resource-kind/location regression | Focused tests, then full project suite |

Artist/chair/room behavior remains. Web kind types and source remain unchanged;
staff is excluded by the legacy list boundary. No workforce screens in I1.

Every row of the I0 inventory's required-I1 column has a direct check:

| I0 boundary | Test in this checkout |
|---|---|
| Customer artists, availability and hold | test_resource_kind_boundaries.py::test_staff_lookalike_never_enters_customer_or_management_booking |
| Management availability and POST booking | Same test, including an explicit POST and zero allocations |
| BookingService and local/test/ci holds | test_workforce.py::test_staff_resource_refused_by_service_holds_and_reservations |
| Reservation service, SQL staff reservation/booking and artist shift | Same service test; test_workforce_guards.py::test_sql_booking_reservation_staff_and_shift_artist_boundaries |
| Legacy staff list and overview count | test_workforce.py::test_staff_resource_is_absent_from_booking_setup_and_fingerprint; existing chair/room test retained |
| Hours, services and rename | Same test, GET/PUT schedule, PUT services and PATCH name each return 404 |
| Legacy POST staff stays three kinds; SQL kind extension requires a profile | test_resource_kind_boundaries.py::test_the_staff_api_and_the_schema_know_three_resource_kinds; workforce atomic profile test |
| Shared allocation function and approved source text | Packaged schema test and damaged-schema mutations, including shared literal/source-kind changes |
| Resource branch policies unchanged | Location-access restoration/regression; I-02 across branches; own-schedule permission test |
| Booking setup fingerprint | test_workforce.py::test_staff_resource_is_absent_from_booking_setup_and_fingerprint |
| Booking readiness stays artist-only | test_workforce.py::test_staff_resource_does_not_change_booking_readiness, full DB snapshot equal before/after |
| Web kind union stays three kinds | No web source diff; legacy list excludes staff; web typecheck/build and browser suite |

## Environment and commands

Python3.14 environment:
C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv.
PYTHONPATH points to THIS checkout's api/src and api. Own PostgreSQL18.6 cluster
i1-root-20261009, loopback51478, max_connections400. Owner/shared clusters were
not reused. DSNs are not recorded. PostgreSQL fixture suites run sequentially.
GBA_REQUIRE_POSTGRES=1 and GBA_REQUIRE_BROWSER=1.

From api:

    python -m ruff check .
    python -m ruff format --check .
    python -m mypy
    python -m pytest -q tests/integration/test_workforce.py tests/integration/test_workforce_guards.py tests/integration/test_workforce_upgrade.py tests/integration/test_resource_kind_boundaries.py tests/integration/test_location_access.py tests/unit/test_workforce_contracts.py -p no:cacheprovider --basetemp <unique directory> --tb=short
    python -m pytest -q -p no:cacheprovider --basetemp <unique directory> --tb=short

- Static gates: PASS,239 files.
- Final focused I1/resource-kind/location/contracts: PASS,81 passed/45.49s.
- Prior focused snapshot: PASS,80 passed/43.41s.
- Earlier focused plus all unit tests: PASS,600 passed/65.17s.
- Final full project suite: PASS, 1301 passed / 4 skipped / 772.12s, exit 0.
  PostgreSQL and browser gates required. Three container tests skipped because
  GBA_REQUIRE_CONTAINER was unset; one external-site test skipped because
  GBA_REQUIRE_TENANT_SITE was unset. These boundaries remain NOT TESTED.

Exact late commands, from the repository root, with the runner setting the api
working directory and required PostgreSQL/browser gates:

    & 'C:\Users\alexa\AppData\Local\Temp\gorgona-i1-check.ps1' -m pytest -q -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i1-full-local-01 --tb=short
    & 'C:\Users\alexa\AppData\Local\Temp\gorgona-i1-check.ps1' -m pytest -q tests/integration/test_provider_admission_upgrade.py tests/integration/test_workforce_upgrade.py tests/integration/test_resource_occupancy.py::test_migration_copies_and_reconciles_existing_booking_allocations -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i1-disk-recovery --tb=short
    & 'C:\Users\alexa\AppData\Local\Temp\gorgona-i1-check.ps1' C:/Users/alexa/AppData/Local/Temp/i1-run-boundary-mutants.py
    & 'C:\Users\alexa\AppData\Local\Temp\gorgona-i1-check.ps1' -m pytest -q tests/integration/test_workforce.py tests/integration/test_workforce_guards.py tests/integration/test_workforce_upgrade.py tests/integration/test_resource_kind_boundaries.py tests/integration/test_location_access.py tests/unit/test_workforce_contracts.py -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i1-final-focused --tb=short
    & 'C:\Users\alexa\AppData\Local\Temp\gorgona-i1-check.ps1' -m pytest -q -p no:cacheprovider --basetemp C:/Users/alexa/AppData/Local/Temp/i1-full-local-03 --tb=short

The runner uses the Python environment named above and this checkout's source.
The mutation helper only changes Python runtime objects for the two named tests:
it removes the artist-only count from readiness._SNAPSHOT and replaces the
management _ensure_available with a no-op. Packaged source is never changed.

From web, Node24, unchanged lockfile:
npm ci, npm run typecheck, lint, format:check, test:unit, build:
PASS;94 unit tests/2.9s. No dependency introduced.

Observed real catalog execute count:76 before batching;5 after. Lists use bounded
keyset pagination and bulk reads. No production latency/load improvement claimed.

## Red evidence and corrections

- Initial feature tests:3 failed/3.86s, missing routes.
- Initial boundary extension:4 failed/10 passed/11.02s. Fingerprint, typed service
  refusal and orphan shift fixed; the fourth failure was a test column typo.
- Independent findings: WHEN(false), same-user resource split, quoted helper and
  case-sensitive expression collision; later home-creation race, scoped hidden
  profile move, literal whitespace, unreadable SQL dates/arrays and overflow.
  Concrete DB bypasses had red regressions before correction. New typed inputs
  and SQL repeat bounds; exact-source guard rejects mutation.
- Catalog-count red showed76 vs5, then green.
- Source-kind removal and shared shift-literal whitespace each returned200 before
  the fix instead of503; corrected regressions pass.
- Broad attempt:2 failed/597 passed/60.85s: historical COPY could not represent
  new staff allocations and an old assertion expected permission5. Historical
  upgrade fixtures now stop at their own migration target and exclude rows
  unrepresentable by that schema; version assertion is6.
- A cleanup restored the prior interval CHECK after new date bounds, causing
  20 failed/59 passed/40.81s. Cleanup now restores the exact previously approved
  baseline definition; guard approvals were not relaxed. Corrected focused run
  is recorded above.
- First full run: FAIL, 1297 passed / 1 failed / 3 errors / 4 skipped, 753.73s.
  Every failure/error was DiskFull during temporary database creation or cleanup
  checkpoint. Drive C had zero free bytes. The owned cluster was 224 MB when
  checked afterward; free space recovered to about 2.1 GB without deleting owner
  files. An orphan test database was dropped through this owned PostgreSQL
  instance. All three affected tests then passed: 3 passed / 8.17s.
- Full attempt i1-full-local-02 was deliberately interrupted to add direct
  management POST and booking-readiness coverage. It has no full PASS outcome.
  Its orphan database was dropped only in the owned test cluster.
- These two added checks caught runtime mutations: 2 failed / 4.71s. Removing
  readiness's artist filter changed active_artists from 2 to 3; bypassing the
  management availability check reached the SQL staff-allocation rejection.
  Without mutation, final focused validation passed 81 tests / 45.49s; the final
  full run passed 1301 tests / 4 skipped / 772.12s. Earlier failures stay FAIL.

## Deliberate limits and open gates

- I2 changes/consents/swaps, I3 timesheets, I4 screens and WORK-01 acceptance remain.
- Own-schedule route broadens only branch GUC after workforce.self authorization,
  always filtering by the trusted user's id in SQL. General read/write scope
  remains restricted.
- Existing staff home transfer requires a separate audited lifecycle. Silent
  membership moves and re-invite/profile in another home fail closed; scoped SQL
  cannot move membership home. Same-home re-invite reuses the resource/history.
- User dates use UTC bounds [0002-01-01,9999-01-01), with timezone padding for
  Python/Psycopg representability; this is not the entire PG timestamp domain.
  Duration subtraction avoids overflow at max datetime.
- Dependency audit: FAIL. npm audit --omit=dev --json reports2 high dependency
  nodes (next,source-map-js); full npm tree reports7. Existing output:export and
  Docker static-out copy exclude a Node/Next server from this deployment runtime.
  No remotePatterns configured; the image-optimizer advisory states this case is
  unaffected. This bounds exposure, not closure of dependency maintenance.
  No audit fix/dependency changes made in I1.
- New-branch CI, Docker/image execution, production data/load/cloud, retention/
  privacy and real-company acceptance: NOT TESTED.
- FIN-03 acceptance-commit review is a separate job.
- Copy-helper root src/tests duplicates remain ONLY in the review checkout:
  automated approval rejected removal, reason blocked by policy. Canonical api
  snapshot is SHA256-verified; reviewer excludes duplicates. Executor has none.

Sources: PostgreSQL18 [RLS](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)
and [constraints](https://www.postgresql.org/docs/18/ddl-constraints.html);
[Psycopg date limits](https://www.psycopg.org/psycopg3/docs/basic/adapt.html#dates-and-times-limits-in-python);
[Next advisory](https://github.com/advisories/GHSA-cjq9-62q9-8jv4);
[source-map-js advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
Tools: PowerShell/Git/Python, real PG, GitHub read connector, official docs,
Ruff/mypy/pytest/Playwright/Node; evidence-engineering skill and a separate
read-only reviewer branch/checkout.

The final validated API/source snapshot is in [SOURCE_SHA256.md](SOURCE_SHA256.md).
Those are executor byte hashes before Git line-ending normalization. Before the
local commit, all 21 staged API blobs were also checked against the validated
files after CRLF-to-LF normalization: PASS. No source mutation after validation.
Final local branch HEAD is read from Git; it is unpublished and has no I1 CI.
The owned test cluster was stopped after validation. Exact lifecycle commands:

    & 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\postgres-18.6\pgsql\bin\pg_ctl.exe' -D 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\i1-root-20261009' -m fast -w stop
    & 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\postgres-18.6\pgsql\bin\pg_ctl.exe' -D 'C:\Users\alexa\AppData\Local\GorgonaBookingTests\i1-root-20261009' status

PASS: server stopped; status says no server running. Cluster data retained.
