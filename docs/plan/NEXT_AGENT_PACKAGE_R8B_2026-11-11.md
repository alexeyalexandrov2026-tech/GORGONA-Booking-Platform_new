# Handoff — package R after R8a; next is R8b (2026-11-11)

Read [NEXT_AGENT_PACKAGE_R8_2026-11-09.md](NEXT_AGENT_PACKAGE_R8_2026-11-09.md) and [PACKAGE_R8A_DESIGN_2026-11-09.md](PACKAGE_R8A_DESIGN_2026-11-09.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R7c | `codex/package-r7c-rental-reconciliation` | `c16edcf` | `6876fee` | `a2bfc54` | none | run 42558093855 success |
| R8a | `codex/package-r8a-rental-screens` | `eef91e1` | `06b3c25` | the docs commit with this file | none | pushed with this commit; check it first |

Next migration **0108**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r8a-20261109-eef91e1` (`adapt_r8a_record.py`).

Next: **R8b** the rental screens for rate cards, the agreement, the security, handover and return inspections, and the
settlement with damage charges, refunds and the reconciliation, on the booking page of R8a (`web/components/rental.tsx`),
with strict contracts in `web/lib/rental-contracts.ts`, a real browser test on desktop and mobile and its Python driver
like `test_r8a_rental_browser.py`. Then **R9** acceptance of RENT-01; readiness only on the owner word.

VM: the idle cron stops it after 60 minutes without SSH; keep an SSH session open (`sleep` in the background) for the whole
work, not only the gates; each start needs the owner word and gives a new IP (read it with `gcloud compute instances
describe gorgona-dev`), passed as `-o HostName=<ip> -o HostKeyAlias=34.30.251.0` (the host key is unchanged).
