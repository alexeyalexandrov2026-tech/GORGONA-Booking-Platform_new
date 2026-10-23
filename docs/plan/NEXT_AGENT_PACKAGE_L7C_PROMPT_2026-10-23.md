# Ready-to-paste prompt — package L after L7b2b (L7c, then L8)

Continue GORGONA Booking locally and inline. Checkout
`C:/Users/alexa/.codex/worktrees/package-l7b2b/Gorgona Booking`, branch
`codex/package-l7b2b-prepaid-screens` (head: the handoff docs commit on top of `594682a`). Run
`git status`, `git log -5 --oneline` and `git ls-remote --heads origin` first; the tree must be clean.
Do not touch the other worktree `.../package-j-review2-fixes/Gorgona Booking` (another session works
there) or `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.

The owner's goal is production for **all 39 directions of the master plan at once**; never plan or
estimate a one-industry launch (master plan top block, §1 item 13; `AGENTS.md`). Package L builds the
beauty cycle BEAUTY-01 as shared platform parts with neutral words.

Read, in this order: `docs/plan/NEXT_AGENT_PACKAGE_L7C_2026-10-23.md` (whole file);
`docs/plan/PACKAGE_L_PLAN_2026-10-22.md`; `docs/plan/PACKAGE_L7_DESIGN_2026-10-22.md`;
`docs/plan/PACKAGE_L2_DESIGN_2026-10-22.md` decisions 8–15; the newest
`docs/plan/evidence/2026-10-23-l7b2b-prepaid-screens/VALIDATION.md`; the master plan top block, §13, §14.

State: slices L1–L7b2b are done, each published for CI only and green; `main` is `0591d3a` (behind
the chain); migrations 0001–0071 are immutable, the next is 0072; BEAUTY-01 stays partial.

Do next, under the owner's full delegation («Делай как считаешь нужным и правильным! Я полностью даю
тебе право выбора»): **L7c**, the customer site — a guest books several services in one visit and sees
the stages of a staged visit (the API already accepts `extra_lines` and answers version 2 quotes). Then
**L8**, BEAUTY-01 acceptance — but ask the owner first for consent to one independent review agent, and
for their word before any readiness change or fast-forward of `main`.

Process for every slice: design and decisions committed first; failing tests first and recorded; a run
folder with `runner.py`, `run_gates.py`, `write_record.py` copied from
`GorgonaBookingTests/package-l7b2b-20261023-fa30344`; `run_gates.py N` (static → focused → full);
`write_record.py N` before the code commit; docs commit (VALIDATION.md, CHECKS.json, checkpoints in
GORGONA_IMPLEMENTATION_STATUS.md, GORGONA_MASTER_PLAN.md, CLOUD_CODE_HANDOFF.md); push the branch for
CI only (no PR); watch CI by branch; update memory. Python: use
`C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking/api/.venv/Scripts/python.exe`
(this worktree has no venv; the runner puts this worktree's `api/src` first).

Hard rules: no PR, merge, `main`, rebase, amend, reset, clean, force-push, readiness change, CodeRabbit,
Azure, production, deployment or live-mode provider action without the owner's separate direct word.
Stripe test mode only; the owner alone signs in; never enter or print a password, key or secret. One
executor, one own disposable cluster (never ports 51454, 51458, 51474, 51511, 49981). Races only with an
observed `pg_locks` wait. Never hide a failure. Tests take "today" in the branch or business zone, never
UTC. Every `<select>` gets an `aria-label`. An extra agent only with the owner's consent. GateGuard
denies the first Bash and the first write of each file once: state the facts, then retry. Write to the
owner in Russian, simply; the owner is they/them. Report PASS/FAIL/BLOCKED/NOT TESTED with exact
commands and numbers. Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
