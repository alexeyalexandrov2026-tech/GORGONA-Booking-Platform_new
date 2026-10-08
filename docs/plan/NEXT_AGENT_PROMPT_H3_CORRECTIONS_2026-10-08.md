# Copyable prompt — continue from the H3 payment corrections

Use the prompt below in the next agent's chat. It is continuation context and
boundaries; inspect current Git, remote, PR and CI state before any action.

~~~text
Continue GORGONA Package H from the H3 payment-corrections slice. Code commit
238b157d979e504cb84e0870c722d23356f4f520 (forward 0028) and a docs-only successor are pushed to origin on
branch codex/package-h3-payment-corrections. Pull requests may not exist yet for
this branch and for codex/package-h3-credits (the author's browser was signed
out of GitHub): check, and open exactly ONE draft PR per branch if none exists:
credits with base codex/package-h3-settlement-guards, then corrections with base
codex/package-h3-credits. Never a second PR for a branch.

Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
Checkout: C:\Users\alexa\Documents\ChatGPT\gorgona-h3-corrections (git worktree;
the stash stack is shared, never use bare git stash).
Stack: PR15 (H1) <- PR16 (H2) <- PR17 (H3 guards, c6c5d89) <- credits (0027,
807ed59) <- this branch (0028). Nothing is merged. Read the actual HEAD; inspect
the current-head CI first; if a run failed, diagnose and report before changing
source.

Read first, in this checkout: docs/plan/NEXT_AGENT_H3_CORRECTIONS_2026-10-08.md
(state, chronology, runbook, pitfalls), then
docs/plan/evidence/2026-10-08-h3-payment-corrections/VALIDATION.md, then the
parent handoffs NEXT_AGENT_H3_CREDITS_2026-10-07.md and
NEXT_AGENT_H3_GUARDS_2026-10-07.md.

WHAT THE SLICE DOES
Forward 0028_payment_corrections.sql (published: frozen) plus
settlements.void_payment / correct_payment and routes
POST .../settlements/{s}/confirmations/{p}/void and /correct. A void or a
correction is a new revision of the same payment under a new settlement event
(payment_voided / payment_corrected) and the expected settlement sequence; the
external identity stays bound forever. One transaction mirrors the replaced
version's journal (origin payment_correction), returns its allocations to the
reserve of a held settlement (a released one only loses P) and, for a
correction, confirms the replacement within that reserve with its own journal.
A void is final. P and R follow the latest revision
(gba.effective_payment_allocations). FINANCIAL_RECONCILIATION_REQUIRED without
effects for an issued credit, a refund obligation or another unknown sent
outcome; FINANCIAL_OUTCOME_UNRESOLVED for the payment's own unknown sent
remainder. SQL rechecks the whole payment at commit.

LOCAL EVIDENCE: see VALIDATION.md (full suite with mandatory PostgreSQL 18.6 and
browser, static and web gates, SQL mutation red, upgrade 0027 -> 0028 on a
populated database).

NEXT, in order
1. Verify HEAD/origin/PRs/current-head CI; open the missing draft PRs.
2. Independent review of 0025-0028 by someone other than the author.
   CodeRabbit skips drafts; triggering it needs the owner's OK.
3. Owner decisions listed in the credit and correction VALIDATION.md files.
4. Credit voids from migration 0029: mirror the credit journal, undo its C and
   cancel an untouched refund obligation atomically; refuse with
   FINANCIAL_RECONCILIATION_REQUIRED when the refund has an effective payment,
   a reserve or an unknown sent outcome. Race with observed pg_locks waits. Add
   any new table's scope section to the location-scope drift test list in
   tests/integration/test_location_access.py.
5. HawkScan and Docker gates when available; exact CI counts.

NOT AUTHORIZED: merge/auto-merge, force-push, rebase/amend of published
commits, reset/clean, deployment, production migration,
Azure/provider/funds/credentials actions, FIN-03/FIN-02 readiness promotion.
Keep all secrets outside Git and output; never print the DSN or password.

ENVIRONMENT (see the runbook in the handoffs): Python 3.14 venv at
C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv
(set PYTHONPATH to <checkout>\api\src); PostgreSQL 18.6 binaries in
%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\pgsql\bin; private cluster
port 51470, data, pwfile and helper scripts (tools\corrtest.ps1, credtest.ps1,
correction_upgrade_check.py, mutate_correction_sql.py) in
%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007 (stopped; start with
Start-Process pg_ctl without -Wait, poll pg_isready). Node 24 for the browser
suite. One executor per checkout and cluster; never run fixture suites
concurrently. Do not touch clusters 51454, 51455, 51458, 51456, 51460, 51462.
Preserve the owner checkout, E2, G, H1, H2, H3 guards, credits and review
worktrees. Keep SQL and test sources ASCII; LF endings. Published migrations
are frozen: fix forward with a new number.
KA Nails and the camera Local Gateway are separate projects.
~~~
