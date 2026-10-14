# Ready-to-paste prompt — package J, slice J5b (Stock documents screen) committed

```text
Continue GORGONA Booking, stage 2 package J (basic materials, STOCK-01). Slices J1-J4, the review fixes and J5a (the Materials screen) are published with CI passed. Slice J5b — the Stock documents screen (/stock-documents/) — is committed as c3da59d on branch codex/package-j5b-stock-documents; with it slice J5 is complete. Nothing is merged into main.

First read:
C:\Users\alexa\.codex\worktrees\package-j5b-stock-documents\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_J5B_STOCK_DOCUMENTS_2026-10-14.md
then docs/plan/evidence/2026-10-14-j5b-stock-documents/VALIDATION.md, docs/plan/PACKAGE_J_PLAN_2026-10-13.md and docs/adr/0026-materials-and-stock-movements.md.

State. The complete local suite passed: 1735 passed, 4 skipped in 1587.30s (0:26:27). The real-browser test covers desktop and phone with zero axe violations: a receipt whose answer is lost and settled by its key without a second document, a refused write-off with a named reason, a transfer, a return against a receipt line, a discarded write-off whose late copy is refused, and a branch manager limited to own-branch transfers without amounts. Open: M2, L6, tests for J-12 and J-13, an independent review of J5, then the acceptance of J-01 to J-14.

Owner's words. 2026-10-13: «i trust you, you make decisions» (publishing package J branches without a pull request for CI; when to review). 2026-10-14: «Делай, как ты считаешь нужным. Я доверяю полностью тебе, и ты принимаешь решение.» (the three review questions and continuing package J). Neither authorizes merge, moving main, pull requests, deployment, readiness, Azure, provider, funds or credential actions.

Do first: read the git state and CI; publish this branch without a pull request if it is not published; then measure M2 and write the J-12 and J-13 tests. Failing test first, then code, static, focused, the complete suite, the record, a local commit. No PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
