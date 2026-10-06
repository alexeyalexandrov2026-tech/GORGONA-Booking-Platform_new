# H — current continuation, 2026-10-06

Branch: `codex/package-h-finance-plan`.
Checkout: `C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking`.
Base: `5be6e7abd7b552903a4f4b2884b150c62532c17d`, accepted G; separate G draftPR12
and original dirty checkouts are preserved. Repository remains
alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new.

Read [planH](PACKAGE_H_PLAN_2026-10-06.md),
[ADR-0024 Proposed](../adr/0024-invoices-obligations-and-external-settlements.md),
[architecture/reuse evidence](evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md),
AGENTS, master plan, and current Cloud handoff before code.

This checkpoint contains documentation only. H endpoints/tables/operations are
NOT IMPLEMENTED; FIN-03/FIN-02 remain planned. The green G CI does not prove H.
The proposed money rules need owner confirmation and independent review before
implementation. Proposed scope includes receivable/payable invoices, manual
obligations, competing settlement reserves, partial external payments, credits
and separate paid-part refund obligations, with explicit account/recognition
selection and human attestation. No provider sends funds.

Implementation order H1→H2→H3→H4 is in the plan. Do not accept FIN-03 from invoice
CRUD or one passing phase. Keep finance/G technically_verified and add an H-specific
gate while H is not verified. Extend the ledger/recovery through approved seams,
not a second money engine. Only forward0021 and explicit view-version evolution.

Owner decision to record: full H including paid-credit refunds and explicit
recognition/account selection, or a narrower first slice with FIN-03 still
partial. Keep ADR Proposed until confirmation; no positive provider admission.
Independent review should check cap equations, partial settlement/release,
credit/refund dependency order, module/scenario gates and legacy compatibility.

Checks for this planning checkpoint: documentation-only diff, local links,
criterion IDs and review source references; exact outcomes recorded by the agent.
Do not report new unit/integration/browser money checks as passed before code.

No merge/deploy/production migration/Azure/DNS/billing/provider activation.
Do not change the original owner or gorgona-e2-documents checkout. No database or
service restart is needed to review this plan. Runtime test DSNs stay outside
Git/logs/artifacts; use one executor per private disposable PostgreSQL when code
tests are actually run. KA Nails and camera Local Gateway remain separate.
