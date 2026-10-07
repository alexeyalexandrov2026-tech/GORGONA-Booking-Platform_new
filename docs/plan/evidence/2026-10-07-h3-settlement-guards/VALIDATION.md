# H3 settlement guards — validation, 2026-10-07

Branch `codex/package-h3-settlement-guards` in its own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h3-guards`, created from the published
H2 head `e93ca5cae9400b7e9c2207089dda0ee101b7517d` and stacked on PR16. This
record is part of the commit it describes; the commit SHA, PR and CI status are
reported in the PR, not here. Nothing is merged.

Scope: fixes F1–F4 of the
[independent H2 money/state review](../2026-10-07-h2-settlements/INDEPENDENT_MONEY_STATE_REVIEW_e93ca5c.md),
closes its four listed test gaps and applies the owner's two policy corrections
(source-aware whitespace for F1, business time zone for F3). Credits, refund
obligations and guarded corrections (the rest of H3) are **not** implemented.
Migrations `0001`–`0024` are untouched; behavior changes only through forward
migration `0025`.

## Changed files

| File | Change |
|---|---|
| `api/src/gorgona_booking/db/migrations/0025_settlement_guards.sql` | New. `gba.external_identity_key(text, text)`, `gba.business_timezone(uuid)`; replaced `enforce_financial_version`, `enforce_external_payment`, `assert_payment_consistent`. Pure ASCII, LF. SHA-256 `bb49694f81855ecbc0481db8e2eb7db0819f198322de210b5207d7bab1a1c3be`. |
| `api/src/gorgona_booking/db/financial_guard.py` | `0025` in `_MIGRATIONS`; both new helpers approved; column-level `references` added to the approved FKs. |
| `api/src/gorgona_booking/business/settlements.py` | `confirm`: identity lookup through the comparison form, book-wide cash/control check, posting-date rule, external date bounded by the business today. |
| `api/tests/integration/test_external_payments.py` | Identity, whitespace, time-zone boundary, cash/control and date tests; SQL-variant identity and settlement-row deletes in the SQL-alone test; four new readiness drift cases; date/cash parameters for the SQL-alone helper. |
| `api/tests/integration/test_settlements.py` | Settlement recovery, replay and cancel while finance is OFF. |
| `api/tests/integration/test_manual_accruals.py` | Legacy-entry case parametrized for `manual` and `opening`. |
| `docs/plan/evidence/2026-10-07-h2-settlements/INDEPENDENT_MONEY_STATE_REVIEW_e93ca5c.md` | Review report plus its resolution table. |
| `docs/plan/evidence/2026-10-07-h3-settlement-guards/VALIDATION.md` | This record. |
| `docs/plan/NEXT_AGENT_H3_GUARDS_2026-10-07.md` | Handoff. |
| `docs/plan/GORGONA_IMPLEMENTATION_STATUS.md` | Current H3 slice section. |

No `web/` file changed.

## Behavior

- **F1, identity.** Two external payments of one book and direction are the same
  fact when `gba.external_identity_key(value, rule)` of the alias and of the
  reference are equal. The comparison form applies NFKC (full-width and other
  compatibility forms, and every Unicode space, become their plain form),
  removes default-ignorable invisible code points (zero-width, bidi controls,
  variation selectors, tags, soft hyphen, fillers), trims the ends and
  lowercases with `pg_c_utf8`. Interior whitespace follows the source's rule.
  The only rule is `preserve`, the conservative default: every interior space
  keeps its place and count, so `FAKE TXN 77`, `FAKE  TXN 77` and `FAKETXN77`
  are three identifiers. It applies because every H2 confirmation is a manual
  attestation with no provider contract; an unknown rule is refused
  (`invalid_parameter_value`), so a provider rule needs its own accepted change.
  The stored alias and reference keep their raw text for audit. Enforced under
  the ledger lock in `enforce_external_payment` (`unique_violation`) and checked
  first by the service, which still answers `FINANCIAL_SOURCE_ALREADY_RECORDED`
  with only the existing `payment_id`. The exact unique constraint stays as a
  second line.
- **F2, accounts.** A confirmation refuses a cash account that is the control
  account of any obligation in the book (SQL and service). A document version
  refuses a control account that already received external cash (SQL; the API
  answers the generic 409 used for every SQL account rule of documents).
- **F3, dates.** A payment's `entry_date` must be on or after `issued_on` of
  every allocated obligation (service 422 `LEDGER_DATE_INVALID`; SQL at commit).
  `actual_external_date` may be earlier (prepaid money is a fact) but not later
  than today in the business time zone. That zone comes from
  `gba.business_timezone(tenant)`: the one IANA zone shared by all the
  business's locations, each validated and governed by the confirmed timezone
  fact. Ledger books and legal entities have no zone and H2 has no provider
  zone, because every confirmation is a manual attestation. With no location, or
  locations in several zones, no zone is authoritative and UTC is the documented
  fallback. The service and the trigger evaluate the same SQL at the same
  transaction instant; the 422 carries `timezone` and `today`.
- **F4, readiness.** The guard also approves column-level `references`
  (`currency`, `created_by`, …) of every H table, and both new helpers by source.

## Runs

Private PostgreSQL 18.6 cluster `127.0.0.1:51470`, `max_connections=400`, data
under `%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007` (credential file
there, never in Git). Python 3.14 venv from G with `PYTHONPATH` set to the
checkout under test. Node 24.18.0. `web/node_modules` copied from the H2
checkout after confirming an identical `package-lock.json` hash; no registry
access. One executor on the cluster at a time.

First version (whitespace removed, UTC+14 bound):

| Gate | Observed |
|---|---|
| Baseline: H2 payment file on this cluster before any change | 25 passed / 24.74s |
| Red: new and changed tests against unmodified `e93ca5c` source in a throwaway detached checkout | 6 failed / 12 passed / 15.56s, exit 1 |
| Affected H suites after the change | 135 passed / 105.27s |
| Full suite, `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1` | 1049 passed / 4 skipped / 529.23s, exit 0 |
| Web typecheck / lint / format:check / unit / build | PASS / PASS / PASS / 69 passed 1.7s / PASS |

After the two policy corrections:

| Gate | Observed |
|---|---|
| Affected suites (payments, settlements, accruals) | 139 passed / 117.05s |
| Full suite, `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1` | 1053 passed / 4 skipped / 480.70s, exit 0 |
| `0025` rewritten as pure ASCII (see below); affected suites, invoices and all unit tests | 633 passed / 117.00s |
| Ruff check / format --check / strict mypy | PASS / 211 files / 211 files |
| Full suite on the final tree, `GBA_REQUIRE_POSTGRES=1`, `GBA_REQUIRE_BROWSER=1` | **1053 passed / 4 skipped / 445.56s, exit 0** |
| Web gates | not rerun: no `web/` file changed since the PASS above |

Red details (first version). Failed for the intended reason: F1 API variant
accepted with 200; F2 another obligation's control accepted as cash with 200;
F3 early posting date accepted with 200; SQL-alone exact repeat raised only the
bare unique constraint; readiness stayed 200 with the inline currency FK dropped
(F4) and with the identity helper replaced. Passed already, as expected for pure
test gaps: table-level FK drift, the `manual` and `opening` legacy cases,
recovery while finance is OFF, and the nine existing drift cases. In the
throwaway copy only, the helper drift case's restore was stubbed, because the
packaged helper does not exist before `0025` and the module would not collect.
The policy-correction tests were not run red separately; the whitespace test
asserts three distinct confirmations that the first version would have merged.

ASCII rewrite. The invisible-character class of `external_identity_key` had
been saved as 22 literal invisible code points, not escapes. It now uses
PostgreSQL `\uXXXX` escapes; the file is ASCII and decodes back byte for byte to
the previous text. On PostgreSQL both classes remove exactly the same 4174 of
the 1,112,063 non-surrogate code points (0 differ).

Skips in the full runs: three container checks (no local Docker: **NOT TESTED
locally**) and the optional tenant-site test.

## Upgrade 0024 → 0025 on a non-empty database

1. The unchanged H2 checkout (`e93ca5c`, migrations `0001`–`0024`, byte-identical
   to this branch) ran its ledger, invoice, accrual, settlement, payment,
   document, counterparty and legal-entity suites with `GBA_TEST_KEEP_DB=1`:
   246 passed / 165.16s. The kept database held 42,353 rows in 78 `gba` tables,
   among them 14 external payments, 15 payment allocations, 48 settlements, 155
   settlement events, 72 obligations, 104 journal entries and 486 locations.
2. Readiness guard as the runtime role before the upgrade: H2 code READY, H3
   code REFUSED (its helpers do not exist yet).
3. `apply_migrations` with this branch as the owner role applied only
   `0025_settlement_guards`; a second run applied nothing. Every recorded
   checksum, `0001`–`0025`, equals the packaged one.
4. Every `gba` table's row count and content hash (md5 of all rows in order) is
   identical before and after: no row changed.
5. Existing rows that conflict with the new rules: identity duplicates under the
   comparison form 0, attested dates after the business today 0, cash accounts
   that are control accounts in the book 0, payments posted before their
   accrual 0. The paying tenants resolve to `America/New_York`.
6. New rules on the old data (complete confirmations beside a recorded payment,
   every deferred check fired, always rolled back): exact copy, letter-case
   variant, zero-width space inside and full-width variant all refused with
   `unique_violation` "this external payment identity is already recorded"; the
   same reference with one interior space added was accepted by every check.
   Table hashes were unchanged afterwards.
7. Readiness guard after the upgrade: H3 code READY; H2 code REFUSED. The old
   application fails closed against `0025`, as for every earlier migration, so
   the migration and the H3 application are deployed together.
8. The kept database was dropped.

Not done: CI (reported in the PR), an independent review of this slice,
HawkScan (no `hawk` runtime or API key), local Docker gates, the twelve COMPLETE
H cases. FIN-03/FIN-02 stay planned and `finance_documents` stays non-enableable.

## Decisions taken in this slice (owner may revise)

1. Interior whitespace is preserved (`preserve`) while no source contract says
   it carries no meaning; `TX 123` and `TX123` are different identifiers. A
   provider rule is a new rule value plus an accepted change, not an edit of
   `preserve`.
2. Look-alike punctuation (for example U+2010 versus `-`) is not unified; NFKC
   does not map it and a confusables table is out of scope.
3. Only issued obligations make an account a control account for the cash
   check; a draft does not lock an account. The reverse check covers drafts too.
4. "Today" for an attested date is the business time zone: the one zone of its
   locations, else UTC. A business whose locations span zones gets UTC until a
   book or business zone exists.
5. The identity check scans the book's payments of one direction under the
   ledger lock (linear in their number). An expression index needs an
   `IMMUTABLE` function and a guard extension and is left for later.
