# K6a — bounded retries, parked events and every event order: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-k6a-bounded-retries`, parent
`8b8f8a3` (the [K6 design](../../PACKAGE_K6_DESIGN_2026-10-21.md) with the owner's decisions), source
commit `2f577bc8be7a821bdd1b063f2a3188bd923234db`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every
source blob, command, exit code and log digest and the failures below. No provider call, no network,
nothing published; readiness unchanged (FIN-02 stays `technically_verified`, K-05 and K-12 stay
PARTIAL until K6b and K6c).

## Owner decisions

2026-10-21: «1» (close the FIN-02 gaps K-05 and K-12), then «Да, все умолчания» for the six K6
questions: a finance user releases a parked event with a note; 5 attempts with waits of 1, 2, 4 and 8
minutes; event backfill for reconciliation (K6b); a 3-day window every 15 minutes; the Stripe CLI as
the sandbox transport; order K6a → K6b → K6c.

## The defect this slice fixes

Before K6a, one event whose decision failed (for example a database refusal on unexpected facts)
stopped the worker's whole batch. Its lease expired after a minute, it was claimed again, failed
again — **forever**, every minute, each time stopping the events behind it — and nothing recorded the
failure, so nobody could see it. RED-1 shows it: `DivisionByZero` of one event aborted the batch.

## What changed

| Part | Change |
|---|---|
| Migration 0063 (K) | `provider_event_failures`: one row per failed lease generation, fenced by the lease like a decision (same holder and generation, unexpired, undecided), the round set by the trigger, at most 5 per round, the error class only (`^[A-Za-z][A-Za-z0-9_]{0,63}$`). `provider_event_releases`: a finance user's note for a parked, undecided event; it starts the next round. The 0050 lease guard now refuses any claim of a parked event. Both tables permanent (no update, delete or truncate, also for the owner and superuser), RLS by company, discovery policies for the worker only; guard-approved |
| Worker | A decision failing with an integrity, data or raise-exception error is recorded and the batch goes on; discovery skips an event for `2^(n-1)` retry units (60 s by default) after its n-th failure and skips a parked one. Lost connections, timeouts (`QueryCanceled`) and damaged privileges (`InsufficientPrivilege`) stop the batch **uncounted**. Logs and metrics: error class, attempts, parked — never a payload or message |
| API | `GET …/provider-attention` items carry `failure` (attempts, error class, last time) and the kind `failed` for a parked event; `PUT …/provider-attention/{event}/release` with a note (finance rights; the same note again repeats the answer; another note `PROVIDER_EVENT_RELEASED`; an event that is not parked `PROVIDER_ATTENTION_NOT_NEEDED`, reason `not_failed`) |
| Screen | *Needs attention* shows "Stopped after 5 failed attempts" with the error class and a **Try again** form with a required note; a waiting event shows its earlier failed attempts |
| Runbook | [PROVIDER_OPERATIONS.md](../../../runbooks/PROVIDER_OPERATIONS.md): the worker's retries, the stopped state, the new code and two counters |
| K-05 | Every order of six events of one payment and its refund (PaymentIntent processing and succeeded, Charge succeeded, refund pending and succeeded, a stale processing duplicate): **720 orders** converge to the same decisions and two operations; equal creation times in all 6 orders of three events |

## Acceptance (new tests: 25)

| Requirement | Test | Result |
|---|---|---|
| A failing event is recorded, the batch goes on | `test_a_failing_event_is_recorded_and_the_batch_goes_on` | PASS |
| Outage or damage stops the batch uncounted | `test_an_outage_or_damage_stops_the_batch_without_counting` (QueryCanceled, InsufficientPrivilege; real database errors) | PASS |
| Waits 1, 2, 4, 8 units, then parked; no more claims | `test_retries_wait_longer_each_time_then_the_event_is_parked` (measured gaps between real failures) | PASS |
| Fenced, bounded, parked claim refused by SQL | `test_sql_keeps_failures_fenced_and_bounded_and_refuses_a_parked_claim` | PASS |
| Only the worker records, only the runtime releases; permanent | `test_only_the_worker_records_failures_and_only_the_runtime_releases` (6), `test_failures_and_releases_are_permanent_even_for_owner_and_superuser` | PASS |
| Shown, released once per parking, worker tries again | `test_a_parked_event_is_shown_and_a_release_lets_the_worker_try_again`, `test_a_second_parking_needs_a_second_release` | PASS |
| Finance rights, foreign company | `test_a_release_needs_company_finance_rights` (4), `test_another_company_cannot_release` | PASS |
| Guard refuses drift | `test_the_guard_refuses_drift_in_the_new_tables` (3) | PASS |
| Every order converges (K-05) | `test_every_order_of_a_payment_and_its_refund_converges` (720), `test_equal_creation_times_converge_in_every_order` | PASS |
| Upgrade 0062 → 0063 keeps every row | `test_nonempty_0062_upgrades_keeping_every_row` | PASS |
| Real browser, desktop and mobile with axe | `test_k4a_real_browser_provider_operations` releases a parked event per project | PASS |

## Failures kept, in order

- **red-1**: 22 failed, 2 passed — missing tables and API; one `DivisionByZero` stopped the whole
  batch (the defect). The two permutation tests passed already: the K2a rules never depended on order;
  they stay as K-05 evidence.
- **dev-1**: 4 failed, 578 passed — my test read the error code at the wrong key; the K4b key list
  gains `failure`; the runbook lacked `PROVIDER_EVENT_RELEASED`; the processes test ran one batch of
  the 50 oldest undecided events of the shared test database and the new tests leave more (fragile:
  it now runs batches until its event is decided).
- **dev-2**: 583 passed, including the real browser.
- **full-1**: 244 failed, 2108 passed, 4 skipped, 2 errors — `test_location_access` drops
  `current_location_id` with every company policy and restores them from a list of migrations that
  lacked 0063, so the receipt guard refused the rest of the run; two upgrade tests listed the K tables
  without the new two. All three updated and added to the focused list; dev-3: 17 passed.

## Gates (final, suffix 2)

Run folder `GorgonaBookingTests/package-k6a-20261021-8b8f8a3`, one executor, own disposable
PostgreSQL 18.6 cluster per phase:

- **static-2** PASS: ruff, format, mypy, web typecheck, lint, format, unit (contracts), build; runtime
  npm audit 0 vulnerabilities.
- **focused-2** PASS: **599 passed** (39 files: every provider, K5 and K6a test, the K4a real
  browser, the location boundary and the stock and inventory upgrades).
- **full-2** PASS: **2354 passed, 4 skipped** (the four skips need a container, a live tenant site or
  other external targets, as before).

## Limits

No network and no provider call (K6b brings the read-only event backfill, K6c the real sandbox run).
The retry unit is 60 s by default; a parked event needs a person. No live mode, deployment or
production migration. Migrations 0001–0063 are immutable; the next is **0064**.
