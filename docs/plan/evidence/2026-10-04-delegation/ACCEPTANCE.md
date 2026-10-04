# GORGONA cross-company delegation acceptance — 2026-10-04

CORE-03 step B is technically verified on commit `ed370c6`, branch `codex/universal-business-foundation`, repository `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. Later commits do not extend this acceptance to changed application code.

An owner business can offer an independent servicing business limited, expiring booking access; the servicer accepts and names its own company-wide employees; delegates work in the owner's booking workspace within the granted permissions and location; either side ends active access, and revocation, delegate removal, expiry and owner-side suspension stop the next command. Both companies keep their own records. Groups, document/financial scopes, TMS dispatcher workflows and offline drafts are outside this increment. See [ADR-0017](../../../adr/0017-cross-company-delegation.md).

## Direct evidence

| Check | Exact outcome |
|---|---|
| Full GitHub PR CI | **PASS**: [run 37238206491](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37238206491), job `111541476109`, exact commit above; all steps succeeded (web build/unit, PostgreSQL 18, production image, Ruff, mypy, pytest) |
| GitHub push CI | **PASS**: [run 37238204250](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37238204250), same commit |
| CI test counts | Not retrieved: job logs require authentication. Step conclusions were read through the public GitHub API |
| Local full Python suite, PostgreSQL 18.6, required browsers | **479 passed, 4 skipped, 298.22 s** (three container gates without local Docker; optional external site gate, not a passed check) |
| Delegation PostgreSQL/API | **PASS: 10** — offer/acceptance/booking cycle, refused owner-only areas, audit; removal/revocation/expiry and receipt replay; servicer suspension, branch limit, role limit, company suspension; read-only and location terms; parties, states, stale revisions, accept/revoke race, third company; direct SQL; owner-side suspension; member list regression (red before fix) |
| Delegation unit | **PASS: 23** — terms, canonical permissions, delegable set, location-scope requirement, exact list of 11 delegated routes |
| Browser harnesses | **PASS: 3** (company, branch, delegation). Delegation desktop: lost-response acceptance retried with the same key, own offer issued and revoked, booking created and cancelled in the owner company's granted location, access ended; mobile: ended state, Axe WCAG 2 A/AA, no horizontal overflow |
| Saved browser results | SQL: the booking belongs to the owner company at the granted location and is cancelled; the owner→servicer grant is revoked by the servicer with the delegate recorded; the servicer→owner offer is revoked by its owner; access audit names only the real executor; no booking in the servicer company |
| Web unit / static | Web unit **25**; typecheck, ESLint, Prettier, 14-page build PASS; Ruff and strict mypy PASS (138 source files) |
| Independent review | `/code-review high` in the same session: 8 findings; 4 fixed before the commit (owner-side suspension bypass, mutable decision metadata, stale delegate choices, date bounds); 4 deliberately not changed and recorded in the register |

Tests and source: [contracts](../../../../api/tests/unit/test_delegation_contracts.py), [PostgreSQL/API](../../../../api/tests/integration/test_delegations.py), [browser](../../../../web/tests/delegation.spec.ts), [harness/SQL assertions](../../../../api/tests/integration/test_management_browser.py), [response boundaries](../../../../web/tests/management-contracts.spec.ts), [migration 0012](../../../../api/src/gorgona_booking/db/migrations/0012_delegation_grants.sql).

## Boundaries

The review ran in the same session as the implementation, not as a separate reviewer. Azure, staging, production migration, live providers, load and industry pilots were not verified. CORE-03 remains partial until the group model (step C) is accepted; TMS-02 needs the TMS modules themselves.
