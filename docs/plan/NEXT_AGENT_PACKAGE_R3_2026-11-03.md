# Handoff — package R after R2; next is R3 (2026-11-03)

Read [NEXT_AGENT_PACKAGE_R2_2026-11-03.md](NEXT_AGENT_PACKAGE_R2_2026-11-03.md) (process and traps) and
[PACKAGE_R2_DESIGN_2026-11-03.md](PACKAGE_R2_DESIGN_2026-11-03.md) first. Same delegation and process: design, failing
tests, code, gates on the VM, record, code and docs commits, push for CI without a PR.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R1 | `codex/package-r1-rental-catalog` | `889c69a` | `15a884d` | `101e3ad` | 0096 | run 41590287564 success |
| R2 | `codex/package-r2-rental-bookings` | `d423d7e` | `e34ac3f` | the docs commit with this file | 0097 | pushed with this commit; check it first |

Next migration **0098**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r2-20261103-d423d7e`
(`adapt_r2_record.py` from the R1 writer); on the VM `~/gba-runs/package-r2-20261103-d423d7e`. The VM checkout holds the
R2 files uncommitted: check each against the fetched commit before the next checkout.

Next: **R3** (plan decisions 3 and 7): assigning a unit to a booking occupies the unit for the period on the shared
occupancy (ADR-0022 exclusion; read how `gba.resources` and occupancy work first), replacement ends the earlier
assignment, maintenance and blocks occupy the unit with a reason, and moves between branches. Decide how a unit
becomes an occupancy resource (a `gba.resources` row of its own kind, or a rental-only exclusion constraint) in the R3
design. When a unit is assigned at another branch, availability of R2 must count it there.

Flaky under load (record, rerun alone, rerun the gates): `test_i4_browser`, `test_l7b_visit_desk_browser` (mobile axe).
