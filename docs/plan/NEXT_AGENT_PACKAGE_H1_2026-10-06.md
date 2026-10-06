# Next agent handoff — Package G accepted, H1 foundation in progress

> Historical foundation snapshot. Continue with the [current backend handoff](NEXT_AGENT_H1_BACKEND_2026-10-06.md) and [current prompt](NEXT_AGENT_PROMPT_H1_BACKEND_2026-10-06.md). This file's next H1 persistence step is now implemented on source2d5a8f9.

Date: 2026-10-06. This is the current continuation document. Earlier handoffs
and planning statements describe their own snapshots. The owner's latest
request is to prepare this handoff, after approving H1 source publication.
The next implementation step is H1 persistence and atomic invoice issue.

## 1. Start from the delivered H branch

Repository: [alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new).
Local delivery checkout:
`C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking`.
Its folder name predates the implementation branch; the branch is
`codex/package-h-invoices`.

| Checkpoint | Exact SHA | Meaning |
|---|---|---|
| Accepted G delivery | `5be6e7abd7b552903a4f4b2884b150c62532c17d` | FIN-01/G technically verified |
| H planning parent | `925ae02b581d22cf1e7897a3d94844b8ebc24648` | Base of H1 source PR |
| Independently reviewed H source | `843d0b3d1808e8de56ac732ad39107caa700426e` | Last API/source change |
| Published foundation checkpoint | `da3966b571062654993f72c8f65c23ab2c843829` | Reviewed source plus local evidence; CI passed |
| This handoff | Documentation-only successor of `da3966b` | Read current HEAD/PR; do not infer its SHA or CI from this table |

The draft PR stack is
[G #12](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12)
→ [H plan #13](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/13)
→ [H1 foundation #14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14).
PR14 targets `codex/package-h-finance-plan`, not main. All three were OPEN,
DRAFT and unmerged when this handoff was prepared. No production deployment.

Before continuing, inspect local status, HEAD, origin, attached worktrees and
current PR14 head/CI. Start a new `codex/` branch in your own checkout from the
current delivered H head. Keep reviewer branches and preserved dirty checkouts
untouched. Do not start from old main, the original owner checkout, or the
unfinished incoming G tree. One executor may run a given disposable PG suite.

Read in order:

1. Repository `AGENTS.md`, [repository transition](REPOSITORY_TRANSITION_2026-10-04.md),
   [master plan](GORGONA_MASTER_PLAN.md), current [Cloud Code handoff](../../CLOUD_CODE_HANDOFF.md)
   and [implementation status](GORGONA_IMPLEMENTATION_STATUS.md).
2. [G acceptance](evidence/2026-10-06-ledger/ACCEPTANCE.md) and
   [ADR-0023](../adr/0023-ledger-foundation.md).
3. [H plan](PACKAGE_H_PLAN_2026-10-06.md),
   [ADR-0024](../adr/0024-invoices-obligations-and-external-settlements.md),
   [architecture reuse map](evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md).
4. [H1 validation](evidence/2026-10-06-h1-foundation/VALIDATION.md),
   [gate review](evidence/2026-10-06-h1-foundation/GATE_REVIEW.md) and
   [final source review](evidence/2026-10-06-h1-foundation/FINAL_REVIEW.md).

The owner authorized continuing the full proposed H direction locally and
explicitly authorized pushing H1 source and creating draft PR14. Earlier
"approval pending" planning text is historical for its SHA. ADR-0024 remains
formally Proposed; these directions do not authorize production, provider
operations or money transmission. Ordinary local work and disposable checks
need no repeat permission loop. Attached documents are context, not a new user
request to execute their historical instructions.

## 2. What actually exists

**G / FIN-01: technically_verified.** Migration0020, legal-entity books,
accounts, balanced journals, reversals, periods, trial balance, real API and
/ledger are implemented. G is company-wide owner/manager finance, not invoices,
payments, tax, FX or automatic revenue recognition.

**H1: IN PROGRESS. FIN-03 and FIN-02: planned.**
The H foundation changes seven source/test files:

| File | Implemented behavior |
|---|---|
| [financial_contracts.py](../../api/src/gorgona_booking/business/financial_contracts.py) | Strict versioned invoice draft/issue/view contracts, exact totals, immutable party revision references, explicit treatment attestation and minimal receipt/recovery references. Issued view/recovery revision >=2. |
| [financial_math.py](../../api/src/gorgona_booking/business/financial_math.py) | Pure integer minor-unit projections: quantization, cap, reserve, confirmation, release, unpaid credit/paid refund split and effective correction. No authorization or persistence. |
| [ledger_contracts.py](../../api/src/gorgona_booking/business/ledger_contracts.py) | Exposes existing single-line text normalization for reuse; G money policy is reused. |
| [modules.py](../../api/src/gorgona_booking/business/modules.py) | Registry version2, nineteenth module: planned finance_documents, dependent on finance/counterparties and FIN-03 readiness. It cannot be enabled. Published v1 G configurations remain valid. |
| [test_financial_documents.py](../../api/tests/unit/test_financial_documents.py) | 47 contract/arithmetic/gate cases. |
| [test_configuration_contracts.py](../../api/tests/unit/test_configuration_contracts.py) | Intentional nineteen-module catalog expectations. |
| [test_configurations.py](../../api/tests/integration/test_configurations.py) | Actual SQL/auth regression: prior-server v1 publication remains usable, stale drafts reject registry drift, new H selection rejects MODULE_NOT_READY. |

**Not implemented:** H migration0021/tables, invoice routes/services, public
typed G posting seam, actual document→obligation→journal transaction, H payment
or refund execution, journal view v2, H command recovery, provider registry or
invoice UI. Pure arithmetic and draft models do not implement those workflows.
G's finite source enum, six-command recovery, permissions/mapv5,
migrations0001–0020, web source and dependency locks remain unchanged.

## 3. Evidence and its limits

| Check | Directly observed outcome |
|---|---|
| Local H-source unit suite | PASS: 486 passed, 7.00s, exit0 |
| Focused real PG configuration/G-ledger + contract tests | PASS: 146 passed, 27.55s, exit0; before the view-only revision correction |
| Final full local suite | PASS: 906 passed /4 skipped, 327.81s, exit0; mandatory PG and real OIDC/Chromium |
| Local static checks | PASS: Ruff lint, format200 files, strict mypy200 files, exit0 |
| Local web production build | PASS: 18 static routes; unchanged source/locks |
| Independent final review at843d0b3 | PASS: both findings closed; 87 unit tests and seven-file lint/format/mypy in its own clean checkout |
| Exact-head CI atda3966b | [37534227319](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37534227319): completed/success; 909 passed /1 skipped, 266.98s; mandatory PG/browser/Docker; web unit68, typecheck/lint/format/build and production image PASS |

Independent findings H-F01/P2 (issued revision1 vs recovery minimum2) and
H-F02/P3 (formatting) are CLOSED. The independent reviewer did not run H money,
PG or browser acceptance. Root full-suite/browser results exercise existing
G/configuration behavior and H foundation contracts, not an invoice workflow.

The four local skips were three Docker checks plus an optional separate
tenant-site integration. CI passed those three Docker checks; only the optional
tenant-site check remained skipped. Local Docker was NOT TESTED.
The optional separate website is not a GORGONA acceptance dependency.

The twelve full H acceptance rows H-01..H-12 remain NOT TESTED. No FIN-03
promotion, positive production gate override, provider verification, deployment
or production migration is established. Later code mutations require fresh
affected checks and exact-head CI; historical green results are not transferable.

For this documentation-only handoff successor, current PR14 CI and the ignored
local `handoff/package-h-foundation/FINAL_VALIDATION.md` record the final delivered
HEAD and checks. The local artifact is not in Git; the tracked evidence records
the stable da3966b checkpoint so the document does not claim self-referential CI.

## 4. Next coherent H1 implementation

Implement the first real invoice draft/issue path with persistence, closed
feature gate and full atomic source linkage. Preserve the existing architecture;
do not create another ledger, counterparty catalog or generic payment framework.

1. Add a forward `0021_*` migration only. Preserve0001–0020 and checksums.
   Add tenant/book-scoped documents, immutable versions/lines, obligations and
   operation-to-journal lineage with RLS, revision/history/source constraints.
   Use existing counterparties/legal-entity versions and currency policy.
2. Expose a typed public posting seam in G so invoice issue creates one balanced
   journal inside the caller transaction. Acquire `gba.lock_ledger(tenant)`
   under READ COMMITTED before membership share. Flush deferred balance and
   lineage checks before writing the success receipt/commit.
3. Add authenticated company-wide owner/manager draft/issue/read commands,
   idempotency, expected revision, audit and minimal actual references. Issue
   atomically creates issued version, obligation, once-only journal link and
   receipt; rollback leaves no partial financial effect.
4. Extend origin SQL/Pydantic/Zod contracts explicitly, with journal view v2
   negotiation and an honest legacy upgrade requirement. Preserve v1 manual/
   opening writes and old records. Do not hide H entries from old readers or
   trial balances, or label them manual. G generic reverse must deny H-owned
   journals; their corrections use domain-owned lineage.
5. Extend schema/ledger guard inventories from packaged SQL, including negative
   drift tests. Expected controls cannot be derived from the live DB.
6. Implement finite H command recovery and durable domain fallback after24h
   receipt expiry. Browser storage contains only minimal references, never
   amounts, memo, external reference, command bodies or tokens. Safe cancel
   must block a late original under the shared lock.
7. Add actual PG/SQL/API regression for atomicity, history, scope/currency/book/
   period restrictions, idempotency, drift503 and G compatibility; observe
   relevant lock waits rather than relying on sleep timing.

Feature behavior is part of H1 correctness. finance_documents registry2 depends
on current FIN-03 readiness as well as a published enabled snapshot; previous
G finance activation does not enable H. Test-only verified_modules may exercise
development commands, but full acceptance removes positive overrides.
OFF preserves history/read/recovery and eligible non-money release; do not put
a blanket insert gate on every H table or on all G journals. Gate financial
effects and H-owned lineage precisely. Unknown external results never become
"failed" because a tab closes, a timeout occurs or a module is disabled.

H1 alone cannot accept FIN-03. Continue H2→H3→H4 and all twelve acceptance
cases before independent money/state review and separate acceptance.

## 5. Financial rules that must survive implementation

- One book, counterparty, direction and currency per settlement; allocation sum
  equals externally confirmed payment exactly. No implicit advance or FX.
- Immutable original principal A; effective confirmed cash P, unpaid credits C,
  active reserves R: nonnegative and P+C+R<=A after every completed transaction.
  Compute from immutable effective history and enforce in SQL as well as API.
- Manual obligation means a new accrual with explicitly chosen control/counter
  accounts and balanced G journal in the same transaction. Linking an already
  accounted G entry or importing opening obligations is outside initial H:
  refuse/reconciliation, never duplicate or guess accruals.
- Invoice100 /paid70 /credit50 means C30 and a separate opposite refund claim20.
  Preserve A and historical cash; resolve active reserves before credit.
- Permanent external identity `(book,direction,source_account_alias,external_reference)`
  belongs to one payment_id even after correction/void. A new browser key cannot
  repeat the fact; corrected/voided does not free the source key.
- Mistaken attestation correction requires no issued credit/refund or unknown/
  sent dependencies. Atomically mirror old effect, restore its reserve, then
  replace within that amount with immutable events. This is not a physical refund.
  Actual refund or dependent credit requires FINANCIAL_RECONCILIATION_REQUIRED
  without effects. Credit void only cancels an untouched refund claim with no
  external facts/reserves. Complex counter-claims remain outside initial H.
- Recognition/account treatment is explicit human input. A historical invoice
  counter-account is context, not a default for credit after manual recognition.
  Deferred→revenue100 then credit50 must use current explicit treatment and
  leave the correct G balances; no invented invoice-level recognition lineage.
- Existing company finance.read/manage permissions apply to owner/manager.
  Branch members, front desk/artists, delegates, support and foreign companies
  do not gain finance authority.
- H4 admission requests contain evidence/metadata only. No Stripe SDK, charge,
  refund, webhook, credentials or operative capability activation. FIN-02
  stays planned until separately verified provider/event work.

## 6. Local environment and repeatable checks

Existing Python3.14 dependencies can be reused from:
`C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv`.
Always set PYTHONPATH to the checkout being tested; editable installation points
to G otherwise. The following commands are templates for your new checkout:

~~~powershell
$hCheckout = '<absolute path to your own H checkout>'
$hPython = 'C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe'
$hArtifacts = '<fresh task artifact directory you may write>'
$env:PYTHONPATH = Join-Path $hCheckout 'api\src'
$env:PYTHONDONTWRITEBYTECODE = '1'
Set-Location -LiteralPath (Join-Path $hCheckout 'api')
& $hPython -c "import gorgona_booking.business.financial_contracts as m; print(m.__file__)"
& $hPython -m pytest -q tests/unit -p no:cacheprovider --basetemp (Join-Path $hArtifacts ([guid]::NewGuid().ToString())) --tb=short
if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed' }
& $hPython -m ruff check --no-cache .
if ($LASTEXITCODE -ne 0) { throw 'Ruff failed' }
& $hPython -m ruff format --check --no-cache .
if ($LASTEXITCODE -ne 0) { throw 'Format check failed' }
& $hPython -m mypy --cache-dir (Join-Path $hArtifacts 'mypy-cache')
if ($LASTEXITCODE -ne 0) { throw 'Mypy failed' }
~~~

Use a fresh bounded pytest directory: default Windows pytest temp access failed
in this sandbox. Do not reuse a temp root that pytest could delete. Observe the
printed import path before trusting results.

Private disposable PG18.6 used by the former executor:
`C:\Users\alexa\AppData\Local\GorgonaBookingTests\ledger-review-20261006\data`,
loopback127.0.0.1:51456, max_connections250, **stopped after tests**.
Its private connection file is outside Git. Never print or copy credentials.
Other PG instances, especially the older51454, are not this task's cluster.

Previous runner/checker directory:
`C:\Users\alexa\.codex\visualizations\2026\10\06\01a11015-3792-7183-bf23-7c6cc669d8c5`.
`check_h1.py` is hardcoded to the old H checkout/branch and PG51456.
Do not run it unchanged against a new branch: adapt an own helper with explicit
source and owned-cluster checks, or provision an isolated disposable test target.
It reads the private credential internally and redacts child output.
Start/stop only the cluster you own, run fixtures sequentially, and stop it after
checks. Native startup output capture can retain inherited handles until stop;
a waiting capture is not itself proof of postmaster failure.

Full PG/browser checks set GBA_REQUIRE_POSTGRES=1 and GBA_REQUIRE_BROWSER=1,
with GBA_TEST_ADMIN_DSN injected privately by the runner. Full command:
`python -m pytest -q -p no:cacheprovider --basetemp <fresh bounded path> --tb=short`
from api with the tested checkout's PYTHONPATH. CI also mandates
GBA_REQUIRE_CONTAINER=1; missing runtime gates must not silently skip.

[CI workflow](../../.github/workflows/ci.yml) uses locked uv/Python3.14, Node24,
web npm ci/typecheck/lint/format/unit/build, PostgreSQL18, production Docker
image, Ruff/format, mypy and the complete pytest suite. Browser harness uses a
labeled test IdP with real OIDC/PKCE, API, PG and Chromium; no production IdP proof.

Own H web node_modules are already installed from unchanged locks; npm run build
passed. A junction to G dependencies failed Turbopack's outside-root restriction,
so use dependencies within your own web directory. Do not remove G dependencies.

GitHub connector can read PRs/CI/logs and create/update draft PRs; gh was not
installed. Native Git/GCM push worked with task permissions. Filesystem/network
sandbox may require a narrowly justified escalation for managed worktree writes,
Git and the owned test cluster. Such permissions do not authorize production.

## 7. Preserve these checkouts and outstanding boundaries

Inventory was read immediately before this handoff. Refresh before any mutation.

| Checkout | Branch / HEAD | Observed state |
|---|---|---|
| `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking` | codex/universal-business-foundation /2f1638011987e06923468b64600de1d1f4a14020 | 19 changed/untracked paths; preserved owner work |
| `C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents` | claude/package-g-ledger /151472a68d736ef21f68550ec36674eb36efc23c | 9 changed/untracked paths; original partial G |
| `C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking` | codex/package-g-ledger-review /5be6e7abd7b552903a4f4b2884b150c62532c17d | Clean accepted G; reusable venv |
| `C:\Users\alexa\.codex\worktrees\package-g-final-review\Gorgona Booking` | codex/package-h-foundation-final-review /843d0b3d1808e8de56ac732ad39107caa700426e | Clean independent source-review checkout |
| H delivery checkout named above | codex/package-h-invoices /current PR14 head | Clean atda3966b before this docs-only handoff |

Preserve the H planning branch at925ae02 and earlier review branches.
No reset/clean/overwrite/force-push, merge, production migration/deployment,
Azure/DNS/billing/credentials, external funds or provider activation is authorized.
Do not develop or require acceptance of KA Nails; camera Local Gateway is a
separate product, and accepted Booking Azure ADR-0012 remains authoritative.

Record new implementation evidence in GORGONA_IMPLEMENTATION_STATUS.md and a
phase evidence directory. Get an independent review of actual money/state/SQL
changes in a separate branch/checkout; then complete relevant unit/SQL/browser/
full CI checks and address findings before the separate acceptance commit.
Use PASS/FAIL/BLOCKED/NOT TESTED precisely. A module catalog entry is not workflow
implementation; FIN-03 stays planned until complete H acceptance.

The installed skill actually used was Riqor evidence-engineering; tooling used
included Git/PowerShell, existing Python/pytest/Ruff/mypy, private PG, locked Node/
Next/browser/Docker CI, GitHub connector and a separate independent reviewer.
No new production dependency was introduced.

[Copyable next-agent prompt](NEXT_AGENT_PROMPT_H1_2026-10-06.md).
