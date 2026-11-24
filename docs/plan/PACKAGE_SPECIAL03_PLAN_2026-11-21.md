# Package SPECIAL-03 Plan — Assets, Field Ops, Safety & Maintenance (2026-11-21)

- Branch: `codex/package-special-03-assets-agro-utilities-facilities`
- ADR: `docs/adr/0044-specialized-assets-field-ops.md`
- Migration: `0147_special_assets_field_ops.sql`
- Profiles covered: 27 (Agriculture), 28 (Utilities), 29 (Mining), 32 (Security),
  33 (Cleaning & Facilities), 34 (Environment & Waste).
- Module: `assets` -> `Readiness.IMPLEMENTED` (`enableable=False`, `MODULE_REGISTRY_VERSION=15`).
- Permissions: `assets.read`, `assets.work`, `assets.manage` (`PERMISSIONS_VERSION=24`).
- Gates: `ruff`, `mypy`, unit contracts, integration (lifecycle, safety lock on critical
  incident, decommissioned guard, idempotency, tenant/branch isolation, module gate),
  live upgrade `0146 -> 0147`, and full 6-worker parallel suite on `gorgona-dev`.
