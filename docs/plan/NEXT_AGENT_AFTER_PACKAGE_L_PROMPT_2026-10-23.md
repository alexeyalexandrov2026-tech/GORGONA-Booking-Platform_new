You continue GORGONA Booking after package L (BEAUTY-01 complete). Work in
`C:/Users/alexa/.codex/worktrees/package-l7b2b/Gorgona Booking`. Read
`docs/plan/NEXT_AGENT_AFTER_PACKAGE_L_2026-10-23.md`, then sections 5-7 of
`docs/plan/NEXT_AGENT_PACKAGE_L7C_2026-10-23.md`, and follow them exactly.

Goal: production for all 39 directions at once; never a single-industry launch. Next work: stage 3, TMS-01..03
(carrier first): plan, design, failing tests first, slices with gates and source-bound records, push for CI
only.

Hard rules: no PR, merge, `main` change, readiness change, rebase, amend, reset, force-push, deployment,
production migration or live provider action without the owner's separate word. One executor and one
disposable PostgreSQL 18 cluster per run. Never hide a failure. Write to the owner in Russian, simply; the
owner is they/them. Two decisions wait for the owner: BEAUTY-01 readiness and bringing `main` up to the
package L chain.
