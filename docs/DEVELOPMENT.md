# Development

## Selected-company query boundaries

Authenticated RLS may expose the caller's memberships in several businesses and
support may see several tenant rows. Company-specific queries on these tables
must also filter by the authorized tenant: `gba.current_tenant_id()` on the same
connection or `access.tenant_id`. Do not narrow the shared discovery policies as
a substitute. The readiness state, owner requirement and member-list regressions
are in `tests/integration/test_setup_isolation.py`; run that file together with
`tests/integration/test_onboarding.py` against required PostgreSQL before the full
suite. See [acceptance evidence](plan/evidence/2026-10-04-selected-company/ACCEPTANCE.md).

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

[ADR-0015](adr/0015-tenant-owned-legal-entity-drafts.md) adds owner-provided legal-entity drafts inside an existing business. Migration 0010 creates identities and immutable versions; no existing migration or tenant data is rewritten. The runtime required all 19 approved scope-policy definitions before reporting readiness; migration 0011 extends this to the 45 definitions described below.

| Route | Behavior |
|---|---|
| `GET /v1/businesses/{id}/legal-entities?limit=50&after=REF` | Bounded current drafts; response provides `next_cursor` or null |
| `GET /v1/businesses/{id}/legal-entities/{entity_id}?revision=1` | Current or explicitly selected saved version; unknown version returns 404 |
| `PUT /v1/businesses/{id}/legal-entities/{entity_id}` | Client-generated UUID identity, `schema_version: 1`, `expected_revision`, `code`, `legal_name` and required `Idempotency-Key`; returns saved draft |

The internal code is immutable and unique per company; names alone never merge records. A new record uses expected revision 0. Company-wide owners/managers may save; other permitted company members may read. Branch-limited members are denied. A repeated body/key returns its original saved version; a changed command/key identity returns 422; a stale revision or duplicate reference returns 409. The existing business profile API is unchanged.

The legal-entity section on `/business/` creates/edits real drafts and views saved history. It keeps the same entity ID and command after an uncertain response. No country, tax ID, currency, registration confirmation or branch assignment is silently populated, and saving does not activate finance or a delegated relationship.

Focused acceptance uses `tests/unit/test_legal_entity_contracts.py` and `tests/integration/test_legal_entities.py` against disposable PostgreSQL. The existing management browser harness now checks legal entities on desktop/mobile and verifies their saved versions through SQL. The broken-boundary test restores the two 0010 policies after its test-only cascade.

### Delegation between businesses (stage 1)

[ADR-0016](adr/0016-limited-cross-business-delegation.md) lets an owner business grant another, independent business limited operational access. Migration 0011 adds grant identities, append-only grant revisions and serving-business designations; it is additive and also adds a unique key on memberships. The runtime now verifies 45 access-boundary definitions (both scope functions, every restrictive branch/delegation policy, the exact cross-tenant delegation policies and no extra policy on delegation tables) at startup, readiness and before every branch-scoped or delegated request.

| Route | Behavior |
|---|---|
| `GET /v1/businesses/{id}/delegations?limit=50&after=GRANT` | Owner's grants with current terms and designated user IDs |
| `GET /v1/businesses/{id}/delegations/{grant_id}?revision=1` | Current or explicitly selected revision |
| `PUT /v1/businesses/{id}/delegations/{grant_id}` | `schema_version: 1`, `expected_revision`, `grantee_business_id`, `purpose`, `permissions`, optional `location_id`, `valid_from`, `valid_until` and required `Idempotency-Key` |
| `POST /v1/businesses/{id}/delegations/{grant_id}/revoke` | `expected_revision`; appends a terminal revoked revision |
| `GET /v1/businesses/{id}/incoming-delegations` | Grants addressed to this business, with its designated employees |
| `PUT`/`DELETE /v1/businesses/{id}/incoming-delegations/{grant_id}/delegates/{membership_id}` | Designate or remove one active member of this business; `Idempotency-Key` required |

All management routes require `delegation.manage`, held by business-wide owners only. Delegable permissions are `booking.read`, `booking.write`, `catalog.read` and `staff.read`; `booking.write` requires the three reads, and one revision lasts at most 366 days. The serving business ID must be supplied by the owner; unknown or unusable IDs and foreign locations return 422 without a record.

A designated employee keeps signing in normally. `/v1/me` lists `delegations`, and only handlers that pass `allow_delegation=True` (workspace, overview, availability, bookings, clients, services list, staff list/schedule) admit them. Each delegated request is re-authorized against both businesses, the designation and the current revision, records `delegation.access`, writes owner-owned rows with `created_by = delegate:{user}@{serving business}/grant:{grant}`, and cannot read memberships, other users, invitations, legal entities, profiles, fact confirmations, embed origins, audit history or delegation records. Idempotency receipts remain keyed to the user.

The `/business/` page shows owners both "Access for other businesses" and "Work you do for other businesses". The management layout lists delegated businesses as `purpose (delegated)` and limits navigation to Overview, Calendar, Bookings and Clients.

Focused acceptance: `tests/unit/test_delegation_contracts.py`, `tests/integration/test_delegations.py` and, after rebuilding the web export with browsers required, `tests/integration/test_delegation_browser.py` (dispatches `test:delegation:management` and `test:delegation:workspace`). The location boundary test now also restores the three 0011 policies that depend on `gba.current_location_id()`.

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
