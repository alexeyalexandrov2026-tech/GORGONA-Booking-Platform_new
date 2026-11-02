# Handoff — package O (construction, BUILD-01) after O6a; next is O6b (2026-11-02)

Written by the agent that built O6a. Read it together with
[NEXT_AGENT_PACKAGE_O6_2026-11-02.md](NEXT_AGENT_PACKAGE_O6_2026-11-02.md): its sections 2 (worktrees), 3
(the slice process), 5 (hard rules) and 6 (traps) still apply unchanged.

## 1. Where things stand

| Slice | Branch | Design | Code | Docs | Migration |
|---|---|---|---|---|---|
| O5 pay applications with retainage | `codex/package-o5-pay-applications` | `67a6bed` | `11a5508` | `47ba8bd` | 0093 |
| O6a stage and final acceptance, retainage release | `codex/package-o6a-acceptance` | `a756265` | `c06ec73` | the docs commit with this file | 0094 |

The O6a branch starts from the O5 docs commit and was built in the O5 worktree
(`C:/Users/alexa/.codex/worktrees/package-o5/Gorgona Booking`). Start O6b there from the O6a docs commit:
`git switch -c codex/package-o6b-reconciliation`. Next migration: **0095**; 0001-0094 are immutable.
The O6a run folder is `C:/Users/alexa/AppData/Local/GorgonaBookingTests/package-o6a-20261102-a756265`
(copy `runner.py`, `run_gates.py`, `disk_monitor.ps1` and `adapt_o6a_record.py` from it).

## 2. What O6a decided that O6b builds on

- Acceptances (`construction_acceptances`): scope `phase` or `final`; the final one records
  `warranty_ends_on`; the warranty period runs from its `accepted_on` to that date. Warranty claims belong
  to that period (a claim date inside it; before the final acceptance there is no warranty).
- Accepted work is closed by triggers on measurements, change-order approvals and pay applications
  (`*_acceptance` triggers). A warranty repair is not a measurement or a change order.
- Retainage release (`construction_retainage_releases`) is a construction fact; FIN-03 collection of the
  retainage accruals is **not** blocked (O6a decision 9). The reconciliation view must show released,
  paid on the retainage obligations and any retainage paid before its release as a difference.
- Phase retainage is `construction_phase_retained` (per application, the phase's billed change times the
  rate, rounded down); the totals are in `GET acceptances` (`retained_minor`, `released_minor`,
  `held_minor`).

## 3. O6b scope (plan decisions 9-10, acceptance BUILD-01 and O-05)

- **Warranty claims**: items against the project with states (as O4b quality items: insert-only events),
  raised on a site date inside the warranty period; refused before the final acceptance or after the
  warranty end.
- **Repair cost**: link actual costs to a claim. O3b's `construction_cost_links` link STOCK-01 write-off
  lines, FIN-03 payables and WORK-01 time to budget lines (unique per fact, reversals as rows). Decide
  whether a claim is a new link target (a column on the link with a check that exactly one target is set,
  which means a new guard beside the 0090 one) or a separate link table; keep "each fact counted once"
  across both.
- **Reconciliation view** per project, all derived: contract sum (original + approved changes), budget,
  committed, actual (including warranty repair cost, shown apart), completed value, billed, retained,
  released, paid (FIN-03 obligations of the pay-application invoices and retainage accruals, through
  `settlements.load_obligation`), and the differences (for example billed minus paid, retained minus
  released, retainage paid before release). No stored margin or balance.

Then O7 (screens, real browser desktop and mobile, axe) and O8 (BUILD-01 and O-01..O-10 acceptance; an
independent review only with the owner's consent; readiness only on the owner's word).
