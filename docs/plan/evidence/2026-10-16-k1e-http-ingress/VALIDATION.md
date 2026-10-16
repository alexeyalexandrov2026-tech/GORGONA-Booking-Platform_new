# K1e raw HTTP receipt ingress — local validation

**PASS for this bounded local, synthetic slice.**
Branch `codex/package-k1e-http-ingress`, parent `2d434bff8081e03d38765caa0b61f5df006dde27` (K1d docs),
source commit `eb46748fa7446754e96e9290ce5261607ae45ce0`. [CHECKS.json](CHECKS.json) was generated before the source commit; it binds
every source blob, the exact commands, exit codes and log digests of every phase, including the
failures below. Nothing is published; no K acceptance or admission is claimed.
Executor: Claude, inline, from the owner's K1e handoff prompt. The owner also chose an
[independent read-only review of K1a–K1d](INDEPENDENT_REVIEW_K1A_K1D.md) by a separate agent;
its two Medium findings shaped this slice.

## What changed

- `api/src/gorgona_booking/providers/receipt_ingress.py` (new): `create_receipt_ingress_app`,
  `IngressLimits`, `INGRESS_ROUTE`
- `api/src/gorgona_booking/providers/authenticated_receipts.py`: transaction-local timeouts, a
  cheap writer-membership check, unlocked authority reads before the signature, full guards and
  a FOR SHARE re-read with identity comparison after it
- `api/tests/integration/test_provider_receipt_ingress.py` (new, 42 cases)
- `api/tests/integration/test_provider_receipt_routing.py` (4 new cases and two helpers)

No migration (0001–0046 unchanged, next 0047), no dependency, no change to the ordinary
application, `api/`, `business/`, `db/` or `web/`.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| E-01 | 200 with the fixed body only after commit; no journals; also over a real loopback socket | `test_signed_delivery_is_acknowledged_only_after_its_commit` ×3 (rows checked at the moment the response starts), `test_signed_delivery_and_oversized_bodies_over_a_real_loopback_socket` | PASS |
| E-02 | Lost acknowledgement replays as a duplicate; conflicting variant retained, 200 | `test_lost_acknowledgement_replays_as_a_duplicate_and_conflicts_are_kept` | PASS |
| E-03 | 16 refusal classes → one byte-identical 400; nothing stored | `test_every_refusal_has_one_body_and_stores_nothing` ×16 | PASS |
| E-04 | Over the cap → 413 by `Content-Length` without reading, and chunked at the first byte past the cap; also over a socket | `test_oversized_bodies_are_refused_before_or_while_reading`, loopback test | PASS |
| E-05 | Body not received within the read budget → 408 | `test_a_body_that_does_not_arrive_in_time_is_refused` | PASS |
| E-06 | Exhausted writer pool → 503 + `Retry-After`; connection terminated while waiting (observed `pg_locks` wait) → 503; retry → 200 | `test_an_exhausted_writer_pool_answers_retryable_then_the_retry_records`, `test_a_receipt_connection_lost_while_it_waits_answers_retryable` | PASS |
| E-07 | Failure at commit → 500, nothing stored | `test_a_failed_commit_is_never_acknowledged` | PASS |
| E-08 | Full concurrency quota → 503 without reading the body; lock timeout (observed `pg_locks` wait) and statement timeout → 503; the direct lock wait is bounded; limits refuse unbounded values | `test_a_full_concurrency_quota_answers_retryable_without_reading_the_body`, `test_a_receipt_waiting_past_its_lock_timeout_answers_retryable`, `test_a_receipt_statement_past_its_timeout_answers_retryable`, `test_a_receipt_lock_wait_is_bounded_by_its_transaction_timeout`, `test_ingress_limits_refuse_unbounded_values` ×9 | PASS |
| E-09 | Writer-role or schema drift → 503 | `test_schema_or_writer_role_drift_answers_retryable` ×2 | PASS |
| E-10 | Only `POST` on the one route; the ordinary application has no receipt route | `test_only_post_on_the_one_route_and_the_ordinary_app_has_none` | PASS |
| E-11 | No raw body, signature header, key or ingress ID in rows or server logs | `test_rows_and_logs_hold_no_raw_body_signature_key_or_ingress` | PASS |
| E-12 | Bad signature while a revocation is held: refused at once, no row lock or catalog scan before the refusal | `test_a_bad_signature_is_refused_without_row_locks_or_catalog_guards` | PASS |
| E-13 | Config revoked or rotated between the unlocked read and the locked re-read → refused | `test_a_config_changed_after_the_unlocked_read_is_refused` ×2 | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| New cases | 46 (42 ingress, 4 routing) |
| Final focused, PostgreSQL 18.6, own cluster | PASS: 450 passed in 273.91s (0:04:33) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2034 passed, 4 skipped in 1700.22s (0:28:20); skips: 3 container checks and 1 optional tenant-site check, not requested in this run (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: exit 0; 314 source files |
| Web typecheck, lint, format, unit, build | PASS: exit 0; 114 unit tests (web unchanged) |
| Runtime npm audit | PASS: 0 vulnerabilities |
| Development npm audit | FAIL: 5 high, existing; dependencies unchanged; not required |
| Exact K CI, human review | NOT TESTED: no publication authorization |
| Real provider account, keys, admission | BLOCKED: separate owner authorization |

## Failures kept in the record

1. **red-1, product RED.** 4 failed in 41.47s on the K1d code: the receipt waited forever on a
   held revocation (`TimeoutError`); a bad signature blocked on FOR SHARE before the signature
   check (`TimeoutError`); the config row stayed locked during signature verification, so a
   revocation from another session timed out (`LockNotAvailable`, ×2).
2. **red-2.** Collection `ModuleNotFoundError`: `receipt_ingress` did not exist yet (expected).
3. **dev-1, a design gap.** 1 failed, 131 passed: moving the guards after the signature also moved
   the writer-role check behind the route read, so the ordinary runtime got
   `InsufficientPrivilege` instead of the K1c `UnsafeReceiptWriterRoleError`. Fix: a cheap
   `pg_has_role` check in the first statement; the full role scan stays after the signature.
   dev-2: 132 passed in 84.45s.

## Self-review (not independent)

- The ingress is an application factory only. There is no process entry point, settings, key
  store loader or deployment; whoever starts it later must run the HTTP server with its own
  access log off (uvicorn logs raw paths) and give it only the writer login.
- Quotas are per process. Edge rate limits and durable per-connection volume quotas need real
  traffic data (K0). A known ingress ID still lets anyone spend one concurrency slot per request
  for at most the read budget plus three indexed reads.
- Unsupported but signed event types are refused with 400; Stripe will retry them. A K0
  prerequisite is to subscribe the endpoint only to the 11 supported types (review IR-04).
- `ProviderEventConfigurationError` (unusable key) is answered with the same 400 and logged
  server-side by class name only.
- Rows are kept permanently; a legal retention period is an owner decision before production.
- The other review findings (IR-03, IR-05–IR-11) are recorded, not fixed here.

## Unchanged

FIN-02 and STOCK-01 `planned`; ADR-0026 and ADR-0027 Proposed; H4 declarations and manual
attestation unchanged; connections `not_admitted` and test-mode only; migrations 0001–0046
unchanged, next 0047; main `fedd0f1`, published J `df88c20`; K not published.
