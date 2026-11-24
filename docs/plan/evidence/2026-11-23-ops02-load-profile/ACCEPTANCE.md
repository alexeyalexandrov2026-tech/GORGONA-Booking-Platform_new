# OPS-02 Technical Acceptance Evidence (2026-11-23)

- **Branch**: `codex/package-ops-02-load-profile-and-benchmarks`
- **Verified code SHA**: `e8e553caa03863c15317e9401fb2ca3cb9b3fad0`
- **Full parallel suite**: `3116 passed / 0 failed / 4 skipped` out of `3120` (`count_ok=True`, `duplicates=0`, `wall=1480.03s`, `browser=53/53`, `serial=218/218`).
- **Measured `full-1000` PG18 benchmark** (`BENCHMARK_REPORT.json`, generator `v1.0.0`):
  - Data: `1000` FAKE companies, `100` enterprise branches, `10000` enterprise staff, `1000000` historical rows (`seed_seconds=24.771s`).
  - Workload: `4000` concurrent ops (`2800` read / `800` write / `400` report), `130.87 ops/s`.
  - Latency: read `p95=17.109ms` (target <= 500ms), write `p95=17.808ms` (target <= 1000ms), report `p95=2468.729ms`.
  - Integrity: `expected_conflicts=32` (counted separately), `unexpected_errors=0` (`0.0%`), `cross_tenant_leaks=0`, `invariant_violations=0`, `targets_met=True`, `full_soak_40m_completed=False`.
