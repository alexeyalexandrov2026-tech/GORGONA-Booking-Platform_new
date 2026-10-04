# GORGONA business platform

GORGONA is being expanded from a tenant-isolated appointment platform into a modular business platform. The [master plan](docs/plan/GORGONA_MASTER_PLAN.md) covers 39 industry profiles, shared company data and industry-specific workflows. Businesses own their goods, vehicles, warehouses and property; GORGONA provides software and intermediary services.

The active repository is [GORGONA-Booking-Platform_new](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new). The owner's 2026-10-04 decision supersedes the previous repository destination. Existing source and uncommitted improvements were preserved during the [repository transition](docs/plan/REPOSITORY_TRANSITION_2026-10-04.md); historical milestone reports remain available.

This repository develops the independent GORGONA business platform. KA Nails is a separate project and is outside this repository's development, release and acceptance scope. Inherited references, candidate fixtures and external-site test reports record earlier work; they do not make that project a platform dependency or assign its development to GORGONA agents.

## Implemented foundation

- PostgreSQL tenant isolation, transactional appointment holds, price calculation, compatible add-ons and immutable booking snapshots.
- Reusable customer booking and OIDC-authenticated business management pages.
- Stable industry identifiers and a typed draft profile supporting several business activities without duplicating the company.
- Local business dates, ISO weekdays, split operating hours and appointment value distinguished from paid revenue.
- One-location membership permissions, restricted operational pages, database policy verification and compatible replay of older management responses.
- A separate AI learning package with versioned examples, evaluation, approval and rollback. Its current local text embedder is deterministic hashing; this is not a general-purpose LLM assistant.

Industry selection does not establish a complete logistics, restaurant, rental, construction or financial workflow. These modules remain development targets. See the [implementation register](docs/plan/GORGONA_IMPLEMENTATION_STATUS.md) and [current handoff](docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md) for evidence and next work.

The [plan-conformance audit](docs/plan/GORGONA_PLAN_AUDIT_2026-10-04.md) maps all 28 acceptance criteria to current implementation and verification. The shared business foundation is partial. The legacy development-only `/v1/holds` route is available only in local/test/CI environments; hosted customer booking uses the validated `/v1/customer/holds` flow.

## Development and verification

The existing stack is Python 3.14/FastAPI, PostgreSQL 18 and Node.js 24/Next.js/TypeScript. Dependency versions are recorded in the existing lockfiles; this transfer introduces no application dependencies. Follow [DEVELOPMENT](docs/DEVELOPMENT.md) for installation, disposable database setup and browser tests.

```bash
cd web
npm ci --ignore-scripts
npm run typecheck
npm run lint
npm run format:check
npm run test:unit
npm run build
```

API gates include Ruff, strict mypy and pytest against a disposable PostgreSQL database. Browser and container gates must be explicitly required in their applicable environments. Historical results belong to their recorded source snapshots; the transition report records checks repeated in this checkout.

Each business's timezone, operating hours, staff, service durations, policies and public domain require verified configuration. Never infer business facts from test fixtures or publish fake booking/payment success.

## Collaboration and hosting

Other agents can work through their own branches and separate checkouts, with scoped changes proposed through Pull Requests. Read [AGENTS](AGENTS.md), the master plan and the current handoff first. One executor owns a shared checkout and shared test database at a time. Local continuation archives and the original history bundle are excluded from commits under `handoff/`.

Azure remains the hosting target under [ADR-0012](docs/adr/0012-azure-hosting.md). GitHub stores and reviews source; Azure hosts the application when separately authorized and validated. Existing Bicep and manual release workflows are preserved. New repository permissions, protected branches, deployment environments and Azure OIDC federation require their own verification before release. CI success is not deployment approval.

The camera surveillance product and its Local Gateway are separate from Booking. Customer data, credentials and private test connections do not belong in this repository. No production deployment, migration or go-live is claimed by this transfer.
