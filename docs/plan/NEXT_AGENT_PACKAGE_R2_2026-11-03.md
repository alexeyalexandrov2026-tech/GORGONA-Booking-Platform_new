# Handoff — package R after R1; next is R2 (2026-11-03)

Read [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), [ADR-0036](../adr/0036-rental-classes-and-units.md),
[PACKAGE_R1_DESIGN_2026-11-03.md](PACKAGE_R1_DESIGN_2026-11-03.md) and [NEXT_AGENT_PACKAGE_O7B_2026-11-02.md](NEXT_AGENT_PACKAGE_O7B_2026-11-02.md)
(how runs go to the VM) first. The starting session relayed the owner's "continue" to build package R slice by slice with
the same process: design, failing tests, code, gates on the VM, record, code and docs commits, push for CI without a PR.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| O7b | `codex/package-o7b-construction-screens` | `1e94aec` | `ded715d` | `506f12c` | none | run 41578843175 success |
| R1 | `codex/package-r1-rental-catalog` | `889c69a` | `15a884d` | the docs commit with this file | 0096 | pushed with this commit; check it first |

Next migration **0097**; migrations 0001-0096 are immutable. `rental` is implemented and not enableable; tests use an
`accepted` fixture (`test_r1_rental_catalog.py`). Run folder: `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r1-20261103-889c69a`
(`adapt_r1_record.py` from the O6b writer reads `sources.txt`); on the VM `~/gba-runs/package-r1-20261103-889c69a`.
The VM checkout holds the R1 files uncommitted: check each against the fetched commit before the next checkout.

Next: **R2** class bookings (plan decision 3): a booking holds a class for a period with pickup and return branches,
accepted while available units of the class at the pickup branch minus overlapping bookings stay at or above zero,
checked under a lock per class and branch; two racing bookings for the last unit leave one with an observed
`pg_locks` wait (the `race` helper in `test_l8b2_finance_races.py`). Package O still has O7b2, O7c and O8.

Traps seen in R1: request models follow the construction convention (`extra="forbid", frozen=True`), never pydantic
strict mode (it refuses UUIDs sent as strings); the platform's 403 code is `PERMISSION_DENIED`.
