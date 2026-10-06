# Next agent handoff — H1 invoice backend, closed feature gate

Checkpoint started 2026-10-06. This supersedes the H1 foundation continuation.
The owner requested a handoff and then continued project work. Local H work and
draft publication are authorized; historical approval-pending planning text
does not create another permission loop. Attached documents are context, not
new user requests. Production, provider actions and money transmission are not
authorized.

## Start from this branch

Repository: [GORGONA-Booking-Platform_new](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new).
Implementation branch: `codex/package-h1-persistence`.
Checkout: `C:\Users\alexa\.codex\worktrees\package-h1-persistence\Gorgona Booking`.
Reviewed source: `2d5a8f917b69f1d52adea96aa8209722d1a24d42`.
Parent: `18e3f5e53b24a7590ef035df7fe3ae41521dc740`, delivered H1 foundation.
The handoff/evidence commit is a documentation-only successor. Obtain its exact
HEAD, origin and PR CI from Git/GitHub; source SHA alone is not final-head CI.

PR stack: G [#12](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12)
→ H plan [#13](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/13)
→ foundation [#14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14)
→ backend [#15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15).
All four are open/draft/unmerged; PR15 targets `codex/package-h-invoices`.
Refresh current state before action. No merge or deployment is established.

Create your own `codex/` branch and checkout from this delivered backend HEAD.
One executor edits each checkout and owns each disposable PostgreSQL cluster.
Do not continue from old main or overwrite a preserved tree.

Read these in order:

1. `AGENTS.md`, [repository transition](REPOSITORY_TRANSITION_2026-10-04.md),
   [master plan](GORGONA_MASTER_PLAN.md), [implementation status](GORGONA_IMPLEMENTATION_STATUS.md),
   current [Cloud Code handoff](../../CLOUD_CODE_HANDOFF.md).
2. [H1 backend validation](evidence/2026-10-06-h1-backend/VALIDATION.md),
   [initial review](evidence/2026-10-06-h1-backend/INITIAL_REVIEW.md) and
   [closure review](evidence/2026-10-06-h1-backend/CLOSURE_REVIEW.md).
3. [H plan and all twelve acceptance cases](PACKAGE_H_PLAN_2026-10-06.md),
   [ADR-0024 Proposed](../adr/0024-invoices-obligations-and-external-settlements.md),
   [reuse map](evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md).
4. [G acceptance](evidence/2026-10-06-ledger/ACCEPTANCE.md),
   [ADR-0023](../adr/0023-ledger-foundation.md), [development guide](../DEVELOPMENT.md).

## What exists now

G/FIN-01 remains `technically_verified`. H1 backend is implemented behind the
closed `finance_documents` gate. FIN-03 and FIN-02 remain `planned`; full H is
unfinished. There is no invoice UI or external payment integration.

| Boundary | Actual implementation |
|---|---|
| Persistence | Forward `0021_invoice_accrual.sql`; seven insert-only tenant/book-scoped tables with FORCE RLS and company scope: anchors, versions, lines, principal obligations, operation links, permanent receipts and cancellations. |
| Draft/issue | Authenticated invoice list/history/draft/issue API. Expected revision; immutable issue copies; exact currency minor units; explicit control/counter accounts and `confirmed_account_treatment`. |
| One accrual | One transaction writes issued version/lines, principal obligation, balanced G journal, lineage, audit and permanent minimal command receipt. Period/refusal rolls back the issue. |
| SQL integrity | Same-transaction markers seal later fills; deferred whole-document checks cover every participating H/G insert, including late balanced journal lines and an older draft line after an early constraint flush. |
| Recovery | Finite invoice_draft/invoice_issue operations, fingerprint-bound replay after ordinary receipt cleanup, reference-only resolve/cancel and cancellation sealing against a delayed original. |
| Compatibility | Explicit journal read schema2 adds invoice; G write-v1 is preserved. V1 detail/list require JOURNAL_VERSION_REQUIRED instead of hiding an invoice. Trial balance includes it; API/SQL refuse generic reversal of an H-owned journal. |
| Web | Existing ledger reads schema2 and validates BigInt totals. Invoice rows expose no generic reversal. Paging restarts when wire versions differ. This is G ledger compatibility, not H invoice UI. |
| Readiness | 57 company-scope policy definitions plus H trigger/function/key/FK/type/privilege approvals. All 25 H CHECKs have repository-owned exact predicates and validated/local status; literals retain whitespace. |
| Feature gate | Current registry readiness and a published finance_documents selection with finance/counterparties dependencies are both required. Old G finance publications do not enable H. OFF history/replay/recovery/cancel survive. |

Relevant implementation files are listed in the validation document. Do not
create a second ledger, generic payment subsystem or duplicate counterparty
catalog. No dependency, lockfile, permission map or migration0001–0020 changed.

Positive H invoice integration tests deliberately override planned readiness
in fixtures. The real registry cannot enable H. The separate withdrawal/config
tests prove the gate. These test successes are not user-facing H acceptance.

## Evidence and review

Initial source `ac7726e` had a real readiness defect: dropping the obligation
source-kind CHECK left health200. Independent review H1-R01 required changes.
Source `2d5a8f9` closes it with the complete predicate inventory and explicit
invoice/principal checks in coupled lineage.

Direct independent closure: 47 real PostgreSQL tests PASS, including the
original failing probe and new CHECK/SQL negatives; 109 relevant unit tests PASS;
scoped Ruff/format/mypy and diff checks PASS. The reviewer used a separate clean
checkout and owned PG51460, then stopped it. No remaining finding in that delta.
Independent full-suite/web/browser/CI validation was NOT TESTED.

Root focused H integration plus all unit tests: 533 PASS, 35.89s, exit0.
Ruff, format and strict mypy: PASS, 204 Python files. Fresh full local:
953 passed/4 skipped/378.14s, exit0, mandatory real PostgreSQL/OIDC/Chromium.
Root-owned PG51456 and reviewer51460 are stopped. Exact-final-head CI belongs in [validation](evidence/2026-10-06-h1-backend/VALIDATION.md)
and the current draft PR. Do not substitute the earlier ac7726e full pass for
the corrected source.

All twelve complete H acceptance rows remain NOT TESTED because they include
settlements, credits/refunds, UI and admission beyond this slice. Some invoice
parts have direct proof; FIN-03 must not be promoted after H1 alone.

## Next coherent phase

Continue H2 on a new branch from this backend delivery. First inspect actual
schema/services/tests and turn the relevant H-01/H-03/H-04/H-05/H-07/H-08/H-09
criteria into real red→green checks.

1. A manual obligation is a **new accrual** with explicit accounts and balanced
   G journal inside the same transaction. Existing manual/opening entries are
   not automatically linked, imported or accrued twice.
2. Add immutable settlement lifecycle/history, preparation/approval, reserves,
   release and partial externally attested confirmation. Reuse the typed posting
   seam, currency policy, lock order, audit and durable minimal recovery.
3. Enforce effective nonnegative P/C/R and P+C+R<=original A in PostgreSQL and
   service code, at commit. Reservations post no cash. Partial confirmation
   transfers exactly R→P; the remainder stays reserved.
4. Bind permanent external identity to one payment_id independently of browser
   idempotency keys. Allocations equal the confirmed external amount exactly.
   No unallocated advance, FX or provider-verified label for human attestation.
5. A sent/unknown outcome cannot release money merely because time passed,
   finance became OFF or an HTTP response was lost. Explicit evidence/state
   resolution is required; eligible non-money release/recovery remains possible.
6. Keep origin enums/protocols finite. Evolve SQL, Python and Zod together when
   adding a real new source. Preserve G-v1 writes and all-entry trial balances.
7. Use a new forward migration after published0021. Preserve its checksum and
   migrations0001–0020. Extend guards with repository-owned approvals, including
   CHECK predicates, and restore every new scope policy in drift-test helpers.
8. Run real two-document70-from100 races with observed pg_locks waits, partial
   confirm/release/credit races, rollback, receipt expiry, late originals,
   source dedup, OFF and tenant/book/party/currency/period negatives.

Then H3 implements unpaid credits/paid refund obligations and guarded immutable
corrections; H4 supplies admission metadata without capability activation and
real desktop/mobile invoice/settlement/credit UI. Invoice100/paid70/credit50
means unpaid C30 and opposite-direction refund20; never rewrite historical cash.
Actual refund, sent/unknown or credit dependencies require reconciliation
instead of a fake undo. Preserve explicit recognition/account choices.

The remaining full-H acceptance sequence is independent money/state review,
all twelve criteria, full local and exact-SHA CI, then a separate readiness
acceptance commit. Remove positive readiness overrides only when that scope
has actually passed. ADR-0024 remains formally Proposed.

## Reproducible local environment

Python3.14 dependencies are reusable from
`C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv`.
Its editable installation points to G, so explicitly set PYTHONPATH to **your**
checkout. Node24 is `C:\Program Files\nodejs`; Next16.3.7 uses the existing locks.
The project supports `uv sync --locked` in an agent's own environment.

~~~powershell
$hCheckout = '<absolute path to your own checkout>'
$hPython = 'C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $hCheckout 'api\src'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath (Join-Path $hCheckout 'api')
& $hPython -c "import gorgona_booking.business.financial_documents as m; print(m.__file__)"
& $hPython -m ruff check .
& $hPython -m ruff format --check .
& $hPython -m mypy
$env:GBA_REQUIRE_POSTGRES = '1'
$env:GBA_REQUIRE_BROWSER = '1'
$env:PATH = 'C:\Program Files\nodejs;' + $env:PATH
# Set GBA_TEST_ADMIN_DSN privately for your own disposable PostgreSQL18 cluster.
# Never print it or write it into Git, documentation or a message.
& $hPython -m pytest -q -p no:cacheprovider --basetemp '<fresh owned temp path>'
~~~

From your web directory, the gates are `npm run typecheck`, `lint`,
`format:check`, `test:unit` and `build`. Build before mandatory browser tests.
CI also requires all three real Docker gates, production image and PostgreSQL.
Local Docker skips are NOT TESTED locally; CI must supply their actual proof.

The root-owned temporary cluster is
`%LOCALAPPDATA%\GorgonaBookingTests\ledger-review-20261006\data` on
`127.0.0.1:51456`, PostgreSQL18.6. Its credential manifest is outside Git in that
cluster root; values must stay private. The root runner is the external
`check_h1_persistence.py` under
`C:\Users\alexa\.codex\visualizations\2026\10\06\01a11015-3792-7183-bf23-7c6cc669d8c5`.
It verifies branch/target and redacts output; it is not a repository dependency.
The independent reviewer alone owned fresh cluster51460. Historical51454 and
51458 were not owned/modified by this continuation. Start a fresh assigned
cluster or coordinate exclusive reuse; never run fixture suites concurrently
against one cluster because they share runtime-role setup.

## Preserved work and boundaries

| Checkout | Branch / observed HEAD | State |
|---|---|---|
| `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking` | codex/universal-business-foundation / `2f1638011987e06923468b64600de1d1f4a14020` | 19 changed/untracked paths, preserved |
| `C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents` | claude/package-g-ledger / `151472a68d736ef21f68550ec36674eb36efc23c` | 9 changed/untracked paths, preserved |
| `.codex\worktrees\package-g-ledger-review\Gorgona Booking` | codex/package-g-ledger-review / `5be6e7abd7b552903a4f4b2884b150c62532c17d` | Clean, accepted G |
| `.codex\worktrees\package-h-finance-plan\Gorgona Booking` | codex/package-h-invoices / `18e3f5e53b24a7590ef035df7fe3ae41521dc740` | Clean, foundation delivered |
| `.codex\worktrees\package-g-final-review\Gorgona Booking` | codex/package-h1-backend-review / `2d5a8f917b69f1d52adea96aa8209722d1a24d42` | Clean, independent review |

Re-observe these before work. Do not reset/clean/overwrite/force-push, merge,
deploy, migrate production, change cloud/DNS/billing/credentials, activate a
provider or transmit funds. KA Nails and camera Local Gateway are separate
projects. No Azure, production, provider, jurisdiction-specific invoice/tax,
load/soak or manual accessibility acceptance is established here.
