# Package OPS-02: Reproducible Load Profile and Scale Benchmarks

- **Date**: 2026-11-23
- **Branch**: `codex/package-ops-02-load-profile-and-benchmarks`
- **Master Plan Reference**: `docs/plan/GORGONA_MASTER_PLAN.md` §14.1.1 (`OPS-02`) and §14.2
- **ADR**: `docs/adr/0046-ops-recovery-reconciliation-and-load-verification.md`
- **Database Migration**: None (strictly verification & reproducible tooling against the 148-migration schema)

## Scope

1. **Deterministic Load Profile Generator & Runner (`api/tools/ops_load_profile.py`)**:
   - Fixed `GENERATOR_VERSION = "1.0.0"` and deterministic PRNG seed.
   - Strict isolation guards:
     - All generated companies MUST use the `"FAKE "` prefix and `.invalid` RFC 2606 emails.
     - Refuses non-loopback PostgreSQL hosts unless explicitly authorized with `--allow-remote`.
   - Two reproducible modes:
     - `ci-smoke`: fast multi-tenant integration profile (20 `"FAKE "` companies + 1 enterprise with 10 branches & 100 staff + 1,000 historical rows + 200 mixed 70/20/10 operations).
     - `full-1000`: §14.2 scale profile (1,000 `"FAKE "` companies + 1 enterprise with 100 branches & 10,000 staff + 1,000,000 historical rows + 70% read / 20% write / 10% report/search concurrent workload with sustained and 200 req/s peak phases).
   - Strict telemetry & invariant checks:
     - Separate `p50`/`p95`/`p99`/`max` latency for read, write, and report/search paths.
     - Explicit separation of `expected_conflicts` (optimistic revision collisions) from `unexpected_errors` (`< 0.1%` threshold).
     - Zero cross-tenant leaks (`tenant_id` verified on every returned row under `gba_runtime` RLS).
     - Zero domain/money invariant violations (`price_cents >= 0`, `revision >= 1`).
     - Explicit `full_soak_40m_completed` flag so short validation runs on dev VMs are never confused with the full 40-minute Azure staging soak run.
2. **Automated Verification**:
   - `api/tests/unit/test_ops_load_profile_contracts.py`
   - `api/tests/integration/test_ops_load_profile.py`
   - Measured `full-1000` benchmark evidence in `docs/plan/evidence/2026-11-23-ops02-load-profile/BENCHMARK_REPORT.json`.

## Explicit Non-Goals (Out of Scope Without Owner Decision)

- No `readiness_registry.py` raises, no enabling optional modules, no merge to `main`, no real Azure production deployment or real external providers.
