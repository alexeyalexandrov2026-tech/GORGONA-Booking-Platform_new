# Selected-company isolation: readiness and member lists

Date: 2026-10-04. Branch: `codex/booking-state-isolation`.
Base: `ef423f3c672bf2da219d6aef85f9a44cf1f37317`, the delegation branch.
PR #1 and PR #2 were open, draft and unmerged when this package started.
The owner's foundation checkout was clean and remains untouched.

## Defects and correction

RLS deliberately permits a user to see their own memberships across businesses,
and support can see multiple tenant rows. Visibility is not the selected business.
Three existing queries incorrectly treated those concepts as equivalent:

- `api/setup.py:_booking_state` selected an arbitrary visible tenant. Readiness,
  live fact protection and automatic confirmation after settings edits could use
  another business's state. It now selects `gba.current_tenant_id()`.
- `onboarding/readiness.py:_SNAPSHOT` counted a user's owner membership elsewhere.
  A platform administrator who owned another business could publish an otherwise
  ready but ownerless business. The count now requires the selected tenant.
- `identity/invitations.py:list_members` included the caller's membership in a
  different business in the selected business's staff list. It now filters on
  the authorized `access.tenant_id`.

Existing RLS, authorization, transaction boundaries, response contracts and
membership discovery are preserved. This repairs the invariant in
[ADR-0009](../../../adr/0009-tenant-context-derivation.md); it adds no architecture
decision, migration, dependency or infrastructure. Applied migrations are untouched.

## Direct evidence

Windows, Python 3.14.6, PostgreSQL 18.6 on loopback; isolated disposable databases.
The private DSN was passed only through the test process environment.

| Check | Observed result |
|---|---|
| Unchanged base, complete API suite with required PostgreSQL/browser | PASS: 471 passed, 4 skipped, 148.56 s; exit 0 |
| Unchanged web: typecheck, lint, format, unit, build | PASS: 16 unit tests; 14 exported pages; each command exit 0 |
| New regression file before the three fixes | Expected FAIL: 8 failed, 3.32 s; exit 1 |
| New regression file plus existing onboarding tests after fixes | PASS: 14 passed, 4.73 s; exit 0 |
| Ruff format/check and strict mypy after code changes | PASS: 135 files; exit 0 |
| Final complete API suite with required PostgreSQL/browser | PASS: 479 passed, 4 skipped, 146.75 s; exit 0 |

The red run returned both tenant states as `not_live`, allowed unconfirming a live
fact, left live settings unconfirmed, counted an owner from elsewhere, published
an ownerless business with HTTP 200, and included the other membership in staff.
The green run checks the expected HTTP responses and stored state. It also checks
the positive control: adding a real owner of the selected company confirms that fact.
An independent read-only review found no further substantial issue in the final
patch; the reviewer did not run tests.

Other unfiltered tenant reads were inspected: public host resolution/customer
bootstrap currently run without identity context; the onboarding fingerprint runs
in an owner transaction. They must be re-audited before reuse in an authenticated
multi-business context. This is a targeted flow review, not an exhaustive security audit.

## Remaining boundaries

Local container gates and the optional external-site gate are not enabled.
Production, Azure/staging, real identity providers, payments, load, recovery and
industry pilots were not tested. No deployment or production migration occurred.
Departments, groups and the remaining master-plan stages are still planned.

Dependency audit: `npm audit --omit=dev` returned zero vulnerabilities, exit 0.
The complete audit reports five high-severity entries in the development
ESLint dependency chain ending in `braces@3.0.3`. The reviewed
[GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
listed no patched version when checked. The suggested forced downgrade of the
Next ESLint configuration was not applied. This remains an open build-tool
dependency finding; it is not a clean full dependency audit.
