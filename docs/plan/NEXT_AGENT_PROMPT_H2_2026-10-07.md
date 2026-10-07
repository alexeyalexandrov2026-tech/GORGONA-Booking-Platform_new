# Copyable prompt — verify published H2, then continue H

Use the prompt below in the next agent's chat. These are continuation context
and boundaries; inspect current Git/remote/PR state before action.

~~~text
Continue GORGONA Package H from the published H2 backend. Owner-requested H2
commit/push and ONE draft PR are COMPLETE; do not repeat them.

FIRST TASK — verify delivery and review H2 boundaries

Checkout: C:\Users\alexa\Documents\ChatGPT\gorgona-h2-settlements
Branch: codex/package-h2-settlements; parent75e809b, codex/package-h1-persistence.
Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
Reviewed original eight Markdown changes committed/pushed as
75c36dac572c8420aa848d322717420d43555c87. Draft PR16 is OPEN/DRAFT/unmerged, targets H1 PR15.
Checkpoint CI37573680437 completed/success:1044 passed/1 skipped/381.36s, required real
PostgreSQL18.6/OIDC/Chromium/all3 Docker/image, 69 web tests/2.3s, static211 PASS.
A later documentation-only delivery records publication; inspect exact current
HEAD/origin/PR16/current-head CI. Code is unchanged from54852b4.
Full evidence: docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md.
Handoff: docs/plan/NEXT_AGENT_H2_2026-10-07.md.
Do not create another H2 PR. First review the H2 money/state design and listed
test gaps; independent review is NOT DONE. Then continue H3 in your own branch
and checkout from the final H2 delivery when that continuation is requested.

Not authorized: merge/auto-merge, force-push, rebase/amend of published commits,
reset/clean, deployment, production migration, Azure/provider/funds/credentials
or FIN-03/FIN-02 readiness promotion. Keep all secrets outside Git/output.
If a new CI fails, diagnose/report before changing source; source fixes require
fresh affected/full validation and a new independent review where applicable.

CONTEXT — what H2 is

Read docs/plan/NEXT_AGENT_H2_2026-10-07.md and
docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md in that checkout.

H2 adds three forward migrations after published 0021:
0022 manual accrual as a second kind of the immutable financial document, one
new obligation and one balanced "accrual" journal per issue; an existing manual
G entry is never linked or accrued again.
0023 settlement documents with prepare/approve/reserve/sent/release/cancel.
A reserve posts no money. gba.obligation_balance computes A/P/C/R from history;
deferred triggers and the service both enforce P,C,R >= 0 and P+C+R <= A.
A sent document is released only by an explicit attested_no_payment resolution
with reason and evidence; OFF, timeout or a lost response release nothing.
0024 externally attested partial confirmations: exactly R to P, remainder stays
reserved, one balanced "payment" journal, allocations equal the amount exactly,
no advance, no FX. External identity (book, direction, source account alias,
external reference) is unique forever and bound to one payment_id, independent
of the idempotency key. Attestation is always manual_attestation; nothing
claims provider verification.
Journal read schema 2 lists invoice, accrual, payment; write/read schema 1 are
unchanged. Generic G reversal refuses every H-owned kind in API and SQL.
Recovery for all families is in business/financial_commands.py.

Local evidence: full suite 1041 passed / 4 skipped with mandatory real
PostgreSQL 18.6 and OIDC/Chromium; Ruff/format/strict mypy on 211 files; web
typecheck/lint/format/69 unit/build. Races are proven with observed pg_locks
waits. Publication checkpoint CI PASS:1044 passed/1 skipped/381.36s, all3 Docker/image;
independent money/state review and HawkScan remain NOT DONE. Slice A has no
recorded red run. Final exact-head CI is separate: inspect current PR16.

G/FIN-01 remains technically_verified. FIN-03/FIN-02 remain planned and
finance_documents non-enableable. Positive H fixtures override readiness only
in tests. All twelve COMPLETE H acceptance rows remain NOT TESTED. Do not
promote H after H2. ADR-0024 remains Proposed.

Open owner/reviewer decisions, listed in the handoff: journal schema 2 extended
in place instead of schema 3; one person may prepare and approve; release frees
the whole unconfirmed remainder; a structurally exact confirmation written by
SQL alone commits without receipt or audit.

THEN — H3, on your own new branch and checkout from the published H2 head

H3 is credits, refund obligations and guarded immutable corrections.
Invoice100/paid70/credit50 means C30/refund20; never rewrite historical cash.
gba.obligation_balance already returns credited_minor = 0: replace it in a new
forward migration (0025+) so the existing cap check covers credits. Race credit
against reserve and confirmation with observed pg_locks waits. A real refund, a
sent/unknown outcome or a dependent credit needs reconciliation, never a silent
undo. New journal origins stay finite and are added together in SQL CHECK,
Pydantic and Zod. Then H4: admission metadata without capability activation and
real desktop/mobile UI. Full FIN-03 needs all twelve acceptance cases,
independent money/state review, exact-SHA CI and a separate acceptance commit.

Working rules from H2: add each new migration to _MIGRATIONS in
db/financial_guard.py; the latest create-or-replace function is the approved
one; every packaged H CHECK needs one CHECK_APPROVAL line; restore drift tests
with approved_check/widened_check/packaged_function from test_invoice_issue.py;
add the new "-- <Name> branch scope:" footer to test_location_access.py and the
definition count (now 63) in test_document_contracts.py; keep table-specific
new.<field> references in nested plpgsql ifs; start the local test cluster with
max_connections=400. Migrations 0022-0024 are published: never edit them.

Read AGENTS.md, master/status/current Cloud Code handoff, ADR0023/0024 and the
H plan. KA Nails and camera Local Gateway are separate projects.

Preserve the owner checkout (19 dirty paths at 2f16380), the E2 checkout
(9 dirty paths at 151472a), accepted G (5be6e7a), foundation (18e3f5e), H1
review (2d5a8f9) and delivered H1 backend (75e809b) trees. One executor per
checkout and disposable PG cluster. Do not run shared fixture suites
concurrently. The existing Python 3.14 venv can be reused, but set PYTHONPATH
to your checkout; its editable source points to G. Node 24, PostgreSQL 18,
mandatory real OIDC/browser and CI Docker checks are required. Do not touch
clusters 51454, 51455 or 51458. Inspect the current state, implement the
smallest coherent phase, diagnose failures, run fresh affected and project
gates, and update exact evidence and the next-agent handoff.
~~~
