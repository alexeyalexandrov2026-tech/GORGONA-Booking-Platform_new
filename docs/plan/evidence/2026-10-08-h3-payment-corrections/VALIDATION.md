# H3 payment corrections — validation, 2026-10-08

Branch `codex/package-h3-payment-corrections` in its own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h3-corrections`, created from the pushed
head of the credit-notes branch `807ed59` (`codex/package-h3-credits`, stacked on
draft PR17). This record is part of the commit it describes; the commit SHA, PR
and CI status are reported in the PR, not here. Nothing is merged.

Scope: the correction part of H-06 in the [H plan](../../PACKAGE_H_PLAN_2026-10-06.md)
and ADR-0024 section 7, through one forward migration
`0028_payment_corrections.sql`. Credit voids (the last part of H3) are **not**
implemented. Migrations `0001`–`0027` are untouched.

## Behavior

- **A revision, never an edit.** A confirmed external payment is voided or
  corrected by a new revision of the same `payment_id` (revision 1 is the
  original `external_payments` row), recorded by a new settlement event
  `payment_voided` or `payment_corrected` under the expected settlement
  sequence. History, the original attestation and its journal stay as they were.
- **Identity stays bound.** Book, direction, source account alias and external
  reference stay bound to the same payment forever; a correction cannot change
  them and neither a void nor a correction frees them, so the same fact can never
  be confirmed again under another payment.
- **Attested.** Both carry `attested_erroneous_confirmation`, a reason and an
  evidence source: the earlier confirmation was wrong. A void says no money moved
  under this identity; it is never a refund. A void is final.
- **Mirror, restore, replace.** One transaction reverses the journal of the
  replaced version line by line (new origin `payment_correction`, source
  `{payment}:{revision}:reversal`), which returns those allocations to the reserve
  of a held settlement. A correction then confirms its replacement within that
  restored reserve, line by line, with its own journal
  (`{payment}:{revision}:replacement`: the cash line, then one control line per
  allocation). A correction may move the payment between lines of the
  settlement, change its amount within the reserve, its actual external date and
  its cash account. A second correction reverses the first replacement.
- **Released settlements.** A payment of a released settlement can only be
  voided; its reserve is gone, so the void lowers P without restoring R.
- **Effective P and R.** `gba.effective_payment_allocations` returns each
  payment's latest revision; `gba.obligation_balance`, settlement finality, the
  per-line cap and the settlement, payment and obligation views read it. A credit
  issued after a correction splits against the corrected P.
- **Dependencies are refused, not undone.** `FINANCIAL_RECONCILIATION_REQUIRED`,
  without effects, when a touched obligation (old or new allocation) has an
  issued credit, is a `credit_refund` obligation (a real refund is never undone
  to make a correction possible), or is held by another settlement whose sent
  outcome is unknown. `FINANCIAL_OUTCOME_UNRESOLVED` when the payment's own
  settlement is sent with an unknown remainder; after a void of a fully confirmed
  sent settlement its remainder is unknown again and needs an attested release.
- **Dates and accounts.** The posting date is in an open month and not before the
  posting of the replaced version nor the accrual; the actual external date is
  not after the business's today; the cash account is an open asset that is no
  control account. Control and refund accounts of new documents never take a
  cash account of any payment revision (`gba.cash_account_used`).
- **SQL is the final arbiter.** Before insert: event order and phase, revision
  order, void finality, cash account, external date. At commit, for the whole
  payment: contiguous revisions, the mirrored reversal, complete correction
  allocations equal to the amount, the replacement journal, dates, and for the
  revisions of the committing transaction the dependency rules; the settlement
  line cap and `P + C + R ≤ A` on effective allocations; every correction event
  has its revision and every correction journal its revision of the same
  transaction. G reverse refuses `payment_correction` journals.
- **Gates and recovery** are those of settlements: `finance_documents` readiness
  and module state, company-wide `FINANCE_MANAGE`, permanent reference-only
  receipts, replay, resolve and cancel for `settlement_payment_void` and
  `settlement_payment_correct`.

## Changed files

| File | Change |
|---|---|
| `api/src/gorgona_booking/db/migrations/0028_payment_corrections.sql` | New. Origin `payment_correction`, events `payment_voided`/`payment_corrected`, commands `settlement_payment_void`/`settlement_payment_correct`; tables `external_payment_revisions` and `external_payment_revision_allocations` with RLS, scope policies, column grants, immutability, lock, workflow, check and deferred consistency triggers; helpers `effective_payment_allocations`, `cash_account_used`; replaced `obligation_balance`, `enforce_settlement_event`, `assert_settlement_consistent`, `check_settlement_integrity`, `assert_payment_consistent`, `check_payment_integrity`, `enforce_invoice_origin`, `enforce_financial_version`. Pure ASCII, LF. SHA-256 `28c5812f254b319b2a821e9568f3b5453fc62aa30c7cda2a52d517349694fe1c`. |
| `api/src/gorgona_booking/business/settlements.py` | `void_payment`, `correct_payment`; effective views; shared date, cash and line helpers; `FinancialReconciliationRequiredError`. |
| `api/src/gorgona_booking/api/financial_documents.py` | Routes `POST …/settlements/{settlement}/confirmations/{payment}/void` and `/correct`. |
| `api/src/gorgona_booking/business/settlement_contracts.py` | `PaymentVoidInput`, `PaymentCorrectInput`, `PaymentRevisionView`; payment state, revision, effective amount and allocations, history; new event kinds. |
| `api/src/gorgona_booking/business/financial_contracts.py`, `financial_commands.py` | Two settlement command kinds and their recovery family. |
| `api/src/gorgona_booking/business/ledger_contracts.py` | `PaymentCorrectionPosting`; `payment_correction` in the v2 origins and the H-owned set. |
| `api/src/gorgona_booking/business/credit_notes.py` | The refund account check uses `gba.cash_account_used`. |
| `api/src/gorgona_booking/db/financial_guard.py` | `0028`, its two check triggers and two helpers in the readiness guard. |
| `api/tests/integration/test_payment_corrections.py` | New, 26 cases. |
| `api/tests/integration/test_location_access.py` | The schema-boundary drift case restores the scope policies of `0028` too. |
| `api/tests/unit/test_payment_correction_contracts.py` | New, 13 cases. |
| `api/tests/unit/test_settlement_contracts.py`, `test_document_contracts.py` | After a release only a void may follow; two more guarded tables. |
| `web/lib/ledger-contracts.ts`, `web/tests/ledger-contracts.spec.ts` | `payment_correction` in the v2 journal origins. |
| `docs/...` | This record, handoff, status. |

## Runs

Private PostgreSQL 18.6 cluster `127.0.0.1:51470` (the H3 cluster, reused by its
only executor), credential file outside Git. Python 3.14 venv from G with
`PYTHONPATH` set to this checkout. Node 24. `web/node_modules` copied from the
credits checkout (same `package-lock.json`); no registry access. One executor on
the cluster at a time.

| Gate | Observed |
|---|---|
| Approved CHECK predicates after writing `0028` | all thirteen read from a throwaway database (placeholders first, never guessed) and approved; the migration applies cleanly on `0001`–`0027` |
| Existing unit, settlement, payment and credit suites with `0028` | 606 passed / 1 failed: a unit test still said nothing may follow a release; a payment void may now, by design. The test now states exactly that (and the guarded-table count 63 → 65) |
| New correction tests, first run | `test_payment_corrections.py` 23 passed / 26.32s; with the SQL-alone correction cases and the unit contracts **39 passed** / 30.20s (after fixing a duplicated keyword in the unit helper) |
| Ruff check / format --check / strict mypy | PASS / 216 files / 216 files |
| Web typecheck / lint / format:check / unit / build | PASS / PASS / PASS / 69 passed / PASS |
| Full suite, first run (`GBA_REQUIRE_POSTGRES=1`) | 1028 passed / 18 failed / 81 errors: from `test_location_access.py` on every test got 503. Its schema-boundary drift case drops `gba.current_location_id()` with cascade and restores the scope policies of a fixed list of migrations that did not include `0028`; the session database then stayed unready. Fixed by adding `0028`; that file alone 11 passed |
| Full suite, second run with `GBA_REQUIRE_BROWSER=1` | 1127 passed / 11 failed: every browser test, "build web first" (the new checkout had no `web/out`). The web build above produced it |
| Full suite, final, `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1` | **1138 passed / 4 skipped / 493.79s, exit 0** |
| SQL mutation red: a throwaway copy of `api` with the revision commit checks removed from `0028` (144 lines: mirrored reversal, correction allocations and journal, dependency rules) | the four SQL-alone correction tests fail with `DID NOT RAISE CheckViolation`: the SQL checks, not the service, stop an unmirrored reversal, a wrong correction and a void another fact depends on. Copy removed |

Skips in the final run: three container checks (no local Docker: **NOT TESTED
locally**) and the optional tenant-site test. HawkScan: no `hawk` runtime and no
API key on this machine: **NOT RUN**.

## Upgrade 0027 → 0028 on a non-empty database

1. The unchanged credits checkout (`807ed59`, migrations `0001`–`0027`,
   byte-identical to this branch) ran its ledger, invoice, accrual, settlement,
   payment, credit, document, counterparty and legal-entity suites with
   `GBA_TEST_KEEP_DB=1`: 291 passed / 192.17s. The kept database held 52,269
   rows in 78 `gba` tables, among them 110 obligations, 31 external payments, 32
   payment allocations, 235 settlement events, 173 journal entries and 353
   journal lines.
2. Readiness guard as the runtime role before the upgrade: credits code READY,
   corrections code REFUSED.
3. `apply_migrations` with this branch as the owner role applied only
   `0028_payment_corrections`; a second run applied nothing. Every recorded
   checksum, `0001`–`0028`, equals the packaged one.
4. All 78 existing tables have identical content; the two new tables are empty;
   no `payment_correction` journal.
5. For all 110 obligations `(A, P, C, R)` from the new effective definition is
   identical to the `0027` definition.
6. New rules on the old data (always rolled back, every deferred check fired): a
   complete void of an old payment of 70 on a held settlement was accepted, P
   70 → 30 and R 0 → 40 for its obligation; a void of a payment whose obligation
   has an issued credit was refused with "an issued credit depends on this
   payment; reconcile it separately". Content hashes were unchanged afterwards.
7. Readiness guard after the upgrade: corrections code READY, credits code
   REFUSED. The older application fails closed against `0028`, so migration and
   application are deployed together.
8. The kept database was dropped.

## Decisions taken in this slice (owner may revise)

1. A void or a correction is a new revision of the same payment under a new
   settlement event; the external identity is never changed or freed.
2. Both require an explicit attestation that the earlier confirmation was wrong,
   with a reason and an evidence source; a void is never a refund.
3. A correction is bounded by the restored reserve of each settlement line, so it
   may raise an understated amount within the reserve but never beyond it.
4. A payment of a released settlement can be voided (P falls, no reserve comes
   back) but not corrected; a new settlement is needed for a new confirmation.
5. Corrections post on their own date, in an open month and not before the
   replaced version; the original month is never reopened.
6. Refused as a dependency: an issued credit on a touched obligation, any refund
   obligation (refund payments are not corrected in this initial H), another
   settlement with an unknown sent outcome on a touched obligation; and a payment
   of a settlement whose own sent remainder is unknown.
7. A void of a fully confirmed sent settlement makes its remainder unknown again,
   so it needs the attested release of a sent outcome.
8. Correction journals have their own origin `payment_correction` (v2 views);
   the original `payment` journal is never reversed by G.

## Not done

Credit voids (mirror credit, undo C, cancel an untouched refund claim) with their
dependency guards, the H UI (H4), independent review of PR17, the credit-notes
slice and this slice, HawkScan (no `hawk` runtime or API key), local Docker
gates, and the twelve COMPLETE H cases. FIN-03/FIN-02 stay planned and
`finance_documents` stays non-enableable.
