# H planning checkpoint — documentation and independent-review evidence

Date: 2026-10-06. Branch: `codex/package-h-finance-plan`.
Base/code: `5be6e7abd7b552903a4f4b2884b150c62532c17d`, accepted G.
Checkout: `C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking`.

**Status: proposed design reviewed; H implementation NOT TESTED.** Owner choice
between full H1–H4 and an H1-only first slice is pending. ADR-0024 stays Proposed;
FIN-03/FIN-02 remain planned (audit runtime status NOT TESTED). No money operation,
migration, provider action or new deployment is claimed by this checkpoint.

## Changed files and purpose

13 Markdown files, documentation only:

- `docs/plan/PACKAGE_H_PLAN_2026-10-06.md`: scope, invariants, phases and H-01..H-12.
- `docs/adr/0024-invoices-obligations-and-external-settlements.md`: proposed rules.
- `docs/plan/evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md`: actual source/reuse boundaries.
- `docs/plan/NEXT_AGENT_PACKAGE_H_2026-10-06.md`: exact checkout/base and next decision.
- `CLOUD_CODE_HANDOFF.md`, `docs/DEVELOPMENT.md`, `docs/plan/NEXT_AGENT_START_HERE.md`: current H references; historical G sections preserved.
- `docs/plan/GORGONA_MASTER_PLAN.md`, `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md`, `docs/plan/GORGONA_PLAN_AUDIT_2026-10-04.md`: proposed H evidence without promoting runtime readiness.
- This evidence plus `INITIAL_REVIEW.md` and `FINAL_REVIEW.md`: checks and independent snapshots.

## Independent design review

[Initial review](INITIAL_REVIEW.md) found two P2 design gaps and one scoped
recommendation. [Final review](FINAL_REVIEW.md) independently re-read the four
proposal documents and reports PASS for the clarified design, with H-D01/02/03
closed by Proposed rules. It does not accept the product scope or implementation.

1. Manual obligations create a new accrual and journal atomically; linking
   already-accounted G origins is explicitly excluded from initial H.
2. Payment corrections retain source identity and derive effective allocations;
   issued-credit/actual-refund/unknown dependencies reject without rewriting cash.
3. Credit counter-accounts require explicit current human treatment after later
   G reclassification; no automatic invoice recognition lineage is claimed.

Reports are preserved byte-for-byte with SHA256:

- INITIAL_REVIEW.md: `4f496a273606c4e0548a3e94c7ebe439ef0b58927c88428b97615881fa266779`.
- FINAL_REVIEW.md: `e2e73c845d37f1cff95f1d2ba2891456bc6141467d567b25ad56f800c7899754`.

The final report's four raw document hashes were matched before copying. The
reviewer used its own unchanged checkout/branch; no DB or money tests were run.

## Exact documentation checks

Local Git/PowerShell plus a stdlib Python checker outside the repository:

- `git -c core.excludesFile= diff --check`: PASS, exit 0 after final doc edits.
- `git -c core.excludesFile= diff 5be6e7abd7b552903a4f4b2884b150c62532c17d --check`: PASS, exit 0 for the full H checkpoint.
- Documentation checker: PASS, exit 0; all 13 changed Markdown files, added/changed local link targets, conflict/whitespace controls, 12 unique NOT TESTED acceptance cases, 15 existing source reuse references, Proposed ADR, unpromoted FIN-02/03 and no runtime/config diff.
- Copied-report SHA256 and four reviewed proposal-document hashes: PASS, exact matches.

The local link check covers new/changed links only, not all historical document
links, anchors, external reachability or legal/accounting-policy certification.
No repository-specific Markdown linter is configured in the inspected manifests
or CI. No new package/dependency or low-impact mirror test was added.

## G baseline and preserved state

Connected GitHub read returned completed/success for G CI
[37499485016](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37499485016)
at exact G SHA 5be6e7a. The earlier measured 861 passed/1 skipped is G evidence;
it is not inherited as H functionality proof. Any CI on this docs branch runs
unchanged G source, and must be described as baseline regression only.

Read-only final inventory: G remains clean at 5be6e7a; original owner checkout
remains at 2f16380 with 19 changed/untracked paths; incoming E2 checkout remains
at 151472a with 9 changed/untracked paths. No files there were edited by H work.
Draft G PR12 remains separate; a planning PR does not merge either package.

## Not verified and next step

H APIs/tables/migration0021, SQL controls/races, money effects, recovery, browser,
schema v2 compatibility, unit/integration/build/container acceptance and provider
admission: NOT TESTED. H is not implemented. No production/database/provider
change occurred. Actual code acceptance needs every H phase's evidence plus
independent code review, exact-code-SHA CI and a separate acceptance commit.

The full plan's human account/recognition choice, paid-credit refund treatment,
bounded correction refusal and owner/manager attestation are explicit proposed
rules awaiting owner scope confirmation. Begin implementation only after that
choice; preserve G's verified finance state and close the new FIN-03 feature gate.

Tools used: local Git/PowerShell and stdlib Python, managed worktree tools,
GitHub connector, independent agent and the already-read Riqor evidence-engineering
skill. PostgreSQL/Stripe official documentation was used for design context only.
