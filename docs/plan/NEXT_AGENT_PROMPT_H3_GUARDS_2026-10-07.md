# Copyable prompt — continue from the H3 settlement guards (draft PR17)

Use the prompt below in the next agent's chat. It is continuation context and
boundaries; inspect current Git, remote, PR and CI state before any action.

~~~text
Continue GORGONA Package H from the H3 settlement-guards slice. Its commits,
push and ONE draft PR are COMPLETE; do not repeat them and do not open a second PR.

Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
Checkout: C:\Users\alexa\Documents\ChatGPT\gorgona-h3-guards (git worktree; the
stash stack is shared, never use bare git stash).
Branch: codex/package-h3-settlement-guards, parent e93ca5c (published H2,
codex/package-h2-settlements, draft PR16, unmerged; PR16 targets H1 PR15).
Code commits: 24ee21bf1d141479af5e18c83fa42431a80d6d8b (forward 0025, service,
guard, tests, docs) and 372da57e4a50bf97be13a533784e34c78e1ae509 (forward 0026,
self-review corrections). A later docs-only commit holds this handoff: read the
actual HEAD.
Draft PR17 (base codex/package-h2-settlements) is OPEN/DRAFT/unmerged:
https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/17
CI: 24ee21b push 37645658564 and PR 37649981128 success; 372da57 push
37654684082 and PR 37654689990 success. Test counts inside CI not yet read
(needs an authenticated client). Inspect the current-head CI first; if a run
failed, diagnose and report before changing source.

Read first, in this checkout: docs/plan/NEXT_AGENT_H3_GUARDS_2026-10-07.md
(state, chronology, runbook, pitfalls), then
docs/plan/evidence/2026-10-07-h3-settlement-guards/VALIDATION.md and
docs/plan/evidence/2026-10-07-h2-settlements/INDEPENDENT_MONEY_STATE_REVIEW_e93ca5c.md.

WHAT THE SLICE DOES
0025 and 0026 (both published, frozen) plus business/settlements.py:
F1 one identity per external fact: gba.external_identity_key(value, rule)
removes invisible characters, then NFKC, lowercase (pg_c_utf8), NFKC, trim;
interior whitespace preserved ('preserve' is the only rule; unknown rules
raise); raw text stored unchanged; enforced under the ledger lock in SQL and
first in the service. F2 a cash account is never an issued control account in
the same book. F3 entry_date on or after the accrual's issued_on;
actual_external_date not after today in the business time zone
(gba.business_timezone: latest local date among the business's location zones,
UTC only without locations). F4 readiness guard approves column-level
references and both helpers. The H2 review's four test gaps have tests.

LOCAL EVIDENCE on the code of 372da57: full suite with mandatory PostgreSQL 18.6
and browser 1053 passed / 4 skipped / 429.52s (3 container checks, optional
tenant site); affected suites plus unit 633 passed; ruff/format/strict mypy on
211 files PASS; web unchanged; red runs recorded; upgrade 0024 -> 0026 on a
database populated by H2's suites: only 0025/0026 applied, no row changed, 0
conflicting rows, H3 guard READY, H2 application fails closed (deploy migration
and application together).

NEXT, in order
1. Verify HEAD/origin/PR17/current-head CI.
2. Independent review of 0025, 0026 and confirm() by someone other than the
   author. CodeRabbit skips drafts; triggering it on PR17 needs the owner's OK.
3. Owner decisions listed in VALIDATION.md (latest-local-date rule, whitespace
   'preserve', look-alike punctuation not unified, issued-only control lock,
   linear identity scan).
4. Not run yet: HawkScan (no hawk runtime/API key), local Docker gates; record
   exact CI counts.
5. Documented follow-ups: IMMUTABLE identity key + unique expression index;
   inline-FK guard pattern for "alter table ... add column ... references".
6. When requested: the rest of H3 (credits, refund obligations, guarded
   immutable corrections) on top of this branch, new migrations from 0027;
   gba.obligation_balance still returns credited_minor = 0 and must be replaced
   forward. Invoice100/paid70/credit50 means C30/refund20; never rewrite
   historical cash; race credit against reserve and confirmation with observed
   pg_locks waits.

NOT AUTHORIZED: merge/auto-merge, force-push, rebase/amend of published
commits, reset/clean, deployment, production migration,
Azure/provider/funds/credentials actions, FIN-03/FIN-02 readiness promotion.
Keep all secrets outside Git and output; never print the DSN or password.

ENVIRONMENT (see the runbook in the handoff): Python 3.14 venv at
C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv
(set PYTHONPATH to <checkout>\api\src); PostgreSQL 18.6 binaries in
%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\pgsql\bin; private cluster
port 51470, data and pwfile in %LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007
(stopped; start with Start-Process pg_ctl without -Wait, poll pg_isready).
Node 24 for the browser suite. One executor per checkout and cluster; never run
fixture suites concurrently. Do not touch clusters 51454, 51455, 51458, 51456,
51460, 51462. Preserve the owner checkout, E2, G, H1 and review worktrees.
Keep SQL and test sources ASCII (tool inputs can decode \u escapes); LF endings.
Migrations 0001-0026 are published: never edit them.
KA Nails and the camera Local Gateway are separate projects.
~~~
