# OPS-03 Technical Acceptance Evidence (2026-11-24)

- **Branch**: `codex/package-ops-03-resilience-offline-and-mobile`
- **Verified code SHA**: `5c44c452e366d4b0453c0d91339d4adb1e55effa`
- **Full parallel suite**: `3118 passed / 0 failed / 4 skipped` out of `3122` (`count_ok=True`, `duplicates=0`, `wall=1502.4s`, `browser=54/54`, `serial=218/218`).
- **Server/API offline & fail-closed matrix verified**:
  - Stale `expected_revision` offline edit -> `409 Conflict`, winning server state intact.
  - Idempotent network retry (same `Idempotency-Key` + same payload) -> `200`, zero duplicates.
  - Mutated offline replay on reused `Idempotency-Key` -> `422 IDEMPOTENCY_KEY_REUSED`.
  - Revoked employee membership offline sync -> `403`, zero state mutation.
  - Forged/broken provider bearer token -> `401`, fail-closed.
  - Late offline ledger posting into a closed accounting month -> rejected (`PeriodClosedError`), book strictly balanced.
- **Real Chromium Desktop (1280px) + Mobile (390px) E2E verified**:
  - Fixed latent WCAG 2.1 A `scrollable-region-focusable` violation across `.mgmt-table-container` wrappers (`tabIndex={0}`).
  - Keyboard `Tab` traversal with zero keyboard traps, `axe-core` WCAG 2.1 A/AA `0` violations, and `0` horizontal overflow on desktop & 390px mobile across `/overview/`, `/counterparties/`, `/supply/`, `/marketplace/`, `/enterprise/`, `/specialized/`.
  - Simulated `503 PROVIDER_UNAVAILABLE` -> accessible `role="alert"` -> idempotent retry -> saved `Version 1 · active` -> simulated `409 REVISION_CONFLICT` -> honest conflict alert, `0` uncaught `pageerror`.
