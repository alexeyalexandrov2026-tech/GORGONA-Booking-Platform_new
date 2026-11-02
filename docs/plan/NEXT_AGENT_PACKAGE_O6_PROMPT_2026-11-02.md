# Ready-to-paste prompt — package O after O5 (next: O6)

Continue GORGONA Booking locally and inline. Checkout
`C:/Users/alexa/.codex/worktrees/package-o5/Gorgona Booking`, branch
`codex/package-o5-pay-applications`. Run `git status` and `git log -5 --oneline` first; the tree must
be clean. Do **not** use the worktree `package-l7b2b`: another session (an accessibility task) uses it
on branch `codex/a11y-table-regions`.

The owner's goal is production for **all 39 directions of the master plan at once**; never plan or
estimate a one-industry launch. Package O (construction, BUILD-01) is stage 4 build order. The owner
delegated it fully («Делай как считаешь нужным я доверяю тебе»): design, build and push each slice
branch for CI without a PR. That delegation covers nothing else.

Read, in this order:

1. `docs/plan/NEXT_AGENT_PACKAGE_O6_2026-11-02.md` (the whole file: state, worktrees, process, O6
   pointers, rules, traps).
2. `docs/plan/PACKAGE_O_PLAN_2026-10-30.md` (decisions 9-12 and the acceptance table).
3. `docs/plan/PACKAGE_O5_DESIGN_2026-11-01.md` and `PACKAGE_O4B_DESIGN_2026-11-01.md`.
4. The "Current checkpoint" at the top of `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md`.

First check the CI of the O5 docs commit:

```bash
curl -s "https://api.github.com/repos/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs?branch=codex/package-o5-pay-applications&per_page=3"
```

Report the result to the owner. Then start O6 (stage and final acceptance, retainage release,
warranty, reconciliation; migration **0094**; consider splitting it into O6a and O6b). Follow the
slice process in section 3 of the handoff: design commit, failing tests first (red-1 before any
code), code, dev-1, gates with `disk_monitor.ps1`, source-bound record, code and docs commits, then
push for CI without a PR.

Hard rules:

- No PR, merge, `main`, readiness, enabling a module, deploy, Azure, production migration or live
  provider without the owner's separate direct word.
- No rebase, amend, reset, clean, force-push, CodeRabbit or bare `git stash`.
- Migrations 0001-0093 are immutable.
- One executor and one disposable PostgreSQL 18 cluster per run. Never use ports 51454, 51458, 51474,
  51511 or 49981.
- A race test only with an observed `pg_locks` wait.
- Failing tests first. Record every slip («Не скрывай ни одного сбоя»).
- No edits to api/, web/ or docs/runbooks/ while tests run.
- Extra agents only with the owner's consent.
- Never touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.
- Write to the owner in Russian, simply. The owner is they/them. Report PASS/FAIL/BLOCKED/NOT TESTED
  with exact numbers.
