# Ready-to-paste prompt — package J, slice J5a (Materials screen) committed

```text
Continue GORGONA Booking, stage 2 package J (basic materials, STOCK-01). Slices J1-J4 and the review fixes are published with CI passed. Slice J5a — the Materials screen (/materials/) and settling an uncertain inventory command by its key (POST /inventory/commands/{key}/resolve and /cancel) — is committed as afda55b on branch codex/package-j5-screens; nothing is merged into main.

First read:
C:\Users\alexa\.codex\worktrees\package-j5-screens\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_J5_MATERIALS_2026-10-14.md
then docs/plan/evidence/2026-10-14-j5-screens/VALIDATION.md, docs/plan/PACKAGE_J_PLAN_2026-10-13.md and docs/adr/0026-materials-and-stock-movements.md. The handoff of slice J4 explains how to run the checks.

State. The complete local suite passed: 1734 passed, 4 skipped in 1279.06s (0:21:19). The real-browser test covers desktop and phone, axe with zero violations, a lost answer settled after a reload, a resend under the same key and a discarded command whose late copy is refused. Open: J5b (the Stock documents screen), M2, L6, tests for J-12 and J-13, the acceptance of J-01 to J-14.

Owner's words. 2026-10-13: «i trust you, you make decisions» (publishing package J branches without a pull request for CI; when to review). 2026-10-14: «Делай, как ты считаешь нужным. Я доверяю полностью тебе, и ты принимаешь решение.» (the three review questions and continuing package J). Neither authorizes merge, moving main, pull requests, deployment, readiness, Azure, provider, funds or credential actions.

Do first: read the git state and CI; publish this branch without a pull request if it is not published; then slice J5b in a new branch from its head. Failing test first, then code, static, focused, the complete suite, the record, a local commit. No PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
