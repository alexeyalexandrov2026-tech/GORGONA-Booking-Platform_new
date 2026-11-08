# Handoff — package R after R7b; next is R7c (2026-11-08)

Read [NEXT_AGENT_PACKAGE_R7B_2026-11-08.md](NEXT_AGENT_PACKAGE_R7B_2026-11-08.md) and [PACKAGE_R7B_DESIGN_2026-11-08.md](PACKAGE_R7B_DESIGN_2026-11-08.md)
first; same delegation and process.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| R7a | `codex/package-r7a-rental-settlement` | `5f968b9` | `31cf73d` | `2ef404e` | 0106 | run 42449693704 success |
| R7b | `codex/package-r7b-rental-damage-refunds` | `0453d6a`, `00c7dc0` | `b174d1b` | the docs commit with this file | 0107 | pushed with this commit; check it first |

Next migration **0108**. Run folder `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-r7b-20261108-00c7dc0` (`adapt_r7b_record.py`).

Next: **R7c** the reconciliation per agreement, derived on read (rental plan decision 8): charged (settlement and damage
charges), paid (FIN-03 allocations to those obligations), security held, captured and released (R5a), refunded (credit
notes and external refunds), and what is still open. No new money records.

VM: it stopped by itself (TERMINATED) on 2026-11-08 and was restarted on the owner word; its external IP changed to
34.68.238.190 while `~/.ssh/config` still names 34.30.251.0. Use `-o HostName=34.68.238.190 -o HostKeyAlias=34.30.251.0`
(the host key is unchanged and checked against the stored one); do not edit the owner's SSH config without asking.
Run long gates detached on the VM with nohup.
