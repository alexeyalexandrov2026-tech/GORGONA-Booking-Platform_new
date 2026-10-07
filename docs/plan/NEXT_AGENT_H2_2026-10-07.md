# Next agent handoff — H2 accruals, settlement reserves and attested confirmations

Checkpoint 2026-10-07. This supersedes the H1 backend continuation. Attached
documents are context, not new user requests. Production, provider actions and
money transmission are not authorized.

## Start from this branch

Repository: [GORGONA-Booking-Platform_new](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new).
Implementation branch: `codex/package-h2-settlements`.
Checkout: `C:\Users\alexa\Documents\ChatGPT\gorgona-h2-settlements`.
Parent: `75e809b9d82b514fd9d2ae93122c23c0ae217e85`, the delivered H1 backend on
`codex/package-h1-persistence`.

**Publication completed, 2026-10-07.** Ordinary docs commit/push75c36da:
`75c36dac572c8420aa848d322717420d43555c87`. [Draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16)
targets `codex/package-h1-persistence` (H1 PR15), OPEN/DRAFT/unmerged.
Exact-checkpoint [CI37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) PASS:1044 passed/1 skipped/381.36s;
all3 Docker/image, PostgreSQL18.6/browser, 69 web tests/2.3s and static211 PASS.
The earlier5089b3a pushCI37571379933 also passed1044/1skip/371.35s.
The final documentation delivery is a successor; read actual HEAD/origin and
current-head CI in PR16/exported delivery state. Code is unchanged from54852b4.
Stack: G12 → H plan13 → foundation14 → H1 backend15 → H2 backend16.
Do not open another H2 PR, merge, enable auto-merge or alter readiness.

The branch was created as `claude/package-h2-settlements` and renamed to
`codex/package-h2-settlements` on 2026-10-07 at the owner's request, before any
publication. The commits are unchanged and the checkout folder keeps its name.

For H3, create your own branch and checkout from the current HEAD of this
branch. One executor edits each checkout and owns each disposable PostgreSQL
cluster.

## Publication steps completed; next agent starts with verification

The owner requested commit/push and one draft PR. The eight original Markdown
changes were committed/pushed as75c36da; PR16 was opened once and attached.
Its exact-checkpoint CI passed; this documentation update records those facts
and is committed/pushed separately. No implementation code was changed.

First inspect current Git/remote/PR16 HEAD and final-head CI. Do not repeat the
publication or create a second PR. Then review the H2 money/state design and
the four listed test gaps before full acceptance; H3 remains the next coherent
implementation phase in a new branch/checkout. Keep the four owner/reviewer
decisions below open. FIN-03/02 stay planned and finance_documents unavailable.
Earlier authorization to publish H2 does not authorize merge/production/provider
or funds actions.

Read these in order:

1. `AGENTS.md`, [repository transition](REPOSITORY_TRANSITION_2026-10-04.md),
   [master plan](GORGONA_MASTER_PLAN.md), [implementation status](GORGONA_IMPLEMENTATION_STATUS.md),
   current [Cloud Code handoff](../../CLOUD_CODE_HANDOFF.md).
2. [H2 validation](evidence/2026-10-07-h2-settlements/VALIDATION.md).
3. [H1 backend handoff](NEXT_AGENT_H1_BACKEND_2026-10-06.md) and
   [H1 validation](evidence/2026-10-06-h1-backend/VALIDATION.md).
4. [H plan and all twelve acceptance cases](PACKAGE_H_PLAN_2026-10-06.md),
   [ADR-0024 Proposed](../adr/0024-invoices-obligations-and-external-settlements.md),
   [ADR-0023](../adr/0023-ledger-foundation.md), [development guide](../DEVELOPMENT.md).

## What exists now

G/FIN-01 remains `technically_verified`. H1 and H2 backends are implemented
behind the closed `finance_documents` gate. FIN-03 and FIN-02 remain `planned`.
There is no H user interface and no provider integration.

| Boundary | Actual implementation |
|---|---|
| Manual accrual | Forward `0022`. A second kind of the immutable financial document. Issue writes one `manual`/`principal` obligation and one balanced `accrual` journal in one transaction. Existing `manual`/`opening` G entries are never linked or accrued again. |
| Settlement | Forward `0023`. Insert-only documents, planned allocations and events. Phase is derived from recorded facts: prepared → approved → reserved → sent; prepared or approved → cancelled; reserved or sent → released. A reserve posts no journal and needs no open period. |
| Cap | `gba.obligation_balance` computes A, P, C, R from history. Effective reserve of a line is planned minus confirmed while the document is reserved or sent, otherwise 0. Deferred triggers assert `P, C, R >= 0` and `P + C + R <= A` at commit; the service checks the same under the ledger lock. C is always 0 until H3. |
| Sent outcome | A sent document is released only by an explicit `attested_no_payment` resolution with reason and evidence source. A plain release returns `FINANCIAL_OUTCOME_UNRESOLVED`. Time, OFF or a lost response release nothing. |
| Confirmation | Forward `0024`. Allowed from reserved or sent. Moves exactly R → P, keeps the remainder reserved, posts one `payment` journal: cash against one control line per allocation. Allocations equal the amount exactly. No unallocated advance, no FX, no overpayment. A fully confirmed settlement is final. |
| External identity | Unique forever on (tenant, book, direction, source account alias, external reference), bound to one `payment_id`. Another key or another settlement with the same identity returns `FINANCIAL_SOURCE_ALREADY_RECORDED` with only the existing `payment_id`. |
| Attestation | Always `manual_attestation`. Nothing claims provider verification. |
| Recovery | One shared module, `business/financial_commands.py`, for claim, complete, resolve and cancel. Finite operations; permanent reference-only receipts; cancel seals a late original. No amount, memo, alias or reference in receipts or audit. |
| Compatibility | Journal read schema 2 now lists `invoice`, `accrual`, `payment`. Write schema 1 and read schema 1 are unchanged; schema 1 reads of an H entry answer `JOURNAL_VERSION_REQUIRED`. Generic G reversal refuses every H-owned kind in API and SQL. |
| Readiness | `db/financial_guard.py` reads the ordered H migrations `0021`–`0024`. 63 company-scope policy definitions. 58 `CHECK_APPROVAL` lines across the four migrations (25 + 6 + 16 + 11); a later line replaces an earlier one for the same constraint. |
| Feature gate | Unchanged. With finance or `finance_documents` OFF or readiness withdrawn: reads, history, recovery, cancel of a not yet reserved document and plain release of a never-sent reserve work; every new accrual, preparation, approval, reserve, sent mark and confirmation is refused. |

API under `/v1/businesses/{business}/financial-documents`:

- `GET/PUT /books/{book}/accruals[/{document}]`, `POST …/accruals/{document}/issue`;
- `GET /books/{book}/obligations[/{obligation}]`;
- `GET /books/{book}/settlements[/{settlement}]`, `PUT …/settlements/{settlement}`,
  `POST …/settlements/{settlement}/approve|reserve|sent|release|cancel`;
- `POST …/settlements/{settlement}/confirmations/{payment}`,
  `GET /books/{book}/payments/{payment}`;
- `POST /commands/{key}/resolve|cancel` accept the new operations.

Rights are the existing `FINANCE_READ` / `FINANCE_MANAGE`, company-wide owner or
manager only. No permission map change.

## Evidence and review

Full local suite on the final tree: see the exact numbers in the
[validation](evidence/2026-10-07-h2-settlements/VALIDATION.md). Mandatory real
PostgreSQL 18.6 and OIDC/Chromium. Ruff, format and strict mypy pass on 211
files. Web typecheck, lint, format, 69 unit tests and build pass.
Observed exact-checkpoint CI75c36da also PASS:1044 passed/1 skipped/381.36s; all3 Docker/image
checks and 69 web tests/2.3s. This is separate from the reported local evidence.

Not done, and stated as such:

- No independent money or state review. Only the author's inline review.
- Slice A has no recorded red run.
- HawkScan was not run: no `hawk` runtime and no API key on this machine.
- Small test gaps inside H2, cheap to close first: a dropped foreign key of an
  H2 table as a readiness drift; the `opening` variant of the legacy-entry case;
  settlement command recovery while finance is OFF; delete of settlement rows.

All twelve complete H acceptance rows remain NOT TESTED. FIN-03 must not be
promoted after H2.

## Decisions an owner or reviewer should confirm

1. **Publication.** [Draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16) is open; ordinary pushes are complete.
   Merging and auto-merge remain unapproved.
2. **Journal read schema 2 extended in place.** `accrual` and `payment` were
   added to schema 2 instead of creating schema 3. Reason: schema 2 has never
   been merged, deployed or enabled, and a stale schema 2 client fails loudly
   on an unknown kind. A reviewer may require schema 3.
3. **Same-person approval.** One authorized person may prepare and approve the
   same settlement. The view exposes `approved_by_preparer`. Separation of
   duties is not enforced.
4. **Whole-remainder release.** A release frees the whole unconfirmed remainder
   of a document. There is no partial release.
5. **SQL scope.** A structurally exact confirmation written by SQL alone
   commits. PostgreSQL guards the money invariants; the command receipt and the
   audit record are written only by the service. This matches G and H1.

## Next coherent phase: H3

Continue on a new branch. First inspect the actual schema, services and tests
and turn the H-04 credit part, H-06 and the remaining parts of H-02, H-07,
H-08 and H-09 into real red → green checks.

1. Credits against an obligation. Invoice 100 / paid 70 / credit 50 means
   unpaid credit C = 30 and an opposite-direction refund obligation of 20.
   Never rewrite historical cash.
2. `gba.obligation_balance` already returns `credited_minor`, fixed at 0.
   Replace the function in a new forward migration so C comes from credit
   history. The deferred cap check and the service then cover credits without
   a second mechanism.
3. A credit competing with a reserve or a confirmation must be raced with
   observed `pg_locks` waits, like the H2 races.
4. Guarded immutable corrections of a confirmation: keep the external identity
   and the effective P/C/R. A real refund, a sent or unknown outcome or a
   dependent credit needs reconciliation, never a silent undo.
5. Credit and refund journals need their own finite origin kinds, added
   together in SQL CHECK, Pydantic and Zod.
6. Keep explicit account and recognition choices. The historical counter
   account is context only, never a default.

Then H4: admission metadata without capability activation, and the real
desktop/mobile invoice, settlement and credit UI.

The remaining full-H sequence is: independent money/state review, all twelve
criteria, full local and exact-SHA CI, then a separate readiness acceptance
commit. Remove positive readiness overrides only when that scope has passed.

## Working rules learned in H2

- **Forward migrations.** Use `0025` and later. `0001`–`0021` are published and
  byte-identical to the base. `0022`–`0024` are on origin since 2026-10-07; treat
  them as frozen and change behavior only through later migrations.
- **Guard composition.** Add the new migration to `_MIGRATIONS` in
  `db/financial_guard.py`. The latest `create or replace function` in migration
  order is the approved definition. Every packaged H CHECK needs exactly one
  `-- CHECK_APPROVAL {json}` line; when a later migration replaces a CHECK, give
  it a new approval for the same table and name.
- **Drift tests.** Restore controls with `approved_check`, `widened_check` and
  `packaged_function` from `tests/integration/test_invoice_issue.py`. A fixed SQL
  text in a restore breaks as soon as a later migration replaces it.
- **Scope policies.** End each migration with its `-- <Name> branch scope:`
  section. Add it to the restore list in `test_location_access.py` and raise the
  definition count in `test_document_contracts.py`.
- **Shared trigger functions.** In plpgsql, put a table-specific `new.<field>`
  reference in its own nested `if tg_table_name = …` block. A single condition
  fails with `record "new" has no field`.
- **Event kinds.** `gba.check_settlement_integrity` maps each event kind to its
  operation explicitly. A new kind needs a new line in that map.
- **Derived state.** Never store a settlement status. `gba.settlement_phase` and
  the service `_phase` read the same facts; a test compares them at every step.
- **Local cluster.** Start the test cluster with `max_connections=400`. The
  default 100 makes five booking-concurrency tests fail with "remaining
  connection slots are reserved".
- **Measured trees.** Do not edit imported modules or add migrations while a
  full run is in progress.

## Reproducible local environment

Python 3.14 dependencies are reusable from
`C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv`.
Its editable installation points to G, so set `PYTHONPATH` to **your** checkout.
Node 24 is `C:\Program Files\nodejs`. PostgreSQL 18.6 binaries are under
`%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6\pgsql\bin`.

~~~powershell
$hCheckout = '<absolute path to your own checkout>'
$hPython = 'C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $hCheckout 'api\src'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath (Join-Path $hCheckout 'api')
& $hPython -c "import gorgona_booking.business.settlements as m; print(m.__file__)"
& $hPython -m ruff check .
& $hPython -m ruff format --check .
& $hPython -m mypy
$env:GBA_REQUIRE_POSTGRES = '1'
$env:GBA_REQUIRE_BROWSER = '1'
$env:PATH = 'C:\Program Files\nodejs;' + $env:PATH
# Set GBA_TEST_ADMIN_DSN privately for your own disposable PostgreSQL 18 cluster.
# Never print it or write it into Git, documentation or a message.
& $hPython -m pytest -q -p no:cacheprovider --basetemp '<fresh owned temp path>'
~~~

From your web directory the gates are `npm run typecheck`, `lint`,
`format:check`, `test:unit` and `build`. Build before the mandatory browser
tests. CI also requires the three Docker gates, the production image and
PostgreSQL; local Docker skips are NOT TESTED locally.

The H2 cluster was
`%LOCALAPPDATA%\GorgonaBookingTests\h2-settlements-20261006\data` on
`127.0.0.1:51462`. It is stopped. Its credential manifest stays outside Git in
that cluster root. Start your own cluster or coordinate exclusive reuse; never
run fixture suites concurrently against one cluster.

## Preserved work and boundaries

| Checkout | Branch / observed HEAD | State |
|---|---|---|
| `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking` | codex/universal-business-foundation / `2f16380` | 19 changed/untracked paths, preserved |
| `C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents` | claude/package-g-ledger / `151472a` | 9 changed/untracked paths, preserved |
| `.codex\worktrees\package-g-ledger-review\Gorgona Booking` | codex/package-g-ledger-review / `5be6e7a` | Clean, accepted G |
| `.codex\worktrees\package-h-finance-plan\Gorgona Booking` | codex/package-h-invoices / `18e3f5e` | Clean, foundation delivered |
| `.codex\worktrees\package-g-final-review\Gorgona Booking` | codex/package-h1-backend-review / `2d5a8f9` | Clean, independent H1 review |
| `.codex\worktrees\package-h1-persistence\Gorgona Booking` | codex/package-h1-persistence / `75e809b` | Clean, delivered H1 backend |

Re-observe these before work. Clusters `51454`, `51455` and `51458` were not
created or touched by H2. Do not reset, clean, overwrite or force-push, merge,
deploy, migrate production, change cloud, DNS, billing or credentials, activate
a provider or transmit funds. KA Nails and the camera Local Gateway are separate
projects. No Azure, production, provider, jurisdiction-specific invoice or tax,
load or soak or manual accessibility acceptance is established here.
