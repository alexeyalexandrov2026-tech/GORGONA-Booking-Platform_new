# Ready-to-paste prompt — after main was fast-forwarded

```text
Continue GORGONA Booking. The whole platform is now on main.

First read:
C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking\docs\plan\NEXT_AGENT_AFTER_MERGE_2026-10-12.md

Repository state: main is at 8a34a8035f268cd757612e885b306c7b8b2ffcda (113 commits on top of the initial commit, migrations 0001-0035). It was fast-forwarded on the owner's decision with one push without force and no pull request; CI on main succeeded (run 38338644832). The execution record is one documents commit ahead of main on the branch codex/merge-plan, checked out in C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking. Read the exact SHAs from git log and git ls-remote before changing anything. Do not reset, clean, amend or rebase.

Start new work from origin/main in a new branch and a new worktree; do not switch or clean existing checkouts (seven of them hold uncommitted changes that were not examined). One executor per checkout and disposable PostgreSQL cluster.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, the master and status plans, docs/plan/MERGE_PLAN_2026-10-12.md with evidence/2026-10-12-merge-plan/{STACK.json,RESULT.json}, and for product state NEXT_AGENT_WEB_DEPENDENCY_AUDIT_2026-10-12.md and NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md.

State: WORK-01 and CORE-04 are technically_verified; npm audit --omit=dev passes with 0 findings; the full npm audit fails with 5 high in one development-only braces chain that has no fixed release. Pull requests #2-#5 are superseded and must never be merged. Pull request pages after the fast-forward: marked merged: #1; closed without merge: none; still open: #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22. Do not merge open pull requests with the GitHub button: their code is already on main, and squash or rebase would create new commits. No pilot, no production approval, nothing deployed. The manual workflows deploy-staging and promote-production are now visible in Actions and must not be run without a separate Azure decision.

Open slices: the remaining decisions of the merge plan (pull request pages, protection of main, carrying the execution record to main), the next stage 2 package, the untested workforce screen situations, an inventory of uncommitted changes in the worktrees. Start the one the owner names in the message that carries this prompt; if none is named, verify the state and ask the owner which slice to start.

Run folders with the runner scripts are in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests (the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests). Those scripts hard-code the package-i4-review-corrections checkout; a new worktree needs its own copy with its own path. No secrets in logs or prompts. The CI job takes about 12 minutes on a fast GitHub runner and about 20 on a slow one; its limit is 30 minutes. Never rebuild web during a full run.

No push/PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the permissions of 2026-10-12 are used up. Opening a pull request invokes CodeRabbit automatically. Preserve other checkouts and immutable migrations 0001-0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
