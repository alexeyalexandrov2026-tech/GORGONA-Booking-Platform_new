# Ready-to-paste prompt — package J, slice J1 committed locally

```text
Continue GORGONA Booking, stage 2 package J (basic materials, STOCK-01): slice J1 is committed locally and is NOT published.

First read:
C:\Users\alexa\.codex\worktrees\package-j1-materials\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_J1_2026-10-13.md

Canonical checkout: C:\Users\alexa\.codex\worktrees\package-j1-materials\Gorgona Booking
Branch: codex/package-j1-materials, local, clean. Code and tests are commit 39fc819; one documents commit sits on top of it (read the head from git log). The branch sits on the plan branch codex/package-j-plan (fedd0f1 is main; fe368d9 the draft plan; 9032a69 the owner's decisions). Read from git ls-remote origin whether anything is published and where main is. Start with status, branch, HEAD, log, worktrees and remotes. Do not reset, clean, amend or rebase, and do not touch other checkouts.

Read AGENTS.md, docs/plan/PACKAGE_J_PLAN_2026-10-13.md (approved by the owner on 2026-10-13, twelve decisions; see its progress section), docs/adr/0026-materials-and-stock-movements.md (Proposed, with the J1 implementation notes), docs/plan/evidence/2026-10-13-j1-materials/VALIDATION.md, docs/adr/0023-ledger-foundation.md and docs/adr/0024-invoices-obligations-and-external-settlements.md.

State. The owner chose: materials carry moving-average cost and post journal entries with a new source kind stock in the book of the owning legal entity; receipts, write-offs and returns are posted only by a company-wide owner or manager, a branch manager reads quantities, manages storage places of the branch and posts transfers inside it; the inventory module depends on finance; a purchase receipt credits a clearing account and creates no payable; no negative balance; no server drafts. J1 holds no money: migration 0036 (stock_items, stock_item_versions, stock_places, stock_place_versions), a packaged schema check, contracts, service, API /v1/businesses/{id}/inventory/items and /places, permissions map version 7 (inventory.read, inventory.manage), module registry version 3. STOCK-01 stays planned; tests enable the module only by substituting readiness in fixtures.

Checks of J1, in the run folder C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-j1-20261013-9032a69 (the physical folder; the Claude app shows it under AppData\Local\GorgonaBookingTests): red-2 FAIL as expected before the code; green-2 PASS, 40 passed; static-1 PASS (the full npm audit still fails with the known 5 high in the development-only braces chain); full-1 PASS, 1573 passed, 4 skipped in 1342.47s, sources unchanged during the run, and the 19 checked files are byte-identical to commit 39fc819. NOT TESTED: independent review, CI (nothing is published), HawkScan (no runtime or key), a race of two commands on one material, refusal to a real delegate.

Do first:
1. Ask the owner two things, each needing a direct decision: whether to publish the branch and read CI (without opening a pull request, which would invoke CodeRabbit), and whether an independent review of J1 is wanted (spawn a reviewer agent only when the owner asks).
2. Meanwhile you may continue locally with slice J2 (posting rules for materials and receipts with amounts, migration 0037) in a new branch from the J1 head and a new worktree; do not switch this checkout. The handoff lists the code to model it on.
3. In J2: failing test first, then code, static, focused, the complete suite, the record, a local commit. Do not commit as green while the suite fails.

Run checks with runner.py <phase> <static|full|focused> [pytest files] in a run folder; the J1 runner is bound to the J1 checkout, so copy runner.py, write_record.py and apply_shared.py to a new run folder and fix ROOT, the branch and the base before the first run. Python: C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe with -X utf8. Run static first (it rebuilds web/out), then focused or full. Never change api/, web/ or web/out during a complete run. One executor per checkout and disposable PostgreSQL cluster. No secrets in logs or prompts. Write scripts that contain backslashes as files, not as shell heredocs. A race counts only with an observed wait in pg_locks. In any browser test name the expected alert text.

No push/PR/merge/readiness/deploy/production/Azure/provider/funds/credential actions or CodeRabbit without separate direct owner authorization; the permissions of 2026-10-12 and 2026-10-13 are used up. Opening a pull request invokes CodeRabbit automatically. Pull requests #2-#5 are superseded and must never be merged; do not merge any open pull request with the GitHub button. Migrations 0001-0035 are immutable. Finish with changed files, exact PASS/FAIL/BLOCKED/NOT TESTED and an updated handoff.
```
