# Ready-to-paste prompt — package J plan awaiting the owner's approval

```text
Continue GORGONA Booking: the plan of stage 2 package J (basic materials, STOCK-01) awaits the owner's approval.

First read:
C:\Users\alexa\.codex\worktrees\package-j-plan\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_J_PLAN_2026-10-13.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\package-j-plan\Gorgona Booking
Branch: codex/package-j-plan. Base: fedd0f115f24aad52f6256298296e8c5123fb427, which was main when the slice started. On top of the base: one documents commit. Read the exact SHA from git log, and from git ls-remote origin whether the branch is published and where main is. Do not reset, clean, amend or rebase.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, the master and status plans, docs/plan/PACKAGE_J_PLAN_2026-10-13.md, docs/adr/0026-materials-and-stock-movements.md (Proposed), docs/plan/STAGE2_PLAN_2026-10-06.md, and for the repository state NEXT_AGENT_WORKFORCE_SCREENS_2026-10-13.md and NEXT_AGENT_AFTER_MERGE_2026-10-12.md. One executor per checkout and disposable PostgreSQL cluster.

State: documents only. The plan lists eight owner decisions, each with a recommended option A; the answer "approved" without details means A in every row. The owner's "continue" asked for the plan; it did not approve the plan or any decision. No package J code, test, migration, module registry or permission change exists. The inventory module is planned and cannot be enabled today because it depends on products_services, which is not implemented; decision 4 changes that dependency. Decision 2 is the main one: the stage 2 plan expected the effects of package J to land in ledger entries, and the recommended option counts quantities only. Readiness statuses did not change. No pilot, no production approval, nothing deployed.

Do not start package J code before the owner answers the eight decisions. If the owner chooses anything other than A, update the plan and ADR-0026 first. Then start slice J1 in a new branch from main and a new checkout: failing test first, then code, focused and full runs, independent review, commit; migrations from 0036.

Other open slices: the remaining untested workforce screen situations, an inventory of uncommitted changes in the worktrees. Start the one the owner names in the message that carries this prompt; if none is named, verify the state and ask the owner which slice to start.

For J1 make a new run folder. The runner of the previous slice, in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\workforce-situations-20261012-455ab14 (the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests), hard-codes its own checkout: use it as a model, not against another checkout. Run the static phase first (it rebuilds web/out), then focused or full. Never rebuild web during a full run. No secrets in logs or prompts. In any browser test name the expected alert text; never assert a bare role=alert. A race counts only with an observed wait in pg_locks. CI names failed tests in annotations, readable without sign-in through GET /repos/{owner}/{repo}/check-runs/{job_id}/annotations; the CI job limit is 30 minutes.

No push/PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the permissions of 2026-10-12 and 2026-10-13 are used up. Opening a pull request invokes CodeRabbit automatically. Pull requests #2-#5 are superseded and must never be merged; do not merge any open pull request with the GitHub button. Preserve other checkouts and immutable migrations 0001-0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
