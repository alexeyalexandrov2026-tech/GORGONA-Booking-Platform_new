# Ready-to-paste prompt — after K0b

Continue GORGONA Booking stage 2, Package K / FIN-02, locally and inline. Checkout
`C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
`codex/package-k0b-entry-points` (K0b source `1eacc1d73c4d13a759be95084d994ef1be6cf4fe` plus the docs commit). Run `git status` and
`git log -5 --oneline` first; the tree must be clean.

Read, in this order: `docs/plan/NEXT_AGENT_PACKAGE_K0B_2026-10-20.md` (the whole file);
`docs/plan/NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md` sections 2 and 6; `docs/plan/PACKAGE_K0A_DESIGN_2026-10-20.md`;
`docs/plan/PACKAGE_K5_PLAN_2026-10-19.md`; `docs/plan/evidence/2026-10-20-k0b-entry-points/VALIDATION.md`;
`docs/runbooks/PROVIDER_OPERATIONS.md`; the master plan §11, §11.2.1, §13 and §14; ADR-0027.

K0b added the owner's admission record (0057), the money gate (0058), the ingress and worker
processes and `gba-db admit-receipt-connection`; everything is synthetic and local. Next is K0c,
the owner's real Stripe test run: prepare a local stack on 127.0.0.1, ask the owner only for the
connected test account ID and its API version, then guide the owner through `stripe login`,
`stripe listen --forward-connect-to …`, the admission command and three triggers. The owner sets the
signing secret in their own terminal; never ask for it, never print it. Afterwards read the
database in the company's context and write a redacted record; then K5b and K5c.

Hard rules: no push, PR, merge, `main`, rebase, amend, reset, clean, force-push, readiness change,
CodeRabbit, Azure, production, provider, account, key, credential or money action without the
owner's separate direct word. Migrations 0001–0058 are immutable; the next is 0059. One executor
and one own disposable PostgreSQL cluster (explicit port, 127.0.0.1, `max_connections=400`; never
51454, 51458, 51474, 51511, 49981; check `postmaster.pid` before stopping; never `pg_ctl` with
captured output). Races only with an observed `pg_locks` wait. Secrets only in memory. Failing tests
first; record every failure. Do not touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.
Write to the owner in Russian, simply; the owner is they/them. Report PASS/FAIL/BLOCKED/NOT TESTED
with exact commands and numbers.
