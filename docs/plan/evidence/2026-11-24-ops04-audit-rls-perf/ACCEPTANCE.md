# OPS-04 Technical Acceptance Evidence (2026-11-24)

- **Branch**: `codex/package-ops-04-audit-rls-perf-and-container-verify`
- **Verified code SHA**: `3aa04667cca465c162575bba2da2f4b53d5cd85c`
- **Database Migration**: `0149_audit_events_rls_index.sql` (index-scanable RLS policy on `gba.audit_events` + `audit_events_platform_time_idx`, next migration **0150**).
- **Full parallel suite**: `3119 passed / 0 failed / 4 skipped` out of `3123` (`count_ok=True`, `duplicates=0`, `wall=1470.06s`, `browser=54/54`, `serial=218/218`).
- **Production Docker image verification (`GBA_REQUIRE_CONTAINER=1`)**: `3/3 passed` (`CONTAINER_VERIFY.txt` — explicit idempotent 149-migration job, non-root runtime without baked secrets, real health + static Next.js + real booking against `postgres:18`).
- **Before vs After `0149` (`full-1000`, 1,000 FAKE companies, 100 enterprise branches, 10,000 staff, 1,000,000 `audit_events` rows)**:
  - Report `p95`: `2468.729 ms` (OPS-02) -> **`24.573 ms`** (OPS-04).
  - Read `p95`: **`9.756 ms`** (target <= 500 ms).
  - Write `p95`: **`10.309 ms`** (target <= 1000 ms).
  - Throughput: **`2838.89 ops/s`** (`expected_conflicts=32`, `unexpected_errors=0`, `cross_tenant_leaks=0`, `invariant_violations=0`, `targets_met=True`).
- **Azure Bicep validation**: `infra/azure/main-shared.bicep` and `infra/azure/main-platform.bicep` compiled cleanly via `az bicep build`.
- **Operations runbook**: `docs/runbooks/OPS_RECOVERY_AND_LOAD_RUNBOOK.md`.
