# Package H — independent architecture review

Date: 2026-10-06. Review type: document/source design review only.

**Result: the architecture direction and intended FIN-03 scope pass design review, but two financial rules require clarification before money-effect implementation.** A third scoped recommendation concerns later revenue/expense recognition. No H runtime PASS, owner acceptance or production authorization is implied. Keep ADR-0024 Proposed and FIN-03/FIN-02 planned.

The reviewer used the separate clean `codex/package-g-final-review` checkout at `95a0de4ac9f5aa3c96b054c5504f59115b0e4b69`; the reviewed H documents and current reuse candidates were read from `C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking`, branch `codex/package-h-finance-plan`, code base `5be6e7abd7b552903a4f4b2884b150c62532c17d`. The H checkout contains documentation work; its documents were not edited by this reviewer. The relevant ledger/API/contracts/migration/recovery source is unchanged between the review checkout and H's base.

Applied [Riqor evidence-engineering](C:/Users/alexa/.codex/plugins/cache/openai-curated-remote/riqor/0.2.5+codex.20260809182719/skills/evidence-engineering/SKILL.md), rule 9: “Use an independent reviewer for high-risk security, data, release, or cross-project changes”. Root's earlier verdicts and test reports were not used as independent H proof.

## Findings requiring design clarification

### H-D01 [P2] Define the ledger origin of a manual obligation

Sources: [plan lines 49–59](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/plan/PACKAGE_H_PLAN_2026-10-06.md:49>) and [ADR obligation identity/posting table](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/adr/0024-invoices-obligations-and-external-settlements.md:40>).

H2 explicitly includes manual obligations, but issue atomicity and the posting table specify invoice creation only. The documents do not choose whether a manual principal creates a new control-account posting or links an already-posted G amount. This choice matters: a manual payable A=100 followed by an outgoing payment70 posts debit payable70/credit bank70. If creation did not credit the payable control account, the ledger control balance has no common basis with the obligation's remaining30. Linking an already-accounted amount and posting it again creates the opposite duplicate-origin problem. These are unruled design paths, not observed runtime failures.

**Recommendation:** define a typed manual-obligation creation/attachment command, explicit control/counter-account mapping or immutable G-origin link, and uniqueness/capacity for every linked origin component. Require one atomic principal/origin/source/journal/audit/receipt operation. Extend H-01/H-08 with manual receivable/payable, an already-accounted origin, duplicate attachment, scope/currency mismatch and rollback. Do not let implementation choose this financial rule implicitly.

### H-D02 [P2] Specify correction events, effective allocation amounts and dependency resolution

Sources: [plan immutable payments/cap](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/plan/PACKAGE_H_PLAN_2026-10-06.md:55>), [plan correction rule](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/plan/PACKAGE_H_PLAN_2026-10-06.md:98>) and [ADR rules 5–7](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/adr/0024-invoices-obligations-and-external-settlements.md:51>).

The cap is clear for reserve/confirmation/credit, but “dependent credits/refunds must be explicitly resolved first” does not define allowed correction transitions or how corrected allocations contribute to effective P/C. External source identity is unique and old allocations are immutable: a mistaken70 corrected to actual50 under the same reference needs a correction version/event, rather than deletion, a fabricated second reference or a second independent payment record. The effective allocations for that one fact must still sum to its corrected amount.

The dependency boundary also needs a concrete rule for invoice100/paid70/credit50/refund20 actually confirmed, followed by correction of the original payment or credit. A real external refund must remain a recorded cash fact; it cannot be reversed merely to clear an internal dependency. For a multi-obligation payment, correction of one allocation must not implicitly erase the other allocations.

**Recommendation:** define the immutable correction graph, effective-net P/C derivation, stable source identity across versions, distinct correction-operation identities, and which states permit correction versus require explicit compensating business facts or rejection. Keep confirmed external cash separate from cancellation of an internal command. Add cases for pending/partly confirmed/fully confirmed refund dependencies, repeated correction/replay, same-reference replacement, one allocation in a multi-obligation fact, and closed-period correction. Until a supported path is specified, reject that correction rather than guessing the dependency resolution.

## Scoped recommendation

### H-D03 [P2] Clarify credit behavior after later recognition

Source: [ADR explicit posting and examples](<C:/Users/alexa/.codex/worktrees/package-h-finance-plan/Gorgona Booking/docs/adr/0024-invoices-obligations-and-external-settlements.md:35>).

Explicit recognition at issue is correctly separated from cash. However, the examples permit deferred-income/prepaid accounts while credits always use original counter-accounts. The existing G manual journal remains available. If invoice100 credits deferred income, a later manual G entry debits deferred100/credits revenue100, then the proposed credit50 mapping debits the original deferred account50 and credits receivable50: recognized revenue remains100. The journal balances, so balance validation alone will not resolve the recognition policy.

**Recommendation for owner scope confirmation:** either define a bounded later-recognition lineage and how credit allocates to recognized/unrecognized amounts, or explicitly state that later recognition and its adjustment are outside H and require a separately recorded human adjustment. Add a concrete later-recognition/partial-credit example to avoid presenting the current posting table as handling that lifecycle automatically. This review does not demand an unapproved expansion into accounting automation or jurisdiction-specific rules.

## Design checks that passed

- **FIN-03 scope:** the plan includes obligations, competing settlement documents, reserves, partial payments, release, credit/refund and correction history. It does not claim FIN-03 from invoice CRUD or one phase.
- **Conservation:** `P,C,R>=0` and `P+C+R<=A` are coherent for one book/currency. Hand-worked design examples: reserve70/confirm40 leaves P40/R30 and availability30; release10 leaves P40/R20 and availability40. These are arithmetic review examples, not executed tests. Confirmation moves the same amount R→P; reservation/release has no journal.
- **Paid credit:** invoice100/paid70/credit50 gives C30 and a separate refund principal20. Original P+C=100; the refund has its own cap. No assumption is made that money was sent by a provider.
- **Unknown external result:** ADR requires explicit confirmation or no-payment attestation before releasing sent/unknown reserves. Finance OFF, timeout and lost HTTP response do not establish failure. Preserve this condition in H-04/H-05/H-09. Internal HTTP-command recovery and external-payment uncertainty must remain separate states.
- **Recognition and permissions:** invoice/booking status does not infer revenue. Owner/manager company-wide rights are explicit proposed rules; front desk, artists, branch members, delegates, support and other companies are denied by design.
- **Module/feature gates:** verified G finance does not accept H. A FIN-03-specific gate and separate acceptance commit are specified; OFF retains reads/recovery and eligible non-money release. H admission metadata never activates capabilities; FIN-02 remains planned.
- **G reuse:** current source confirms closed source enums in SQL/Pydantic/Zod, finite six-command recovery, immutable once-only reversal, reference receipts, tenant ledger locking and a single trial balance. The plan explicitly requires forward0021, a public typed posting/correction seam, source evolution, extended journal v2, old G write-v1 preservation, explicit legacy-read upgrade and managed-H reversal controls. These are necessary changes, not existing H-ready behavior. No second ledger is proposed.
- **Evidence boundary:** H-01..H-12 remain NOT TESTED. Runtime races, direct-SQL controls, recovery, browser, G compatibility and exact-SHA CI remain future implementation gates.

[PostgreSQL 18 advisory-lock documentation](https://www.postgresql.org/docs/18/explicit-locking.html#ADVISORY-LOCKS) confirms that application-defined locks must be used consistently; the plan correctly also requires actual SQL controls/race evidence. [Stripe's SaaS guide](https://docs.stripe.com/connect/saas) is compatible with a future direct-charge SaaS path, but its existence proves no account admission or operational capability. Both were read directly for this review; neither service was configured or called operationally.

## Source snapshot — SHA256

The following four raw-file hashes matched at initial read and final review check. They identify these Proposed drafts, independent of any later edits.

| Document under H checkout | SHA256 |
|---|---|
| docs/plan/PACKAGE_H_PLAN_2026-10-06.md | 1a318e33d8d95c3c3e82f4ef37eff535e92fcc1b846636b79ab7d2d813123206 |
| docs/adr/0024-invoices-obligations-and-external-settlements.md | f38baaed8efc13f542a81ccbd420157b75a2d96b8469e8a27a92968fe0f173cd |
| docs/plan/evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md | 9da4ad96e94f50ad201f465be0bd773ba8d4f67f9278021f872e9e32deb5f098 |
| docs/plan/NEXT_AGENT_PACKAGE_H_2026-10-06.md | 0e2304836dbd456e5609e4f214922ad5f7237673a315929fdfc5d73ee2db84c8 |

Tools: local Git/PowerShell read-only source/doc inspection, the named installed skill, and authoritative-documentation browser reads. No database, money/runtime tests, manual SQL probes, implementation edits, checkout changes, commits, pushes, provider actions or deployment. Only this requested external report was written. H runtime, unit/integration, schema, browser and provider admission: **NOT TESTED independently**.
