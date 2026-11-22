# ADR-0041: Enterprise Identity Lifecycle (SSO/SCIM Deprovisioning) & Consent-Based Group Reporting

- Status: Proposed (implemented behind `analytics` module `enableable=False` until acceptance)
- Date: 2026-11-21
- Scenario: `ENTERPRISE-01` (`docs/plan/GORGONA_MASTER_PLAN.md` §12.2, §12.5, §13, §14.1.1)

## Context
Master Plan §13 Stage 7 and §14.1.1 (`ENTERPRISE-01`) require:
1. Corporate Single Sign-On (SSO) provider configuration and employee lifecycle management where a **deprovisioned employee immediately loses access** (both direct business membership and any delegated access).
2. Group/holding consolidated analytics that **preserves Stage 1 ownership and group boundaries (ADR-0018)**: belonging to a group never transfers ownership or grants raw cross-tenant row access; the organizer receives **only explicitly consented report sets** attributed to each owner business, legal entity, and separate currency (never summing distinct currencies without explicit FX conversion).

## Decision
Implement `ENTERPRISE-01` in three incremental slices without `SECURITY DEFINER` and without bypassing RLS:
1. **Slice 1 (`0143_enterprise_sso_and_lifecycle.sql`)**:
   - Registers `ENTERPRISE_READ` / `ENTERPRISE_MANAGE` permissions (`PERMISSIONS_VERSION = 21`) and moves the existing optional `analytics` module to `Readiness.IMPLEMENTED` (`enableable = False`, `MODULE_REGISTRY_VERSION = 12`).
   - Adds `enterprise_sso_providers`, `enterprise_directory_links`, and append-only `enterprise_lifecycle_events` (all RLS-enforced with `gba_runtime` grants and `analytics` module write gates).
   - Deprovisioning a directory link atomically (in one transaction): transitions the link to `deprovisioned`, suspends the user's `gba.memberships` row (`status = 'suspended'`), marks active `gba.delegation_grant_members` removed (`removed_at = now()`), and records immutable lifecycle + audit events. Because `tenancy/authorization.py` checks `status = 'active' FOR SHARE` and rejects suspended users even via delegations, access stops immediately.
2. **Slice 2 (`0144_enterprise_group_reporting.sql`)**:
   - Adds `enterprise_group_report_grants` (owner-controlled allow-list of `allowed_report_sets`, revocable at any time) and `enterprise_group_report_snapshots` (owner-published, legal-entity- and currency-tagged aggregate metrics).
   - Uses explicit cross-company RLS read policies strictly scoped to `(organizer_tenant_id = current_tenant_id() AND active group membership AND active grant AND report_set = ANY(allowed_report_sets))` — preserving invoker rights and zero raw-table access across tenants.
   - Consolidated group reporting returns rows grouped by currency and legal entity, strictly filtering out revoked grants, left/removed group members, and unconsented report sets.
3. **Slice 3 (`/enterprise/` UI + real-browser E2E)**:
   - 3-tab responsive workspace (`/enterprise/`): SSO & Lifecycle, Group Reporting Consents, and Consolidated Group Analytics, verified on Chromium desktop & mobile (390px) with axe-core and PostgreSQL 18 read-back.
