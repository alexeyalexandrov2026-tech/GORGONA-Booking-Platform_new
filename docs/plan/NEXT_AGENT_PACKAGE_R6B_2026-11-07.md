# Handoff — package R after R6a; next is R6b (2026-11-07)

Read [NEXT_AGENT_PACKAGE_R6_2026-11-07.md](NEXT_AGENT_PACKAGE_R6_2026-11-07.md) and [PACKAGE_R6A_DESIGN_2026-11-07.md](PACKAGE_R6A_DESIGN_2026-11-07.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R5b | `codex/package-r5b-rental-provider-holds` | `58391fd` | `e4efe63` | `fc1c378` | 0104 | run 42413235532 FAIL: flaky browser check `tests/service-catalog.spec.ts:137`; no web change; rerun needs GitHub credentials |
| R6a | `codex/package-r6a-rental-inspections` | `7d5dec6` | `78db1a8` | the docs commit with this file | 0105 | pushed with this commit; check it first |

Next migration **0106**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r6a-20261107-7d5dec6` (`adapt_r6a_record.py`).

Next: **R6b** overdue time and meter excess derived from the inspections: the return time against the current period
end, and the meter distance against the agreement's included allowance per day (R4a) and its excess rate. Derived
only; charges, refunds and settlement are R7 (rental plan).

Traps from R6a: in PL/pgSQL a record field read before the record is assigned raises even inside a false branch, so
keep such values in plain variables; write `sources.txt` with Unix line ends (tar reads `` as part of the name); the
documents module must be enabled in a test before it makes a photo.
