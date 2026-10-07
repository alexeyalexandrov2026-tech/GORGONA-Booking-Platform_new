# H2 manual accruals, settlement reserves and attested confirmations — validation and boundaries

Base: `75e809b9d82b514fd9d2ae93122c23c0ae217e85`, the delivered H1 backend on
`codex/package-h1-persistence`.
Branch: `codex/package-h2-settlements`, created as `claude/package-h2-settlements`
and renamed on 2026-10-07 before any publication; commits unchanged. Own checkout
`C:\Users\alexa\Documents\ChatGPT\gorgona-h2-settlements`.

| Slice | Source commit | Content |
|---|---|---|
| A | `536250af966b7ab0cc6b21999fd336d5e295327c` | Manual accrual as a second kind of the immutable financial document; forward `0022`. |
| B | `e8ec1d6df59d22c234995d93124f5583b04e7f34` | Settlement documents: prepare, approve, reserve, sent, release, cancel; forward `0023`. Posts no money. |
| C | `aa95dde75896a774c7199e44f1559382f55e2499` | Externally attested partial confirmations; forward `0024`. |
| C, test only | `54852b4b816be1aeec8025c1a22a967a7b135ad7` | One added direct-SQL test for the payment cap and external identity. No source or migration change. |

Financial H2 source checkpoint is54852b4; subsequent UI correction is15edbed.
This file is a documentation-only successor of the corrective source. Read
the current branch HEAD from Git; a source commit is not the delivery HEAD.

**Publication completed, 2026-10-07.** The owner's eight Markdown changes were
reviewed, checked and committed as documentation only in
`75c36dac572c8420aa848d322717420d43555c87`, then pushed ordinarily.
[Draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16) is OPEN/DRAFT/unmerged and targets
`codex/package-h1-persistence` at75e809b. No second PR, merge or auto-merge.

Observed exact-checkpoint [CI37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) completed/success:
**1044 passed/1 skipped/381.36s**, PostgreSQL18.6, real OIDC/Chromium and all three Docker tests.
69 web tests/2.3s, web typecheck/lint/format/build, production image,
Ruff/format211 and strict mypy211 PASS. Remaining skip is the optional separate
tenant-site integration. Earlier pushCI37571379933 on5089b3a independently
completed/success:1044 passed/1 skipped/371.35s, web69/1.9s.

The documentation-only successor15e8d0c was pushed and its exact CI failed.
It was diagnosed/reported before a bounded UI correction15edbed. Financial
Python/SQL remains byte-identical to54852b4; only two web files change. Fresh
local/full/peer/CI evidence for the correction is recorded below. Read actual
final HEAD/origin and current-head CI in PR16/exported delivery state. The
tracked source checkpoint does not claim CI on its own future documentation
SHA. Independent H2 money/state review remains NOT DONE.

This is a bounded H2 backend increment behind the closed `finance_documents`
gate. G/FIN-01 remains technically verified. FIN-03 and FIN-02 remain `planned`;
the real registry cannot enable `finance_documents`. Positive H fixtures override
readiness only in tests. H3 credits, refund obligations and corrections and H4
UI and admission metadata are not implemented. ADR-0024 remains Proposed.

## Publication correction — ledger book refresh

Failed source/delivery head: `15e8d0cd2a58544b7c6fefa73a2c78ade63c1861`.
[CI37574622979](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37574622979), job112640628374:
**FAIL:1 failed/1043 passed/1 skipped/392.04s**, exit1. Web69/2.2s,
Ruff/format/mypy211, PostgreSQL18.6, production image and all three Docker tests
passed; only `tests/integration/test_ledger_browser.py::test_real_ledger_browser_oidc_pkce_and_database`
failed. Desktop first read an open month instead of closed, then a late book
refresh cleared the period result. That case left the month closed; the next
desktop case received a cascading409. Both original mobile scenarios passed.

Root cause: `execute()` cleared busy/pending and incremented `tick` before a
separate `loadBook` effect finished. That effect later cleared period/report.
A newer read could start in between and then be erased. The cause was reported
before source changes; CI was not retried blindly.

Corrective source: `15edbed1d608ada9d0901a7710c00eff28c23e71`, two files,83 insertions/10 deletions:

- [ledger.tsx](../../../../web/components/ledger.tsx): typed loaded-business/book/tick
  marker. Writes, selection and period/report reads stay locked until the active
  refresh accepts book/accounts/entries and resets dependent state. Stale effect
  callbacks cannot mark a new selection ready. Refresh remains usable after a
  failed read; the UI shows updating/error state.
- [ledger.spec.ts](../../../../web/tests/ledger.spec.ts): holds the actual GET
  after Close month, asserts Read month disabled until release, then verifies
  closed/open results; separately aborts one book GET and verifies retry. All
  scenarios still use real API/database/OIDC on desktop and mobile. Cleanup uses
  [Playwright unrouteAll behavior wait](https://playwright.dev/docs/api/class-page#page-unroute-all).

No financial Python/SQL, frozen0022–0024, dependency, lockfile, permission,
retry count or timeout change. No gate/acceptance/provider/production action.

| Fresh corrective check | Exact observed outcome |
|---|---|
| Baseline real browser, held post-command GET (clean RED) | FAIL:1 Python wrapper failed/26.84s, exit1; desktop/mobile saw Read month enabled while GET held. |
| `check_h2_root_ui.py pytest tests/integration/test_ledger_browser.py -q -p no:cacheprovider --basetemp <fresh> --tb=short` | PASS:1 passed/17.95s, exit0; all4 Playwright desktop/mobile cases pass. |
| `check_h2_root_ui.py pytest -q -rs -p no:cacheprovider --basetemp <fresh> --tb=short` | PASS:1041 passed/4 skipped/434.68s, exit0, mandatory real PostgreSQL18.6/OIDC/Chromium. |
| `npm run typecheck`, `lint`, `format:check`, `test:unit`, `build` | PASS, exit0;69 units/1.1s,18 routes. Type/lint/format rerun after final test-locator correction. |
| `python -m ruff check .`, `ruff format --check .`, `mypy` from api with H2 PYTHONPATH | PASS, exit0;211 formatted files and no mypy issues in211 files. |
| Separate bounded [design review](LEDGER_REFRESH_DESIGN_REVIEW.md) and [exact-source review](LEDGER_REFRESH_REVIEW_15EDBED.md) | PASS at15edbed for the UI source/build/browser correction only; full H2 money/state review NOT DONE. |
| Corrective-source [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793), job112651898225 | PASS:1044 passed/1 skipped/379.86s; web69/2.3s, all3 Docker/image, PG/browser, web/static211 gates. |
| Current corrective documentation gate after recording evidence | PASS:10 Markdown files,8 added/changed local links from5089b3a,UTF-8; working/staged/base diff checks exit0. Source unchanged from15edbed; financial backend unchanged from54852b4; only2 corrective web files. Full12 H criteria NOT TESTED; finance_documents non-enableable. Fresh gate rerun after this row. |
| Owned corrective clusters stopped after checks | PASS:root51456 and reviewer51460 stopped; original H2 cluster51462 remains stopped. Other clusters untouched. |

Root runner uses existing Python3.14 and H2 `PYTHONPATH`, private loopback PG18.6
on51456 with400 connections; credentials stay in the private manifest and are
redacted from logs. One executor per cluster, fresh basetemp, no shared fixture
suite overlap. Local four skips are three Docker and optional tenant-site;
Docker is verified remotely above. The independent report names its own exact
checkout and isolated51460 runtime.

Attempts excluded from PASS: initial regression harness had CP1251 output and
route-cleanup errors; these were repaired before the clean RED. First post-fix
run failed because a global alert locator also matched Next's empty route
announcer; scoped to the ledger's real alert and rerun. These are recorded
failed attempts, not accepted product verification. Reviewer dependency-junction
build limitation and the safe alternate checkout are recorded in its report.

This CI result is for the corrective source SHA, not a future docs SHA. Final
delivery HEAD and exact-head CI are verified separately in PR16 and the exported
delivery state. Publication review reports do not approve full H2 or FIN-03.

## Changed source and test files

The delta from the base to `54852b4` is 23 files, 5904 insertions and 314
deletions. Documentation is an additional delivery commit.

| File | Change |
|---|---|
| [0022_manual_accruals.sql](../../../../api/src/gorgona_booking/db/migrations/0022_manual_accruals.sql) | Document kind column (`invoice`, `manual_accrual`), journal kind `accrual`, obligation source `manual`, accrual operations; replaced origin, consistency and integrity functions. 6 CHECK approvals. |
| [0023_settlements.sql](../../../../api/src/gorgona_booking/db/migrations/0023_settlements.sql) | Four insert-only FORCE RLS tables (documents, allocations, events, command receipts); `gba.settlement_phase`, `gba.obligation_balance`, deferred cap and sequence checks; four company-scope policies. 16 CHECK approvals. |
| [0024_external_payments.sql](../../../../api/src/gorgona_booking/db/migrations/0024_external_payments.sql) | Two insert-only FORCE RLS tables (payments, payment allocations); permanent unique external identity; journal kind `payment`; event kind `confirmed`; replaced balance, event, consistency and origin functions; two company-scope policies. 11 CHECK approvals. |
| [db/financial_guard.py](../../../../api/src/gorgona_booking/db/financial_guard.py) | Approvals composed over the ordered H migrations `0021`–`0024`: the latest packaged function or CHECK definition is the approved one; added tables, triggers, helper functions and columns added by `ALTER TABLE`. |
| [business/financial_commands.py](../../../../api/src/gorgona_booking/business/financial_commands.py) | New shared module: claim, complete, resolve and cancel of finite financial commands for the document and settlement families. |
| [business/financial_documents.py](../../../../api/src/gorgona_booking/business/financial_documents.py) | Document kind in draft, read, list and issue; recovery delegated to the shared module. |
| [business/financial_contracts.py](../../../../api/src/gorgona_booking/business/financial_contracts.py) | Document kind and the extended finite operation list. |
| [business/settlement_contracts.py](../../../../api/src/gorgona_booking/business/settlement_contracts.py) | New strict settlement, obligation, confirmation and payment models. |
| [business/settlements.py](../../../../api/src/gorgona_booking/business/settlements.py) | New: obligation balances, settlement lifecycle, confirmation and payment read. |
| [business/ledger.py](../../../../api/src/gorgona_booking/business/ledger.py), [business/ledger_contracts.py](../../../../api/src/gorgona_booking/business/ledger_contracts.py) | Typed posting seam `append_financial_journal` for invoice, accrual and payment; journal read schema 2 adds `accrual` and `payment`; one H-owned set refuses generic reversal. |
| [api/financial_documents.py](../../../../api/src/gorgona_booking/api/financial_documents.py) | Accrual, obligation, settlement, confirmation and payment routes; resolve and cancel accept the new operations. |
| [web/lib/ledger-contracts.ts](../../../../web/lib/ledger-contracts.ts), [ledger-contracts.spec.ts](../../../../web/tests/ledger-contracts.spec.ts) | Zod read schema 2 accepts `accrual` and `payment`; schema 1 still rejects them. |
| [test_manual_accruals.py](../../../../api/tests/integration/test_manual_accruals.py) | New: 25 real API/SQL tests for slice A. |
| [test_settlements.py](../../../../api/tests/integration/test_settlements.py) | New: 31 real API/SQL tests for slice B. |
| [test_external_payments.py](../../../../api/tests/integration/test_external_payments.py) | New: 25 real API/SQL tests for slice C, including one that writes confirmations by SQL alone. |
| [test_invoice_issue.py](../../../../api/tests/integration/test_invoice_issue.py) | Still 46 tests. New shared helpers `approved_check`, `widened_check`, `packaged_function`; five H1 drift cases now restore the latest packaged definition instead of a fixed `0021` text. |
| [test_location_access.py](../../../../api/tests/integration/test_location_access.py) | Drift restoration includes the `0023` and `0024` restrictive policy footers. |
| [test_settlement_contracts.py](../../../../api/tests/unit/test_settlement_contracts.py) | New: 6 tests for strict settlement, release, recovery and confirmation contracts. |
| [test_document_contracts.py](../../../../api/tests/unit/test_document_contracts.py), [test_ledger_contracts.py](../../../../api/tests/unit/test_ledger_contracts.py), [test_financial_documents.py](../../../../api/tests/unit/test_financial_documents.py) | 63 scope definitions (57 → 61 → 63); new journal kinds; document kind. |

Migrations `0001`–`0021` are byte-identical to the base: `git diff 75e809b` is
empty for them. No dependency, lockfile or permission map changed. No second
ledger, provider SDK or capability activation was added.

## Direct checks

Python 3.14 from the existing G venv with `PYTHONPATH` pointing at this
checkout. Own PostgreSQL 18.6 cluster on loopback `51462`, started with
`max_connections=400`; credentials stay in the private cluster manifest. Every
pytest run used a fresh `--basetemp` and `-p no:cacheprovider`. `h2run.py` is an
external redacting runner, not a repository dependency; it sets
`GBA_REQUIRE_POSTGRES=1` and, with `--browser`, `GBA_REQUIRE_BROWSER=1`.

| Check / actual command | Outcome |
|---|---|
| Baseline before any edit: `h2run.py pytest tests/integration/test_invoice_issue.py tests/unit -q` on `75e809b` | PASS: 533 passed, the H1 number. |
| Slice A full: `h2run.py --browser pytest -q -rs` after `npm run build` | PASS: 979 passed / 4 skipped / 389.33s, exit 0. |
| Slice B full: same command on the slice B tree | PASS: 1015 passed / 4 skipped / 419.22s, exit 0. |
| Slice C focused: `h2run.py pytest -q` over `tests/unit`, the four finance integration files, `test_location_access.py` and the ledger integration files | PASS: 676 passed / 136.38s, exit 0. |
| Slice C full: `h2run.py --browser pytest -q -rs` after `npm run build`, on the exact tree committed as `aa95dde` | PASS: 1040 passed / 4 skipped / 464.55s, exit 0. |
| Final full: the same command on the exact tree committed as `54852b4` (one added test; web source and build unchanged) | PASS: 1041 passed / 4 skipped / 459.51s, exit 0. |
| `python -m ruff check .` from api, after each slice and on `54852b4` | PASS, exit 0. |
| `python -m ruff format --check .` from api, after each slice and on `54852b4` | PASS, exit 0; 211 files. |
| `python -m mypy` from api, strict project configuration | PASS: no issues in 205 (A), 210 (B), 211 (C and `54852b4`) source files. |
| Web `npm run typecheck`, `lint`, `format:check`, `test:unit` after slices A and C; slice B changed no web source | PASS: 69 unit tests. |
| Web `npm run build` after slices A and C | PASS, exit 0, 18 routes. |
| `git diff --check 75e809b 54852b4` | PASS, exit 0. |
| Local links added in the seven changed Markdown files; LF line endings; `git diff --check` of the documentation change | PASS: 48 links, none missing; exit 0. |
| Preserved checkouts after the work, read with `git --no-optional-locks` | PASS: owner `2f16380` 19 changed paths, E2 `151472a` 9, G `5be6e7a` 0, foundation `18e3f5e` 0, H1 review `2d5a8f9` 0, H1 backend `75e809b` 0. |
| Own cluster `51462` stopped with `pg_ctl -m fast stop`; loopback listeners afterwards | PASS: no server running for the H2 data directory; `51455` still listening and untouched. |
| `git push -u origin codex/package-h2-settlements` after the owner's "push" | PASS: new remote branch at `5089b3a`; base `codex/package-h1-persistence` still at `75e809b`. No force. |
| Push CI run37571379933 on5089b3a | PASS:1044 passed/1 skipped/371.35s; all3 Docker tests/image, web69/1.9s and static211 PASS. |
| Draft pull request | PASS: [PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16), OPEN/DRAFT/unmerged; target H1, original checkpoint75c36da. [Description](PULL_REQUEST.md). |
| Exact-checkpoint PR CI37573680437 on75c36da | PASS:1044 passed/1 skipped/381.36s; PG/browser/all3 Docker/image, 69 web tests/2.3s, static211 PASS. |
| Original publication documentation gate, before UI correction | PASS:eight Markdown files, one added/changed local link from5089b3a, UTF-8, source unchanged from54852b4 at that checkpoint, full12 H criteria NOT TESTED, finance_documents non-enableable, own51462 stopped; diff checks exit0. |
| Pattern scan of the added lines for credentials, DSNs, tokens, keys, the cluster port and user name | PASS: no match. Test references use `FAKE-…` values only. |

The four skips in every full run are the three container tests
(`GBA_REQUIRE_CONTAINER`) and the optional tenant-site test
(`GBA_REQUIRE_TENANT_SITE`). They are NOT TESTED locally.

Collected finance tests on `54852b4`: 46 invoice, 25 accrual, 31 settlement and
25 payment integration tests; 494 unit tests in total.

The added direct-SQL payment test passed on its first run. It has no red run:
it confirms controls that already existed in `0024`. Its control case shows the
raw path is otherwise valid, and each rejection is matched on the message of
its own check.

### Red runs and attempts that are not counted as PASS

- Slice A: the tests were written before the implementation, but no red run was
  executed and recorded. There is no red evidence for slice A.
- Slice B red run before the implementation: 1 failed, 29 errors.
- Slice C red run before the implementation: collection error, `StopIteration`
  in the test module because the migration did not exist yet.
- First slice A full run: 5 failed, 974 passed, 4 skipped. All five were in
  `test_booking_concurrency.py` with "remaining connection slots are reserved":
  the new cluster had the default `max_connections=100`. Only this cluster was
  restarted with 400; the rerun is the accepted 979.
- Slice B: `record "new" has no field "sequence"` in a trigger function shared
  by several tables; fixed with a nested table check in `0023` before commit.
- Slices B and C: H1 drift tests restored fixed `0021` or `0022` texts after a
  later migration had replaced them, which produced 503 cascades. The tests now
  restore from the packaged approvals. This changed five H1 drift cases; their
  assertions are unchanged.
- Slice C: the first implementation run failed with "receipt needs its exact
  settlement event" because `0023` mapped unknown event kinds to `cancel`;
  `0024` replaces the function with an explicit kind-to-operation map.

## Observable bounded behavior

Slice A, manual accrual:

- A receivable or payable manual accrual creates one new obligation
  (`manual`/`principal`), one balanced `accrual` journal with the chosen control
  and counter accounts, one link and one permanent receipt in one transaction.
  A closed period rolls back every effect.
- An existing `manual` G entry is not linked or accrued again; a forged issue
  written by direct SQL that names it as its accrual is rejected. The rule is
  that the journal must be of kind `accrual`, so it covers `opening` entries as
  well, but only the `manual` case is tested.
- Invoice routes never return an accrual and the reverse. Legacy journal reads
  answer `JOURNAL_VERSION_REQUIRED`; schema 2 shows `accrual`; the trial balance
  includes it; generic reversal is refused in API and SQL.
- Two competing issue requests are observed waiting in `pg_locks`; one commits.

Slice B, settlements and reserves:

- Prepare, approve, reserve, release and cancel change only the reserve; no
  journal is written. The view names who prepared and who approved and states
  whether it was the same person.
- Two documents each reserve 70 of principal 100, in both request orders: both
  requests are observed waiting in `pg_locks`; exactly one 200 and one 409
  `FINANCIAL_CAP_EXCEEDED`; reserved stays 70.
- A release racing a competing reserve keeps the cap and nonnegative counters.
- Direct SQL cannot insert an over-cap reserve, a sequence gap, a skipped
  approval, a late allocation, a document without its prepared event or an
  allocation whose obligation does not match the document, and cannot update
  settlement rows.
- The API refuses a foreign party, direction or currency, an unknown
  obligation, a wrong scale and an amount above the principal. Another company
  can neither read nor settle these obligations.
- A document marked sent cannot be released plainly
  (`FINANCIAL_OUTCOME_UNRESOLVED`), also while finance is OFF. Only an explicit
  `attested_no_payment` resolution with reason and evidence source releases it.
- With finance OFF: prepare, approve, reserve and sent are refused with
  `MODULE_DISABLED`; the list and the views still read, a never-sent reserve is
  released plainly and a prepared document is cancelled. With readiness
  withdrawn: prepare, reserve and sent are refused with `MODULE_NOT_READY` and a
  plain release works. Command recovery while OFF is tested for documents (H1
  and slice A) through the same shared module, not separately for settlements.
- Tested readiness drifts for the settlement tables: disabled triggers, removed
  FORCE RLS, a weakened and an extra policy, extra privileges, a widened CHECK
  and replaced functions. Each gives 503 and recovers after restoration.
- The API status equals `gba.settlement_phase` at every step.

Slice C, externally attested confirmations:

- Reserve 70, confirm 40: paid 40, reserved 30. Confirm 30 more: paid 70,
  reserved 0, status `confirmed`. Each confirmation writes one `payment` journal:
  cash debit against the obligation control account, or the mirror for outgoing
  payments, with one control line per allocation. The trial balance includes
  them. A fully confirmed settlement accepts nothing further.
- An allocation above the remaining reserve of its line is refused
  (`FINANCIAL_CAP_EXCEEDED`); allocations that do not sum to the amount are
  refused (`FINANCIAL_AMOUNT_INVALID`); a wrong scale, a foreign obligation, a
  control or non-asset account as cash and any attestation other than
  `manual_attestation` are refused. No journal is written in these cases.
- The same key and body replays the stored view. A different key with the same
  external identity (book, direction, source account alias, external reference)
  returns 409 `FINANCIAL_SOURCE_ALREADY_RECORDED` with only the existing
  `payment_id`; the reference is not echoed. Another settlement cannot repeat
  the identity. Money posts once.
- Replay survives receipt cleanup; the stored receipt and the audit record hold
  identifiers only. A cancelled unresolved key seals a late original.
- Two concurrent partial confirmations and a confirm/release/reserve race are
  observed waiting in `pg_locks`; `P + C + R <= A` holds afterwards.
- A partial confirmation on a sent document leaves the outcome unresolved; the
  remainder is released only by the explicit attested resolution, and the paid
  amount stays.
- A closed posting period refuses the confirmation with `LEDGER_PERIOD_CLOSED`
  and leaves the reserve; a plain release still works.
- SQL alone, without the service: a structurally exact confirmation commits (the
  control case); a confirmation above the remaining reserve of its line,
  allocations that differ from the amount and a second row with the same
  external identity are rejected; so are an orphan `payment` journal, a
  `confirmed` event without its payment, a payment without its event, a late
  allocation and a late balanced journal pair. Payment rows can be neither
  updated nor deleted. An unbalanced journal is refused by the existing G
  balance check; that is not re-tested for the `payment` kind.
- Generic reversal of a `payment` entry is refused in API and SQL.
- Tested readiness drifts for the payment tables: disabled triggers, a dropped
  identity key, a dropped CHECK, a weakened policy, an extra privilege and
  replaced functions. Each gives 503 and recovers after restoration. A dropped
  foreign key of the H2 tables is not among the tested drifts.
- With finance OFF or readiness withdrawn a confirmation is refused; the
  recorded payment and the settlement still read, and the never-sent remainder
  is released plainly.

No race is claimed from sleeps alone; every race waits for the expected number
of blocked backends in `pg_locks` before the lock holder commits.

## Acceptance rows

All twelve **complete** H-01..H-12 criteria remain NOT TESTED. Parts with
direct proof in this increment:

| Row | Part with direct local proof | Still missing |
|---|---|---|
| H-01 | Invoice (H1) and manual accrual: atomic issue, rollback, no legacy G link. | Independent review. |
| H-02 | Insert-only invoice, accrual, settlement and payment history. | Credit history (H3). |
| H-03 | 70-of-100 reserve race, both orders, observed lock waits. | Independent review. |
| H-04 | Concurrent partial confirmations; release/confirm/reserve race. | Credit/reserve race (H3). |
| H-05 | Replay, other key with the same identity, receipt cleanup, cancel before a late original. | Browser reload path (H4). |
| H-06 | None. | Credits, refunds, corrections (H3). |
| H-07 | Closed period for accrual and confirmation; scope, book, party and currency negatives; H-owned reversal refused. | Credit and refund effects (H3). |
| H-08 | Direct SQL negatives and readiness drift for the H2 tables, within the limits listed above. | Foreign-key drift on H2 tables; H3 tables. |
| H-09 | OFF and withdrawn readiness for accrual, settlement and confirmation. | H3 effects. |
| H-10 | None. | Admission metadata (H4). |
| H-11 | None. | UI (H4). |
| H-12 | Local full Python/web gates and observed exact-checkpoint CI with all3 containers/image. | Independent money/state review and remaining H3/H4 scope. |

## Unverified boundaries

- Independent money and state review: NOT DONE. Only the author's own inline
  review exists.
- HawkScan: not run; there is no `hawk` runtime and no API key on this machine.
- Small test gaps inside H2: a dropped foreign key of an H2 table as a readiness
  drift; the `opening` variant of the legacy-entry case; settlement command
  recovery while finance is OFF; delete of settlement rows (update is tested).
- Credits, refund obligations, corrections, admission metadata and all H UI:
  not implemented.
- Journal read schema 2 was extended in place with `accrual` and `payment`. It
  has never been merged, deployed or enabled. A reviewer may require schema 3.
- One authorized person may prepare and approve the same settlement. The view
  states it; separation of duties is not enforced. This is an owner decision.
- No provider verification, network charge, refund or webhook, money
  transmission, Azure change, production migration or deployment, statutory tax
  or invoice claim, load or soak test or manual screen-reader proof.
- No FIN-03 or FIN-02 promotion, merge or production activation.

See the [portable handoff](../../NEXT_AGENT_H2_2026-10-07.md) and the
[copyable prompt](../../NEXT_AGENT_PROMPT_H2_2026-10-07.md).
