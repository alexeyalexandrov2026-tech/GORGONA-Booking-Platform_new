# H3 credit notes — validation, 2026-10-07

Branch `codex/package-h3-credits` in its own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credits`, created from the published
head of draft PR17 `c6c5d89a752a526d72ae310c42dbc63106612705`
(`codex/package-h3-settlement-guards`). This record is part of the commit it
describes; the commit SHA, PR and CI status are reported in the PR, not here.
Nothing is merged.

Scope: the credit part of H-04 and the credit and refund part of H-06 in the
[H plan](../../PACKAGE_H_PLAN_2026-10-06.md), through one forward migration
`0027_credit_notes.sql`. Payment corrections, credit voids and their dependency
guards (the rest of H3) are **not** implemented. Migrations `0001`–`0026` are
untouched.

## Behavior

- **A credit note is a document.** A third kind of the immutable financial
  document (`credit_note`) with drafts under expected revision and one issue.
  It names the invoice or manual-accrual obligation it credits; direction,
  counterparty, currency and control account follow that obligation and the
  client cannot choose others. A refund obligation is never credited.
- **Line by line.** Every credit line names the original line it reduces and
  never exceeds it; at issue the credit lines of all issued credits of a line
  never exceed that line. A counter account other than the original line's
  needs a reason, exactly then; such a line may cite a G entry of the same book
  and currency (for example the manual recognition entry), as context only.
- **The split.** At issue the unpaid balance `A − P − C` is credited first and
  becomes `C` of the credited obligation; the rest, which was already paid,
  becomes a separate `credit_refund` obligation of the opposite direction with
  the same counterparty and currency. Invoice 100, paid 70, credit 50 gives
  `C = 30` and a refund obligation of 20 (H-06). Historical cash and the
  original principal never change.
- **No active reserve.** A reserved or sent (unknown outcome) settlement of the
  credited obligation must be released or resolved first.
- **Refund account.** Exactly when a refund arises, the user chooses its control
  account: an open liability for a receivable credit, an open asset for a
  payable one, never an account that received external cash. Otherwise the
  field must be empty. The error carries the refund amount.
- **One journal.** Origin `credit`, posting date in an open month and not before
  the credited accrual: each credit line against its counter account (debit for
  a receivable credit), then the unpaid part against the original control and
  the refund part against the refund control. G reverse refuses it; it needs
  journal view schema 2.
- **The refund settles like any obligation.** Settlement reserve, sent,
  confirmation, release and the cap `P + C + R ≤ A` apply unchanged; a refund
  payment is not posted before the credit that created it.
- **SQL is the final arbiter.** At commit the credit's whole document is
  rechecked: journal lines and split, refund obligation lineage exactly when part
  was paid, no active reserve, cap, the unpaid balance credited before any
  refund, line capacity. `gba.obligation_balance` derives `C` from issued
  credits, so every existing reserve and confirmation check now includes it.
- **Gates and recovery** are those of invoices: `finance_documents` readiness and
  module state, company-wide `FINANCE_READ` / `FINANCE_MANAGE`, permanent
  reference-only receipts, replay, resolve and cancel for `credit_draft` and
  `credit_issue`.

## Changed files

| File | Change |
|---|---|
| `api/src/gorgona_booking/db/migrations/0027_credit_notes.sql` | New. Kinds `credit_note`, `credit_refund`, origin `credit`, commands `credit_draft`/`credit_issue`; columns `credited_obligation_id`, `applied_minor`, `refund_control_account_id` on versions and `credited_line_id`, `reason`, `reference_entry_id` on lines with named FKs and CHECKs; replaced `obligation_balance`, `enforce_financial_version`, `enforce_financial_line`, `enforce_invoice_origin`, `assert_invoice_consistent`, `check_invoice_integrity`; partial index for credits of an obligation. Pure ASCII, LF. SHA-256 `8628f21fdbd1e29d0a611768d6725936836689f43948d840dfc07fe9a0ea3878`. |
| `api/src/gorgona_booking/business/credit_notes.py` | New service: draft, issue, read, list. |
| `api/src/gorgona_booking/api/financial_documents.py` | Routes `GET/PUT …/books/{book}/credits[/{document}]`, `POST …/credits/{document}/issue`. |
| `api/src/gorgona_booking/business/financial_contracts.py` | Credit contracts; command kinds. |
| `api/src/gorgona_booking/business/ledger_contracts.py` | `CreditPosting`; `credit` in the v2 origins and the H-owned set. |
| `api/src/gorgona_booking/business/financial_commands.py` | Recovery family of the credit commands. |
| `api/src/gorgona_booking/business/settlement_contracts.py` | Obligation source `credit_refund`. |
| `api/src/gorgona_booking/db/financial_guard.py` | `0027` in `_MIGRATIONS`. |
| `api/tests/integration/test_credit_notes.py` | New, 33 cases. |
| `api/tests/unit/test_credit_contracts.py` | New, 13 cases. |
| `api/tests/integration/test_manual_accruals.py` | A drift case widens the kind check with an unknown kind, since `credit_note` is now approved. |
| `web/lib/ledger-contracts.ts`, `web/tests/ledger-contracts.spec.ts` | `credit` in the v2 journal origins. |
| `docs/...` | This record, handoff, status. |

## Runs

Private PostgreSQL 18.6 cluster `127.0.0.1:51470` (the H3 cluster, reused by its
only executor), `max_connections=400`, credential file outside Git. Python 3.14
venv from G with `PYTHONPATH` set to this checkout. Node 24. `web/node_modules`
copied from the H3 guards checkout after confirming an identical
`package-lock.json`; no registry access. One executor on the cluster at a time.

| Gate | Observed |
|---|---|
| Red: the new credit module against the parent `c6c5d89` | collection error, `credit_notes` cannot be imported (the capability does not exist) |
| Approved CHECK predicates after writing `0027` | every guessed PostgreSQL deparse matched except the one left as a placeholder (`financial_versions_issued_refs`), read from a throwaway database and approved |
| First green run of `test_credit_notes.py` | 33 passed / 1 failed: a refund payment dated 2026-10-02 was refused because the credit that created it was posted 2026-10-03. The refusal is correct; the test now asserts it and pays on 2026-10-04 |
| `test_credit_notes.py` | **33 passed** / 30.83s |
| Unit suite plus credit, invoice, accrual, settlement, payment and ledger suites | 724 passed / 1 failed (a unit expectation: `0` has the decimal form and is refused later by exact quantization); fixed, the test and the new zero-line API case pass |
| Ruff check / format --check / strict mypy | PASS / 214 files / 214 files |
| Web typecheck / lint / format:check / unit / build | PASS / PASS / PASS / 69 passed / PASS |
| Full suite, `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1` | **1099 passed / 4 skipped / 513.90s, exit 0** |
| SQL mutation red: a throwaway worktree at the code commit with the credit's commit-time journal, reserve, cap, split, date and line checks removed from `0027` (63 lines) | both SQL-alone credit tests fail with `DID NOT RAISE CheckViolation`: the SQL checks, not the service, stop an altered credit journal, a wrong split, an over-credit and a skipped reserve. Worktree removed |

Skips in the full run: three container checks (no local Docker: **NOT TESTED
locally**) and the optional tenant-site test. HawkScan: no `hawk` runtime and
no API key on this machine: **NOT RUN**.

## Upgrade 0026 → 0027 on a non-empty database

1. The unchanged H3 guards checkout (`c6c5d89`, migrations `0001`–`0026`,
   byte-identical to this branch) ran its ledger, invoice, accrual, settlement,
   payment, document, counterparty and legal-entity suites with
   `GBA_TEST_KEEP_DB=1`: 258 passed / 163.14s. The kept database held 44,951
   rows in 78 `gba` tables, among them 95 financial documents, 174 versions,
   176 lines, 79 obligations, 22 external payments, 56 settlement allocations,
   120 journal entries and 242 journal lines.
2. Readiness guard as the runtime role before the upgrade: guards code READY,
   credits code REFUSED.
3. `apply_migrations` with this branch as the owner role applied only
   `0027_credit_notes`; a second run applied nothing. Every recorded checksum,
   `0001`–`0027`, equals the packaged one.
4. No table's row count changed. 76 of 78 tables have identical content
   hashes; the two widened tables differ only in the text form of their rows
   (new columns), and no existing row has any new column set.
5. All 79 obligations: `C = 0`, none over the cap; no `credit` journal.
6. New rules on the old data (a complete credit on a partly paid invoice, every
   deferred check fired, always rolled back): principal 100.00, paid 70.00,
   credit 30.01 = C 30.00 + refund 0.01 accepted by every check (afterwards
   P 70.00, C 30.00); the same credit with C 29.99 and refund 0.02 refused with
   "a credit refunds only what remains after the unpaid balance". Content
   hashes were unchanged afterwards.
7. Readiness guard after the upgrade: credits code READY, guards code REFUSED.
   The older application fails closed against `0027`, so migration and
   application are deployed together.
8. The kept database was dropped.

## Decisions taken in this slice (owner may revise)

1. The unpaid balance is credited first; only the rest is refunded (the plan's
   100/70/50 example). A credit never refunds money while part of the
   obligation is still unpaid.
2. A credit needs every reserve of the credited obligation resolved, including a
   sent one with an unknown outcome.
3. The refund account is required exactly when a refund arises and refused
   otherwise, so a stored account always has an effect.
4. A reason is required exactly when a credit line uses another counter account
   than its original line; a cited G entry is context, not proof of the
   recognition of this document.
5. A credit is posted no earlier than the accrual it credits; a refund payment
   no earlier than the credit.
6. Invoice and manual-accrual obligations can be credited; refund obligations
   cannot.
7. As for invoices, a credit needs the counterparty to be active now.
8. Until voids exist, an issued credit is final.

## Not done

Payment corrections and credit voids with their dependency guards
(`FINANCIAL_RECONCILIATION_REQUIRED`), the H UI (H4), independent review of this
slice, HawkScan (no `hawk` runtime or API key), local Docker gates, and the
twelve COMPLETE H cases. FIN-03/FIN-02 stay planned and `finance_documents`
stays non-enableable.
