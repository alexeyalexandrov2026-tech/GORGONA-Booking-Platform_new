# Handoff — package R after R3b; next is R4 (2026-11-03)

Read [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), [NEXT_AGENT_PACKAGE_R3B_2026-11-03.md](NEXT_AGENT_PACKAGE_R3B_2026-11-03.md)
and [PACKAGE_R3B_DESIGN_2026-11-03.md](PACKAGE_R3B_DESIGN_2026-11-03.md) first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R3a | `codex/package-r3-rental-assignment` | `ce29972` | `ab98936` | `cf9ff3f` | 0098 | run 41627679283 success |
| R3b | `codex/package-r3b-rental-blocks` | `427b8f0` | `b5cff95` | the docs commit with this file | 0099 | pushed with this commit; check it first |

Next migration **0100**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r3b-20261103-427b8f0` (`adapt_r3b_record.py`).

Next: **R4** rate cards, quotes and the frozen agreement; extensions and changes as versions (RENT plan row R4).

Traps from R3a and R3b: a migration may never `disable`/`no force` row security or use `security definer`
(`test_migration_files`); `copy_fixture_data` in `test_h3_upgrade.py` is an elif chain — a new rental row kind must be
left out in every earlier rule that matches its table, not only in a new later rule; the shared guard text is approved
literally by `schema_guard.py` (whitespace-insensitive) and by `workforce_guard.py` (it reads the latest migration that
replaces it), and the restore list in `test_workforce_guards.py` must carry every source kind; `rental_booking_peak`
now counts bookings and unreleased blocks together.
