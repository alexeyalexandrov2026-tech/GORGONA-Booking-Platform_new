# PROPERTY-01 6a · Move-out condition report and photos

Design for step 6 ("Акт выезда") of [the PROPERTY-01 plan](PACKAGE_PROPERTY01_PLAN_2026-11-14.md),
symmetric to [move-in 3c](PACKAGE_PROPERTY01_MOVE_IN_DESIGN_2026-11-15.md). Next migration: **0129**.

## Scope

- One immutable private move-out condition report (`gba.property_move_outs`) and 1–50 ordered
  PNG/JPEG photo versions (`gba.property_move_out_photos`) per lease.
- Requires a recorded move-in first (`foreign key (tenant_id, lease_id) references gba.property_move_ins`).
- `term_revision` must match the lease's current `term_revision` under the tenant agreement lock in
  `READ COMMITTED`.
- `moved_out_on` must fall within `[move_in.moved_in_on, coalesce(occupied_through, ends_on)]` and
  not exceed the branch's current local day.
- `report` must reference a non-archived stored ADR-0020 `report` document version that is distinct
  from the lease's move-in report version.
- Records structured `condition_summary` (`normal_wear` or `damage_noted`) and optional `note`
  (1–2000 characters, no control characters).
- Updates `gba.guard_property_lease_term()` so a recorded move-out cannot be extended or preceded
  by an earlier release (`property_lease_term_move_out`), while finalizing a release on or after
  `moved_out_on` remains allowed.
- Routes (`property.manage`, company-wide only):
  - `GET /v1/businesses/{business_id}/property/leases/{lease_id}/move-out`
  - `PUT /v1/businesses/{business_id}/property/leases/{lease_id}/move-out`

## Out of scope

- Deposit balance calculations, deductions, and owner statements (Step 6b, depends on Step 4
  jurisdiction/custody decisions).
- UI screens (follow in Step 5c/6 UI slice).
- Module enablement (`property.enableable`) and `readiness_registry.py` (`PROPERTY-01 = planned`)
  remain unchanged.
