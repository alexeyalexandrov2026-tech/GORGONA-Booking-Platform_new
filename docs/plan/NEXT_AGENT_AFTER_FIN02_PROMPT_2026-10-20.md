# Ready-to-paste prompt — after FIN-02 technical acceptance

Continue GORGONA Booking locally and inline. Checkout
`C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
`codex/package-k5c-fin02-readiness` (code `ea74bec` plus the docs commit). Run `git status` and
`git log -5 --oneline` first; the tree must be clean.

The owner's goal is production for **all 39 directions of the master plan at once**; never plan or
estimate a one-industry launch (master plan top block, §1 point 13; `AGENTS.md`).

Read, in this order: `docs/plan/NEXT_AGENT_AFTER_FIN02_2026-10-20.md` (whole file);
`docs/plan/NEXT_AGENT_PACKAGE_K5B_2026-10-20.md` section 3 (rules) and 4 (the K0c run);
`docs/plan/evidence/2026-10-20-fin-02-acceptance/ACCEPTANCE.md`;
`docs/plan/evidence/2026-10-20-k5r-review-fixes/VALIDATION.md`; the master plan top block, §13 and §14.

FIN-02 is technically verified within its limits; packages J and K are on stacked branches not yet in
`main`. Start by proposing a merge plan to the owner (merging needs their word), then the next work
they choose: FIN-02 gaps (K-05, K-12), the STOCK-01 record, or the industry modules toward one launch
of all 39 directions.

Hard rules: no push of a new branch, PR, merge, `main`, rebase, amend, reset, clean, force-push,
Azure, production or live-mode provider action without the owner's separate direct word. The owner
alone signs in and accepts terms in Stripe; never enter a password, SSN or key. Migrations 0001–0062
are immutable; the next is 0063. One executor and one own disposable PostgreSQL cluster (explicit
port, 127.0.0.1, `max_connections=400`; never 51454, 51458, 51474, 51511, 49981; check
`postmaster.pid` before stopping; never `pg_ctl` with captured output). Races only with an observed
`pg_locks` wait. Secrets only in memory. Failing tests first; record every failure. Do not touch
`C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`. Write to the owner in Russian, simply; the owner is
they/them. Report PASS/FAIL/BLOCKED/NOT TESTED with exact commands and numbers.
