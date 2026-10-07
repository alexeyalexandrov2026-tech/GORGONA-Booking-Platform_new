# Independent H2 money/state review — e93ca5c

Date: 2026-10-07. Reviewer: Claude Code (Opus 5.5), separate session, read-only.
Scope: H2 financial Python/SQL from parent `75e809b` to `54852b4` (unchanged at
`e93ca5c`): migrations `0022`–`0024`, `business/settlements.py`,
`business/financial_commands.py`, `business/financial_math.py`,
`business/settlement_contracts.py`, `db/financial_guard.py`, the H2 API routes
and the H2 test files.

Method: static code review of the exact tree. **No test, cluster or browser was
run for this review**; remote CI evidence below was observed, not reproduced.
No file other than this report was written; nothing was committed or pushed.

## Delivery state observed

| Check | Observed |
|---|---|
| Local HEAD / `origin/codex/package-h2-settlements` | both `e93ca5cae9400b7e9c2207089dda0ee101b7517d`, working tree clean |
| PR16 | open, draft, unmerged, no auto-merge; head `e93ca5c`, base `codex/package-h1-persistence` |
| CI on `e93ca5c` | push run 37579456529 success; pull_request run 37579458252 success |
| Branch CI history | only failure is the recorded `15e8d0c` PR run 37574622979 |

## Verdict

No defect found that breaks `P + C + R <= A`, double-posts a journal, releases a
sent outcome without attestation, or lets a cancelled command commit. Three
money-relevant gaps, which a human can trigger through the API without forging
anything, should be fixed or explicitly accepted before full H acceptance.

## Findings

### F1 — Medium: external identity is exact-match only

`external_payments_identity` (`0024_external_payments.sql:54`) and the service
lookup (`settlements.py:726`) compare `source_account_alias` and
`external_reference` byte-for-byte. `TX-123`, `tx-123`, `TX 123` and variants
with a no-break or zero-width space are different identities. The same bank
transaction can therefore be confirmed twice against two reserves. Each
confirmation stays within its own cap, but P and the cash account are overstated
by the duplicate. This defeats the ADR-0024 §6 promise that the same external
source never repeats its effect, for the most common operator error.

Fix or decide: unique on a normalized form (for example NFKC, casefold and
collapsed whitespace) in a forward migration `0025+`, keeping the original text
for display. Alternatively, record an owner decision that exact match is intended.

### F2 — Medium-low: the cash account can be another obligation's control account

The service (`settlements.py:782`) and SQL (`0024_external_payments.sql:333-340`)
only refuse a cash account equal to the control account of an obligation
*allocated in this payment*. Any other open asset account is accepted
(`0024_external_payments.sql:176-184`), including the receivable control account
of a different obligation. That confirmation debits receivable control B and
credits receivable control A. H records P on A while no cash entered G, and G
control balances drift from the H obligation balances.

Fix or decide: refuse any account used as `control_account_id` by an obligation
or document in the book. Long-term, G needs an explicit cash/bank account role,
because type `asset` cannot distinguish them.

### F3 — Low-medium: payment posting date may precede the obligation's accrual

Neither `confirm` nor `gba.enforce_external_payment` relates `entry_date` to the
`issued_on` date of the allocated obligations. ADR-0024 only requires an open
period. An invoice issued in October can be paid with an `entry_date` in an
earlier, still-open September. Control is credited before it was debited, so the
control balance for that month is negative. That is in effect an advance, which
H2 says it does not create. `actual_external_date` is also unbounded, so a future
date is accepted as an attested past fact.

Fix or decide: require `entry_date >= max(issued_on)` of the allocated
obligations, and reject future `actual_external_date`, or record that both are
intended.

### F4 — Low: readiness guard does not cover inline column references

`_FK_PATTERN` (`financial_guard.py:103`) matches only `foreign key (...)`
syntax. Inline references, such as `currency … references gba.currencies(code)`
and `created_by … references gba.users(id)` in every H table, are not verified.
Dropping, for example, `external_payments_currency_fkey` would not fail
readiness. The money impact is small, because payment currency must equal the
document currency by trigger. The pattern dates from H1.

## Listed H2 test gaps — static assessment

All four are covered by an existing mechanism; only the tests are missing.

| Gap | Mechanism that already covers it |
|---|---|
| Dropped FK of an H2 table as readiness drift | Table-level FKs of all H2 tables are in `_FKS` (except inline references, F4) |
| `opening` variant of the legacy-entry case | `assert_invoice_consistent` requires `entry.source_kind = 'accrual'` for a manual accrual; `opening` fails like `manual` |
| Settlement recovery while finance is OFF | `claim`/`resolve_command`/`cancel_command` and `financial_command_cancellations` have no module gate; `require_book` only reads |
| Delete of settlement rows | `reject_ledger_mutation` triggers, no UPDATE/DELETE/TRUNCATE grant, both checked by the guard |

## Verified as designed

- API write routes take `gba:ledger:{tenant}` at transaction start. It is the
  same key as SQL `gba.lock_ledger`, so service reads and cap checks run under
  the lock. `lock_ledger` refuses any isolation level other than read committed.
- SQL `obligation_balance` and the service agree. P is every confirmed
  allocation. R is allocation minus this settlement's confirmations while
  reserved or sent. Confirmation moves R to P with no net change. A per-line
  check prevents confirming more than reserved.
- A fully confirmed settlement is final in both layers. Releasing a sent
  outcome needs `attested_no_payment` with reason and evidence in both layers.
  A plain release and cancel stay possible while the module is OFF.
- The payment journal is exactly the cash line plus one control line per
  allocation, on the correct sides. There is one journal per payment
  (`journal_entries_operation_unique`, unique `entry_id`). Generic reversal is
  refused for `invoice`, `accrual` and `payment` in the API and in SQL.
- The runtime cannot insert `created_transaction` (guard `_PRIVATE`). Allocations
  and payment rows are tied to the transaction of their document or payment.
- The positive readiness override is test-only (`monkeypatch`); no environment
  switch exists.

## Owner/reviewer decisions — reviewer view

1. Journal read schema 2 extended in place: acceptable while schema 2 is unmerged
   and undeployed; the Zod enum is closed, so stale clients fail loudly.
2. Same-person approval: the highest risk is an attested release of a sent
   payable followed by a new payment. Consider requiring a second person at
   least for `attested_no_payment` releases.
3. Whole-remainder release: acceptable for H2.
4. SQL-only confirmation without receipt or audit: consistent with G and H1.

Not done here: execution of any test, HawkScan, the twelve COMPLETE H
acceptance cases. FIN-03/FIN-02 readiness is unchanged.

## Resolution — branch `codex/package-h3-settlement-guards`

Fixed after this review in forward migration
`0025_settlement_guards.sql` and `business/settlements.py`; the four test gaps
were closed with tests. Exact runs are in the
[H3 guards validation](../2026-10-07-h3-settlement-guards/VALIDATION.md).

| Finding | Resolution |
|---|---|
| F1 | `gba.external_identity_key(value, rule)` (invisible format characters removed first, then NFKC, Unicode lowercase via `pg_c_utf8`, NFKC again, ends trimmed; order corrected in `0026`) is compared under the ledger lock in `enforce_external_payment` and in the service lookup; the exact unique constraint stays and the raw text is stored unchanged. Interior whitespace follows the source's rule; the only rule, `preserve`, keeps it, because manual attestations have no provider contract. |
| F2 | A cash account may not be the control account of any obligation in the book, and a document version may not take an account that already received external cash. |
| F3 | `entry_date` must be on or after `issued_on` of every allocated obligation (SQL at commit and service); `actual_external_date` may not be later than today in the business time zone (the latest local date among the business's location zones since `0026`; UTC as the documented fallback without any location). |
| F4 | `financial_guard` also approves column-level `references` (currency, created_by, …). |

The owner corrected two first-version policies before publication: whitespace is
no longer removed from identifiers (the recommendation above said "collapsed
whitespace"), and "today" is no longer the current date at UTC+14.
