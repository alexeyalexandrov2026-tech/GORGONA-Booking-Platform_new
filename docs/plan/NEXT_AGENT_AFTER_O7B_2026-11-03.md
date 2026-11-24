# Handoff — package O after O7b; then O7b2, O7c, O8 and package R (2026-11-03)

Read [NEXT_AGENT_PACKAGE_O7B_2026-11-02.md](NEXT_AGENT_PACKAGE_O7B_2026-11-02.md) (how O7a ran on the VM) first;
the same process holds. The delegation covers designing, building and pushing slice branches **for CI only, without
a PR**.

| Slice | Branch | Design | Code | Docs | CI |
|---|---|---|---|---|---|
| O7a | `codex/package-o7a-construction-screens` | `074d42c` | `6c5ea3d` | `dec2b58` | run 41568069482 success |
| O7b | `codex/package-o7b-construction-screens` | `1e94aec` | `ded715d` | the docs commit with this file | pushed with this commit; check it first |

No migration since 0095; next migration **0096**. Run folders: `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-o7b-20261102-1e94aec`
(`adapt_o7b_record.py` reads `sources.txt`) and `~/gba-runs/package-o7b-20261102-1e94aec` on the VM. The VM checkout
`~/gorgona` holds the O7b files uncommitted: check each against the fetched commit before the next checkout.

Next in package O: **O7b2** cost links (check which STOCK-01, FIN-03 and WORK-01 reads can offer the facts before
designing the pickers), **O7c** (quality, retainage, pay applications, acceptances, warranty, reconciliation) and
**O8** (acceptance). The starting session asked to move on to **package R (RENT-01)** after O7b:
[PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md) holds the proposed decisions and slices R1-R9.

Trap seen in O7b: a `<label>` that wraps a `<select>` takes the option texts into its accessible name; keep
placeholders free of other labels' words, and give a select its own `htmlFor` label when a test matches it exactly.
