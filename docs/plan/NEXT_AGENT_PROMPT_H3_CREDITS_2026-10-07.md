# Copyable prompt — continue from the H3 credit notes

Use the prompt below in the next agent's chat. It is continuation context and
boundaries; inspect current Git, remote, PR and CI state before any action.

~~~text
Continue GORGONA Package H from the H3 credit-notes slice. Code commit
76ed64e849983c770c00966581dfb560f91238f5 (forward 0027) and a docs-only
successor are pushed to origin. A pull request may not exist yet (the author's
browser was signed out of GitHub): check, and if none exists open exactly ONE
draft PR with base codex/package-h3-settlement-guards; never a second one.

Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
Checkout: C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credits (git worktree; the
stash stack is shared, never use bare git stash).
Branch: codex/package-h3-credits, parent c6c5d89 (head of draft PR17,
codex/package-h3-settlement-guards, unmerged). Stack: PR15 (H1) <- PR16 (H2)
<- PR17 (H3 guards) <- this branch. Read the actual HEAD; inspect the
current-head CI first; if a run failed, diagnose and report before changing
source.

Read first, in this checkout: docs/plan/NEXT_AGENT_H3_CREDITS_2026-10-07.md
(state, chronology, runbook, pitfalls), then
docs/plan/evidence/2026-10-07-h3-credits/VALIDATION.md, then the parent
handoff docs/plan/NEXT_AGENT_H3_GUARDS_2026-10-07.md.

WHAT THE SLICE DOES
Forward 0027_credit_notes.sql (published: frozen) plus
business/credit_notes.py and routes
GET/PUT .../books/{book}/credits[/{document}], POST .../credits/{document}/issue.
A credit note is a third immutable document kind crediting one invoice or
manual-accrual obligation line by line. At issue the unpaid balance is credited
first (C of the obligation); the paid part becomes a separate opposite-direction
credit_refund obligation (100 / paid 70 / credit 50 -> C 30, refund 20). One
'credit' G journal; G reverse refuses it. Rules in the service and again in SQL
at commit: no active reserved/sent reserve, line capacity, reason exactly when
the counter account differs (optional citation of a same-book same-currency G
entry), explicit open opposite-type non-cash refund account exactly when a
refund arises, posting not before the accrual. gba.obligation_balance derives C
from issued credits. The refund settles through the existing settlements.

LOCAL EVIDENCE: see VALIDATION.md (full suite with mandatory PostgreSQL 18.6 and
browser, static and web gates, red checks including a SQL mutation red, upgrade
0026 -> 0027 on a populated database).

NEXT, in order
1. Verify HEAD/origin/PR/current-head CI.
2. Independent review of 0025/0026 (PR17) and 0027 (this branch) by someone
   other than the author. CodeRabbit skips drafts; triggering it needs the
   owner's OK.
3. Owner decisions listed in VALIDATION.md.
4. H3 remainder from migration 0028: payment corrections (confirmed/corrected/
   voided, replacement under expected revision, external identity kept,
   effective P/R) and credit voids (mirror credit, undo C, cancel an untouched
   refund claim), with FINANCIAL_RECONCILIATION_REQUIRED for an issued credit, a
   real refund or a sent/unknown dependency; race them with observed pg_locks
   waits; never undo a real refund.
5. HawkScan and Docker gates when available; exact CI counts.

NOT AUTHORIZED: merge/auto-merge, force-push, rebase/amend of published
commits, reset/clean, deployment, production migration,
Azure/provider/funds/credentials actions, FIN-03/FIN-02 readiness promotion.
Keep all secrets outside Git and output; never print the DSN or password.

ENVIRONMENT (see the runbook in the handoffs): Python 3.14 venv at
C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv
(set PYTHONPATH to <checkout>\api\src); PostgreSQL 18.6 binaries in
%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\pgsql\bin; private cluster
port 51470, data, pwfile and helper scripts (tools\credtest.ps1,
guardskeep.ps1, credit_upgrade_check.py, mutate_credit_sql.py) in
%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007 (stopped; start with
Start-Process pg_ctl without -Wait, poll pg_isready). Node 24 for the browser
suite. One executor per checkout and cluster; never run fixture suites
concurrently. Do not touch clusters 51454, 51455, 51458, 51456, 51460, 51462.
Preserve the owner checkout, E2, G, H1, H2, H3 guards and review worktrees.
Keep SQL and test sources ASCII; LF endings. Published migrations are frozen:
fix forward with a new number.
KA Nails and the camera Local Gateway are separate projects.
~~~
