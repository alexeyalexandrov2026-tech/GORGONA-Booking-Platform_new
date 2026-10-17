# K1g receipt schema guard additions — local validation

**PASS for this bounded local slice** (after one failed full run, kept below). Branch
`codex/package-k1g-guard-additions`, parent `af26f1d`, source commit `4401a2e7bcdc716eaa5664285c0ca383ddf77163`.
[CHECKS.json](CHECKS.json) was generated before the source commit. Not published. Closes
[independent review](../2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md) finding IR-05.
Executor: Claude, inline, at the owner's request for the IR-05 slice.

## What changed

- `api/src/gorgona_booking/db/provider_receipt_guard.py`: four more checks in the same catalog query of `assert_provider_receipt_ready`
- `api/tests/integration/test_provider_guard_additions.py` (new, 10 drift cases)

No migration (next 0047), dependency, receipt-flow or infrastructure change.

## Criteria and evidence

| id | Requirement | Drift cases in `test_guard_drift_stops_routed_and_runtime_receipts` | Result |
|---|---|---|---|
| G-01 | Role topology | runtime login in the writer group; parent role on the writer group; BYPASSRLS writer member | PASS |
| G-02 | Table shape | rewrite rule; unlogged table | PASS |
| G-03 | ACLs | table grant to a third role; grant option to `gba_runtime`; function grant to a third role | PASS |
| G-04 | Context functions | replaced `current_location_id()` body; `current_tenant_id()` SECURITY DEFINER | PASS |
| G-05 | Existing tests, full suite | focused-2, full-2 | PASS |

Each case: the routed writer receipt and the runtime archive both refuse and store nothing; after
repair the guard passes and a receipt records again. For the parent-role case the writer path
already refused before K1g (the K1c writer-role check, `UnsafeReceiptWriterRoleError`); the
runtime archive path did not.

## Gates

| Gate | Exact observed outcome |
|---|---|
| static-1, static-2 | PASS (mypy 316 files; web unchanged; runtime audit 0; development audit 5 high, existing) |
| focused-1 / focused-2 | PASS: 468 passed in 248.41s / 468 passed in 294.65s (0:04:54) |
| full-1 | **FAIL**: 1 failed, 2051 passed, 4 skipped in 2000.42s — `test_stock_scale::test_posting_time_does_not_grow_with_a_long_history`: after a 100k history 310.8 ms vs 64.1 ms (limit 3× + 50 ms) |
| dev-3 | that test alone on a fresh cluster PASS (52.9 → 61.5 ms) |
| full-2 (final) | PASS: 2052 passed, 4 skipped in 2011.34s (0:33:31); the stock test passed narrowly (237.8 vs 67.9 ms) |
| K CI | NOT TESTED (K1g not published) |

## Failures kept in the record

1. **red-1, product RED.** 10 failed: nine drifts were not detected (`DID NOT RAISE`); the
   parent-role case was refused only on the writer path.
2. **dev-1, my design defect.** 43 failed, 146 passed: `relhasrules` stays true after
   `DROP RULE` ("has or once had rules"), so the repaired schema kept failing and later tests
   cascaded. Fixed by checking `pg_rewrite` only. dev-2: 189 passed in 100.73s.
3. **full-1, timing.** Stock posting does not call the receipt guard. Earlier full runs were
   already near this test's limit: K1d 218.6/65.7 ms, K1f 366.1/127.1 ms, K1e 125.9/51.0 ms.
   Recorded as a pre-existing load-sensitive check, not a K1g regression; it needs its own
   follow-up (the threshold or the measurement).

## Limits

Function sources outside K and the two context functions, and column grants held by the owner,
are not covered. Membership is read from `pg_auth_members`; a superuser sees every role but is
not counted as a member. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.
