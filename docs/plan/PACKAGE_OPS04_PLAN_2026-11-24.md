# Package OPS-04: Audit Events RLS Index Optimization (0149), Production Container Verification & Operations Runbook

- **Date**: 2026-11-24
- **Branch**: `codex/package-ops-04-audit-rls-perf-and-container-verify`
- **Master Plan Reference**: `docs/plan/GORGONA_MASTER_PLAN.md` §14.1.1 (`OPS-01..03`) & §14.2
- **Database Migration**: `0149_audit_events_rls_index.sql`

## Motivation (Evidence-Driven From OPS-02)

During the `OPS-02` full-scale PG18 benchmark (`1,000` FAKE companies, `100` enterprise branches, `10,000` staff, `1,000,000` historical rows in `gba.audit_events`), read (`p95 = 17.11ms`) and write (`p95 = 17.81ms`) paths easily beat the §14.2 targets, while aggregate report queries over `gba.audit_events` measured `p95 = 2468.73ms`.

Root cause: `0004_identity.sql` defined `audit_events_scope` using `tenant_id IS NOT DISTINCT FROM gba.current_tenant_id()`, which PostgreSQL cannot evaluate via btree index lookup, forcing a sequential scan over all `1,000,000` rows on every tenant report.

## Scope

1. **Migration `0149_audit_events_rls_index.sql`**:
   - Replaces `audit_events_scope` with the logically identical, index-scanable predicate:
     `tenant_id = gba.current_tenant_id() OR (tenant_id IS NULL AND gba.current_tenant_id() IS NULL)`.
   - Adds partial index `audit_events_platform_time_idx (occurred_at) WHERE tenant_id IS NULL`.
   - Keeps `FORCE ROW LEVEL SECURITY` intact, zero `SECURITY DEFINER`.
2. **RLS Equivalence & Planner Verification (`api/tests/integration/test_audit_events_rls_index.py`)**:
   - Proves identical read/write isolation across tenant A, tenant B, and unscoped platform (`NULL`) contexts, plus `EXPLAIN (FORMAT JSON)` index usage on both `audit_events_tenant_time_idx` and `audit_events_platform_time_idx`.
3. **Re-measured `full-1000` Benchmark (`docs/plan/evidence/2026-11-24-ops04-audit-rls-perf/BENCHMARK_REPORT.json`)**:
   - Captures direct before/after latency on the exact same `1,000,000`-row dataset (`seed=20261123`).
4. **Real Production Docker Container Verification (`GBA_REQUIRE_CONTAINER=1`)**:
   - Builds the real repository `Dockerfile` (all 149 migrations + 43 static Next.js routes) and executes all 3 tests in `api/tests/container/test_container_image.py` against a disposable `postgres:18` container on an isolated Docker network (`test_migration_job_is_explicit_and_idempotent`, `test_image_runs_non_root_without_baked_secrets`, `test_api_container_serves_health_web_and_a_real_booking`).
5. **Operations & Staging Runbook (`docs/runbooks/OPS_RECOVERY_AND_LOAD_RUNBOOK.md`)**:
   - Documents repeatable commands for `OPS-01` backup/restore reconciliation, `OPS-02` load/40-minute staging soak execution, `OPS-03` resilience/a11y browser verification, and `OPS-04` container smoke tests.
6. **Status Registry Checkpoint (`docs/plan/GORGONA_IMPLEMENTATION_STATUS.md`)**:
   - Appends a factual, non-inflated checkpoint summarizing Stages 5–9 (`REST-01`, `PRO-01`, `SUPPLY-01`, `MARKET-01`, `ENTERPRISE-01`, `SPECIAL-01..05`, `OPS-01..04`) while preserving every owner-only gate (`main`, `readiness_registry.py`, `enableable=False`, Azure staging/prod deployment).
