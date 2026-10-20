# Ready-to-paste prompt — after K5b

Continue GORGONA Booking stage 2, Package K / FIN-02, locally and inline. Checkout
`C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
`codex/package-k5b-open-findings` (K5b source `58cf561d0f2d065ad44dac850182fdd61d3fae20` plus the docs
commit). Run `git status` and `git log -5 --oneline` first; the tree must be clean.

The owner's goal is production for **all 39 directions of the master plan at once** — never plan or
estimate a salon-only or one-industry launch (master plan, top block and §1 point 13).

Read, in this order: `docs/plan/NEXT_AGENT_PACKAGE_K5B_2026-10-20.md` (the whole file);
`docs/plan/NEXT_AGENT_PACKAGE_K0B_2026-10-20.md` sections 2, 5 and 6;
`docs/plan/NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md` sections 2 and 6;
`docs/plan/PACKAGE_K5_PLAN_2026-10-19.md`; `docs/plan/evidence/2026-10-20-k5b-open-findings/VALIDATION.md`;
`docs/runbooks/PROVIDER_OPERATIONS.md`; the master plan top block, §11, §11.2.1, §13 and §14; ADR-0027.

Next is K0c, the real Stripe test run, in the owner's sandbox only. The Stripe CLI is installed and
authorized for the sandbox `acct_1UJtGO0mkpVWlKYX`. First check whether Connect is enabled there
(`stripe accounts list`; with Git Bash set `MSYS_NO_PATHCONV=1`); if creating an account still says
"signed up for Connect", ask the owner to enable Connect in that sandbox. Then follow section 4 of the
K5b handoff: connected test account with Stripe's test values only, own local stack on 127.0.0.1,
admission, `stripe listen` with the signing secret kept in memory, three triggers, one payment and one
refund applied, a redacted record; then K5-CI and K5c.

Hard rules: no push, PR, merge, `main`, rebase, amend, reset, clean, force-push, readiness change,
CodeRabbit, Azure, production or live-mode provider action without the owner's separate direct word.
The owner alone signs in and accepts terms in Stripe; never enter a password, never read or print a
key or signing secret. Migrations 0001–0060 are immutable; the next is 0061. One executor and one own
disposable PostgreSQL cluster (explicit port, 127.0.0.1, `max_connections=400`; never 51454, 51458,
51474, 51511, 49981; check `postmaster.pid` before stopping; never `pg_ctl` with captured output).
Races only with an observed `pg_locks` wait. Secrets only in memory. Failing tests first; record every
failure. Do not touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`. Write to the owner in
Russian, simply; the owner is they/them. Report PASS/FAIL/BLOCKED/NOT TESTED with exact commands and
numbers.
