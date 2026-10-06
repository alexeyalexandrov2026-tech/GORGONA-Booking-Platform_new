# H — evidence of current architecture and reuse candidates

Date: 2026-10-06. Evidence kind: **source inspection/design**, not runtime H proof.
Code baseline: `5be6e7abd7b552903a4f4b2884b150c62532c17d` in a separate clean
`codex/package-h-finance-plan` checkout. H logic/tables/endpoints do not exist.

## Actual flow and candidates

| Existing file | Observed behavior | Reuse or necessary extension |
|---|---|---|
| `api/src/gorgona_booking/api/ledger.py` | authorized_tenant, company permissions, ledger lock before access, actual service calls and readiness | Same authorization/module/transaction boundary for H; no route cloning |
| `api/src/gorgona_booking/business/ledger.py` | Actual G posting, source uniqueness, deferred balance flush, once-only reverse, reports, resolve/cancel | Public typed posting/correction seam; one ledger, no parallel balances |
| `api/src/gorgona_booking/business/ledger_contracts.py` | to_minor/from_minor, supported0/2/3, strict decimal strings, closed SourceKind and finite receipts | Reuse money conversion; introduce bounded H sources/contracts explicitly |
| `api/src/gorgona_booking/business/commands.py` | Fingerprint, actor/operation/key claim, reference receipt, audit within caller transaction | Reuse directly; supplement permanent domain/source identity and minimal recovery |
| `api/src/gorgona_booking/business/agreements.py` | Draft/attested state with insert-only versions; immutable counterparty/legal entity refs; minimal receipt/audit | Reuse pattern, not copy lifecycle or legal meaning |
| `api/src/gorgona_booking/business/counterparties.py` | Versioned company-owned cards, archive/match logic and bounded queries | Refer to existing version; do not create a second party catalog |
| `api/src/gorgona_booking/db/migrations/0020_ledger.sql` | Seven finance-gated financial tables plus cancellation control; FORCE RLS, balance/history/period functions | Forward0021 extends controlled origins and H tables, never edit0020 |
| `api/src/gorgona_booking/db/ledger_guard.py` + schema_guard | Approved source and access controls, rejects extra permissive ledger policies | Extend approvals to actual H controls from packaged migration; no expected definitions from DB |
| `api/src/gorgona_booking/auth/permissions.py` | Mapv5 finance read/manage/close owner/manager, no delegation/platform support | Keep company-wide scope; do not silently add bank authority |
| `api/src/gorgona_booking/business/modules.py` + readiness_registry | Finance verified forG; FIN-03 planned | H-specific scenario gate untilH acceptance, preserveG configs/readiness |
| `web/lib/ledger-contracts.ts` | Strict Zod, BigInt money/per-row equations, closed source-kind enum | Reuse minorUnits; explicit new view version, no unknown-origin coercion |
| `web/lib/ledger-recovery.ts` + `web/components/ledger.tsx` | Minimal session refs, same-key retry, blocking unknown result, safe recovery/cancel after reload | Extend finite protocol forH without financial body in storage |
| `web/components/management-layout.tsx` and business pages | Static exported Next pages; role-filtered navigation, API-authenticated data | Matching finance pages/states; no private SSR or separate website |
| `api/tests/integration/test_ledger.py` and browser harness | Real SQL/API/races; fake labeled IdP with actual OIDC/PKCE; actual app/Chromium/PostgreSQL | Extend domain fixtures/controls and reuse real browser harness |

Candidates were read in the current checkout. This table is not evidence that
the proposed new seam/API/schema has already been implemented.

## Architecture conformance criteria

- One financial ledger and currency policy; no invoice-only money store.
- Domain state, command identity, external source identity and journal entry
  identity are separate typed records, all tenant/book scoped.
- No payment SDK, callback simulator, network charge or fake health/provider fact.
- Invoice recognition is an explicit human choice, not a booking/status inference.
- Reserve/pay/credit/reverse share the lock and transaction; SQL checks completed
  invariants, not only prior service reads.
- Planned H cannot become enabled merely because G finance is enabled.
- Forward migration/contract evolution preserve existing G paths and history;
  legacy readers never receive a silently incomplete financial result.
- The Azure/local camera architecture boundary is unchanged; no infrastructure
  work, another website or another tenant's data is required.

## Baseline and checks

Read-only Git verification: primary owner checkout still
codex/universal-business-foundation/2f16380 with its unrelated dirty work; G is
clean at5be6e7a. New H worktree starts at the exact G head with its own branch.
Connected GitHub read confirmed CI
[37499485016](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37499485016)
completed/success for5be6e7a. Earlier measured861passed/1skipped belongs only toG.

Installed skill actually read: [Riqor evidence-engineering](C:/Users/alexa/.codex/plugins/cache/openai-curated-remote/riqor/0.2.5+codex.20260809182719/skills/evidence-engineering/SKILL.md).
Other routed skill names were searched and not found; no load/execute/pass is
claimed for them. Relevant tools: local Git/PowerShell/source reads, managed
worktree tool, connected GitHub read and authoritative PostgreSQL/Stripe docs.

Documentation diff/link/ID checks and independent design review are recorded
after this proposal is written. H runtime/unit/schema/browser, migration0021,
FIN-03 and provider access: **NOT TESTED**. No H implementation status is promoted.
