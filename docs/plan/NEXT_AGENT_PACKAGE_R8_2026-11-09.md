# Handoff — package R after R7c; next is R8 (2026-11-09)

Read [NEXT_AGENT_PACKAGE_R7C_2026-11-08.md](NEXT_AGENT_PACKAGE_R7C_2026-11-08.md) and [PACKAGE_R7C_DESIGN_2026-11-08.md](PACKAGE_R7C_DESIGN_2026-11-08.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R7b | `codex/package-r7b-rental-damage-refunds` | `0453d6a`, `00c7dc0` | `b174d1b` | `6f20a26` | 0107 | run 42511820796 success |
| R7c | `codex/package-r7c-rental-reconciliation` | `c16edcf` | `6876fee` | the docs commit with this file | none | pushed with this commit; check it first |

Next migration **0108**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r7c-20261108-c16edcf` (`adapt_r7c_record.py`).

Next: **R8** (rental plan): screens for the catalogue, the availability board, the booking, the agreement, handover,
return and settlement (with charges, refunds and the reconciliation), checked in a real browser on desktop and mobile
like the construction screens of O7b. Then **R9** acceptance of RENT-01 (R-01..R-10); readiness only on the owner word.

VM: the idle cron stops it after 60 minutes without SSH or load; keep one SSH session open during long gates. After a
restart its external IP may change (`gcloud compute instances describe gorgona-dev`); the host key is unchanged and is
checked with `-o HostKeyAlias=34.30.251.0`. Test dates follow the FAKE business zone America/New_York, not UTC.
