# GORGONA — current E1 continuation, 2026-10-05

Start here, then read [AGENTS](../../AGENTS.md), [master plan](GORGONA_MASTER_PLAN.md),
[registry](GORGONA_IMPLEMENTATION_STATUS.md), [audit](GORGONA_PLAN_AUDIT_2026-10-04.md),
[ADR-0020](../adr/0020-counterparties-documents-and-contracts.md),
[Package E plan](PACKAGE_E_PLAN_2026-10-04.md) and
[E1 acceptance](evidence/2026-10-05-counterparties/ACCEPTANCE.md).
Earlier E0/D/October-4 handoffs are history; their TODOs and counts are not current.

## Repository and preservation

- Active repository: [GORGONA-Booking-Platform_new](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new).
- E1 checkout: `C:\Users\alexa\.codex\worktrees\booking-state-isolation\Gorgona Booking`.
  Branch `codex/package-e1-counterparties`, based on E0 `bbe6ecd80d8827ca94a63f15587704ffc22dba62`.
  Before edits, fetch and inspect current HEAD/PR/CI; the code/CI identifiers are
  in acceptance. Do not assume a historical SHA is the latest HEAD.
- E1 draft PR targets `codex/package-e-isolation-audit`, whose
  [draft PR #6](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/6)
  targets `codex/universal-business-foundation`. Neither is merged by this work.
- Owner checkout: `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`, branch
  `codex/universal-business-foundation`, last inspected HEAD
  `2f1638011987e06923468b64600de1d1f4a14020`; its 14 modified and 5 untracked
  files plus 6 ignored drafts were preserved. Never reset/clean/restore it.
- Old PR #2–5 lineage has different migration numbering. Do not combine it blindly
  with the current lineage: current 0011 departments, 0012 delegation,
  0013 groups, 0014 configuration, 0015 counterparties.
- Separate branches/checkouts for agents; one executor owns the shared disposable
  PostgreSQL suite. Reviewer checkout `counterparty-review` is separate/read-only.

## What E1 adds

Five append-only FORCE-RLS tables in migration 0015; versioned cards/contacts,
normalized match suggestions, manual merged/distinct/separated decisions, and
confirmed link/unlink to booking snapshots. One hybrid business has one list;
groups do not grant visibility. Merge transfers no data and rejects cycles,
chains and duplicate decisions for the same revision even in staged direct SQL.
History and idempotent results stay immutable; current merged children are read
separately. Audit and receipts contain references, not counterparty names/contacts.

Company-wide owner/manager only; permission map v4. Branch members, delegated
operators, platform support, artists/front desk and other companies are refused.
34 guarded access definitions; five optional-module gates and the booking gate
check source/metadata/arguments, including VOLATILE. Mutation breaks readiness
and company-wide E1 handlers fail closed.

Page `/counterparties/`: search, paged cards, contacts, history, explicit duplicate
check/decision, fresh merge-target confirmation, separation and manual booking
links. Lost-response retry retains the same in-memory command; version conflict
requires reload. Disabled modules permit history/reads and prevent new commands.

**Initial readiness: implemented, not enableable.** After exact code CI succeeds,
a separate acceptance commit may promote only counterparties to technically_verified;
registry version stays 1. No unvalidated business facts are seeded. E2/E3 are absent.

## Code map and checks

- Server: `api/.../api/counterparties.py`, `business/counterparties.py`,
  `counterparty_contracts.py`, `counterparty_matching.py`, `module_gate.py`.
- Database: `db/migrations/0015_counterparties.sql`, `db/schema_guard.py`.
- Web: `components/counterparties.tsx`, `counterparty-editor.tsx`,
  `counterparty-relationships.tsx`, `lib/counterparty-api.ts` and strict
  `counterparty-contracts.ts`; central route validation remains mandatory.
- Tests: `test_counterparties.py`, `test_counterparty_contracts.py`,
  `test_counterparty_browser.py`, `web/tests/counterparties.spec.ts`,
  `counterparty-contracts.spec.ts`. Configuration fixtures are shared via
  `configuration_support.py`; `module_support.py` is test-only.
- Do not edit applied migration files. E2 uses new 0016 and expands the guard to
  38 definitions/10 module gates; E3 new 0017, 40 definitions/12 gates.
  Restore new location-dependent policies in the fail-closed location test.

Verified locally: fresh baseline 538 passed/4 skipped; full E1 595 passed/4 skipped
in 248.75 s; final added readiness refusal 1 passed/1.89 s. Web 47 unit tests,
15-page export, typecheck/lint/format; Ruff/mypy 163 files. Code CI and the final
readiness transition require their own exact-SHA evidence; do not substitute local
skips or historical E0 CI for it. See acceptance for red→green and review details.

Windows disposable cluster: PostgreSQL 18.6, loopback port 51454,
`max_connections=250`. Runtime DSN comes only from the private
`%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\test-connection.json`;
never print, copy or commit it. The root ignored helper
`handoff/run_test_database.py` sets mandatory PostgreSQL/browser flags and passes
the DSN only in the child process environment. No second fixture suite in parallel.
Build the fresh web export before browser tests. If starting this known test
cluster, use `pg_ctl -o "-h 127.0.0.1 -p 51454 -c max_connections=250"`.
Do not touch cluster 51455 or another agent's services.

## Next work

1. Verify E1 HEAD, draft PR and exact CI; complete any pending acceptance gate.
2. E2 documents/files per ADR-0020: insert-only metadata/files/versions/link logs,
   strict typed API, DB module gates, file-size/type/integrity/content checks,
   staging/production refusal without scanner, no inline preview. Treat the PDF
   parser/security design as a real validation problem, not string matching alone.
3. E3 agreements: append-only agreed versions, controlled amendment/termination,
   explicit outside-platform signature attestation, no simulated provider.
4. F/CORE-04: shared occupancy and verified transfer from booking_allocations;
   no second independent reservation table before accepted transition.
5. Finance/workforce/materials and industry cycles in master-plan order.

For each package: relevant ADR/plan, red→green, static/build checks, real PostgreSQL
and browsers, independent sensitive-path review, full CI for exact SHA, registry,
audit and handoff updates. Draft PRs only; no merge or production action authorized.

## Unverified and remaining issues

E2/E3, files/scanner, real IdP/Stripe/DAT/Motive/Gusto, Azure, scale/latency,
restore/RPO/RTO, industry pilots, production and manual screen-reader certification
are NOT TESTED. Azure Failed/apps0, development braces findings and the false-PASS
load tool are inherited E0 evidence, not newly checked here. Load-harness repair
and release gates still need their own work. API/web evidence excludes production
AI and the separate AI package. KA Nails and camera Local Gateway are separate.

The original Package E archives and October-4 complete handoff in
`C:\Users\alexa\OneDrive\Desktop\handoff777` are preserved; new evidence must use
distinct names, never overwrite them or include secrets/cache/database data.
