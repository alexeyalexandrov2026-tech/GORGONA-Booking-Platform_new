# H1 foundation continuation — 2026-10-06

Current branch: `codex/package-h-invoices`.
Checkout: `C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking`.
Reviewed source:843d0b3; planning parent925ae02/draftPR13. G/PR12 remains separate.
Read [foundation evidence](evidence/2026-10-06-h1-foundation/VALIDATION.md),
[full H plan](PACKAGE_H_PLAN_2026-10-06.md), ADR-0024, master and current handoff.

Owner continuation permits progressing locally with the proposed full H design;
the earlier publication block was resolved by the owner's continue and PR13 is
published. Preserve all original/other checkouts. No production/provider approval.

Contracts/arithmetic/closed-feature metadata are implemented and reviewed;
**H1 is IN PROGRESS**, FIN-03/FIN-02 planned, finance_documents non-enableable.
Actual H endpoints, SQL persistence, money operations and UI are NOT IMPLEMENTED.
Pure balance projections do not prove SQL race protection or real external facts.

Next implement forward0021 and a public typed G posting seam, immutable invoice
versions/lines, obligation+source+journal link with one atomic issue. Keep G
source contracts honest: explicit extended journal v2, legacy upgrade behavior,
all trial balances inclusive and managed-source G reversal denial. Extend guard
inventories from packaged SQL. Never edit0001–0020/checksums.

The FIN-03 feature reuses finance_documents/registry2. Existing published v1
finance does not enable H. Test-only verified_modules can exercise development
publication, but final H acceptance must remove positive overrides. An OFF
non-money release/recovery must not be blocked by blanket insert gates. Actual
H commands also check current readiness, not only a past enabled snapshot.

Then follow H2→H3→H4. Keep12 full H cases NOT TESTED until actual execution,
independent money/state review, full suite/browser/container exact-SHA CI and
separate acceptance. Do not accept FIN-03 from this foundation or invoice CRUD.

Reuse existing private disposable runner; one executor per PostgreSQL. Secrets
remain outside checkout. Any cluster started for checks must be stopped afterward.
No merge/deploy/production migration or external payment/provider action.
