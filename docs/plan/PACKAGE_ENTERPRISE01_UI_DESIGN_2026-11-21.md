# ENTERPRISE-01 Slice 3 — `/enterprise/` 3-Tab Operations UI & Real-Browser E2E

Date: 2026-11-21
ADR: `docs/adr/0041-enterprise-sso-lifecycle-and-group-reporting.md`
Parent plan: `docs/plan/PACKAGE_ENTERPRISE01_PLAN_2026-11-21.md`

## Scope
- Route: `/enterprise/` inside `ManagementLayout` (navigation item `"Enterprise"`, gated by active staff / owner-admin role).
- Strict Zod contracts (`web/lib/enterprise-contracts.ts`) registered in `management-contracts.ts` and unit-tested (`web/tests/enterprise-contracts.spec.ts`).
- Typed API client (`web/lib/enterprise-api.ts`) with mandatory `Idempotency-Key` on every mutation.
- 3 accessible, responsive tabs (`role="tablist"`, `ArrowLeft`/`ArrowRight` keyboard navigation, mobile 390px zero-overflow layout):
  1. **Corporate SSO & Lifecycle**: register OIDC/SAML identity providers, link employees to corporate directory subjects, atomically deprovision employees (suspending memberships and revoking delegations immediately), and inspect immutable lifecycle audit events.
  2. **Group Reporting Consents**: member businesses manage revocable `allowed_report_sets` consents per group and publish legal-entity- and currency-tagged aggregate report snapshots.
  3. **Consolidated Group Analytics**: group organizers inspect consented reports grouped strictly by currency and report set without ownership transfer or cross-tenant raw data access.
- Real-browser Chromium Playwright E2E (`web/tests/enterprise.spec.ts` + `api/tests/integration/test_enterprise_browser.py`) across `desktop` and `mobile` (390px) viewports with `@axe-core/playwright` zero-violation check and direct PostgreSQL 18 read-back proving:
  1. Deprovisioned employee immediately loses access (`403 TENANT_ACCESS_DENIED`).
  2. Organizer receives ONLY consented report sets (`revenue_by_currency`), never unconsented sets (`headcount`), and revocation hides all entries immediately.
