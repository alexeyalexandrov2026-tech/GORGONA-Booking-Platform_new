# Handoff — package R after R5b; next is R6 (2026-11-07)

Read [NEXT_AGENT_PACKAGE_R5B_2026-11-07.md](NEXT_AGENT_PACKAGE_R5B_2026-11-07.md) and [PACKAGE_R5B_DESIGN_2026-11-07.md](PACKAGE_R5B_DESIGN_2026-11-07.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R5a | `codex/package-r5a-rental-security` | `5d25694` | `ffe05b8` | `7129d83` | 0103 | run 42404010560 FAIL: flaky visit-desk mobile axe check (`tests/visit-desk.spec.ts:65`); no web change; rerun needs GitHub credentials |
| R5b | `codex/package-r5b-rental-provider-holds` | `58391fd` | `e4efe63` | the docs commit with this file | 0104 | pushed with this commit; check it first |

Next migration **0105**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r5b-20261107-58391fd` (`adapt_r5b_record.py`).

Next: **R6** handover and return inspections, damage charges and refunds.

Traps from R5b: a charge receipt keeps only the captured amount (K5a), so an uncaptured hold shows `amount_minor` 0;
revoking a provider connection needs `revoked_reason`. Open test defect: `test_i4_browser` and
`test_l7b_visit_desk_browser` fail now and then and pass alone (separate task).
