# Handoff — package R after R4c; next is R5 (2026-11-07)

Read [NEXT_AGENT_PACKAGE_R4C_2026-11-06.md](NEXT_AGENT_PACKAGE_R4C_2026-11-06.md) and [PACKAGE_R4C_DESIGN_2026-11-06.md](PACKAGE_R4C_DESIGN_2026-11-06.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R4b | `codex/package-r4b-rental-agreements` | `7e793ea` | `a098477` | `86d2cad` | 0101 | run 42291512691 success |
| R4c | `codex/package-r4c-rental-extensions` | `0cb38f2` | `c38efe8` | the docs commit with this file | 0102 | pushed with this commit; check it first |

Next migration **0103**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r4c-20261106-0cb38f2` (`adapt_r4c_record.py`).

Next: **R5** payment states of rental deposits and holds (requested, held, captured, released, expired), separate from
charges; no live provider without the owner's word.

Traps from R4c: a regex rename in SQL also touches comments; deferred constraint triggers need `set constraints all
immediate` inside the transaction so the error maps to the right code; `test_l7b_visit_desk_browser` and
`test_i4_browser` fail now and then and pass alone.
