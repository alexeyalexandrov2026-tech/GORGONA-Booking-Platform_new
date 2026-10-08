# H3 credit voids — validation, 2026-10-08

Branch `codex/package-h3-credit-voids` in its own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credit-voids`, created from the pushed
head of the payment-corrections branch `1d96a64`. This record is part of the commit
it describes; SHA, PR and CI are reported elsewhere. Nothing is merged.

Scope: the credit-void part of H-06 (ADR-0024 section 7) through forward
`0029_credit_voids.sql`. With it, every H3 capability of the plan exists in code
(guards, credits, payment corrections, credit voids); none of the twelve
COMPLETE criteria is accepted. Migrations `0001`–`0028` are untouched.

## Behavior

- **A version, never an edit.** An issued credit note is voided by one more
  immutable version of the same document (`state = 'voided'`, expected revision,
  revision issued + 1) that keeps every issued fact (journal, refund obligation,
  split, issue date, attestation, lines) and adds `void_entry_id`, `voided_on`,
  `void_reason`, `void_evidence_source`. Input attestation
  `attested_erroneous_credit`. A void is final; invoices and accruals are never
  voided.
- **Atomic effect.** The credit journal is mirrored line by line (origin
  `credit_void`, source = the document, posting date in an open month, never
  before the credit). C of the credited obligation is undone. The refund
  obligation is cancelled: `obligation_balance` reports its C as its principal,
  so the existing cap refuses any later reserve or payment.
- **Refused, not undone.** A refund with an effective payment, or one sent with
  an unknown outcome: `FINANCIAL_RECONCILIATION_REQUIRED`. A plain reserve on
  the refund: `FINANCIAL_STATE_INVALID` (release it first). A credit whose unpaid
  part another non-voided credit relied on to refund money:
  `FINANCIAL_RECONCILIATION_REQUIRED` with that document.
- **Voided credits stop counting.** For C, original-line capacity (a voided
  credit's line amount is free again), and the payment-correction dependency (a
  payment held only by a voided credit can be corrected again). The balance
  rules of an issued credit (no reserve, cap, unpaid first, line capacity) are
  checked by the transaction that issues it, so a later void never re-judges an
  older credit against today's balances.
- **SQL is the final arbiter.** Before insert: a void follows the issued version
  of a credit note once and preserves every issued fact. At commit: lines kept,
  void journal lineage and mirror, date, and for the voiding transaction the
  untouched refund and dependent refunded credits; receipts map to
  `credit_void`; G reverse refuses `credit_void` journals.
- **Gates and recovery** as for credits: `finance_documents` readiness and module
  state, `FINANCE_MANAGE`, permanent receipts, replay, resolve and cancel.

## Changed files

| File | Change |
|---|---|
| `api/src/gorgona_booking/db/migrations/0029_credit_voids.sql` | New, 878 lines, ASCII, LF, SHA-256 `2250f15eb5188c07adda7fcbcdd83a5ffa0530f1d83aded4cced7b126b660257`. State `voided`, origin `credit_void`, command `credit_void`; four void columns with approved CHECKs and a named deferred FK; `financial_versions_issued_refs` and new `financial_versions_void_refs`; helper `credit_voided`; replaced `obligation_balance`, `enforce_financial_version`, `enforce_invoice_origin`, `assert_invoice_consistent`, `check_invoice_integrity`, `assert_payment_consistent` (0028 body plus one voided-credit exclusion). |
| `api/src/gorgona_booking/business/credit_notes.py` | `void_credit`; void fields in read and list; voided credits excluded from line capacity. |
| `api/src/gorgona_booking/business/financial_contracts.py` | `CreditVoidInput`, `CreditState`, void fields and validation. |
| `api/src/gorgona_booking/business/ledger_contracts.py`, `financial_commands.py`, `settlements.py` | `CreditVoidPosting` and origin; recovery family; voided credits no longer block payment corrections. |
| `api/src/gorgona_booking/api/financial_documents.py` | `POST …/credits/{document}/void`. |
| `api/src/gorgona_booking/db/financial_guard.py` | `0029` and helper `credit_voided`. |
| `api/tests/integration/test_credit_voids.py` | New, 19 cases. |
| `api/tests/unit/test_credit_void_contracts.py` | New, 3 cases. |
| `web/lib/ledger-contracts.ts`, `web/tests/ledger-contracts.spec.ts` | `credit_void` in the v2 origins. |

## Runs

Private PostgreSQL 18.6 cluster `127.0.0.1:51470`, one executor; Python 3.14 venv;
Node 24; `web/node_modules` copied from the corrections checkout.

| Gate | Observed |
|---|---|
| Approved CHECK predicates | eight read from a throwaway database and approved |
| Existing unit, credit, correction, payment, settlement, invoice and accrual suites with `0029` | **718 passed** / 178.58s |
| New tests, first run | 18 passed / 1 failed: the test used expected revision 1, which the contract refuses (422) before any conflict; the test now uses a valid stale revision. Then **22 passed** |
| Ruff / format / strict mypy | PASS / 215 files |
| Web typecheck / lint / format / unit / build | PASS / PASS / PASS / 69 passed / PASS |
| Full suite, `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1` | **1160 passed / 4 skipped / 531.92s, exit 0** |
| SQL mutation red: a throwaway copy with the voided branch of `assert_invoice_consistent` emptied (47 lines) | the SQL-alone void test fails with `DID NOT RAISE CheckViolation`; copy removed |

Skips: three container checks (no local Docker: **NOT TESTED locally**) and the
optional tenant-site test. HawkScan: no runtime or key: **NOT RUN**.

## Upgrade 0028 → 0029 on a non-empty database

The corrections checkout (`1d96a64`, byte-identical `0001`–`0028`) ran its
ledger, invoice, accrual, settlement, payment, credit, correction, document and
counterparty suites with `GBA_TEST_KEEP_DB=1` (308 passed): 58,077 rows in 80
`gba` tables, 37 credit notes, 137 obligations. Guard before: corrections READY,
voids REFUSED. `apply_migrations` applied only `0029`; a re-run nothing; all
checksums match. No row count changed; 79 of 80 tables identical, the widened
`financial_document_versions` differs only by its new empty columns (no row has a
void fact). All 137 `(A, P, C, R)` identical to the `0028` definition. On old
data (rolled back): a void of credit 50 on 100/paid 70 with an untouched refund
was accepted (credited obligation C 30 → 0, refund C 0 → 20 = cancelled); a void
whose refund was reserved was refused ("a refund that was paid or is reserved is
reconciled separately"); content unchanged afterwards. Guard after: voids READY,
corrections REFUSED. The kept database was dropped. (A first attempt of this
check lost only the guard lines to an event-loop bug of the helper script; it
was repeated in full on a fresh database.)

## Decisions taken in this slice (owner may revise)

1. A void is a new version of the credit note; the issued version stays.
2. A void requires an explicit erroneous-credit attestation with reason and
   evidence; it never reverses a real refund.
3. A cancelled refund obligation is represented as fully credited (C = A), so the
   existing cap refuses it everywhere without a new state.
4. Plain refund reserves must be released first; paid or unknown-outcome
   refunds, and credits another refunded credit relied on, require
   reconciliation.
5. The void posts on its own date, not before the credit, in an open month.
6. A voided credit frees its line capacity and stops blocking payment
   corrections.

## Not done

H4 (UI, admission records), independent review of PR17 and the three stacked
slices, HawkScan, local Docker gates, the twelve COMPLETE H cases and every
acceptance or readiness promotion. FIN-03/FIN-02 stay planned.
