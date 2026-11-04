# Handoff — package R after R4a; next is R4b (2026-11-04)

Read [NEXT_AGENT_PACKAGE_R4_2026-11-03.md](NEXT_AGENT_PACKAGE_R4_2026-11-03.md) and [PACKAGE_R4A_DESIGN_2026-11-04.md](PACKAGE_R4A_DESIGN_2026-11-04.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R3b | `codex/package-r3b-rental-blocks` | `427b8f0` | `b5cff95` | `90fb28f` | 0099 | run 41708625225 success |
| R4a | `codex/package-r4a-rental-rates` | `281d3f6` | `79d678f` | the docs commit with this file | 0100 | pushed with this commit; check it first |

Next migration **0101**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r4a-20261104-281d3f6` (`adapt_r4a_record.py`).

Next: **R4b** the agreement as the accepted quote, frozen (who accepted, the source: platform, paper or email, the
time; an optional signed copy as a document version), with the chosen extras; an extension or a change is a new
insert-only version checked against occupancy (the assigned unit's hold and the class availability).

The VM `gorgona-dev` gets a new external IP after every start: update `HostName` in the `gorgona-dev` SSH alias.
On Windows, compare hashes with `diff` of both `sha256sum` outputs; `sha256sum -c -` over Windows output fails.
