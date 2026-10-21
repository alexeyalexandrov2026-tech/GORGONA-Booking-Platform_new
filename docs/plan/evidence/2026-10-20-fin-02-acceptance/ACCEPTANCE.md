# FIN-02 — technical acceptance record (2026-10-20)

**Decision: FIN-02 is `technically_verified` within the limits below.** Not a pilot acceptance and not a
production approval. Decided by the agent on the owner's delegation («делай, как ты считаешь нужным… я
доверяю тебе», 2026-10-20, in answer to the K5c readiness question).

Master plan §14.1.1: *"Повтор и перестановка provider-событий не повторяют оплату/возврат/проводку;
источник операции прослеживается."* Verified source: `b4e69e82152961380d21761c9a100515ea1645d1`
(branch `codex/package-k5r-review-fixes`, migrations to 0062). Full disposable PostgreSQL 18.6 and browser
suite on that source: 2327 passed, 4 skipped. Exact-head CI SUCCESS (run 39523031370): see §Gates.

## Package criteria (K plan, K-01–K-14)

| id | Result | Evidence |
|---|---|---|
| K-01 signature and body before reads | PASS | unit `test_stripe_event_boundary` (wrong key, modified body, stale/future, byte budgets before crypto, bad signature never parsed); ingress `test_every_refusal_has_one_body_and_stores_nothing`; routing `test_a_bad_signature_is_refused_without_row_locks_or_catalog_guards`; real signed sandbox events accepted (K0c) |
| K-02 wrong account, mode, tenant, book fail closed; admission not forgeable | PASS | `test_signed_does_not_mean_admitted_account_mode_or_version`; inbox `test_connection_scope_mismatch_never_records`; routing refusals and foreign ingress; admissions `test_no_application_role_can_record_or_change_an_admission`; real suspension refused deliveries (K0c) |
| K-03 one identity for repeats; lost acknowledgement replays; conflicts visible | PASS | inbox replay, conflict and `test_duplicate_writers_wait_on_the_uncommitted_event_insert` (pg_locks); ingress `test_lost_acknowledgement_replays_as_a_duplicate_and_conflicts_are_kept`; real Stripe resend made no second receipt (K0c) |
| K-04 one operation, effect and journal per payment | PASS | `test_payment_intent_and_its_charge_are_one_payment_operation`; `test_an_operation_is_applied_once_across_settlements_and_keys`; receipts never expire (permanent inbox) |
| K-05 permutations converge; stale, equal-time and missing objects reconcile safely | **PARTIAL** | Covered: refund before payment, stale state after success, refund failure/success in both orders (K5a), conflicts to review. **Not covered: provider retrieval of missing objects (K2b, no API backfill); permutations are tested by representative orders, not exhaustively** |
| K-06 tenant/book/currency/amount/binding must match; bad money refused | PASS (USD only) | `test_amount_currency_and_direction_come_from_the_provider`; unit money contract refusals and overflow; `test_a_mismatching_delivery_refuses_the_operation`; partial capture uses the captured amount (K5b) |
| K-07 success, partial, failed and reordered refunds; no double refund | PASS | refund after/before parent, refund cap on the corrected parent (K5a), linked refunds counted (K5r), refund conflicts both orders; real sandbox refund applied (K0c) |
| K-08 lineage and caps not bypassable by SQL; rollback leaves nothing | PASS | `test_sql_alone_cannot_forge_provider_provenance`, `test_sql_cannot_forge_or_change_a_link`, runtime cannot write receipts (K5b), admission gate by SQL alone (K5r), `test_commit_failure_rolls_back_archive_and_attestation_before_return` |
| K-09 concurrent workers, leases, retries and period close have one outcome (pg_locks) | PASS | `test_a_second_claimer_waits_for_the_first_and_skips`, `test_an_expired_lease_cannot_commit_after_a_new_claim`, `test_two_applications_of_one_operation_wait_and_one_wins`, `test_a_closed_period_and_a_concurrent_close_have_one_outcome`, revocation and suspension waits |
| K-10 manual attestation stays truthful; no duplicate journal; cross-path identity reviewed | PASS | links move no money (K3b); a manual payment naming an operation needs linking; names checks with direction (K5a, K5r) |
| K-11 disablement stops new effects; corruption refuses | PASS | links need the workflow (K5b, GBM01); `test_a_disabled_admission_gate_stops_receipts`; damaged controls answer 503; schema damage refuses receipts |
| K-12 bounded retries, no fabricated success, no secrets in logs | **PARTIAL** | Covered: ingress timeouts and exhausted pools answer retryable; the worker survives a failed batch (K5r); logs hold no body, key or ingress ID (ingress tests; 0 signing secrets in every K0c log). **Not covered: a dead-letter queue and provider reconciliation** |
| K-13 finance rights, foreign refusals, browser, pagination, safe recovery | PASS (synthetic) | provider screen, review and link permission tests; `test_another_company_cannot_*`; K4a real browser desktop and mobile with axe and complete pagination |
| K-14 real Stripe test events, full gates, CI, independent review, regression | PASS | K0c real sandbox events (E-02–E-05); full suite 2327 passed incl. Booking/FIN-01/FIN-03/WORK-01/STOCK-01 regression; independent reviews K5a and the final review (no Critical/High; fixed in K5r); exact-head CI below |

## Gates

- Full suite on `b4e69e8`: 2327 passed, 4 skipped (K5r validation).
- Exact-head CI: branch `codex/package-k5r-review-fixes` published for CI only (owner's trust, no PR, no
  `main`); head `2b640e2` (code `b4e69e8` plus docs) **SUCCESS**, run 39523031370 (job 118971150705), read
  once. The K5b head `e03c678` had passed too (run 39502582514, including the production image build).
- Real Stripe sandbox run (K0c): PASS, [validation](../2026-10-20-k0c-stripe-sandbox/VALIDATION.md).

## What `technically_verified` covers, and what it does not

Covers: Stripe Connect signed snapshot events in **test mode**, **USD**, one admitted connection per
company, receipts, attestations, decisions, applying payments and refunds into H with provenance,
linking earlier manual payments, review and attention, admission and final suspension.

Does **not** cover: **no live mode** or real money; no provider retrieval or reconciliation API; no
dead-letter queue; no other currency or provider; no fees, payouts or disputes; no pilot acceptance
and **no production approval**. Live use needs a separate owner decision, a production admission state
and the master plan stage 9 launch of all 39 directions.
