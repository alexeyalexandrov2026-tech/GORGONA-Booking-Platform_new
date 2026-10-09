# H-01–H-12 — проверяемая матрица

Источник критериев: [Package H plan](../../PACKAGE_H_PLAN_2026-10-06.md).
Источник нового исполнения: [VALIDATION](VALIDATION.md).
Integration filenames ниже относятся к `api/tests/integration/`; web paths
относительны repository root. Local full/review проверены; exact-SHA CI после
push отдельно записывается в Draft PR, это внешний delivery gate.
Production acceptance и FIN-03/FIN-02 promotion не выполняются.

| ID | Сценарии и evidence | Результат на текущем source |
|---|---|---|
| H-01 | `test_invoice_issue.py::test_issue_is_one_invoice_obligation_and_exact_journal`, `test_closed_period_rolls_back_every_issue_effect`; `test_manual_accruals.py::test_manual_accrual_is_one_new_obligation_and_exact_journal`, `test_closed_period_rolls_back_every_accrual_effect`, `test_existing_manual_entry_is_never_linked_or_accrued_twice`. Атомарный source/obligation/journal/minimal receipt, explicit new accrual. | PASS local full/667.92s |
| H-02 | `test_invoice_issue.py::test_sql_history_stays_insert_only`; `test_credit_notes.py::test_issued_credit_history_and_journal_stay_unchanged`; `test_payment_corrections.py::test_correction_history_stays_unchanged`; `test_credit_voids.py::test_voided_history_stays_unchanged`; expected-version races в invoice/credit suites. | PASS local full/667.92s |
| H-03 | `test_settlements.py::test_two_documents_reserving_70_of_100_wait_on_real_lock_and_one_wins`. Два порядка стартов, реальное ожидание lock. | PASS local full/667.92s |
| H-04 | `test_external_payments.py::test_two_partial_confirmations_wait_on_real_lock_and_one_wins`, `test_release_and_confirmation_race_keep_the_cap`; `test_credit_notes.py::test_credit_and_reserve_wait_on_one_lock_and_keep_the_cap`; `test_credit_voids.py::test_void_and_refund_reserve_wait_on_one_lock`. | PASS local full/667.92s |
| H-05 | `test_invoice_issue.py::test_replay_and_minimal_recovery_survive_receipt_cleanup`; `test_manual_accruals.py::test_accrual_replay_and_recovery_survive_receipt_cleanup`; settlement/credit/correction/void `replay_recovery_and_cancel_before_late_original`; `test_external_payments.py::test_replay_and_the_same_external_identity_post_money_once`; реальный browser reload/retry в `test_h4_browser.py`. | PASS local full + final H4 browser |
| H-06 | `test_credit_notes.py::test_paid_70_credit_50_is_credit_30_and_a_separate_refund_obligation_of_20`, `test_another_account_needs_a_reason_and_may_cite_the_recognition_entry` (actual G closing balance deferred=0, revenue credit50, receivable debit50), `test_refund_obligation_settles_through_its_own_reserve_and_payment`; correction tests preserve identity/effective allocations; `test_credit_voids.py::test_a_touched_refund_is_never_undone`; H4 browser paid refund refuses later credit void. | PASS local full + final H4 browser |
| H-07 | Invoice/accrual/confirmation/credit/correction/void closed-date tests; each suite `*_routes_keep_company_finance_permissions`, foreign-party/book/currency tests, invoice/accrual/payment generic reversal negatives; H3 F4 archived exact-mirror regressions. | PASS local full/667.92s |
| H-08 | Invoice/accrual/settlement/payment/credit/correction/void `test_sql_*` negatives и `test_damaged_*_controls_fail_readiness_with_503`; packaged predicate tests; `test_h3_upgrade.py` preserves rows/checksums/RLS and refuses conflicts. Admission extends equivalent checks without altering financial guard. | PASS local full + focused upgrade/admission |
| H-09 | H suites OFF/withdrawn-readiness tests; `test_settlements.py::test_settlement_recovery_replay_and_cancel_work_while_finance_is_off`, sent outcomes require explicit resolution; `test_financial_overview.py` and closed-registry desktop/mobile browser. | PASS local full + overview/closed browser |
| H-10 | `test_provider_admission.py::test_history_lifecycle_has_no_money_or_positive_capability`, SQL positive-assessment rejection, permissions/tenant isolation, immutable evidence, concurrent revision/idempotency/cancel/TTL, damaged guard; admission browser lifecycle. Нет gateway/network/webhook handlers. | PASS focused/full/final browser |
| H-11 | `test_h4_browser.py::test_h4_real_browser_and_closed_production_gate`, `web/tests/finance.spec.ts`, `admission.spec.ts`: desktop/mobile actual OIDC/API/PG, partial confirmation, response loss/re-auth reload/same-key retry, untouched void and actually paid refund/refusal, truthful historical labels, Axe=0/overflow=false. | PASS final browser/51.06s; full run PASS before same-book-only UI delta |
| H-12 | Full Python включает G ledger/old-new journal contracts/browser/security; web 94 unit PASS, type/lint/format/build PASS. Independent static reviewer и exact-SHA CI/container checks являются отдельными gate. | PASS local/review; exact-SHA CI/container gate recorded in Draft PR after push |

Утверждения ограничены выполненными сценариями и предусмотренными schema guard
approvals. Это не доказательство отсутствия всех возможных финансовых ошибок,
provider compliance, production data quality или runtime parity с production.
Миграция 0031 не меняет ранее записанные финансовые facts; populated upgrade
сравнивает все прежние таблицы и checksums. FORCE RLS/policies/grants проверяет
admission readiness guard и его negative integration tests.
