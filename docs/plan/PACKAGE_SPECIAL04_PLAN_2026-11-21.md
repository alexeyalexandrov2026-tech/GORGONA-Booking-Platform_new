# Package SPECIAL-04 Plan — Staffing, Advisory, Organizations & Public Admin (2026-11-21)

- Branch: `codex/package-special-04-staffing-advisory-orgs-public`
- ADR: `docs/adr/0045-specialized-staffing-advisory-orgs-public.md`
- Migration: `0148_special_staffing_advisory_orgs_public.sql`
- Profiles covered: 30 (Finance & Insurance Advisory), 31 (Staffing & Recruiting),
  36 (Organizations & Associations), 39 (Public & Municipal Administration).
- Module: `public_civic` -> `Readiness.IMPLEMENTED` (`enableable=False`,
  `MODULE_REGISTRY_VERSION=16`, `len(MODULES)=28`).
- Permissions: `civic.read`, `civic.work`, `civic.manage` (`PERMISSIONS_VERSION=25`).
- Completes backend domain & migration coverage across **all 39 industry profiles (1..39)**.
