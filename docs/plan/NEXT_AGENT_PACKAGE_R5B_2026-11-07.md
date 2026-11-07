# Handoff — package R after R5a; next is R5b (2026-11-07)

Read [NEXT_AGENT_PACKAGE_R5_2026-11-07.md](NEXT_AGENT_PACKAGE_R5_2026-11-07.md) and [PACKAGE_R5A_DESIGN_2026-11-07.md](PACKAGE_R5A_DESIGN_2026-11-07.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R4c | `codex/package-r4c-rental-extensions` | `0cb38f2` | `c38efe8` | `63b2318` | 0102 | run 42394185544 success |
| R5a | `codex/package-r5a-rental-security` | `5d25694` | `ffe05b8` | the docs commit with this file | 0103 | pushed with this commit; check it first |

Next migration **0104**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r5a-20261107-5d25694` (`adapt_r5a_record.py`).

Next: **R5b** provider holds in sandbox: a `card_hold` security held through the provider inbox (sandbox only, no live
provider without the owner's word), its events recorded from verified provider events.

Traps from R5a: on the VM use the project venv python (`api/.venv/bin/python`), never the system one; drop byte-equal
copies with `rm`, never `git clean`; the run glob `*-1` also matches `red-1`; Windows `sha256sum` marks files with `*`.
