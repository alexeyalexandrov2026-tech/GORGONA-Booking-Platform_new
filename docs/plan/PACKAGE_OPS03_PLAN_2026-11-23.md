# Package OPS-03: Mobile UI, Keyboard Accessibility, Error Handling, Provider Failure & Offline Sync Conflicts

- **Date**: 2026-11-23
- **Branch**: `codex/package-ops-03-resilience-offline-and-mobile`
- **Master Plan Reference**: `docs/plan/GORGONA_MASTER_PLAN.md` §14.1.1 (`OPS-03`)
- **ADR**: `docs/adr/0046-ops-recovery-reconciliation-and-load-verification.md`
- **Database Migration**: None

## Scope

1. **Server / API Resilience & Offline Conflict Matrix (`api/tests/integration/test_ops_resilience_and_offline_conflicts.py`)**:
   - Optimistic revision conflict (`409 Conflict`) on stale offline counterparty edits without overwriting server state;
   - Idempotent retry after dropped connection (same `Idempotency-Key` + same payload -> `200`, zero duplicates) vs payload mismatch conflict (same `Idempotency-Key` + altered payload -> `409`, zero corruption);
   - Offline sync submitted by a revoked employee membership -> `403` fail-closed, zero mutations;
   - Late offline ledger posting into a closed accounting month -> rejected (`LedgerStateError`), double-entry book remains strictly balanced;
   - Fail-closed provider/auth rejection (invalid bearer token / malformed provider token) -> `401`, zero fabricated financial writes.
2. **Real Chromium Desktop + Mobile (390px) Resilience & Accessibility Suite (`web/tests/ops-resilience.spec.ts` + `api/tests/integration/test_ops_resilience_browser.py`)**:
   - Real OIDC/PKCE sign-in, keyboard-only `Tab`/`Shift+Tab` traversal with zero keyboard traps;
   - Zero `axe-core` accessibility violations and zero horizontal overflow (`scrollWidth <= innerWidth`) on both desktop (1280px) and mobile (390px) across `/overview/`, `/counterparties/`, `/supply/`, `/marketplace/`, `/enterprise/`, `/specialized/`;
   - Simulated provider/backend `503 Service Unavailable` and offline `409 Conflict` responses during card save on `/counterparties/`: verifies visible accessible error feedback (`role="alert"`), zero uncaught `pageerror`, zero silent success, and clean recovery once the outage clears.
