# Handoff — package R after R4b; next is R4c (2026-11-06)

Read [NEXT_AGENT_PACKAGE_R4B_2026-11-04.md](NEXT_AGENT_PACKAGE_R4B_2026-11-04.md) and [PACKAGE_R4B_DESIGN_2026-11-06.md](PACKAGE_R4B_DESIGN_2026-11-06.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R4a | `codex/package-r4a-rental-rates` | `281d3f6` | `79d678f` | `4902f23` | 0100 | run 41900546592 success |
| R4b | `codex/package-r4b-rental-agreements` | `7e793ea` | `a098477` | the docs commit with this file | 0101 | pushed with this commit; check it first |

Next migration **0102**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r4b-20261106-7e793ea` (`adapt_r4b_record.py`).

Next: **R4c** extensions and shortened periods: a new agreement version with a new period that moves the booking
period, the class availability (the peak) and the assigned unit's hold on the shared occupancy together.

Traps from R4b: plpgsql reads an IF condition up to the first THEN, so a CASE inside it breaks the parse; the runtime
role has no update grant on insert-only tables, so a guard can lock only rows it may update (the class row).
