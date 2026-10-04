# GORGONA delegation between businesses — technical acceptance, 2026-10-04

The stage-1 increment of [ADR-0016](../../../adr/0016-limited-cross-business-delegation.md) is implemented on branch `claude/keen-mayer-lg9ift`, built on `codex/universal-business-foundation` at `eaa62339cf82ea69b96f2e8ec346ede585729f02`, in repository `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. The results below were produced in a Linux cloud container on the final tree before commit. The application change was published as `bd1a138a11ebbe506010c243a5a02d9989bc1b52`; its GitHub CI run is the authoritative result for container gates and the pinned browser build. Later documentation commits do not extend this acceptance to changed application code.

An owner business can grant another, independent business time-limited access to its operational booking work, optionally for one location. The serving business designates its own employees. A designated employee books for the owner inside the grant; the rows stay in the owner's tenant and every delegated request is audited there. Revocation, expiry and changes on either side apply to the next request. Groups, departments, offline synchronization and transport workflows are outside this increment.

## Direct evidence

| Check | Exact outcome |
|---|---|
| GitHub push CI, exact commit `bd1a138a11ebbe506010c243a5a02d9989bc1b52` | **PASS**: [run 37212099717](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37212099717), job `111465192442`: **474 passed, 1 skipped, 118.32 s**, with required PostgreSQL, browser and container gates. The skip is the optional external tenant-site gate |
| Baseline, unchanged tree `eaa6233`, same environment | **410 passed, 4 skipped, 75.11 s, exit 0** |
| Full API suite, final tree, PostgreSQL 18.4, browsers required | **471 passed, 4 skipped, 112.25 s, exit 0** |
| Skips | Three container gates (`GBA_REQUIRE_CONTAINER=1`; this container has no Docker daemon) and the optional external tenant-site gate. Skips are not passes |
| New delegation tests | **61 PASS**: 33 contract/permission unit, 26 PostgreSQL/API integration, 2 browser harness scenarios |
| Browser: owner of two businesses | PASS desktop and mobile: create grant (dependencies auto-checked), designate an employee of the serving business, see the designated user ID, revoke with confirmation, view the preserved previous version. SQL: two grants, each `active → revoked`; two active designations; the serving business owns no grant |
| Browser: designated employee | PASS desktop and mobile: delegated business in the selector, explanatory notice, navigation limited to Overview/Calendar/Bookings/Clients, company endpoints 403, calendar create → reschedule → cancel. SQL: four cancelled bookings in the owner business with `created_by = delegate:{user}@{serving}/grant:{grant}`, booking events with the same actor, `delegation.access` audit rows, none in the serving business. After revocation the next API request is 403 |
| Accessibility and viewport | Axe WCAG 2 A/AA: no violations in the tested states; no horizontal overflow at 1280 and 390 px |
| Web unit / static | **16 PASS** (11 existing, 5 new); TypeScript, ESLint, Prettier and the 14-page build PASS |
| Python static | Ruff check/format and strict mypy PASS, **134 files** |
| Schema guard | 45 definitions. Intact schema ready; six damage cases (widened grantee policy, weakened deny policy, extra policy on a delegation table, replaced scope function, `NO FORCE RLS`, widened users policy) unavailable; restored ready |
| Mutation checks | Each deliberate break made its targeted test fail; source restored: no delegation GUC, serving membership not required, no shared grant lock, designation not locked, term ignored, suspended owner membership ignored, location/permission/state not re-checked after a concurrent revision, guard skipped for delegated requests |

The concurrency tests hold a delegated transaction open and show that grant revocation, designation removal and membership revocation wait for it and deny the next request. A second test commits a narrower revision while a delegated request waits for the grant lock; the request is denied for a location limit, a removed permission and a revocation.

Tests and source: [contracts](../../../../api/tests/unit/test_delegation_contracts.py), [PostgreSQL/API](../../../../api/tests/integration/test_delegations.py), [browser harness](../../../../api/tests/integration/test_delegation_browser.py), [owner browser flow](../../../../web/tests/delegation-management.spec.ts), [employee browser flow](../../../../web/tests/delegation-workspace.spec.ts), [response boundaries](../../../../web/tests/delegation-contracts.spec.ts), [migration 0011](../../../../api/src/gorgona_booking/db/migrations/0011_delegation_grants.sql), [authorization](../../../../api/src/gorgona_booking/tenancy/authorization.py), [guard](../../../../api/src/gorgona_booking/db/schema_guard.py).

Screenshots (FAKE data only): [owner, desktop](delegation-management-1280.png), [owner, mobile](delegation-management-390.png), [employee, desktop](delegation-workspace-1280.png), [employee, mobile](delegation-workspace-390.png).

## Environment of the local run

- PostgreSQL **18.4** server binaries from the npm package `@embedded-postgres/linux-x64@18.4.0-beta.17` (the PostgreSQL apt repository was blocked by the network policy), disposable cluster on loopback, `max_connections=250`; the fixture created and dropped one `gba_test_*` database per session.
- Python **3.14.8**, dependencies from the locked `uv.lock`; Node **24.21.0** from nodejs.org with a verified checksum.
- Playwright 1.63 expects Chromium revision 1243; only revision 1194 was preinstalled and the Playwright CDN was blocked, so a local path shim pointed Playwright at 1194. CI installs the matching browser.
- No application dependency was added. Only disposable databases were migrated.

## Boundaries

Not verified here: container gates (CI runs them), HawkScan DAST (no Docker daemon or API key in this container), a real identity provider, providers, Azure/staging, production migration, load targets, recovery, industry pilots. CORE-03 and TMS-02 remain partial: company groups and consolidated reports, departments, multiple data areas per grant, owner-visible delegate names, offline draft synchronization and transport workflows are open.

A pre-existing defect was found while reviewing tenant reads: `api/setup.py` reads `booking_state` from `gba.tenants` without a tenant filter, so a person who belongs to two businesses can see or be governed by the other business's state. A probe reproduced it on PostgreSQL 18 (readiness of a not-live business answered `live`). It is unrelated to delegation, unchanged here and queued as separate work.
