# K2a receipt decisions without money — local validation

**PASS for this bounded local slice.** Branch `codex/package-k2a-receipt-decisions`, parent
`b6c8040`, source commit `6e9bbfc74a09a5d472aaff25328356d6f71e8706`. [CHECKS.json](CHECKS.json) was
generated before the source commit and binds source blobs, commands, exit codes and log digests.
Not published. Design: [K2a](../../PACKAGE_K2A_DESIGN_2026-10-17.md). Executor: Claude, inline,
after the owner's decisions of 2026-10-17: «отдельная группа gba_receipt_worker, все конфликты на
ручную сверку, только прямые платежи и возвраты, события без аттестации не обрабатывать».

## What changed

- `db/bootstrap.py`, `db/cli.py`, `db/migrate.py`: NOLOGIN group `gba_receipt_worker`; optional
  worker login from `GBA_RECEIPT_WORKER_ROLE`/`GBA_RECEIPT_WORKER_PASSWORD` (both or neither); all
  role names and passwords differ; no role in two groups; migrate refuses without the group
- `db/pool.py` (runtime check) and `providers/authenticated_receipts.py` (writer check) refuse
  worker membership
- `db/migrations/0050_provider_receipt_decisions.sql` (new): `gba.provider_receipt_operation`
  (identity and classification of stored facts, rules version 1), `provider_operations`,
  `provider_event_leases` (fencing `generation`, at most ten minutes, takeover only after expiry,
  never deleted), `provider_event_decisions` (append-only; the trigger derives outcome, reason
  and operation from the facts, checks the lease and locks the operation row); RLS, company
  policies, worker-only discovery policies on attestations and decisions, column grants to the
  worker only, TRUNCATE refused
- `db/provider_receipt_guard.py`: three groups, the three tables, the new functions, policies,
  checks, keys and column grants
- `providers/receipt_worker.py` (new): `process_batch` (role and schema check, discovery, one
  claim and one decision transaction per event), `claim`, `decide`, `discover`
- Tests: `test_provider_receipt_decisions.py` (new, 40), `tests/unit/test_receipt_worker_bootstrap.py`
  (new, 18), `test_bootstrap_order.py` (+1: migrate without the worker group);
  `test_location_access.py` restores the 0050 company policies and the worker grant after it drops
  `current_location_id()`; `test_stock_upgrade.py`/`test_inventory_upgrade.py` name the new tables
- `docs/DEVELOPMENT.md`: worker credential row and bootstrap order

Migrations 0001–0049 unchanged (next 0051). No dependency, HTTP route, process entry point,
ledger, settlement, obligation, readiness or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| W-01 | PaymentIntent and Charge are one payment operation; a refund is its own operation with its parent, also when first | `test_payment_intent_and_its_charge_are_one_payment_operation`, `test_a_refund_is_its_own_operation_even_when_it_arrives_first` | PASS |
| W-02 | One decision per event across duplicate deliveries and repeated runs; a stale state after a success is `not_final` | `test_duplicates_and_repeated_runs_decide_each_event_once`, `test_a_stale_state_after_a_success_is_not_final_and_the_success_stays` | PASS |
| W-03 | Conflicts and unkeyed facts are `needs_review` with their reason | `test_conflicts_and_unkeyed_facts_go_to_manual_review` ×7, `test_a_conflicting_variant_of_an_event_goes_to_manual_review` | PASS |
| W-04 | A second claimer waits (observed `pg_locks` wait) and skips | `test_a_second_claimer_waits_for_the_first_and_skips` | PASS |
| W-05 | Events of one operation are decided in turn (observed wait); the second sees the first's success | `test_events_of_one_operation_are_decided_in_turn` | PASS |
| W-06 | Fencing: expired-then-reclaimed, forged holder or generation refused; leases change only by bounded claim or expired takeover | `test_an_expired_lease_cannot_commit_after_a_new_claim`, `test_leases_change_only_by_a_bounded_claim_or_an_expired_takeover` ×4 | PASS |
| W-07 | Unattested rows never claimed or decided; no non-receipt table changes | `test_unattested_archive_rows_are_never_processed_and_no_money_moves` | PASS |
| W-08 | Permanence for worker, owner and superuser; runtime and writer cannot read the new tables; the worker reaches nothing else | `test_worker_cannot_rewrite_decisions_or_reach_other_tables` ×8, `test_decisions_and_operations_are_permanent_even_for_owner_and_superuser`, `test_runtime_and_writer_cannot_read_worker_tables` ×3, `test_worker_role_is_neither_runtime_nor_writer`, `test_runtime_and_writer_are_not_workers` | PASS |
| W-09 | Bootstrap and migrate for the worker group; runtime refuses worker membership | `test_receipt_worker_bootstrap.py` ×18, `test_migrate_refuses_before_bootstrap_created_the_writer_group[gba_receipt_worker]`, `test_runtime_role_refuses_worker_membership` | PASS |
| W-10 | Drift refuses the worker, the writer and the runtime archive; repaired schema passes | `test_worker_drift_stops_the_worker_the_writer_and_the_runtime_archive` ×5 | PASS |
| W-11 | Existing K and full suite | focused-2, full-2 | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 571 passed in 478.99s (0:07:58) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2154 passed, 4 skipped in 1765.52s (0:29:25); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 323 source files |
| Web typecheck, lint, format, unit, build | PASS (web unchanged) |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop (`data_removed: true`); no `postmaster.pid` left |
| K CI | NOT TESTED (not published) |

New cases 59, regression cases 272 (see CHECKS.json).

## Failures kept in the record

**red-1, product RED** on `b6c8040`: collection failed (no `receipt_worker` module, no
`RECEIPT_WORKER_GROUP`).

**dev-1, test defect**: 2 failed, 131 passed in 88.26s. The test helper read every company's
decisions: the worker may discover decisions of all companies by design. The helper now filters
by company.

**dev-2**: 233 passed in 180.82s.

**gates-1, focused-1 FAIL**: 8 failed, 563 passed in 481.21s; full-1 did not run.
`test_location_access` drops `current_location_id()` with CASCADE, which also drops the 0050
company policies; it restored only those of 0044–0046 and the writer's grant, so the guard refused
every later receipt path. `test_stock_upgrade` named only the K tables of 0044–0046. Both tests
(and `test_inventory_upgrade`) now restore or name the 0050 objects. Not counted as green.

**dev-3**: 66 passed in 76.36s. Then gates-2 above.

## Limits

Nothing is applied: no ledger, settlement or obligation effect (K3). No provider retrieval for
ambiguous facts (K2b, needs K0). A conflicting variant attested after an event's decision does not
revise it; K3 must recheck deliveries before any money. The worker can read every company's
attestation and decision IDs for discovery (like the writer's route lookup). There is no process
entry point, schedule or deployment; the Azure bootstrap job does not pass the worker variables.
FIN-02 planned; ADR-0027 Proposed.
