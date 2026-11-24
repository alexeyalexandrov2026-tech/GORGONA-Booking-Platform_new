# GORGONA Operations Runbook: Recovery, Load Benchmarking, Resilience & Container Verification

This runbook covers the repeatable technical verification tools built in Stage 9 (`OPS-01..04`, ADR-0046). All load generation and destructive drills MUST run only in isolated test or staging environments using synthetic `"FAKE "` tenants.

---

## 1. Backup, Restore & Reconciliation Drill (`OPS-01`)

Tool: `api/tools/ops_recovery_drill.py`

1. Capture a pre-restore snapshot, execute `pg_dump --format=custom` and `pg_restore --exit-on-error` into a clean target database, enforce `REVOKE ALL ON DATABASE ... FROM PUBLIC` and `GRANT CONNECT ... TO gba_runtime`, and reconcile all migration checksums, `gba.*` row counts, and currency-separated double-entry ledger balances:
   ```bash
   cd api
   uv run --locked python -m tools.ops_recovery_drill \
     --admin-dsn "$GBA_TEST_ADMIN_DSN" \
     --source-db "$SOURCE_DB" \
     --source-owner-dsn "$SOURCE_OWNER_DSN" \
     --target-db "${SOURCE_DB}_restore_drill"
   ```
2. Verify exit code `0` and `"matched": true`, `"unbalanced_ledgers": []`.
3. Verify `apply_migrations` on the restored DB is a no-op (`[]`) and `assert_location_scope_ready` passes under `gba_runtime` (all RLS policies, triggers, and `FINANCIAL_BOUNDARY` restored-AST CHECK constraints).
4. Automated regression test (serial lane):
   ```bash
   uv run --locked pytest tests/integration/test_ops_recovery_and_replay.py -q
   ```

---

## 2. Reproducible Multi-Tenant Load Profile & Staging Soak (`OPS-02`, `OPS-04`)

Tool: `api/tools/ops_load_profile.py` (`GENERATOR_VERSION = "1.0.0"`)

Safety guards enforced in code:
- Every generated company name must start with `"FAKE "` and every staff email uses `.invalid` (RFC 2606).
- Non-loopback PostgreSQL hosts are refused unless `--allow-remote` is explicitly passed.

Commands:
- Fast CI smoke (`20` companies, `10` enterprise branches, `100` staff, `1,000` historical rows, `200` ops):
  ```bash
  uv run --locked python -m tools.ops_load_profile \
    --admin-db-dsn "$ADMIN_DB_DSN" \
    --app-dsn "$APP_DSN" \
    --mode ci-smoke
  ```
- Full scale (`1,000` companies, `100` enterprise branches, `10,000` staff, `1,000,000` historical rows, `70/20/10` read/write/report mix):
  ```bash
  uv run --locked python -m tools.ops_load_profile \
    --admin-db-dsn "$ADMIN_DB_DSN" \
    --app-dsn "$APP_DSN" \
    --mode full-1000 \
    --out-json BENCHMARK_REPORT.json
  ```
- Staging 40-minute soak target (§14.2): run against Azure Staging (`--allow-remote`) with warm-up (10 min), sustained 100 req/s (30 min), and three 2-minute peaks at 200 req/s with 5-minute recovery windows; archive full report with Azure SKU, pool size, and `full_soak_40m_completed=true`.

Acceptance thresholds:
- Read `p95 <= 500 ms`, Write `p95 <= 1000 ms`, unexpected error rate `< 0.1%`, `cross_tenant_leaks == 0`, `invariant_violations == 0`, and `expected_conflicts` reported separately from successes.

---

## 3. Mobile/Keyboard UX, Provider Failure & Offline Sync Conflicts (`OPS-03`)

- Server/API offline conflict matrix (`409` stale revision, `200` idempotent retry, `422 IDEMPOTENCY_KEY_REUSED`, `403` revoked employee, `401` forged bearer, `PeriodClosedError` closed accounting period):
  ```bash
  uv run --locked pytest tests/integration/test_ops_resilience_and_offline_conflicts.py -q
  ```
- Real Chromium Desktop (`1280px`) + Mobile (`390px`) keyboard traversal, WCAG 2.1 A/AA `axe-core` audit, zero horizontal overflow, and `503`/`409` error recovery:
  ```bash
  GBA_REQUIRE_BROWSER=1 uv run --locked pytest tests/integration/test_ops_resilience_browser.py -q
  ```

---

## 4. Production Container Image Verification (`OPS-04`)

Build the production multi-stage image (`web/out` + `api` non-root runtime) and run all 3 real Docker tests against disposable `postgres:18`:
```bash
docker build -t gorgona-api:verify .
cd api
GBA_REQUIRE_CONTAINER=1 GBA_CONTAINER_IMAGE=gorgona-api:verify \
  uv run --locked pytest tests/container/test_container_image.py -q
```

---

## 5. Azure Staging Provisioning Reference (`infra/azure/`)

All Bicep templates live in `infra/azure/` (`main-shared.bicep`, `main-platform.bicep`, `params/staging.create.bicepparam`) and are validated via:
```bash
az bicep build --file infra/azure/main-shared.bicep --stdout >/dev/null
az bicep build --file infra/azure/main-platform.bicep --stdout >/dev/null
```
Actual staging/production deployment, `readiness_registry.py` raises, enabling optional modules (`enableable=True`), live payment/OIDC providers, and DNS cutover require explicit owner authorization.
