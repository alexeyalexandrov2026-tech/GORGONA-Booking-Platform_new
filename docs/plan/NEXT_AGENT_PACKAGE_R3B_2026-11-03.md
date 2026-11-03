# Handoff — package R after R3a; next is R3b (2026-11-03)

Read [NEXT_AGENT_PACKAGE_R3_2026-11-03.md](NEXT_AGENT_PACKAGE_R3_2026-11-03.md) and [PACKAGE_R3A_DESIGN_2026-11-03.md](PACKAGE_R3A_DESIGN_2026-11-03.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R2 | `codex/package-r2-rental-bookings` | `d423d7e` | `e34ac3f` | `e96e8fc` | 0097 | run 41606651336 success |
| R3a | `codex/package-r3-rental-assignment` | `ce29972` | `ab98936` | the docs commit with this file | 0098 | pushed with this commit; check it first |

Next migration **0099**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r3a-20261103-ce29972` (`adapt_r3a_record.py`).

Next: **R3b** maintenance and blocks (a block occupies the unit's resource with a reason, through a new allocation
source kind; the shared guard must be replaced again from the 0098 body, and `schema_guard.py`, `workforce_guard.py`
and the restore list in `test_workforce_guards.py` updated together), moves between branches (a unit's branch and
its resource move together; refuse while it holds a future assignment), and R2 availability counting blocked units.

Traps from R3a: a migration may never `disable`/`no force` row security or use `security definer`
(`test_migration_files`); `copy_fixture_data` in `test_h3_upgrade.py` needs a rule for every new resource kind and
allocation source kind; the shared guard text is approved literally by `schema_guard.py` (whitespace-insensitive) and
by `workforce_guard.py` (it reads the latest migration that replaces it).
