# Ready-to-paste prompt — after the workforce screen situations slice

```text
Continue GORGONA Booking after the workforce screen situations slice.

First read:
C:\Users\alexa\.codex\worktrees\workforce-screen-situations\Gorgona Booking\docs\plan\NEXT_AGENT_WORKFORCE_SCREENS_2026-10-13.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\workforce-screen-situations\Gorgona Booking
Branch: codex/workforce-screen-situations. On 2026-10-13 the owner chose to publish it and, after green CI on its exact commit, to fast-forward main to its head with one push; read from git ls-remote origin whether that has happened. Base: 455ab14c99eb8d05f532f798a7986b55b7e5d8b4, which is the earlier main (8a34a80) plus one documents commit, the record of the first fast-forward of main. On top of the base: fdcf124 with the fix and the tests, 81920e1 with the record, then the record of the owner's decision, then a change of the new spec and of CI. The first two CI runs of the branch (a62bf64 and a2bd82b) failed in the pytest step. CI now names failed tests in annotations, readable without sign-in through GET /repos/{owner}/{repo}/check-runs/{job_id}/annotations, and that named the cause: a check of the new spec accepted any alert, and on CI the route announcer of Next.js was a second one. The checks now name their message. In any browser test name the expected alert text; never assert a bare role=alert. Read the exact SHAs from git log and git ls-remote, and compare git rev-parse HEAD:<path> with changed_sources in evidence/2026-10-13-workforce-screen-situations/CHECKS.json before changing anything. Do not reset, clean, amend or rebase.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, the master and status plans, evidence/2026-10-13-workforce-screen-situations/{VALIDATION.md,CHECKS.json}, and for the repository state NEXT_AGENT_AFTER_MERGE_2026-10-12.md and MERGE_PLAN_2026-10-12.md. One executor per checkout and disposable PostgreSQL cluster.

State: eight situations the Package I acceptance listed as untested pass in a real browser on desktop and mobile (web/tests/workforce-situations.spec.ts, driven by api/tests/integration/test_i4_situations_browser.py). Two defects of the My shifts screen were found and fixed in web/components/my-shifts.tsx: shifts outside the chosen four weeks were listed, and a cut list was shown without a note. Local full serial suite PASS: 1532 passed, 4 skipped in 1419.45s (0:23:39). CI results are not written into the documents: read them from GitHub Actions for the exact commit. Server, API, migrations and readiness statuses did not change. No pilot, no production approval, nothing deployed.

Still untested: a real screen reader; review findings F2, F6 and N2 in a browser; note P3; the clock change on the Timesheets screen; real lists longer than 1000 records. Pull requests #2-#5 are superseded and must never be merged; do not merge any open pull request with the GitHub button.

Open slices: the remaining untested situations, a plan for stage 2 package J (basic materials, STOCK-01) for the owner's approval, an inventory of uncommitted changes in the worktrees. Start the one the owner names in the message that carries this prompt; if none is named, verify the state and ask the owner which slice to start.

Read runner.py in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\workforce-situations-20261012-455ab14 before reuse (the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests): it hard-codes this checkout and refuses existing phase directories. Run the static phase first (it rebuilds web/out), then focused or full. No secrets in logs or prompts. The CI job takes about 12 minutes on a fast GitHub runner and about 20 on a slow one; its limit is 30 minutes. Never rebuild web during a full run.

No push/PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the permissions of 2026-10-12 are used up, and the permission of 2026-10-13 covers publishing this branch and one fast-forward of main to its head. Opening a pull request invokes CodeRabbit automatically. Preserve other checkouts and immutable migrations 0001-0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
