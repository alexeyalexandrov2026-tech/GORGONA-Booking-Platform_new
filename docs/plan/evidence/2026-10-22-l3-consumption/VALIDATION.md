# L3 — visit completion and material consumption: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l3-consumption`, parent `2402352`
([L3 design](../../PACKAGE_L3_DESIGN_2026-10-22.md)), source commit `4ed11af637138943173061799a5f73ec9b663ab9`. [CHECKS.json](CHECKS.json)
was written before the source commit and binds every source blob, command, exit code and log digest. No
network; readiness unchanged (BEAUTY-01 stays partial until L8).

## What changed

| Area | Change |
|---|---|
| Schema (0068) | `variant_materials`, `add_on_materials` (recipes in the material's smallest unit, at most 20 lines); `visit_completions` (one per booking; only a started confirmed booking of its branch; consumption posted once); `visit_material_uses` (planned and actual, written with the completion). Tenant policies, branch scope for completions and uses; the runtime role may not delete or rewrite them |
| Recipes | `PUT .../services/{variant}/materials`, `PUT .../add-ons/{id}/materials`: replaced whole with the expected revision (`catalog.manage`); the revision moves; a finer quantity than the material's scale or an unknown material is refused |
| Completion | `POST .../bookings/{id}/complete`: `booking.write` of a member, branch scope; the booking stays CONFIRMED; planned = recipes of every quoted variant and add-on; actual quantities replace them per material; idempotent by key; a second completion is `VISIT_ALREADY_COMPLETED` |
| Consumption | `POST .../bookings/{id}/consumption`: one STOCK-01 write-off (reason `used`) of the actual quantities at moving-average cost, once per visit; a company-wide member with `inventory.manage` and `finance.manage`, under the ledger lock |

## Failures kept

- **red-1**: 2 failed, 6 errors (routes 404, migration 0068 missing) — expected.
- Found while writing 0068, before any run: an unqualified `booking_id` in the uses branch policy would
  have compared a completion with itself; qualified.
- **full-1**: 2 failed — the row-security statements of 0068 were built in a loop, not written out
  (`test_migration_files`); completion was open to delegates, but delegation stays exactly the booking
  workspace (`test_delegation_contracts`). Both fixed; completion is for members.

## Gates (final, suffix 2)

Run folder `GorgonaBookingTests/package-l3-20261022-2402352`: **static-2** PASS; **focused-2** PASS, **257
passed**; **full-2** PASS, **2487 passed, 4 skipped**.

## Remaining

No test with the inventory module off for this route (the write-off refuses through STOCK-01's
`require_inventory`, covered by the stock tests). No screen for recipes, completion or consumption yet
(L7). Migrations 0001–0067 unchanged; the next is **0069**.
