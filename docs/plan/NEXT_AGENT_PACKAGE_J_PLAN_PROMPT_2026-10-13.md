# Ready-to-paste prompt — package J plan approved, code not started

```text
Continue GORGONA Booking: the owner approved the plan of stage 2 package J (basic materials, STOCK-01); no package J code exists yet.

First read:
C:\Users\alexa\.codex\worktrees\package-j-plan\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_J_PLAN_2026-10-13.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\package-j-plan\Gorgona Booking
Branch: codex/package-j-plan. Base: fedd0f115f24aad52f6256298296e8c5123fb427, which was main when the slice started. On top of the base: two documents commits, the draft plan and the record of the owner's decisions. Read the exact SHAs from git log, and from git ls-remote origin whether the branch is published and where main is. Do not reset, clean, amend or rebase.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, the master and status plans, docs/plan/PACKAGE_J_PLAN_2026-10-13.md, docs/adr/0026-materials-and-stock-movements.md (Proposed), docs/adr/0023-ledger-foundation.md, docs/adr/0024-invoices-obligations-and-external-settlements.md, and for the repository state NEXT_AGENT_WORKFORCE_SCREENS_2026-10-13.md and NEXT_AGENT_AFTER_MERGE_2026-10-12.md. One executor per checkout and disposable PostgreSQL cluster.

State: documents only. On 2026-10-13 the owner chose twelve decisions, listed in the plan with the chosen and the rejected option. The main ones: materials carry cost by moving average and post journal entries with a new source kind stock in the book of the owning legal entity; receipts, write-offs and returns are posted only by a company-wide owner or manager, while a branch manager reads quantities, manages storage places of the branch and posts transfers inside it; the inventory module depends on finance; a purchase receipt credits a clearing account and creates no payable. Amounts and cost go to separate tables with the ledger's company-only policy. No package J code, test, migration, module registry or permission change exists. Readiness statuses did not change. No pilot, no production approval, nothing deployed.

Next: slice J1 in a new branch on top of this branch and a new checkout: module inventory in registry version 3 depending on finance, permissions version 7, materials and storage places with versions, row security by business and location, the module gate and a packaged schema check, API, migration 0036; no money in J1. Failing test first, then code, focused and full runs, independent review, commit. Then J2-J5 and the acceptance by the plan. STOCK-01 is promoted only in a separate acceptance commit by the owner's decision.

Other open slices: the remaining untested workforce screen situations, an inventory of uncommitted changes in the worktrees.

For J1 make a new run folder. The runner of the previous slice, in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\workforce-situations-20261012-455ab14 (the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests), hard-codes its own checkout: use it as a model, not against another checkout. Run the static phase first (it rebuilds web/out), then focused or full. Never rebuild web during a full run. No secrets in logs or prompts. In any browser test name the expected alert text; never assert a bare role=alert. A race counts only with an observed wait in pg_locks. CI names failed tests in annotations, readable without sign-in through GET /repos/{owner}/{repo}/check-runs/{job_id}/annotations; the CI job limit is 30 minutes.

No push/PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the permissions of 2026-10-12 and 2026-10-13 are used up. Opening a pull request invokes CodeRabbit automatically. Pull requests #2-#5 are superseded and must never be merged; do not merge any open pull request with the GitHub button. Preserve other checkouts and immutable migrations 0001-0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
