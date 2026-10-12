# Ready-to-paste prompt — Package I acceptance

```text
Continue GORGONA Booking Package I: the acceptance slice (WORK-01).

First read:
C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking
Branch: codex/package-i4-review-corrections (published)
Verified source commit: f41f9a849a34a732433bea75514da758e345b859 (CI success, run 38227457763). HEAD is a documents-only commit on top of it. Verify with git log and git ls-remote, and compare git rev-parse HEAD:<path> with FOLLOWUP_SOURCE_PROOF.json before changing anything. Do not reset, clean, amend or rebase.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, master/status/package-I plan, ADR-0025 and evidence/2026-10-12-i4-review-corrections/{FOLLOWUP_VALIDATION.md,PUBLICATION_CHECKS.json,FOLLOWUP_SOURCE_PROOF.json,INDEPENDENT_REVIEW_FOLLOWUP.md,CORRECTIONS_REVIEW_FOLLOWUP.md}. One executor per checkout and disposable PostgreSQL cluster.

State: corrections R2-1/R2-2/R2-3/CR-1 and the two browser-spec assertions are published. Local full serial suite PASS: 1526 passed, 4 skipped in 997.19s (0:16:37). CI PASS on the published commit. Matrix I-01..I-12 PASS. Package I is NOT accepted: WORK-01 and CORE-04 are still planned, the workforce module is closed, ADR-0025 is still Proposed.

The acceptance slice needs the owner's direct, named confirmation for WORK-01 before any readiness change. With it: follow the seven steps in the handoff (registry record citing the verified commit and schema 35; the workforce module must derive its readiness from WORK-01 in modules.py; tests that rely on the closed module move to a withdrawn acceptance, failing test first; CORE-04 as a separate commit under plan decision 9 with a short independent check; acceptance record; ADR-0025 accepted as implemented). Model commit: ec39622. Then focused, static/web and the full serial suite with PostgreSQL/browser required, an independent check of the acceptance commit, and exact-commit CI. Never rebuild web during the full run.

Read runner.py in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\i4-counterparty-locator-20261012-490652b before reuse (this is the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests, other tools do not): it hard-codes this checkout and refuses existing phase directories; use a new phase name and its own cluster. No secrets in logs or prompts. The CI job takes about 12 minutes on a fast GitHub runner and about 20 on a slow one; its limit is 30 minutes.

Production npm audit FAIL: 2 high next/source-map-js. No PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the publication permission of 2026-10-12 covers this branch only. Preserve other checkouts and immutable migrations 0001–0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
