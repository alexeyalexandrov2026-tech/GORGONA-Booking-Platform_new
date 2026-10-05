# Development

## Counterparties (Package E1, 2026-10-05)

Migration 0015 adds five FORCE-RLS append-only tables for cards, version contacts,
duplicate decisions and booking-link events. Runtime has minimal insert/select
grants; immutable identity/history and decision/version coupling also hold in SQL.
Company-wide owner/manager only; permission map v4. No branch, delegation or
platform-support access. Guard: 34 definitions plus the booking gate and five
optional-module gates; damaged executable metadata fails readiness. Gate functions
are VOLATILE so a read after the configuration lock observes a committed disable.

API base: `/v1/businesses/{business_id}/counterparties`. GET list supports q/state/
after/limit; PUT `{counterparty_id}` uses Idempotency-Key and expected_revision.
GET card supports revision; `versions` uses before/limit. `merged-from` is the
current relationship read and deliberately excluded from immutable card views.
POST `match-check` takes potential identifiers in the body. Per-card endpoints:
`duplicates`, `match-decisions` (GET/POST), `booking-candidates`, `bookings`,
`booking-links` (GET/POST). Paged reads expose cursors; web validates schema and IDs.

Matching is advisory. Merge/separate preserve source data and require human
confirmation. Decisions couple to exactly one version in the same transaction;
staged cycles/chains and duplicate decisions for one version are refused. Manual
links recheck normalized email/phone against the current card/contacts; booking
snapshots are never rewritten. Read/history/replay work when disabled, new writes
do not. Company publication and writes share the existing configuration lock.

Counterparties is technically_verified after exact implementation CI. Registry
version stays 1. Initial code CI proved refusal while only implemented; acceptance
API/browser fixtures now use the real registry with explicit profile/draft/
validation/publication. module_support.py remains a test-only helper for unaccepted
module development; it is not used by current accepted E1 fixtures. Baseline remains booking-only;
no module is automatically enabled for an existing business.

Focused: `tests/integration/test_counterparties.py`,
`tests/unit/test_counterparty_contracts.py`, `test_configurations.py`,
`test_location_access.py` and `test_delegation_contracts.py`. Browser harness:
`test_counterparty_browser.py`, fresh web export, real OIDC/PKCE test IdP, HTTP and
PostgreSQL; invokes `npm run test:management:counterparties` on desktop/mobile.
New web contract cases are included in `npm run test:unit` (47 total).
Shared config fixtures: `configuration_support.py`, test-only `module_support.py`.
See [E1 acceptance](plan/evidence/2026-10-05-counterparties/ACCEPTANCE.md) and
[handoff](plan/NEXT_AGENT_PACKAGE_E1_2026-10-05.md) for exact results/limitations.

## Selected-company isolation (Package E0)

Company-specific reads of tenants/memberships/tenant_hosts must include the
authorized business predicate even when RLS discovery policies expose the user's
other companies. Keep intentional discovery paths in the conservative scanner
allowlist; the scanner is a linter, not a SQL parser or runtime authorization.
Readiness web contracts use items[{fact,status,detail}], not missing; PUT policies,
business-hours and facts return the typed Readiness view; GET readiness is registered.
Focused: test_cross_company_reads.py, test_invitations_api.py, test_onboarding.py,
test_cross_tenant_queries.py and the readiness test in management-contracts.spec.ts.
See [acceptance](plan/evidence/2026-10-04-isolation-audit/ACCEPTANCE.md) and
[current handoff](plan/NEXT_AGENT_AUDITED_E0_2026-10-04.md).

**Known load-harness defect:** the existing tool below can report PASS after 4xx
confirm failures/missing requested bookings, select overlapping slots and combine
different phase windows. It is unchanged; do not use its verdict for OPS-02 until
the saved regressions and measurement repairs are implemented. Actual workload,
errors and latency thresholds require separate verified evidence.


## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (installs CPython 3.14 on demand).
- A PostgreSQL 18 server for integration tests. The simplest route is Docker via `infra/local/compose.yaml`; any PostgreSQL 18 reachable with a superuser DSN works. The application itself never needs Docker.
- Node.js 24 for the M3 customer export and Chromium browser checks.

## Customer booking (M3)

```bash
cd web
npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
npx playwright install chromium
```

The build exports `web/out/`. Set `GBA_CUSTOMER_WEB_DIR` to its absolute path when starting the existing API with its **runtime-role** DSN, then visit `/book/` on the salon's configured host. API routes are registered before static files. Unknown, suspended and not-live hosts receive the unchanged safe 404 from the bootstrap API; the web shows an unavailable state. No tenant ID URL parameter or header is required or trusted.

The real browser gate creates disposable FAKE salons and a throwaway PostgreSQL 18 database. It does not modify KA Nails or the persistent development database:

```bash
cd api
GBA_REQUIRE_POSTGRES=1 GBA_REQUIRE_BROWSER=1 uv run --env-file ../.env pytest -q
```

PowerShell: set `$env:GBA_REQUIRE_POSTGRES='1'` and `$env:GBA_REQUIRE_BROWSER='1'`, then run the same `uv` command. Use your actual private env-file path; never put credentials in the repository. Browser tests launch the existing FastAPI app on a random loopback port, execute `web/tests/booking.spec.ts`, verify confirmed records via SQL, stop the server and drop the test database. Without `GBA_REQUIRE_BROWSER=1` the browser test is explicitly BLOCKED/skipped; this is not an M3 acceptance run.

For a live test fixture, location timezone/hours, artist hours, artist/service eligibility and versioned policies are explicit FAKE values in `tests/integration/customer_support.py`. Consult ADR-0011 for the customer policy contract. Do not transplant those values into KA Nails. Required deposits are unsupported and fail closed. `npm run dev` alone is not an integrated tenant environment; the acceptance path uses the static export and API on the same Host.

Tenant assets are owned by the independent site repository, not bundled as a platform default. KA-nails verifies the supplied logo bytes with SHA-256 in its acceptance suite. A published logo reference can use `/assets/ka-nails-logo.png`; an optional palette reference can use a validated `#RRGGBB` accent. Branding references are supplied explicitly and never selected by a hard-coded tenant ID.

## Universal business foundation (2026-10-04)

The governing scope is `plan/GORGONA_MASTER_PLAN.md`; actual acceptance is in
`plan/GORGONA_IMPLEMENTATION_STATUS.md`. The first package adds business profile
**drafts**, without activating industry workflows or copying salon data.
`business_id`, existing `tenant_id` and legacy `salon_id` refer to the same owner.

Authenticated routes:

| Route | Permission | Behavior |
|---|---|---|
| `GET /v1/businesses/{id}` | `business.read` | Current draft, business name and existing locations |
| `GET /v1/businesses/{id}/industry-catalog` | `business.read` | Versioned catalog: 39 stable industries and separate business formats |
| `PUT /v1/businesses/{id}/profile` | `business.manage` | Append a draft revision using `expected_revision` and a required `Idempotency-Key` |

The PUT body uses schema/catalog version 1, unique integer `industry_ids`, optional
`business_formats` (`b2b`, `b2c`, `marketplace`, `franchise`, `holding`) and an optional
`custom_activity_name`. New profiles use `expected_revision: 0`. Unknown versions,
duplicate selections, coercible string/bool IDs and extra fields are rejected.
A stale revision returns 409; a reused key with a different command returns 422.
Retry an uncertain command with its original body and key. A deterministic rejection
may be corrected before issuing a new command.

Migration 0008 adds three FORCE-RLS tables with tenant-bound references. Committed
headers and selections are immutable, including against later child INSERTs.
The draft, selections, audit and command receipt commit or roll back together.
Managers/owners may save; other business roles may read. Platform support remains
audited and read-only. Company-wide handlers reject location-limited memberships. Reviewed operational
handlers use the transaction-local branch RLS boundary and `/workspace`, as
described in [ADR-0014](adr/0014-location-scoped-workspace.md). Migration 0009
and approved scope definitions are mandatory for this runtime; startup/readiness
and scoped requests fail closed if that protection is incomplete or altered.

`/business/` is the real management UI. `/v1/salons/` and the customer booking API
remain available. Booking date filters accept `local_day`, `local_start_day`,
`local_end_day` and `location_id`; legacy instant filters require a UTC offset.
Appointments are entered and displayed using the location timezone. Weekly hours
use ISO weekdays 1..7 and retain multiple intervals and a closing minute of 1440.
The overview displays confirmed booking value by currency, not paid revenue;
`today_revenue_cents` remains a deprecated compatibility field with its old meaning.

Run `npm run test:unit` for time/interval rules without a running server.
The PostgreSQL suite with `GBA_REQUIRE_BROWSER=1` runs both `test:e2e` (customer)
and `test:management` (management). The latter uses a test-only OIDC provider with
real code/PKCE requests, the actual API and disposable SQL data. Only the negative
proxy rejection and lost-response scenarios inject network faults; successful saves
and bookings are real. Do not run two PostgreSQL suites concurrently on the same
server: fixture role names are shared.

Apply new migrations to a disposable database for acceptance first. Development
or production database changes are separate operations; the tests never target
KA Nails data. Follow ADR-0012 for Azure and obtain owner authorization before
production migrations or deployment.

## Deployment readiness (M4)

### Legal-entity drafts (stage 1)

[ADR-0015](adr/0015-tenant-owned-legal-entity-drafts.md) adds owner-provided legal-entity drafts inside an existing business. Migration 0010 creates identities and immutable versions; no existing migration or tenant data is rewritten. The runtime requires all 19 approved scope-policy definitions before reporting readiness.

| Route | Behavior |
|---|---|
| `GET /v1/businesses/{id}/legal-entities?limit=50&after=REF` | Bounded current drafts; response provides `next_cursor` or null |
| `GET /v1/businesses/{id}/legal-entities/{entity_id}?revision=1` | Current or explicitly selected saved version; unknown version returns 404 |
| `PUT /v1/businesses/{id}/legal-entities/{entity_id}` | Client-generated UUID identity, `schema_version: 1`, `expected_revision`, `code`, `legal_name` and required `Idempotency-Key`; returns saved draft |

The internal code is immutable and unique per company; names alone never merge records. A new record uses expected revision 0. Company-wide owners/managers may save; other permitted company members may read. Branch-limited members are denied. A repeated body/key returns its original saved version; a changed command/key identity returns 422; a stale revision or duplicate reference returns 409. The existing business profile API is unchanged.

The legal-entity section on `/business/` creates/edits real drafts and views saved history. It keeps the same entity ID and command after an uncertain response. No country, tax ID, currency, registration confirmation or branch assignment is silently populated, and saving does not activate finance or a delegated relationship.

Focused acceptance uses `tests/unit/test_legal_entity_contracts.py` and `tests/integration/test_legal_entities.py` against disposable PostgreSQL. The existing management browser harness now checks legal entities on desktop/mobile and verifies their saved versions through SQL. The broken-boundary test restores the two 0010 policies after its test-only cascade.

### Departments (stage 1)

[ADR-0016](adr/0016-tenant-owned-departments.md) adds owner-provided departments inside an existing business. Migration 0011 creates identities and immutable versions with optional company-bound links; no existing migration or tenant data is rewritten. The runtime now requires 21 approved scope-policy definitions before reporting readiness.

| Route | Behavior |
|---|---|
| `GET /v1/businesses/{id}/departments?limit=50&after=REF` | Bounded current drafts, including archived ones; response provides `next_cursor` or null |
| `GET /v1/businesses/{id}/departments/{department_id}?revision=1` | Current or explicitly selected saved version; unknown version returns 404 |
| `PUT /v1/businesses/{id}/departments/{department_id}` | Client-generated UUID identity, `schema_version: 1`, `expected_revision`, `code`, `name`, `parent_department_id`, `legal_entity_id`, `location_id` (each UUID or null), `archived` and required `Idempotency-Key`; returns saved draft |

`PUT` replaces the whole draft, so every link is stated explicitly. The code is immutable and unique per company. A parent must be active unless the saved department is archived; cycles, self-parenting, chains deeper than 32 levels and archiving a department with active subdepartments return 422 `DEPARTMENT_STRUCTURE_INVALID`. Another company's or an unknown parent, legal entity or location returns 422 `INVALID_REFERENCE` with the field name. Permissions, replay, stale-revision and duplicate-reference behavior match legal entities.

The department section on `/business/` creates/edits real drafts, links a parent, legal entity and location, archives, and views saved history. No head, employee assignment, budget or access right is implied.

Focused acceptance uses `tests/unit/test_department_contracts.py` and `tests/integration/test_departments.py` against disposable PostgreSQL. The management browser harness checks departments on desktop/mobile and verifies their versions through SQL. The broken-boundary test restores the 0010 and 0011 scope policies after its test-only cascade.

### Cross-company delegation (stage 1)

[ADR-0017](adr/0017-cross-company-delegation.md) lets an owner business grant an independent servicing business limited, expiring booking access. Migration 0012 adds grants and delegate history; the runtime requires 23 approved scope-policy definitions.

| Route | Behavior |
|---|---|
| `GET /v1/businesses/{id}/delegations?limit=50&after=UUID` | Grants where the business is owner or servicer (`members.manage`) |
| `GET /v1/businesses/{id}/delegations/{grant_id}` | One grant of a party; 404 otherwise |
| `PUT /v1/businesses/{id}/delegations/{grant_id}` | Owner-only offer: `servicer_business_id`, `permissions` (subset of booking.read, booking.write, catalog.read, staff.read), `location_id` or null, `expires_at` (≤366 days); `Idempotency-Key` required |
| `POST …/{grant_id}/accept` | Servicer: `expected_revision`, `delegate_user_ids` (active company-wide members) |
| `POST …/{grant_id}/decline`, `POST …/{grant_id}/revoke` | `expected_revision`; owner may revoke pending/active, servicer may end active |
| `PUT …/{grant_id}/delegates` | Servicer replaces the delegate set of an active grant |

Delegated employees use the existing `/v1/salons/{owner_id}/…` booking workspace (eleven opted-in handlers). Effective permission is grant ∩ servicer role, and grant location becomes the location RLS scope. Each request writes `delegation.access` to the owner's audit. `/v1/me` returns `delegations` separately from `memberships`. Revocation, removal, expiry and owner-side suspension refuse the next request, including an old receipt replay.

Focused acceptance: `tests/unit/test_delegation_contracts.py`, `tests/integration/test_delegations.py`, and `test_real_delegation_browser_oidc_pkce_and_database` running `npm run test:management:delegation`. The broken-boundary test restores the 0010–0012 scope policies.

### Company groups (stage 1)

[ADR-0018](adr/0018-company-groups.md) records consent-based groups of independent businesses. Migration 0013 adds groups and membership history; the runtime requires 25 approved scope-policy definitions. Group membership grants no data access.

| Route | Behavior |
|---|---|
| `GET /v1/businesses/{id}/groups`, `GET …/groups/{group_id}` | Groups the business organizes or is invited to (`business.read`); members see only their own membership |
| `PUT /v1/businesses/{id}/groups/{group_id}` | Organizer creates `{code, name}` |
| `PUT …/groups/{group_id}/members/{member_id}` | Organizer invites a business by ID |
| `POST …/groups/{group_id}/members/{member_id}/remove` | Organizer ends an invitation or membership (`expected_revision`) |
| `POST …/groups/{group_id}/accept`, `/decline`, `/leave` | The member business decides for itself (`expected_revision`) |

Commands need `business.manage`, company-wide access and an `Idempotency-Key`. Focused acceptance: `tests/unit/test_group_contracts.py`, `tests/integration/test_groups.py` and `test_real_group_browser_oidc_pkce_and_database` (`npm run test:management:groups`).

### Configuration publication and modules (stage 1, CORE-02)

[ADR-0019](adr/0019-configuration-publication-and-modules.md) adds company configuration versions (draft → validated → published → superseded), a code-defined registry of 18 platform modules (`business/modules.py`) and readiness records for the 28 scenarios and 39 profiles (`business/readiness_registry.py`; the industry catalog reads `workflow_readiness` from it). Migration 0014 adds versions, their module selections and effective module states. The runtime requires 29 approved policy definitions plus the `bookings_require_booking_module` trigger and its function; damage fails readiness.

| Route | Behavior |
|---|---|
| `GET /v1/businesses/{id}/module-catalog`, `GET …/readiness-registry` | Registries (`business.read`) |
| `GET /v1/businesses/{id}/configuration` | Published version or implicit baseline (`baseline: true`, booking on), latest version, effective modules |
| `GET …/configuration/versions?limit=20&before=N`, `GET …/versions/{n}` | History, newest first |
| `GET …/versions/{n}/preview` | Modules turned on/off, operations that stop, activity changes, problems and warnings |
| `PUT …/configuration/draft` | `expected_version`, `profile_revision`, `module_ids` (optional modules only) → next draft |
| `POST …/versions/{n}/validate`, `…/publish` | `expected_revision`; only the latest version; validation failure is 422 `CONFIGURATION_INVALID`; publication re-validates and supersedes the previous version |

Commands need `business.manage`, company-wide access and an `Idempotency-Key`; they are never delegable and share the `business-configuration` advisory lock with the booking trigger. Only optional modules that are at least `technically_verified` can be enabled; today that is `booking_resources`. When a published configuration disables it, every path that inserts a booking (workspace, reschedule, customer site, delegates, development holds) answers 409 `MODULE_DISABLED`; cancellation, confirming an existing hold and reads continue. `/v1/salons/{id}/workspace` returns `booking_enabled`.

Focused acceptance: `tests/unit/test_configuration_contracts.py`, `tests/integration/test_configurations.py` and `test_real_configuration_browser_oidc_pkce_and_database` (`npm run test:management:configuration`). The broken-boundary test of `test_location_access.py` restores the 0010–0014 scope policies.

**Embedding allowlist.** The customer web may be framed only by origins the owner approves per tenant (migration 0007, audited, FORCE RLS). Every HTML response carries `Content-Security-Policy: frame-ancestors 'self' <approved>`; API responses carry `frame-ancestors 'none'`. With no approved origin, `X-Frame-Options: SAMEORIGIN` is added too. Plain `http://` origins are accepted only for loopback, and only in `local`/`test`/`ci`.

```bash
cd api
uv run --env-file ../.env gba-db embed-origin list <tenant-slug>
uv run --env-file ../.env gba-db embed-origin add <tenant-slug> https://www.example.test
uv run --env-file ../.env gba-db embed-origin revoke <tenant-slug> https://www.example.test
```

**Behind Azure Front Door.** Set `GBA_TRUSTED_PROXY=azure_front_door` and `GBA_FRONT_DOOR_ID=<profile frontDoorId>`. Every request except `/health/live` and `/health/ready` must then carry exactly one matching `X-Azure-FDID`. The tenant host is taken from `X-Forwarded-Host`; anything else is a 404 `TENANT_NOT_FOUND`. The default (`none`) ignores forwarded headers. `GBA_ENV=staging` starts only with a configured OIDC provider and this Front Door mode; `production` always refuses to start.

**Observability.** Logs are JSON lines with an allowlist of fields, never customer data. Telemetry is exported to Application Insights only when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set; in Azure the exporter authenticates with the managed identity in `AZURE_CLIENT_ID`.

Opt-in gates (each fails, never skips, once enabled):

| Gate | Enable | Proves |
|---|---|---|
| Container | `GBA_REQUIRE_CONTAINER=1`, `GBA_CONTAINER_IMAGE=<tag>` (build: `docker build -t gorgona-api:local .` at the repo root) | The production image runs bootstrap/migrate jobs, is non-root with no baked secrets, serves health, `/book/` and a real booking, and exits cleanly within the grace period |
| Tenant site | `GBA_REQUIRE_TENANT_SITE=1`, `GBA_TENANT_SITE_DIR=<KA-nails checkout>` (build `web/` first) | An independent site embeds the real wizard through public configuration only; confirmed rows and tenant isolation are verified |

Load baseline (public customer API only; creates bookings only for a tenant named `FAKE ...`; non-loopback targets need `--allow-remote`):

```bash
cd api
uv run python tools/load_baseline.py --base-url http://127.0.0.1:8000 \
  --host <fake-salon-host> --day <YYYY-MM-DD> --out load-report.json
```

It reports throughput, p50/p95/p99 and status/error codes per operation, and a contention check where exactly one concurrent hold may win. It exits 1 on any 5xx, a transport error, or a contention violation.

## Checks (no database needed)

```bash
cd api
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Without `GBA_TEST_ADMIN_DSN`, tests marked `postgres` are **skipped with a BLOCKED reason**. They are never replaced by SQLite or mocks. CI sets `GBA_REQUIRE_POSTGRES=1`, which turns a missing database into a failure.

## Local PostgreSQL 18

From the repository root:

```bash
cp .env.example .env    # then replace every password
docker compose --env-file .env -f infra/local/compose.yaml up -d
```

Integration tests create a throwaway database per run, bootstrap the test roles, apply migrations as the owner role and run every assertion as the non-owner runtime role:

```bash
cd api
uv run --env-file ../.env pytest
```

Set `GBA_TEST_KEEP_DB=1` to keep the test database for inspection.

## Local database and API

```bash
cd api
uv run --env-file ../.env gba-db bootstrap            # superuser: roles + database
uv run --env-file ../.env gba-db migrate              # owner: apply migrations
uv run --env-file ../.env gba-db check-runtime-role   # runtime role cannot bypass RLS
uv run --env-file ../.env python -m gorgona_booking   # API on 127.0.0.1:8000
```

Tenants, host mappings and catalog data are provisioned by the owner role (see `gorgona_booking.db.provisioning`). Nothing seeds KA Nails data: `api/fixtures/ka_nails_catalog.candidate.json` is owner-unconfirmed and never loaded into a database.

`POST /v1/holds` resolves the salon from the `Host` header through `gba.tenant_hosts`. This M1 development endpoint has no authentication or customer availability/capability validation. It is registered only for `GBA_ENV=local`, `test` or `ci`; never expose those environments publicly. Staging and production omit the route from OpenAPI and do not invoke its booking handler, including when a static web export is mounted. Public bookings use `/v1/customer/holds` with the customer policy, availability and `Booking-Token` checks. The shared booking service and tenant resolution remain available to the customer API.

## Authentication (M2)

Staff and admin routes need an external OIDC identity provider (ADR-0007). Set all three or none:

```
GBA_AUTH_ISSUER=https://<your-idp>/
GBA_AUTH_AUDIENCE=<api audience>
GBA_AUTH_JWKS_URL=https://<your-idp>/.well-known/jwks.json
# optional: GBA_AUTH_ALGORITHMS=RS256,ES256   GBA_AUTH_LEEWAY_SECONDS=30
```

Without them, protected routes answer `503 AUTH_NOT_CONFIGURED`. Tests use a FAKE IdP (`tests/support/fake_idp.py`) with local keys and no network.

## Salon onboarding (M2, owner credential)

```bash
cd api
uv run --env-file ../.env gba-db onboard fixtures/ka_nails_onboarding.candidate.json
uv run --env-file ../.env gba-db readiness ka-nails        # exit 2 while facts are missing/unconfirmed
uv run --env-file ../.env gba-db go-live ka-nails         # refuses until readiness passes
uv run --env-file ../.env gba-db link-user --issuer https://<idp>/ --subject <sub> --display-name "<name>"
uv run --env-file ../.env gba-db grant-platform-admin --issuer https://<idp>/ --subject <sub>
```

A spec that invites the first owner needs `--invitation-token-file PATH`. The token is written there once and never printed. Only its SHA-256 is stored.

## Credentials

| Credential | Used by | Never used by |
| --- | --- | --- |
| Superuser (`GBA_ADMIN_DATABASE_URL`, `GBA_TEST_ADMIN_DSN`) | bootstrap, test fixture | migrations, the API |
| Owner (`GBA_MIGRATION_DATABASE_URL`) | migrations, provisioning | the API |
| Runtime (`GBA_DATABASE_URL`) | the API | DDL. It is refused at startup if it is a superuser, `BYPASSRLS`, or a member of the table owner |

## Windows

psycopg's async driver needs a selector event loop. The test suite and `uv run python -m gorgona_booking` set one up. Production runs on Linux.

Without Docker, the official EDB PostgreSQL 18 Windows binaries ZIP works as a disposable local server (`initdb --pwfile`, `listen_addresses = '127.0.0.1'`, `max_connections = 250`). Start it **detached**, e.g. PowerShell `Start-Process pg_ctl.exe -ArgumentList 'start','-D',<dir>,'-l',<log>,'-o','"-h 127.0.0.1 -p 51454 -c max_connections=250"','-w' -WindowStyle Hidden`. If the shell or console that ran `pg_ctl start` is closed, new backends can fail with `0xC0000142` / `could not reserve shared memory region … error code 487`, and every connection then drops with "server closed the connection unexpectedly".

Repository ownership, hosted embed and tenant asset routing are documented in `architecture/REPOSITORY_SEPARATION.md`.

## Location-scoped acceptance

`/me` includes the assigned location. A company owner may supply `location_id`
when creating an invitation; the accepted scope cannot widen during acceptance.
Calendar, booking mutations/history, clients and resource schedules are scoped
through RLS; full settings, profile changes and member administration remain
company-wide. Test-only browser setup exercises actual OIDC/PKCE, HTTP and SQL
for both unrestricted and location-limited managers. Run the Python management
browser harness after rebuilding the web export. It dispatches `test:management`
and `test:management:location`; no browser login/API success is simulated.
