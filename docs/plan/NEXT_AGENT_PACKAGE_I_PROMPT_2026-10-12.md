# Ready-to-paste prompt — after the Package I technical acceptance

```text
Continue GORGONA Booking after the Package I technical acceptance.

First read:
C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking
Branch: codex/package-i4-review-corrections (published)
Verified code: f41f9a849a34a732433bea75514da758e345b859. On top of it: the CORE-04 record (1b925f1becff730be33716dfcf2f89b367356c43), the WORK-01 acceptance commit (75f2b9bb1296f727678650bd72036e5f9140abb7; CI success, run 38236481277) and a documents-only commit. Read the exact SHAs from git log and git ls-remote, and compare git rev-parse HEAD:<path> with changed_sources in evidence/2026-10-12-work-01-acceptance/CHECKS.json before changing anything. Do not reset, clean, amend or rebase.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, master/status/package-I plan, ADR-0025 and evidence/2026-10-12-work-01-acceptance/{ACCEPTANCE.md,CHECKS.json,INDEPENDENT_CHECK.md}. One executor per checkout and disposable PostgreSQL cluster.

State: WORK-01 and CORE-04 are technically_verified; the workforce module is enableable by a company's own published configuration; ADR-0025 is accepted as implemented. Local full serial suite on the acceptance tree PASS: 1531 passed, 4 skipped in 972.96s (0:16:12). This is a technical acceptance only: no pilot, no production approval, no PR, nothing merged.

The handoff lists four candidate next slices (dependency audit remediation, a merge plan for the unmerged stack, the next stage 2 package, the untested workforce screen situations). Start the one the owner names in the message that carries this prompt; if none is named, verify the state, read exact-head CI and ask the owner which slice to start.

Read runner.py in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\i4-counterparty-locator-20261012-490652b before reuse (this is the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests, other tools do not): it hard-codes this checkout and refuses existing phase directories; use a new phase name and its own cluster. No secrets in logs or prompts. The CI job takes about 12 minutes on a fast GitHub runner and about 20 on a slow one; its limit is 30 minutes. Never rebuild web during a full run.

Production npm audit FAIL: 2 high next/source-map-js. No PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the publication permission of 2026-10-12 covers this branch only. Preserve other checkouts and immutable migrations 0001–0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
