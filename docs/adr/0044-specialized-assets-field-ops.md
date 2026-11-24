# ADR-0044: Assets, Inspections, Maintenance and Safety Incidents (SPECIAL-03)

- Status: Accepted (implemented, not enableable until jurisdictional acceptance and the owner's word)
- Date: 2026-11-21
- Stage: Stage 8 (Specialized industries: profiles 27, 28, 29, 32, 33, 34)
- Migration: `0147_special_assets_field_ops.sql`

## Context

Master plan §3 and §4 specify the `assets` optional module ("Assets and maintenance") and
specialized field/site profiles:
- 27: Agriculture and forestry
- 28: Energy and utilities
- 29: Mining and extraction
- 32: Security and safety
- 33: Cleaning and facility maintenance
- 34: Environment and waste

All six industries share a strict operational core: branch-owned managed assets or sites
(optionally owned by a counterparty), immutable compliance/patrol/meter inspections,
preventive/corrective/remediation work orders, and safety/environmental/security incidents.

## Decision

1. Transition the existing `assets` module in `modules.py` from `PLANNED` to
   `Readiness.IMPLEMENTED` (`enableable=False`, `MODULE_REGISTRY_VERSION = 15`,
   `len(MODULES) = 27`).
2. Add permissions `assets.read`, `assets.work`, `assets.manage` (`PERMISSIONS_VERSION = 24`,
   not delegated).
3. Store four branch-scoped, RLS-protected, module-gated tables in `0147`:
   `gba.managed_assets`, `gba.asset_inspections` (insert-only), `gba.asset_work_orders`,
   and `gba.asset_safety_incidents`.
4. Enforce industrial safety invariants on the server:
   - Logging a `critical` open incident moves an `active` asset to `out_of_service`.
   - An asset with any `open` `critical` incident cannot be set back to `active` until the
     incident is `contained` or `resolved`.
   - Decommissioned assets reject new active work orders.
   - Completed or cancelled work orders are terminal and cannot be reopened.
   - All mutations are idempotent via `gba.idempotency_keys` and recorded in `gba.audit_log`.
