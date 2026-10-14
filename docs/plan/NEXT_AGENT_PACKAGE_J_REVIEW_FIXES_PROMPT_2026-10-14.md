# Ready-to-paste prompt — package J, review fixes committed

```text
Continue GORGONA Booking, stage 2 package J (basic materials, STOCK-01). Slices J1-J4 are published with CI passed; an independent review of J1-J4 found no critical or high defect; its findings M1, L1, L2, L4, L5 and part of L3 are fixed in commit 33a3ec6 on branch codex/package-j-review-fixes; nothing is merged into main.

First read:
C:\Users\alexa\.codex\worktrees\package-j-review-fixes\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_J_REVIEW_FIXES_2026-10-14.md
then docs/plan/evidence/2026-10-14-j-review-fixes/VALIDATION.md, docs/plan/evidence/2026-10-13-j-review/REVIEW.md, docs/plan/PACKAGE_J_PLAN_2026-10-13.md and docs/adr/0026-materials-and-stock-movements.md. The handoff of slice J4 (docs/plan/NEXT_AGENT_PACKAGE_J4_RETURNS_2026-10-13.md) explains how to run the checks.

State. Migration 0041 refuses balance and cost rows that no document explains. Receipts and returned write-offs lock the existing balance rows before inserting new ones, so they no longer deadlock with transfers; a deadlock that still happens answers 409 STOCK_BUSY. An archived account of a stock entry answers 409 STOCK_ACCOUNT_ARCHIVED with its account_id. The supplier of a document is read only together with the amounts. The schema guard refuses rewrite rules. The CI job limit is 45 minutes (branch codex/ci-time-limit, the base of this branch). The complete local suite passed: 1724 passed, 4 skipped in 1300.24s (0:21:40). Open: M2 (measure commit-time checks with about 100k movements of one balance), L6 (deployment order of migration 0037), the screens (J5) and the acceptance of J-01 to J-14.

Owner's words. 2026-10-13: «i trust you, you make decisions» (publishing package J branches without a pull request for CI; when to review). 2026-10-14: «Делай, как ты считаешь нужным. Я доверяю полностью тебе, и ты принимаешь решение.» (the three questions of the review). Neither authorizes merge, moving main, pull requests, deployment, readiness, Azure, provider, funds or credential actions.

Do first: read the git state and CI; publish this branch without a pull request if it is not published; then slice J5. Failing test first, then code, static, focused, the complete suite, the record, a local commit. No PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
