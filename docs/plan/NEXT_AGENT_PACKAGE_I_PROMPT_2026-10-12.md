# Ready-to-paste prompt — Package I corrections

```text
Continue GORGONA Booking Package I from the local correction handoff.

First read:
C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking
Branch: codex/package-i4-review-corrections (local, unpublished)
Base: 490652b3f01a1b3de2df2d2e6257fced6caf32e2
Code commit: 2bca502d7c0c1caf77e9d88a9238974c8bee258b
Spec commit: 3b9734cd90f76726a27ba604d6ee441d7d3cbfeb
The documents commit on top of them is HEAD. Verify with git log, and compare git rev-parse HEAD:<path> with FOLLOWUP_SOURCE_PROOF.json before changing anything. Do not reset, clean, amend or rebase.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, master/status/package-I plan, ADR-0025 and evidence/2026-10-12-i4-review-corrections/{FOLLOWUP_VALIDATION.md,FOLLOWUP_CHECKS.json,FOLLOWUP_SOURCE_PROOF.json,FOLLOWUP_AUTHOR_REVIEW.md}. VALIDATION.md and CHECKS.json in the same folder preserve the earlier failing run. Verify actual Git/worktrees/remote/exact-head CI before edits. One executor per checkout and disposable PostgreSQL cluster.

State: the R2-1/R2-2/R2-3/CR-1 corrections and the two browser-spec assertions are committed locally. Full serial suite PASS: 1526 passed, 4 skipped in 997.19s (0:16:37). The earlier failure was an unscoped getByRole("alert") that also matched the empty Next.js route announcer; both specs now name the conflict message. Exact-SHA CI is NOT TESTED because the branch is unpublished. The two spec lines have an author review only.

Next: obtain the owner's direct decision on publishing the branch; only then push and read exact-head CI with real logs. If the owner asks, run an independent review of 490652b..HEAD by a non-author. After green CI update the I-12 acceptance record. If any source changes, rerun focused, static/web and the full serial suite with PostgreSQL/browser required; never rebuild web during the full run.

Read runner.py in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\i4-counterparty-locator-20261012-490652b before reuse (this is the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests, other tools do not): it hard-codes this checkout and refuses existing phase directories; use a new phase name and its own cluster. No secrets in logs or prompts.

WORK-01/CORE-04 remain planned; workforce stays closed outside fixtures; Package I is not accepted. reason_source is required in strict v1 API/web DTO; matched API/web must release together. Production npm audit FAIL: 2 high next/source-map-js. No push/PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization. Preserve other checkouts and immutable migrations 0001–0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
