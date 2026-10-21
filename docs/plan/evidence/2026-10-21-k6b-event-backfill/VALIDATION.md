# K6b1 — events lost on the way fetched back from the Stripe API: local validation

**PASS for this bounded local slice with a fake Stripe API.** Branch `codex/package-k6b-event-backfill`,
parent `73570bd` (the [K6b detailed decisions](../../PACKAGE_K6_DESIGN_2026-10-21.md)), source commit
`73f5c45efc5cb3c8a1ac17297b3ca836ca9764ab`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every source
blob, command, exit code and log digest and the failures below. No real network, key, account or
money; nothing published; readiness unchanged (FIN-02 stays `technically_verified`; K-05 and K-12 stay
PARTIAL until the real sandbox run K6c).

## Owner decisions

2026-10-21: «1» (close the FIN-02 gaps), «Да, все умолчания» (event backfill, 3 days every 15
minutes, up to 30 days by hand, the Stripe CLI as the sandbox transport). The agent decided the details
within those defaults and recorded them in the design before code.

## What changed

| Part | Change |
|---|---|
| Migration 0064 (K) | The attestation `verifier` may be `stripe_api_v1` besides `stripe_snapshot_v1`, and the writer names it. `provider_reconciliation_runs`: one permanent row per run (writer only, RLS by company): window, pages, seen, recorded, duplicates, conflicts, refused, outcome and error class; the counts must add up and a failed run must name its class |
| Decoder | `stripe_events`: one strict decoder for webhooks and listed events (duplicate keys, non-finite numbers, shapes, version, account, live mode, type); a page must be a bounded Stripe list of at most 100 objects. A listed event gets the **same facts** as its webhook; its digest is the SHA-256 of its canonical JSON |
| Receipt path | `receive_retrieved_event` shares the webhook transaction (writer check, owner's binding and admission, full guards, share locks, inbox, attestation) without a signature, attested as `stripe_api_v1` |
| Reconciler | `providers/reconciliation.py`: the routes of **one platform namespace** (the key's) whose connection is active and admitted; `GET /v1/events` per connected account (`Stripe-Account`), window `[now−days, now)`, 100 per page, newest first, at most 100 pages; 429, 5xx and timeouts retried after 1, 2 and 4 s, then the run fails; any other answer fails it at once; no network call inside a transaction; counts and error class only in logs |
| Process | `python -m gorgona_booking.providers.reconcile_main` (`--once`, `--interval` 60–3600, default 900; `--days` 1–30, default 3) with the writer login, `GBA_STRIPE_NAMESPACE` and `GBA_STRIPE_API_KEY_REF` (`env:NAME`); the key lives in memory only |
| Runbook | [PROVIDER_OPERATIONS.md](../../../runbooks/PROVIDER_OPERATIONS.md): the reconciler, provenance and run records |

## Acceptance (new tests: 29)

| Requirement | Test | Result |
|---|---|---|
| A lost payment and refund arrive through the inbox and are decided (list without `account`) | `test_lost_events_arrive_through_the_inbox_and_are_decided` | PASS |
| A webhook and its retrieval are one event; a second run adds nothing | `test_a_webhook_and_its_retrieval_are_one_event` | PASS |
| A different fact under the same ID is a visible conflict, decided `needs_review` | `test_a_different_fact_under_the_same_id_is_a_visible_conflict` | PASS |
| Another API version, account, live mode or type is refused and counted | `test_another_version_account_mode_or_type_is_refused_and_counted` (4) | PASS |
| A malformed event is refused; a malformed page fails the run | `test_a_malformed_event_is_refused_and_a_malformed_page_fails_the_run` | PASS |
| Every page of the window, nothing outside it; second run all duplicates | `test_every_page_of_the_window_is_read_and_a_second_run_adds_nothing` (250 events, 3 pages) | PASS |
| More pages than allowed fails visibly | `test_a_window_with_more_pages_than_allowed_fails_visibly` | PASS |
| 429/500/503 retried then succeed; persistent failures, 401, 400 and timeouts fail without a receipt | `test_rate_limits_and_server_errors_are_retried_then_succeed`, `test_a_failing_provider_never_fabricates_a_receipt` (5) | PASS |
| A suspended connection and another namespace are never asked | `test_a_suspended_connection_is_never_asked`, `test_only_the_namespace_of_the_key_is_reconciled` | PASS |
| No key, account or event ID in logs, rows or `repr` | `test_logs_and_rows_hold_no_key_account_or_event`, `test_the_key_is_never_shown` | PASS |
| Only the writer records runs; runs permanent and consistent; guard refuses drift | `test_only_the_writer_records_runs` (5), `test_runs_are_permanent_and_consistent`, `test_the_guard_refuses_drift_in_the_reconciliation_schema` (2) | PASS |
| Upgrade 0063 → 0064 keeps every row | `test_nonempty_0063_upgrades_keeping_every_row` | PASS |
| Process settings bounded, key never shown | `tests/unit/test_receipt_processes.py` (2 new, 12 cases) | PASS |

## Failures kept, in order

- **red-1**: collection error — the module `reconciliation` did not exist (expected).
- **red-2**: the new settings unit tests could not import `reconcile_settings` (expected).
- **dev-1**: 7 failed, 656 passed — all K6b tests passed; every upgrade test copies the shared test
  database into an older schema, where the K6b `stripe_api_v1` attestations break the old check.
  `copy_fixture_data` now leaves them out before 0064, as it already does for later staff, stock and
  provider rows. Lesson from K6a applied in advance: the location boundary test and the upgrade
  table lists learned 0064 before the first run.
- **dev-2**: 54 passed (K6b and all 17 upgrade test files).

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-k6b-20261021-73570bd`, one executor, own disposable
PostgreSQL 18.6 cluster per phase:

- **static-1** PASS: ruff, format, mypy, web typecheck, lint, format, unit, build; runtime npm audit
  0 vulnerabilities.
- **focused-1** PASS: **673 passed** (47 files: every provider, K5, K6a and K6b test, the K4a real
  browser, the location boundary and all 17 upgrade test files).
- **full-1** PASS: **2395 passed, 4 skipped** (container, live tenant site and other external
  targets, as before).

## Limits

The real Stripe API is not called here; K6c runs the reconciler against the owner's sandbox (through
the signed-in Stripe CLI, so no key enters our code) with webhooks lost on purpose. K6b2 adds the
delivery source and the 24-hour marker to the screen. No live mode, deployment or production
migration. Migrations 0001–0064 are immutable; the next is **0065**.
