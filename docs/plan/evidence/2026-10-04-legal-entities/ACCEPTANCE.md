# GORGONA legal-entity draft acceptance — 2026-10-04

The stage-1 increment is technically verified on commit `d97924f53a8ff34a69f82d36fe675b965e8aa6e6`, branch `codex/universal-business-foundation`, repository `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. Subsequent documentation changes do not extend this acceptance to changed application code.

The business owner can create legal-entity draft records, change a name through a new version, read saved history and retry an uncertain save without creating a duplicate. The existing business remains the tenant and owner; matching names do not merge records. Registration, payment activation, company groups and delegation are outside this increment. See [ADR-0015](../../../adr/0015-tenant-owned-legal-entity-drafts.md).

## Direct evidence

| Check | Exact outcome |
|---|---|
| Full GitHub PR CI | **PASS**: [run 37204951503](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37204951503), job `111444095826`, exact commit above |
| GitHub push CI | **PASS**: [run 37204947143](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37204947143), same application commit |
| Python suite in PR CI | **413 passed, 1 skipped, 91.41 seconds, exit 0**; 414 collected, required PostgreSQL/browser/container checks enabled |
| Legal-entity contracts | **PASS: 15 tests** in the full suite; strict version/revision, names, identifiers and rejection of client-supplied ownership/activation |
| Legal-entity PostgreSQL/API | **PASS: 9 tests** in the full suite; history, pagination, duplicate/race/replay, isolation/revocation, rollback, direct SQL integrity and readiness after policy damage |
| Management browser harnesses | **PASS: 2 Python harness tests**, including company-wide and branch-limited desktop/mobile flows. The company-wide flow exercises the new list/save/history helpers through the real response validator and test-only OIDC/PKCE, API and PostgreSQL |
| Saved browser results | SQL asserts two legal-entity identities, each with four immutable versions and current revision 4; no corresponding rows in the other tenant |
| Browser failure handling | Lost response after actual server persistence keeps the same ID/key; retry succeeds. A competing revision gives 409, preserves the edit, and requires explicit reload |
| Browser accessibility | Automated Axe WCAG 2 A/AA and viewport overflow assertions passed in the tested desktop/mobile states |
| Existing behavior | Full suite includes existing business-profile, branch-access, booking and production-container regressions; hosted legacy-hold restriction remains checked |
| Web unit | **PASS: 11** in CI (1.5 seconds); local **11**, 821 ms, exit 0. Before the dispatcher fix, four new response-boundary tests failed and one rejection test passed |
| Static checks/build | CI and final local TypeScript, ESLint, Prettier and 14-page build **PASS**; Ruff check/format and strict mypy **PASS: 128 files**, exit 0 |
| Documentation before application commit | **PASS**: 5 changed documents, 35 relative links, all 28 criteria and 39 industries retained; `git diff --check`, exit 0 |
| Independent source review | No remaining substantial finding after the dispatcher correction. Reviewer did not execute tests |

The one Python skip is the optional external tenant-site gate requiring `GBA_REQUIRE_TENANT_SITE=1`. It is outside the GORGONA acceptance dependency and is **not** a passed check.

Tests and source: [contracts](../../../../api/tests/unit/test_legal_entity_contracts.py), [PostgreSQL/API](../../../../api/tests/integration/test_legal_entities.py), [management browser](../../../../web/tests/management.spec.ts), [harness/SQL assertions](../../../../api/tests/integration/test_management_browser.py), [response-boundary regression](../../../../web/tests/management-contracts.spec.ts), [migration 0010](../../../../api/src/gorgona_booking/db/migrations/0010_legal_entities.sql).

## Boundaries and continuation

Local Python/runtime execution after implementation was declined and did not run. The full runtime PASS above is from the separately authorized GitHub branch publication and CI; it is not a claimed local PostgreSQL run. No production database, migration, deployment or provider account was used. The test identity provider and business facts are explicitly synthetic fixtures.

Not verified: registration facts or legal suitability, industrial pilot, visual inspection of the new screenshots, complete keyboard journeys, live OIDC/providers, Azure/staging, performance targets or recovery. All 39 full industry workflows remain planned. CORE-03 and stage 1 remain partial.

Continue with departments/groups and limited delegation while preserving independent company ownership, then configuration preview/validation/publication and shared resource occupancy (CORE-04). Finance, workforce and complete industry modules follow the master plan.
