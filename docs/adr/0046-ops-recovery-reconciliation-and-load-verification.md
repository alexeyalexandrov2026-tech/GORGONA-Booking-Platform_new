# ADR-0046: Stage 9 Technical Verification — Recovery, Reconciliation, Load Profile & Resilience

- Status: Accepted (technical verification harness; production cutover and readiness raises still require explicit owner approval)
- Date: 2026-11-23
- Stage: Stage 9 (`OPS-01`, `OPS-02`, `OPS-03`)
- Migrations: none (uses existing schema `0001`–`0148`)

## Context

Master plan §13–14 defines three technical operations verification gates prior to any
production cutover:
- `OPS-01`: Measured backup/restore recovery, queue/command replay idempotency, migration
  reconciliation, and reverse-switchback verification.
- `OPS-02`: Reproducible load profile (§14.2: 1,000 synthetic companies + 1 enterprise
  company with 100 branches / 10,000 staff, 70/20/10 read/write/report mix, 100 RPS
  sustained / 200 RPS peaks, < 0.1% unexpected errors, zero leaks/invariant breaks).
- `OPS-03`: Mobile (390px) & keyboard accessibility, clear errors, provider outage
  fail-closed behavior, and offline sync conflict resolution.

## Decision

1. Place reusable, strictly typed operational verification logic under
   `api/src/gorgona_booking/ops/` with thin CLI runners under `api/tools/`.
2. Enforce strict non-production safety guards on every drill/load tool:
   - Synthetic tenant names must start with `"FAKE "`.
   - Non-loopback targets are refused unless `--allow-remote` is explicitly passed.
   - No real payment/telematics providers, DNS, production databases, or `readiness_registry`
     status raises are performed by these tools.
3. Verify every pillar in real PostgreSQL 18 (using `pg_dump` / `pg_restore`, real HTTP
   servers, and real Chromium desktop + mobile browsers) with zero mocks.
