# K3a observed provider money into H — local validation

**PASS for this bounded local slice.** Branch `codex/package-k3a-provider-money`, parent
`1476108`, source commit `2f91368271458d6f20030e43ab9409751c3fa62d`. [CHECKS.json](CHECKS.json)
was generated before the source commit and binds source blobs, commands, exit codes and log
digests. Not published. Design: [K3a](../../PACKAGE_K3A_DESIGN_2026-10-17.md). Executor: Claude,
inline, after the owner's decisions of 2026-10-17: a finance user applies; one registered
clearing account; USD; manual voids and corrections allowed.

## What changed

- `db/migrations/0051_provider_money_access.sql` (new, K): the runtime reads its company's
  `provider_operations` and `provider_event_decisions`, may lock an operation row (`update
  (currency)`, refused by the immutability trigger) and executes `gba.provider_receipt_operation`
- `db/migrations/0052_provider_payment_provenance.sql` (new, H): `external_payments.attestation`
  adds `provider_observed`; `provider_clearing_accounts` (one per connection) and
  `external_payment_provenance` (one per operation in the company, with its success event), both
  with the H trigger set and company scope; `gba.assert_provider_payment`, called from
  `gba.assert_payment_consistent` in the applying transaction, rechecks decisions, deliveries,
  revocation, book, USD, amount, date, alias and reference, clearing account, obligation kind,
  earlier manual references and, for refunds, the applied parent, party and cap
- `db/financial_guard.py`, `db/provider_receipt_guard.py`: the new objects and grants
- `business/provider_payments.py` (new): operation list with states, readiness (lock the operation,
  then read in a new statement), clearing account registration
- `business/settlements.py`: `confirm_provider`; the manual and provider paths share one posting
  step; the command receipt stays `settlement_confirm`; `load_payment` names the operation
- `business/settlement_contracts.py`, `api/financial_documents.py`: contracts and three routes
  (`GET …/provider-operations`, `PUT …/provider-connections/{id}/clearing-account`,
  `POST …/settlements/{id}/provider-confirmations/{payment}`)
- `web/lib/financial-contracts.ts`, `web/components/financial-workspace.tsx`: the payment
  contract accepts the provenance (coupled to the attestation) and labels a provider payment
- Tests: `test_provider_payments.py` (new, 27); K2a drift case `runtime-loses-decisions` (+1) and
  the runtime read expectations; `test_location_access` restores the 0052 company policies;
  upgrade fixtures omit companies with provider payments and name the two tables; web unit and a
  schema-guard count

Migrations 0001–0050 unchanged (next 0053). No dependency, provider call, worker entry point,
readiness or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| M-01 | One payment, allocations and journal with provenance; replay | `test_an_observed_payment_posts_once_with_provider_provenance` | PASS |
| M-02 | Once per operation; concurrent applications wait (observed lock waits) and one wins | `test_an_operation_is_applied_once_across_settlements_and_keys`, `test_two_applications_of_one_operation_wait_and_one_wins` | PASS |
| M-03 | Amount, USD, direction, cap and date from facts and H; no typed amount; clearing account | `test_amount_currency_and_direction_come_from_the_provider`, `test_the_clearing_account_is_registered_once_and_is_never_a_control` | PASS |
| M-04 | Pending, review, not final, mismatching delivery, revoked connection or config refuse | `test_an_operation_that_is_not_ready_moves_no_money` ×3, `test_a_mismatching_delivery_refuses_the_operation`, `test_a_revoked_connection_or_config_refuses_new_money` ×2 | PASS |
| M-05 | A worker decision and an application serialise on the operation row (observed wait) | `test_a_worker_decision_and_an_application_wait_for_each_other` | PASS |
| M-06 | Refunds after an applied parent, refund obligations only, within the parent's amount | `test_a_refund_applies_after_its_parent_within_its_amount`, `test_a_refund_before_its_parent_payment_is_refused` | PASS |
| M-07 | Closed period and a concurrent close: one legal outcome, no partial row | `test_a_closed_period_and_a_concurrent_close_have_one_outcome` | PASS |
| M-08 | SQL cannot forge or change provenance; company scope; worker and writer reach no H table | `test_sql_alone_cannot_forge_provider_provenance` ×2, `test_provenance_is_permanent_and_scoped_to_its_company`, `test_worker_and_writer_cannot_reach_provider_money` | PASS |
| M-09 | A manual payment naming the ID needs linking; void like a manual payment; never reapplied | `test_a_manual_payment_naming_the_provider_id_needs_linking`, `test_a_provider_payment_is_voided_like_a_manual_one_and_never_reapplied` | PASS |
| M-10 | Later facts change no money and show a conflict | `test_later_facts_change_no_money_and_show_a_conflict` | PASS |
| M-11 | Drift of the H trigger or the K grant refuses with 503; repaired schema applies; existing suites | `test_damaged_provider_money_controls_fail_with_503` ×2, focused-2, full-2 | PASS |

Also: authentication, another company's manager refused, unknown operation at the service level.

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 777 passed in 626.41s (0:10:26) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2182 passed, 4 skipped in 1723.33s (0:28:43); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 325 source files |
| Web typecheck, lint, format, unit, build | PASS |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop; no `postmaster.pid` left |
| K CI | NOT TESTED (not published) |

New cases 28, regression cases 531 (see CHECKS.json).

## Failures kept in the record

- **red-1, product RED** on `1476108`: collection failed (no `ProviderPaymentConfirmInput`).
- **dev-1, product**: a plpgsql `IF` condition held an unparenthesised `CASE … THEN` (0052 did not
  compile). Fixed.
- **dev-2, product and test**: 18 failed, 9 passed. The plpgsql variable `v` was ambiguous with a
  table alias in the copied `assert_payment_consistent` (renamed `provenance`); the test used the
  revocation reason `compromised` (allowed: `compromise`, `retired`).
- **dev-3, product**: 13 failed, 14 passed. The receipt operation `settlement_provider_confirm` was
  refused by the H rule pairing a `confirmed` event with `settlement_confirm`; the new command kind
  was dropped.
- **dev-4, test defect**: 1 failed, 26 passed. The closed-period test issued an invoice after
  October closed.
- **dev-5, test defects**: 17 failed, 294 passed. The K2a drift case `runtime-reads-decisions`
  repaired itself by revoking the read 0051 makes necessary, so the receipt guard refused every
  later receipt path; the upgrade fixture copied provider payments into pre-0052 schemas; a unit
  count of schema-guard definitions. dev-6: 312 passed.
- **gates-1, product**: static-1 PASS, focused-1 776 passed in 586.75s; full-1 **1 failed**,
  2181 passed, 4 skipped in 1699.70s. The strict web payment contract refused the new
  `provider_operation_id`, so the H4 browser test found no payment detail. Fixed in the web
  contract and label; dev-7 28 passed. Not counted as green.

## Limits

USD only. Gross amounts go to the clearing account; provider fees, payouts and bank
reconciliation stay manual. An earlier manual payment naming the provider ID refuses the
application until linking exists (K3b). No provider retrieval (K2b, needs K0). No UI for
operations; "applied with conflict" is visible only in the API list (K4). Readiness scans the
connection's inbox per operation (no expression index yet). No worker entry point, schedule or
deployment. FIN-02 planned; ADR-0027 Proposed.
