# Package Plan: ENTERPRISE-01 (Corporate SSO/Lifecycle & Consent-Based Group Reporting)

Date: 2026-11-21
ADR: `docs/adr/0041-enterprise-sso-lifecycle-and-group-reporting.md`
Acceptance ID: `ENTERPRISE-01` ("Отключенный сотрудник теряет доступ; группа получает только разрешенные отчеты без переноса владения")

## Slices
1. **Slice 1 (`codex/package-enterprise-01-holding-and-governance`, migration `0143`)**:
   - `analytics` module `IMPLEMENTED` (`enableable=False`, `MODULE_REGISTRY_VERSION=12`), `ENTERPRISE_READ` / `ENTERPRISE_MANAGE` (`PERMISSIONS_VERSION=21`).
   - Corporate SSO provider registry, directory links, atomic deprovisioning (suspending `gba.memberships` + revoking delegation membership + immutable lifecycle & audit logs), and immediate 403 loss-of-access proof.
2. **Slice 2 (`codex/package-enterprise-01-group-reporting`, migration `0144`)**:
   - Consent-based `enterprise_group_report_grants` (`allowed_report_sets`) and `enterprise_group_report_snapshots` (owner business + legal entity + currency + report set).
   - Consolidated group report endpoint enforcing strict ownership boundaries, currency separation, and immediate revocation exclusion.
3. **Slice 3 (`codex/package-enterprise-01-ui`, no migration)**:
   - `/enterprise/` 3-tab UI + strict Zod contracts + real Chromium desktop & mobile (390px) E2E with axe-core and PostgreSQL 18 read-back.
