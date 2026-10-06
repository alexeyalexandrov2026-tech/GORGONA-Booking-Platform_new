# Package H — final independent proposed-design review

2026-10-06. **PASS for the reviewed design clarifications.** H-D01, H-D02 and H-D03 are addressed; no new substantive contradiction was found within this rereview. This is not owner acceptance, implementation acceptance or runtime verification. ADR-0024 stays Proposed; H/FIN-03/FIN-02 remain unimplemented/planned.

Read all four current H documents from `C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking`, branch `codex/package-h-finance-plan`, base `5be6e7abd7b552903a4f4b2884b150c62532c17d`. Work remained in the independent clean `codex/package-g-final-review` checkout at `95a0de4ac9f5aa3c96b054c5504f59115b0e4b69`. Git shows no H implementation/source changes.

| Finding | Status | Independent assessment |
|---|---|---|
| H-D01: manual-obligation origin | CLOSED by Proposed design clarification | Manual means a new accrual, atomically creating explicit control/counter accounts, obligation/source, balanced G origin and receipt. Settlement uses the fixed control account. Existing G-entry attachment/opening import is excluded and requires reconciliation, preventing implicit duplicate accrual. H-01 now covers this. |
| H-D02: corrections/identity/dependencies | CLOSED by Proposed design clarification | Payment_id and permanent external identity remain stable; effective P/C exclude superseded/voided versions. Replacement mirrors the previous effect and restores its allocations to reserve atomically before confirming within that reserve. Issued-credit/actual-refund/sent-unknown dependencies produce FINANCIAL_RECONCILIATION_REQUIRED without effects. Credit void only mirrors an untouched refund claim with no reserves or external facts. Real money is preserved; complex reconciliation is explicitly outside initial H. H-06 includes these gates. |
| H-D03: credit after later recognition | CLOSED by explicit scoped treatment rule | Credit has no original-account default; a human selects current treatment with reason and a same-book/currency G reference where applicable. The deferred100→manual revenue100→credit50 example explicitly chooses revenue, leaving revenue50/deferred0/AR50. H does not certify invoice-level recognition lineage or implement an automatic recognition workflow. |

Evidence locations: [manual origin](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/plan/PACKAGE_H_PLAN_2026-10-06.md:91>), [correction protocol](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/plan/PACKAGE_H_PLAN_2026-10-06.md:127>), [dependency refusal](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/plan/PACKAGE_H_PLAN_2026-10-06.md:143>), [recognition example](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/adr/0024-invoices-obligations-and-external-settlements.md:122>).

Conservation remains coherent: correction70→50 restores70 to its reserve and consumes50, leaving effective P50/R20, with the old version retained only in history. This is hand-reviewed arithmetic, not an executed money test. The original100/paid70/credit50 case remains C30/refund20. Feature gates, unknown-result reserve protection, provider non-activation, single-ledger reuse, forward0021 and journal-v2/G-v1 compatibility requirements remain intact.

## Current source snapshot — raw SHA256

Hashes matched at read and final check.

| Document under H checkout | SHA256 |
|---|---|
| docs/plan/PACKAGE_H_PLAN_2026-10-06.md | 9ddcc1b6a47096c37099accf3c4c61098bb0c361a40dd7d6b98c85998d94ee00 |
| docs/adr/0024-invoices-obligations-and-external-settlements.md | a26b70eb5a15a41ffeb7f745fef585a50d17c3db2394a780be220fd1087096d9 |
| docs/plan/evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md | 9da4ad96e94f50ad201f465be0bd773ba8d4f67f9278021f872e9e32deb5f098 |
| docs/plan/NEXT_AGENT_PACKAGE_H_2026-10-06.md | 0e2304836dbd456e5609e4f214922ad5f7237673a315929fdfc5d73ee2db84c8 |

The original PACKAGE_H_INDEPENDENT_REVIEW.md remains unchanged, SHA256 `4f496a273606c4e0548a3e94c7ebe439ef0b58927c88428b97615881fa266779`.

Tools: read-only Git/PowerShell document review under the already-read Riqor evidence-engineering skill. Only this requested final external report was written. No checkouts or implementation were edited; no DB, payment/runtime tests, SQL probes, commits, pushes, provider actions or deployment occurred. H runtime/unit/integration/schema/browser/CI/provider admission: **NOT TESTED independently**. Owner confirmation of Proposed financial rules and actual implementation/acceptance evidence remain required.
