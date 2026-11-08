# Handoff — package R after R6b; next is R7 (2026-11-07)

Read [NEXT_AGENT_PACKAGE_R6B_2026-11-07.md](NEXT_AGENT_PACKAGE_R6B_2026-11-07.md) and [PACKAGE_R6B_DESIGN_2026-11-07.md](PACKAGE_R6B_DESIGN_2026-11-07.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R6a | `codex/package-r6a-rental-inspections` | `7d5dec6` | `78db1a8` | `18470ae` | 0105 | run 42426865948 success |
| R6b | `codex/package-r6b-rental-usage` | `af3f01f` | `010692f` | the docs commit with this file | none | pushed with this commit; check it first |

Next migration **0106**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r6b-20261107-af3f01f` (`adapt_r6b_record.py`).

Next: **R7** (rental plan): final settlement through FIN-03, damage charges with approval, refunds; reconciliation per
agreement. Inputs already exist: the frozen agreement total (R4b/R4c), the recorded security and its captures (R5a/R5b),
the inspections and damage marks (R6a) and the derived overdue time and meter excess (R6b, `GET bookings/{id}/usage`).
Read FIN-03 (finance documents) before the design; split R7 if it is large.

Traps: a test fixture may move a recorded time only as the owner and only for FAKE data; write heredoc-free Python
files with the Write tool on Windows (backslash paths break escapes).
