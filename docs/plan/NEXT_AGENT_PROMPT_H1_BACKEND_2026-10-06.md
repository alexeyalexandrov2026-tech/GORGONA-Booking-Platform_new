# Copyable prompt — continue H after the invoice backend

Use the prompt below in the next agent's chat. These are continuation context
and boundaries; inspect current Git/PR state before following dated evidence.

~~~text
Continue GORGONA Package H from the delivered H1 invoice backend. First read:

C:\Users\alexa\.codex\worktrees\package-h1-persistence\Gorgona Booking\docs\plan\NEXT_AGENT_H1_BACKEND_2026-10-06.md
and docs/plan/evidence/2026-10-06-h1-backend/VALIDATION.md in that checkout.

Repository: alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.
Delivered branch: codex/package-h1-persistence, stacked on codex/package-h-invoices
(backend PR15 → foundation PR14 → planning PR13 → G PR12).
Reviewed source: 2d5a8f917b69f1d52adea96aa8209722d1a24d42; documentation delivery
is a successor. Read actual current HEAD/origin/backend draft PR and exact-head CI.
Create your own codex/ branch and checkout from delivered backend HEAD.

H1 now has forward0021, seven insert-only RLS tables, real typed invoice
draft/read/history/issue and command resolve/cancel API. Issue atomically writes
immutable version/lines, principal obligation, one balanced G journal, lineage,
audit and permanent minimal receipt. Explicit account treatment, currency scale,
period/scope controls, immutable history and deferred final-graph checks apply.
Journal read-v2 handles invoice; old write-v1 and all-entry trial balance survive.
G generic reversal refuses H-owned entries. Existing ledger UI supports v2;
there is no invoice UI yet.

H1-R01 was independently reproduced on ac7726e and CLOSED on 2d5a8f9:
all 25 H CHECK predicates/validated status now have repository-owned exact
approval, literals preserve whitespace, and coupled invoice/principal lineage
is explicit. Independent 47 PostgreSQL tests, 109 relevant units and scoped
static checks passed in a separate checkout/cluster. Root focused H+all unit
533 passed; full local 953 passed/4 skipped/378.14s, mandatory real PG/browser.
Ruff/format/mypy 204 files PASS. Read current PR15 for exact-final-head CI.
Root PG51456 and reviewer51460 are stopped.
Independent full suite/web/browser/CI were not tested.

G/FIN-01 remains technically_verified. FIN-03/FIN-02 remain planned and
finance_documents non-enableable. Positive invoice integration fixtures override
readiness only for development; the real registry/published-configuration gate
and current-readiness withdrawal are tested. Do not promote H after H1 alone.
All twelve COMPLETE H acceptance rows remain NOT TESTED.

Next coherent work: H2 manual new-accrual obligations and immutable settlement
documents, preparation/approval/reserves/release/partial externally attested
confirmation. Reuse existing ledger posting seam, money conversion, auth,
READ COMMITTED ledger-before-membership lock order, audit and minimal recovery.
Use a new forward migration after published0021; preserve prior checksums.
Enforce nonnegative effective P/C/R and P+C+R<=original A in SQL and service.
Reserve posts no money; partial confirmation transfers exactly R→P and retains
the remainder. External identity remains permanently bound to one payment_id,
independent of browser idempotency. Allocations equal confirmed money exactly.
Sent/unknown outcomes need explicit resolution; OFF/timeout/tab close cannot
silently release them. No provider verification claim for manual attestation.

Then H3 credits/refund obligations and immutable guarded correction; H4 admission
metadata without capability activation and real desktop/mobile UI. Preserve
historical cash and explicit recognition choices. Invoice100/paid70/credit50
means C30/refund20. Actual refund, credit or sent/unknown dependencies require
reconciliation instead of a fake undo. Full FIN-03 needs all twelve acceptance
cases, independent money/state review, full exact-SHA CI and separate acceptance.

Read AGENTS.md, master/status/current Cloud Code handoff, ADR0023/0024 and H plan.
The owner already authorized continuing this local direction and draft
publication. Earlier approval-pending attached text is historical context.
No repeat permission loop for ordinary reversible work or disposable checks.
No merge/deployment/production migration/Azure/provider/funds/credential action.
KA Nails and camera Local Gateway are separate projects.

Preserve owner checkout (19 dirty paths at2f16380), incoming E2 checkout
(9 dirty paths at151472a), accepted G and delivered foundation/reviewer trees.
One executor per checkout and disposable PG cluster. Do not reset/clean/overwrite,
force-push or run shared fixture suites concurrently. Existing Python3.14 venv
can be reused, but set PYTHONPATH to your checkout; its editable source points G.
Node24, PostgreSQL18, mandatory real OIDC/browser and CI Docker checks are required.
Keep credentials outside Git and never print them. Do not touch old51454/51458.
Inspect current state, implement the smallest coherent phase, diagnose failures,
run fresh affected/project gates, and update exact evidence and next-agent handoff.
~~~
