# Ready-to-paste prompt — after the web dependency audit slice

```text
Continue GORGONA Booking after the web dependency audit slice.

First read:
C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking\docs\plan\NEXT_AGENT_WEB_DEPENDENCY_AUDIT_2026-10-12.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\package-i4-review-corrections\Gorgona Booking
Branch: codex/web-dependency-audit (published on 2026-10-12 with the owner's permission). Base: 4630ca38832c0d6126f5c352f9c4e3f636ac085c, the published head of codex/package-i4-review-corrections, which this slice did not change. On top of the base: ab3e6b6bcaa020b47e505b126d7dc0735e1f4078 changes web/package.json and web/package-lock.json, 8a1a7ab65da54c23396cae4f780a0f379369673f adds the record (CI success, run 38315410876), then a documents-only commit. Read the exact SHAs from git log and git ls-remote, and compare git rev-parse HEAD:<path> with changed_sources in evidence/2026-10-12-web-dependency-audit/CHECKS.json before changing anything. Do not reset, clean, amend or rebase.

Read AGENTS.md, the current CLOUD_CODE_HANDOFF.md, master/status plan and evidence/2026-10-12-web-dependency-audit/{VALIDATION.md,CHECKS.json}; for Package I read NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md. One executor per checkout and disposable PostgreSQL cluster.

State: next 16.3.8, eslint-config-next 16.3.8, source-map-js 1.2.2. npm audit --omit=dev PASS: 0 findings. Full npm audit FAIL: 5 high in one development-only braces chain (GHSA-vfj7-8cjw-p6xm) that has no fixed release; do not downgrade eslint-config-next to clear it. Local full serial suite on the upgraded tree PASS: 1531 passed, 4 skipped in 1023.50s (0:17:03). CI of 8a1a7ab: success, run 38315410876. WORK-01 and CORE-04 stay technically_verified; no pilot, no production approval, no PR, nothing merged.

Open slices: a merge plan for the unmerged stack, the next stage 2 package, the untested workforce screen situations. Start the one the owner names in the message that carries this prompt; if none is named, verify the state and ask the owner which slice to start.

Read runner.py in C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\web-dependency-audit-20261012-4630ca3 before reuse (this is the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests, other tools do not): it hard-codes this checkout and refuses existing phase directories; use a new phase name and its own cluster. After changing web dependencies run npm ci --ignore-scripts and the static phase before a full run. No secrets in logs or prompts. The CI job takes about 12 minutes on a fast GitHub runner and about 20 on a slow one; its limit is 30 minutes. Never rebuild web during a full run.

No push/PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the publication permissions of 2026-10-12 cover codex/package-i4-review-corrections and codex/web-dependency-audit only. Preserve other checkouts and immutable migrations 0001–0035. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
