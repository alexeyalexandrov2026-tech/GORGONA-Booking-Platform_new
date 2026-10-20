# Ready-to-paste prompt — after K5a-fix (updated 2026-10-20)

Continue GORGONA Booking stage 2, Package K / FIN-02, locally and inline, as Claude in this
checkout only: `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, branch
`codex/package-k5a-review-fixes` (source `76f776447b0b4fcb1699047aa2fa496531ee6b34`, docs
`7b08507`, published for CI only, run 39371433810 SUCCESS; plus a local handoff update). Do not
touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.

Read first, in this order: `AGENTS.md`; `docs/plan/NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md` (state,
master plan reminder, rules, next step, how a slice is run, traps); the master plan
`docs/plan/GORGONA_MASTER_PLAN.md` §1 (main decisions), §11.2.1 (provider admission: test access
never allows production payments), §13 (stage order) and §14 (readiness); the K5 plan
`docs/plan/PACKAGE_K5_PLAN_2026-10-19.md`; the K5a review and the K5a-fix VALIDATION and
CHECKS.json; `docs/runbooks/PROVIDER_OPERATIONS.md`; ADR-0027 and ADR-0012.

State: K1f–K4b, K3b and K5a-fix are locally verified (K5a-fix focused 527 passed, full 2250
passed, 4 skipped). Migrations 0001–0056 immutable; next 0057. FIN-02 planned; ADR-0027 Proposed.

Your task now: **K0a** — write `docs/plan/PACKAGE_K0A_DESIGN_2026-10-20.md` with defaults and
questions to the owner, before any code: an owner-recorded admission (migration 0057, aligned with
§11.2.1, test access only), an ingress entry point on `127.0.0.1` that reads the signing secret by
environment variable name and fails closed, a worker entry point, the K0b tests, and the exact
commands the owner will run in K0c. Commit it as docs only, show it to the owner in Russian,
simply and briefly, and stop for the answers. Then K0b on a new branch, failing tests first.

Hard rules: no push, PR, merge, `main` change, rebase, amend, reset, clean, force-push, readiness
change, CodeRabbit, Azure or cloud action, production migration, deployment, provider, account,
key, credential or money action without the owner's separate direct word. Each Stripe step
(login, `stripe listen`, triggers) is the owner's; never enter, read aloud or print a secret.
One executor and one disposable PostgreSQL cluster (explicit port, 127.0.0.1, max_connections
400, never ports 51454, 51458, 51474, 51511, 49981). Races only with an observed `pg_locks` wait.
Never hide a failure or commit as green while a required suite fails. Report PASS, FAIL, BLOCKED
or NOT TESTED with exact commands and numbers. The owner is they/them. Commit trailer:
`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
