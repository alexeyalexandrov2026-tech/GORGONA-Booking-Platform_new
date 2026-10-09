# Cloud Code handoff — GORGONA business platform

## Current package H technically accepted (FIN-03) — 2026-10-09

[Handoff and copyable prompt](docs/plan/NEXT_AGENT_H_ACCEPTANCE_2026-10-09.md),
[audit](docs/plan/evidence/2026-10-09-h-acceptance-audit/AUDIT.md),
[acceptance record](docs/plan/evidence/2026-10-09-h-acceptance/ACCEPTANCE.md).
H1–H4 are implemented at `319f144` on `codex/package-h4-ui-admission`:
migrations 0021–0031, the H API and the Financial documents and Provider
admission screens. Draft PR15–PR22 are stacked and open; nothing is merged.
Exact-SHA CI for `319f144` is success (push 37876007880, pull_request
37876031010); its steps build the web app and the production image and run
PostgreSQL 18, Ruff, mypy and pytest.
Independent audit on a separate checkout and cluster: full local suite
1231 passed / 4 skipped / 662.06 s with mandatory PostgreSQL and browser;
Ruff/format/mypy 230 and web gates PASS; four SQL guard mutations were all
caught. No money defect was found. Findings A-01–A-11 are in the audit; the only
P2 (provider admission is writable with `finance` alone) is closed by the
owner's decision of 2026-10-09: no code change, H4 is not deployed before H
acceptance, admission is accepted together with H.
**FIN-03 is `technically_verified` by the owner's decision of 2026-10-09** on
code `319f144`. `finance_documents` is enableable by a company's own published
configuration and the test-only readiness overrides are removed. Full local run
on the acceptance tree: 1231 passed / 4 skipped / 666.05 s. ADR-0024 is
Accepted. FIN-02 remains planned. Branch `codex/package-h-acceptance` holds the
audit `71359f9` and the acceptance commit `ec39622`; it was pushed on 2026-10-09
by the owner's decision and exact-SHA CI for `ec39622` is success (push
37887856597). No draft PR is open for it yet (GitHub sign-in needed); an
independent check of the acceptance commit is NOT DONE.
No merge/deploy/production/provider/funds action. The sections below are
historical snapshots.

## Historical H2 backend handoff — 2026-10-07

[Full successor handoff](docs/plan/NEXT_AGENT_H2_2026-10-07.md),
[copyable prompt](docs/plan/NEXT_AGENT_PROMPT_H2_2026-10-07.md),
[changed files/checks/limits](docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md).
Branch codex/package-h2-settlements from the delivered H1 backend 75e809b.
**Published in [draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16), target H1 PR15; no merge.**
Original eight docs committed/pushed as75c36da; final docs are a successor.
Read actual final HEAD/origin/current-head CI in PR16/exported delivery state.
Corrective source `15edbed1d608ada9d0901a7710c00eff28c23e71` fixes a diagnosed ledger refresh race in two web files;
financial Python/SQL and frozen migrations are unchanged from54852b4. [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793) PASS:1044 passed/1 skipped/379.86s;
all3 Docker/image, PG/browser, web69/2.3s and static211 PASS.
Fresh local full:1041 passed/4 skipped/434.68s; focused browser1/17.95s.
Bounded independent UI review PASS; full H2 money/state review remains NOT DONE.
Forward 0022–0024 add manual accruals as new obligations, settlement documents
with approval/reserve/sent/release/cancel, and externally attested partial
confirmations that move exactly R→P with one balanced journal and a permanent
external identity. PostgreSQL and the service both enforce P+C+R<=A at commit.
Historical author full suite1041/4/459.51s; fresh corrective results are above.
Mandatory PostgreSQL18.6 and browser;
Ruff/format/mypy211 and web gates PASS. Exact-checkpoint CI75c36da
[37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) PASS:1044 passed/1 skipped/381.36s; all3 Docker/image,
PG/browser, 69 web tests/2.3s and static211 PASS.
Independent money/state review NOT DONE; HawkScan was not run.
FIN-03/02 remain planned and finance_documents unavailable. H3 credits, refund
obligations and corrections and H4 UI/admission remain unfinished.
Owner/E2 dirty trees preserved; own cluster 51462 stopped.
No merge/deploy/production/provider/funds action. The H1 section below is
superseded for continuation; its evidence remains snapshot-specific.

## Historical H1 backend handoff — 2026-10-06

[Full successor handoff](docs/plan/NEXT_AGENT_H1_BACKEND_2026-10-06.md),
[copyable prompt](docs/plan/NEXT_AGENT_PROMPT_H1_BACKEND_2026-10-06.md),
[changed files/checks/reviews](docs/plan/evidence/2026-10-06-h1-backend/VALIDATION.md).
Delivery branch codex/package-h1-persistence; reviewed source2d5a8f9 from
foundation18e3f5e. [Draft PR15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15)
targets PR14. Read exact current delivery HEAD/CI there.
Real forward0021 and invoice API persist one immutable issue, principal
obligation and G accrual atomically; minimal permanent recovery and explicit
journal-v2 are implemented. Root953/4skip/378.14s, Ruff/format/mypy204 PASS;
independent corrective review47 PG/109 units PASS, H1-R01 closed.
FIN-03/02 remain planned and finance_documents unavailable. H2 settlement/
manual accrual, H3 credits/refunds and H4 UI/admission remain unfinished.
Owner/E2 dirty trees preserved; own root51456 and review51460 stopped.
No merge/deploy/production/provider/funds action. Historical foundation below
has been superseded for continuation; its evidence remains snapshot-specific.

## Historical H1 foundation — 2026-10-06

Owner continued local work and explicitly approved H1 source publication.
[Draft PR14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14)
targets planning PR13. Delivery branch codex/package-h-invoices; reviewed
source843d0b3, checkpointda3966b. Exact-head CI37534227319 PASS909 passed/
1 optional skip with PG/browser/Docker and build. This handoff update is a
docs-only successor; refresh current PR14 head/CI.
[Copyable successor prompt](docs/plan/NEXT_AGENT_PROMPT_H1_2026-10-06.md).
Read [H1 handoff](docs/plan/NEXT_AGENT_PACKAGE_H1_2026-10-06.md) and
[checks/boundaries](docs/plan/evidence/2026-10-06-h1-foundation/VALIDATION.md).
Strict contracts, pure allocation math and planned finance_documents/registry2
are implemented. H1 workflow is IN PROGRESS; actual H SQL/API/UI is not built.
FIN-03/02 remain planned; G acceptance and old published configurations remain.
Earlier planning/review statements below describe their own snapshots.

## Historical H planning snapshot — 2026-10-06

Own branch codex/package-h-finance-plan from G head5be6e7a.
Read [H handoff](docs/plan/NEXT_AGENT_PACKAGE_H_2026-10-06.md),
[H plan](docs/plan/PACKAGE_H_PLAN_2026-10-06.md) and
[ADR-0024 Proposed](docs/adr/0024-invoices-obligations-and-external-settlements.md).
Docs only: typed invoices/obligations/settlement reserves, externally attested
partial payments, credits/refund obligations and admission requests are proposed.
No H money code/schema/provider activation; FIN-03/02 remain planned.
Independent proposed-design review PASS; owner scope confirmation remains
pending before code. [Review/check evidence](docs/plan/evidence/2026-10-06-package-h-plan/VALIDATION.md).
G finance remains technically verified; its exact-SHA CI is not H validation.

## Current G continuation — 2026-10-06

Read [package G handoff](docs/plan/NEXT_AGENT_PACKAGE_G_2026-10-06.md) and
[fresh evidence](docs/plan/evidence/2026-10-06-ledger/ACCEPTANCE.md).
Branch codex/package-g-ledger-review from accepted stage-2 plan 151472a;
own checkout under .codex/worktrees/package-g-ledger-review/Gorgona Booking.
The original gorgona-e2-documents and owner checkout are preserved.
Ledger books/accounts/double entry/reversals/periods/trial balance and real API/UI
are implemented. The early-SET-CONSTRAINTS balance bypass was reproduced and fixed.
All seven independent findings are closed, including unexpected permissive SQL policies.
Evidence code 95a0de4: full local 858 passed/4 skipped, exact-SHA CI 861 passed/1 skipped
with required Docker gates; independent final guard-delta code/unit review PASS.
Fresh accepted-registry focused: 68 Python and 4 desktop/mobile browser flows,
without positive readiness overrides; 68 web unit tests PASS. Recovery and safe cancellation prevent
the delayed original from running after an unresolved request is cancelled.
Finance/FIN-01 are technically verified by a separate acceptance commit. A new
configuration publication enables finance; no existing configuration is changed.
Check the fresh acceptance HEAD CI in draft PR #12; evidence names source SHA and review boundaries.
No merge, deployment, production migration, providers or Azure changes.
Older continuation sections below are historical for their own code versions.

## Current E2-A continuation — 2026-10-05

Read [E2-A handoff](docs/plan/NEXT_AGENT_E2_FILE_VALIDATION_2026-10-05.md) and
[evidence](docs/plan/evidence/2026-10-05-file-validation/ACCEPTANCE.md).
Branch codex/package-e2-file-validation from accepted E1 3983dd4. This increment
is the bounded file-profile/CSP prerequisite, no storage/API/UI/migration or
documents readiness promotion. Continue E2 persistence/integration per ADR0020/0021,
then E3 and CORE-04. Owner dirty checkout is preserved; no production action.

## Current E1 continuation — 2026-10-05

Read [the E1 handoff](docs/plan/NEXT_AGENT_PACKAGE_E1_2026-10-05.md) and
[acceptance](docs/plan/evidence/2026-10-05-counterparties/ACCEPTANCE.md) first.
Current branch codex/package-e1-counterparties builds on audited E0 bbe6ecd and
targets that branch in its own draft PR. Owner checkout remains untouched.
Versioned counterparties/contacts, explicit duplicate decisions and manual booking
links are implemented; E2 documents/files and E3 agreements are next, then CORE-04.
Code 2392566595a2df59f8ec3f073ed9bf184df6447f has green exact push/PR CI (599/1);
a separate acceptance promotes counterparties to technically_verified. Registry v1
and booking-only baseline remain unchanged; each business explicitly publishes it. Local API/browser/static gates passed with explicit
container/external-site skips; production/providers/Azure/load remain unverified.
The October-4 continuation and earlier counts below are historical, not current
code acceptance. Preserve all 39 profiles, 28 criteria and generic booking.

## Current continuation — 2026-10-04

The owner authorized correction of the complete universal-business plan and the start of implementation. Read [the corrected master plan](docs/plan/GORGONA_MASTER_PLAN.md) and [implementation evidence](docs/plan/GORGONA_IMPLEMENTATION_STATUS.md) first. Preserve all 39 industry profiles and existing generic booking workflows. `business_id` is the existing tenant boundary; multiple profiles do not create duplicate companies. GORGONA supplies software, including inventory and transport tools for its customers, without operating its own warehouse or carrier.

The current repository develops GORGONA only. KA Nails is a separate project, outside this implementation and release scope. The first-tenant proposals and brand instructions below are historical context; do not treat them as current tasks or platform acceptance requirements.

The [2026-10-04 plan-conformance audit](docs/plan/GORGONA_PLAN_AUDIT_2026-10-04.md) maps all 28 acceptance criteria. Stage 1 is partial. A confirmed security issue in the old development hold endpoint has been corrected: `/v1/holds` is registered only in local/test/CI, while hosted bookings retain the customer validation/capability path. The linked audit records the failing regression, fresh focused PASS and independent review; compare every later CI result with its exact commit.

Azure is the accepted deployment direction ([ADR-0012](docs/adr/0012-azure-hosting.md)); the OCI proposal below is historical. Production actions still require their acceptance gates and owner authorization. Begin with baseline defects, then the typed business foundation and shared resource/financial/material invariants. No provider approval or production readiness is implied by this handoff.

Baseline at the start of this work: clean checkout at `76ce4e52f1c19b176586c8f69e55d4df735d1a1e`. Prior results on that unchanged version were 151 API tests passed, 12 AI tests passed, 17 AI tests skipped, and web type checking passed. Rerun relevant checks after changes; do not reuse these as evidence for a new tree.

The current implementation also includes location-scoped booking/resource operations, branch invitations, legacy command-receipt compatibility and a fail-closed PostgreSQL access-definition guard. Read [ADR-0014](docs/adr/0014-location-scoped-workspace.md) and the latest [next-agent handoff](docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md) before continuing. No industry-wide or production readiness is implied.

## Historical handoff — 2026-09-30 (preserved reference)

The sections below describe the original proposal, audit and later repository separation. They are not current deployment instructions or current implementation status. The current continuation, master plan and accepted ADRs take precedence.

Prepared 2026-09-30. This document is the starting context for the next coding environment. Read it before writing application code. The complete local project is this repository; all paths below are relative to its root.

## Objective and scope

Build a reusable, tenant-aware appointment platform named **GORGONA Booking AI** with **KA Nails** as its first tenant. The customer-facing KA Nails experience should follow the supplied official logo. Implement a deterministic booking system before the AI concierge. This handoff is Phase 0 audit/design; do not report the product as implemented.

The owner asked for a new GitHub project and considered Cloudflare/Supabase. They then asked whether **Oracle server could replace Supabase and Cloudflare**. Proposed direction: OCI-hosted web/API plus PostgreSQL, with Cloudflare optional for DNS/CDN/WAF. This is an architecture proposal, not a deployed system. The owner explicitly chose **not** to pause existing Supabase projects; the new Supabase project is deferred. Preserve existing GORGONA/Fresh Nails services and data.

## What exists here

- `assets/brand/ka-nails-logo.png`: exact supplied logo; SHA-256 `BB2FE1C05EB7183B8B8F55EEE861B06D80256CF5349B2958E1432FA3B83FBF53`.
- `source/PRODUCT_BRIEF.txt`: complete pasted owner brief, copied verbatim for full context. The later OCI/deferred-Supabase decisions in this handoff take precedence.
- `docs/architecture/INITIAL_AUDIT.md`: evidence and limitations from the two owner-controlled Fresh Nails reference repositories.
- `docs/architecture/TARGET_ARCHITECTURE.md`: proposed OCI-first modular monolith and decision list.
- `docs/architecture/DATA_MODEL.md`, `BOOKING_ENGINE.md`, `MULTITENANCY.md`, `SECURITY_MODEL.md`, `AI_TOOL_MODEL.md`: domain, trust and concurrency contracts.
- `docs/architecture/DESIGN_SYSTEM.md`, `ANALYTICS.md`, `OBSERVABILITY.md`, `RELEASE_PLAN.md`: customer experience and quality gates.
- Local Git repository on `main`, with no external remote until account access is restored.

## Verified findings and blockers

1. This task's starting folder had no Git repository. The owner's accessible GitHub account is `alexeyalexandrov2026-tech`. `Fresh-Nails` is a Vite/React marketing site with static JSX prices and Square links. `Fresh-Nails-AI-Receptionist-by-Gorgona-One-AI` is a separate Next.js/Dify/Supabase chat project. Neither is a KA Nails booking core. They were cloned read-only into this task's `work/` folder, outside this deliverable.
2. The old OCI `gorgona-node` was recorded as **TERMINATED** in a prior audit. On 2026-09-30, `oci iam region-subscription list --profile GORGONA --auth security_token` failed because the session expired. No current VM, cost, IP, SSH access or deployed application was verified. Do not target historical IP `150.136.90.12`.
3. Supabase organization `Gargona One` is free; creation reported $0/month but failed because its owner has reached the two active free-project limit. Active projects are `gorgona-camera-feed` and `Gorgona-one-claude`. The owner chose to keep both running and defer the new project.
4. The GitHub connector lacks a create-repository operation. GitHub's in-app page was unauthenticated and Git Credential Manager supplied no reusable credential. No GitHub repo or remote exists for this project. Cloudflare's in-app page was also at sign-in. No Cloudflare project or DNS change was made.
5. The product brief refers to a separate GORGONA/KA Nails architecture image, but only the logo image and text brief were available. Authentic KA Nails photos, domain, address, schedule, staff, legal/policy wording and the base Hammam booking duration were not supplied/verified.

## Next execution sequence

1. Reconcile owner decisions: confirm OCI compartment and current host plan, budget, domain, business timezone, staff/hours, service durations, deposit/cancellation/tax rules, photo rights and whether Square remains temporary booking. Do not infer these from Fresh Nails.
2. Renew OCI browser security-token session using `GORGONA` profile; list current instances/compartments and verify exact target. No VM restart, infrastructure creation or production deployment before cost, blast radius and rollback are reviewed with owner. Do not create an OCI API signing key by default.
3. Once GitHub login is available, create a **private** `gorgona-booking-ai` repository under the owner's chosen account, add its URL as `origin`, push the reviewed local `main`, and verify GitHub file/hash parity. Do not push cloned Fresh Nails references, secrets or task `work/` files.
4. Turn the approved architecture into ADRs, exact migrations, typed API contracts and tests. Implement tenant/catalog and staff/scheduling first; then transactional holds and appointments. Use PostgreSQL `tstzrange` + GiST exclusion for exclusive resources; the 100-concurrent-attempt acceptance is one success and 99 typed conflicts. Keep the AI outside booking authority.
5. Set up isolated staging on verified OCI infrastructure, private PostgreSQL, TLS, backups/PITR, restore drill, telemetry and CI before production. Cloudflare remains optional. Do not turn on a public booking CTA until it reaches a real validated booking/payment flow.

## Product facts from supplied brief that may be seeded after owner validation

- Hammam Luxury: $145; heel care and ritual included; gel not included.
- Hammam Luxury + Gel: $160, public duration range 120–145 minutes.
- Hammam Luxury + Gel French: $175, public range 130–155 minutes.
- Extra Foot Massage: +$20 and exactly +15 minutes booking time.
- Other Salon Gel Removal: +$15, subject to staff assessment when required.
- Hammam Spa Upgrade: +$40 only for compatible pedicures; must not stack with Hammam Luxury.
- French Gel: +$15 and only with compatible gel service.
- Base Hammam deterministic booking duration is **unknown**. Do not invent one or publish it as bookable.

## Security and release rules

No browser service-role credentials; trusted tenant context; composite tenant foreign keys and RLS; verified payment webhooks and idempotency; transactional outbox; structured, redacted logs; tested restore. AI tools are typed, tenant-scoped, policy-checked and have no arbitrary SQL/shell/HTTP access. Preserve human correction and audit history. Treat tests and live validation as separate evidence, and keep the status labels PASS / FAIL / BLOCKED / NOT TESTED.

## Suggested first prompt in Cloud Code

> Open this repository and read `CLOUD_CODE_HANDOFF.md` and every file in `docs/architecture/`. Treat the supplied KA Nails logo as the brand source. First verify Git state and the current OCI/GitHub access. Do not reuse Fresh Nails as KA Nails source. Make a detailed, testable M1 plan for an OCI-first modular monolith, identify owner decisions and deployment gates, and implement only the next approved, reviewable slice. Do not claim application or infrastructure completion from these design documents.

## Repository separation update (30 September 2026)
The logo source paths above record Phase 0 provenance. The unchanged PNG now belongs to the independent KA-nails repository at `public/assets/ka-nails-logo.png`; the old bytes remain in Git history. Platform origin is `alexeyalexandrov2026-tech/-GORGONA-Booking-Platform`. No push or deployment was performed. See `docs/architecture/REPOSITORY_SEPARATION.md`.
