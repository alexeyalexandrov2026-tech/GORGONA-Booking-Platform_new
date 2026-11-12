# Handoff — package R after R8b; next is R8c (2026-11-11)

Read [NEXT_AGENT_PACKAGE_R8_2026-11-09.md](NEXT_AGENT_PACKAGE_R8_2026-11-09.md),
[NEXT_AGENT_PACKAGE_R8B_2026-11-11.md](NEXT_AGENT_PACKAGE_R8B_2026-11-11.md) and
[PACKAGE_R8B_DESIGN_2026-11-11.md](PACKAGE_R8B_DESIGN_2026-11-11.md) first. Same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R8a | `codex/package-r8a-rental-screens` | `eef91e1` | `06b3c25` | `454c70f` | none | run 43058107935 failed in the web build step (browser install); rerun 43061387414 on the empty commit `9b60600` success |
| R8b | `codex/package-r8b-rental-agreement-screens` | `bf5dd55` | `b3528b8` | the docs commit with this file | none | pushed with this commit; check it first |

The R8b branch starts from `454c70f`, not from the empty commit `9b60600`.

Next migration **0108**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r8b-20261111-bf5dd55`
(`adapt_r8b_record.py`; the VM copy is `~/gba-runs/package-r8b-20261111-bf5dd55`).

The R8b session stopped after gates-1 on the VM, before the record. A new session read the results, started the VM
again on the owner's word, copied the run folder back, wrote the record and committed. Everything is recorded in the
record's `FAILURES`.

Next: **R8c**, the rental screens for:

- handover and return inspections (R6a);
- overdue time and meter excess (R6b);
- the final settlement (R7a);
- damage charges and refunds (R7b);
- the reconciliation per agreement (R7c).

Build them on the booking page next to `web/components/rental-agreement.tsx`, with strict contracts in
`web/lib/rental-contracts.ts`, a real browser test on desktop and mobile and its Python driver like
`test_r8b_rental_agreement_browser.py`. Then **R9**, acceptance of RENT-01 (R-01..R-10). Readiness only on the owner's
word.

VM:

- On 2026-11-11 it was started on the owner's word and has external IP `35.222.102.154`. Pass it as
  `-o HostName=35.222.102.154 -o HostKeyAlias=34.30.251.0`; the host key is unchanged.
- The idle cron stops it after 60 minutes without SSH. Keep an SSH session open (`sleep` in the background) for the
  whole work.
- Each start needs the owner's word and gives a new IP: read it with
  `gcloud compute instances describe gorgona-dev --zone us-central1-a --project gorgona-one-ai`.

The worktree `.codex/worktrees/package-o5` is shared by the package O and R sessions; read `git status` before acting.
Leave its untracked `.claude/` folder alone.
