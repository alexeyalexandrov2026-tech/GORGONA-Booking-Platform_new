# Handoff — package R after R8c; next is R9 (2026-11-12)

Read [NEXT_AGENT_PACKAGE_R8_2026-11-09.md](NEXT_AGENT_PACKAGE_R8_2026-11-09.md),
[NEXT_AGENT_PACKAGE_R8C_2026-11-11.md](NEXT_AGENT_PACKAGE_R8C_2026-11-11.md) and
[PACKAGE_R8C_DESIGN_2026-11-11.md](PACKAGE_R8C_DESIGN_2026-11-11.md) first. Same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R8b | `codex/package-r8b-rental-agreement-screens` | `bf5dd55` | `b3528b8` | `977a96f` | none | run 43128481780 success |
| R8c | `codex/package-r8c-rental-settlement-screens` | `bc54650` | `c45d3da` | the docs commit with this file | none | pushed with this commit; check it first |

Next migration **0108**. Run folder: `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r8c-20261111-bc54650`
(`adapt_r8c_record.py`; the VM copy is `~/gba-runs/package-r8c-20261111-bc54650`).

R8 is complete: rental screens for the catalogue, availability and bookings (R8a), rate cards, the agreement and the
security (R8b), and inspections, usage, settlement, damage charges, refunds and the reconciliation (R8c). R8c is web
only.

Next: **R9**, acceptance of RENT-01. Rows R-01..R-10 are in [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md).
Do it like O8 for BUILD-01:

- an acceptance test of the whole rental scenario;
- the acceptance record;
- an independent review only with the owner's consent;
- readiness of rental only on the owner's word.

Known limits not on screen: photos on marks, agreement extensions and extras, rate card extras, provider evidence.
Credit refunds are offered on screen but tested through the API (R7b).

VM:

- Each start needs the owner's word and gives a new IP. The last one, on 2026-11-12, was `136.113.205.4`; the host
  key is unchanged. Pass `-o HostName=<ip> -o HostKeyAlias=34.30.251.0`.
- Keep an SSH session open for the whole work; the idle cron stops the VM after 60 minutes.
- Copy run folders back before the VM can stop. In R8c it stopped after the gates, and starting it again just to copy
  the results needed the owner's word a second time.
- Mind time zones in test data: a booking that crosses a daylight-saving change counts an extra rental day.
