# K1k TRUNCATE guard and random route IDs — local validation

**PASS for this bounded local slice.** Branch `codex/package-k1k-truncate-guard`, parent
`ae9e1e2`, source commit `a5f21e41f550d5d07e428c644e9f718082b3f619`. [CHECKS.json](CHECKS.json) was
generated before the source commit and binds source blobs, commands, exit codes and log digests.
Not published. Closes [independent review](../2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md)
finding IR-09 and the default part of IR-08. Executor: Claude, inline; the owner, away, asked to
keep working and decide alone.

## What changed

- `api/src/gorgona_booking/db/migrations/0049_provider_receipt_truncate_guard.sql` (new):
  `gba.reject_provider_receipt_truncate()` (plpgsql, `search_path=pg_catalog`, no PUBLIC execute)
  and a `BEFORE TRUNCATE FOR EACH STATEMENT` trigger `<table>_no_truncate` on all six receipt
  tables; `provider_receipt_routes.ingress_id` defaults to `gen_random_uuid()`
- `api/src/gorgona_booking/db/provider_receipt_guard.py`: expects the six triggers, the function
  and the default
- `api/tests/integration/test_provider_receipt_truncate.py` (new, 18 cases)

Migrations 0001–0048 unchanged (next 0050). No row, grant, dependency, API, receipt flow,
readiness or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| T-01 | TRUNCATE … CASCADE of each receipt table and of `ledger_books`, by the owner and by a superuser, is refused (`check_violation`); every row stays | `test_receipt_history_cannot_be_truncated` ×14 (each inside a forced rollback) | PASS |
| T-02 | A route without `ingress_id` gets a random version-4 UUID; two differ; it routes a receipt | `test_a_route_without_an_id_gets_a_random_one_that_routes` | PASS |
| T-03 | Drift refuses receipts and archives; repaired schema passes | `test_truncate_guard_drift_stops_routed_and_runtime_receipts` ×3 (dropped trigger, disabled trigger, default removed) | PASS |
| T-04 | Existing K and guard tests and the full suite | focused-1, full-1 | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 512 passed in 443.01s (0:07:23) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2095 passed, 4 skipped in 1656.78s (0:27:36); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 320 source files |
| Web typecheck, lint, format, unit, build | PASS (web unchanged) |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop (`data_removed: true`); no `postmaster.pid` left |
| K CI | NOT TESTED (not published) |

New cases 18, regression cases 212 (K receipt modules, see CHECKS.json).

## Failures kept in the record

**red-1, test defect** on `ae9e1e2`: 18 failed, but for the four referenced tables a plain
TRUNCATE already stopped at their foreign keys (`FeatureNotSupported`) before any trigger runs,
so the test could never pass for them. The test now truncates every table with `CASCADE`, which
passes the foreign-key check and is the real way to empty them.

**red-2, product RED** on `ae9e1e2`: 18 failed in 16.93s. All 14 TRUNCATE … CASCADE statements
succeeded (rolled back by the test); a route without `ingress_id` was refused by NOT NULL; the
three drift cases were not refused.

**dev-1**: 241 passed in 156.97s.

## Limits

A superuser can still switch `session_replication_role` or drop the triggers (as for UPDATE and
DELETE). Ledger, stock and other tables have no TRUNCATE guard. IR-08 remainder: no per-route
disable and the owner cannot list routes; the ID stays non-secret. FIN-02 planned; ADR-0027
Proposed.
