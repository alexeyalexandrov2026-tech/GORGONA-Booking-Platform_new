# Copyable prompt — continue H after H2

Use the prompt below in the next agent's chat. These are continuation context
and boundaries; inspect the current Git state before following dated evidence.

~~~text
Continue GORGONA Package H from the local H2 backend. First read:

C:\Users\alexa\Documents\ChatGPT\gorgona-h2-settlements\docs\plan\NEXT_AGENT_H2_2026-10-07.md
and docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md in that checkout.

Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
H2 branch: codex/package-h2-settlements, parent 75e809b (delivered H1 backend,
codex/package-h1-persistence, draft PR15 → PR14 → PR13 → G PR12).
The H2 branch is LOCAL ONLY unless Git shows otherwise: not pushed, no pull
request, no CI run. Read the actual current HEAD and remote state first.
Create your own branch and checkout from the current H2 HEAD.

H2 adds three forward migrations after published 0021:
0022 manual accrual as a second kind of the immutable financial document, one
new obligation and one balanced "accrual" journal per issue; existing
manual/opening G entries are never linked or accrued again.
0023 settlement documents with prepare/approve/reserve/sent/release/cancel.
A reserve posts no money. gba.obligation_balance computes A/P/C/R from history;
deferred triggers and the service both enforce P,C,R >= 0 and P+C+R <= A.
A sent document is released only by an explicit attested_no_payment resolution
with reason and evidence; OFF, timeout or a lost response release nothing.
0024 externally attested partial confirmations: exactly R → P, remainder stays
reserved, one balanced "payment" journal, allocations equal the amount exactly,
no advance, no FX. External identity (book, direction, source account alias,
external reference) is unique forever and bound to one payment_id, independent
of the idempotency key. Attestation is always manual_attestation; nothing
claims provider verification.
Journal read schema 2 now lists invoice, accrual, payment; write/read schema 1
are unchanged. Generic G reversal refuses every H-owned kind in API and SQL.
Recovery for all families is in business/financial_commands.py.

Local evidence is in the H2 validation file: full suite with mandatory real
PostgreSQL 18.6 and OIDC/Chromium, Ruff/format/strict mypy on 211 files, web
typecheck/lint/format/69 unit/build. Races are proven with observed pg_locks
waits. NOT done: exact-head CI and Docker gates (unpublished), independent
money/state review, HawkScan. Slice A has no recorded red run.

G/FIN-01 remains technically_verified. FIN-03/FIN-02 remain planned and
finance_documents non-enableable. Positive H fixtures override readiness only
in tests. All twelve COMPLETE H acceptance rows remain NOT TESTED. Do not
promote H after H2. ADR-0024 remains Proposed.

Open owner/reviewer decisions, listed in the handoff: publication; journal
schema 2 extended in place instead of schema 3; one person may prepare and
approve; release frees the whole unconfirmed remainder; a structurally exact
confirmation written by SQL alone commits without receipt or audit.

Next coherent work: H3 credits, refund obligations and guarded immutable
corrections. Invoice100/paid70/credit50 means C30/refund20; never rewrite
historical cash. gba.obligation_balance already returns credited_minor = 0:
replace it in a new forward migration (0025+) so the existing cap check covers
credits. Race credit against reserve and confirmation with observed pg_locks
waits. A real refund, a sent/unknown outcome or a dependent credit needs
reconciliation, never a silent undo. New journal origins stay finite and are
added together in SQL CHECK, Pydantic and Zod. Then H4: admission metadata
without capability activation and real desktop/mobile UI. Full FIN-03 needs all
twelve acceptance cases, independent money/state review, exact-SHA CI and a
separate acceptance commit.

Working rules from H2: add each new migration to _MIGRATIONS in
db/financial_guard.py; the latest create-or-replace function is the approved
one; every packaged H CHECK needs one CHECK_APPROVAL line; restore drift tests
with approved_check/widened_check/packaged_function from test_invoice_issue.py;
add the new "-- <Name> branch scope:" footer to test_location_access.py and the
definition count (now 63) in test_document_contracts.py; keep table-specific
new.<field> references in nested plpgsql ifs; start the local test cluster with
max_connections=400.

Read AGENTS.md, master/status/current Cloud Code handoff, ADR0023/0024 and the
H plan. No merge/deployment/production migration/Azure/provider/funds/credential
action. Ask the owner before any push or pull request. KA Nails and camera
Local Gateway are separate projects.

Preserve the owner checkout (19 dirty paths at 2f16380), the E2 checkout
(9 dirty paths at 151472a), accepted G (5be6e7a), foundation (18e3f5e), H1
review (2d5a8f9) and delivered H1 backend (75e809b) trees. One executor per
checkout and disposable PG cluster. Do not reset/clean/overwrite, force-push or
run shared fixture suites concurrently. The existing Python 3.14 venv can be
reused, but set PYTHONPATH to your checkout; its editable source points to G.
Node 24, PostgreSQL 18, mandatory real OIDC/browser and CI Docker checks are
required. Keep credentials outside Git and never print them. Do not touch
clusters 51454, 51455 or 51458. Inspect the current state, implement the
smallest coherent phase, diagnose failures, run fresh affected and project
gates, and update exact evidence and the next-agent handoff.
~~~
