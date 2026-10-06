# H1 invoice backend — validation and boundaries

Reviewed source: `2d5a8f917b69f1d52adea96aa8209722d1a24d42`.
Base: `18e3f5e53b24a7590ef035df7fe3ae41521dc740` (delivered foundation).
Branch: `codex/package-h1-persistence`, own checkout under
`C:\Users\alexa\.codex\worktrees\package-h1-persistence\Gorgona Booking`.
The documentation delivery is a successor of the reviewed source. Inspect
current Git/PR HEAD and exact-head CI; a source checkpoint is not final-head CI.

This is a bounded, closed H1 backend increment. G/FIN-01 remains technically
verified. FIN-03/FIN-02 are planned; finance_documents cannot be enabled through
the real registry. Positive H fixtures override readiness only in tests.
H2 settlements/manual accruals, H3 credits/refunds and H4 invoice UI/admission
are not implemented.

## Changed source and test files

The delta from the foundation is 18 files, 3221 insertions and 94 deletions.
Documentation and independent reports are additional delivery files.

| File | Change |
|---|---|
| [api/app.py](../../../../api/src/gorgona_booking/api/app.py) | Registers typed invoice router. |
| [api/financial_documents.py](../../../../api/src/gorgona_booking/api/financial_documents.py) | Company finance list/history/draft/issue/resolve/cancel endpoints and shared authorization/guard. |
| [api/ledger.py](../../../../api/src/gorgona_booking/api/ledger.py) | Explicit finite schema1/schema2 query negotiation. |
| [business/financial_contracts.py](../../../../api/src/gorgona_booking/business/financial_contracts.py) | Strict invoice list/summary and command-status models. |
| [business/financial_documents.py](../../../../api/src/gorgona_booking/business/financial_documents.py) | Atomic persistence/issue, expected revision, current gate, fingerprint replay, permanent receipts and safe cancellation. |
| [business/ledger.py](../../../../api/src/gorgona_booking/business/ledger.py) | Reusable typed append inside caller transaction, v2 views, explicit v1 upgrade and invoice reversal refusal. |
| [business/ledger_contracts.py](../../../../api/src/gorgona_booking/business/ledger_contracts.py) | Typed invoice posting seam and finite strict v2 read models; v1 writes retained. |
| [db/financial_guard.py](../../../../api/src/gorgona_booking/db/financial_guard.py) | Packaged trigger/function/policy/key/FK/type/privilege and exact CHECK approvals. |
| [0021_invoice_accrual.sql](../../../../api/src/gorgona_booking/db/migrations/0021_invoice_accrual.sql) | Seven insert-only FORCE RLS tables; locked finite origin, current published gates, immutable history and deferred full-graph integrity. |
| [db/schema_guard.py](../../../../api/src/gorgona_booking/db/schema_guard.py) | H controls and seven added company-scope policies; 57 scope definitions. |
| [test_invoice_issue.py](../../../../api/tests/integration/test_invoice_issue.py) | 46 real H API/SQL tests, including concurrency, late inserts, recovery, scope/gate/period/currency and drift. |
| [test_location_access.py](../../../../api/tests/integration/test_location_access.py) | Drift restoration includes migration0021 restrictive policy footer. |
| [test_document_contracts.py](../../../../api/tests/unit/test_document_contracts.py) | 57-definition and H boundary expectations. |
| [test_ledger_contracts.py](../../../../api/tests/unit/test_ledger_contracts.py) | Strict v2 invoice origin/headers and preserved v1 rejection. |
| [ledger.tsx](../../../../web/components/ledger.tsx) | No generic reverse for invoice; reload page when wire versions change. |
| [ledger-api.ts](../../../../web/lib/ledger-api.ts) | Negotiates v2 ledger reads. |
| [ledger-contracts.ts](../../../../web/lib/ledger-contracts.ts) | Discriminated finite v1/v2 models and exact BigInt checks. |
| [ledger-contracts.spec.ts](../../../../web/tests/ledger-contracts.spec.ts) | Invoice-v2 accept; legacy/unknown kind/version and malformed totals reject. |

No dependency, lockfile, permission map, prior migration0001–0020 or checksum
was changed. No second money ledger, provider SDK or activation was added.

## Direct checks

Python3.14 executable: existing G venv with PYTHONPATH explicitly pointing to
this H1 checkout. Root alone owned PG18.6 on loopback51456. Repeated pytest runs
used fresh owned basetemp directories and no cache provider; credentials stayed
in the private cluster manifest and masked process environment.

| Check / actual command | Outcome |
|---|---|
| `check_h1_persistence.py pytest tests/integration/test_invoice_issue.py tests/unit -q -p no:cacheprovider --basetemp <fresh> --tb=short` | PASS: 533 tests, 35.89s, exit0; corrected source. |
| `python -m ruff check .` from api | PASS, exit0. |
| `python -m ruff format --check .` from api | PASS: 204 files, exit0. |
| `python -m mypy --cache-dir <owned-external-cache> .` from api, strict project configuration | PASS: no issues in 204 source files, exit0. |
| Fresh full local `GBA_REQUIRE_BROWSER=1 ... check_h1_persistence.py pytest -q ...` on corrected source | PASS: 953 passed/4 skipped/378.14s, exit0, corrected source2d5a8f9; real PostgreSQL and OIDC/Chromium mandatory. |
| Web typecheck/lint/format/unit/build on ac7726e | PASS: 69 unit tests/1.8s, 18 build routes; web source is unchanged by2d5a8f9. Final exact-head CI must independently exercise these gates. |
| `git diff --check` and `git diff --check 18e3f5e..HEAD` | Source checkpoint PASS, exit0; rerun after final documentation mutation. |
| Final documentation/links/report hashes/source-preservation check | PASS: 14 changed Markdown files, 58 added/changed local links, three peer report hashes, three helper AST checks, all12 complete H cases NOT TESTED, unchanged18 reviewed source files and preserved checkouts19/9/0/0/0. Both diff checks exit0; own51456/51460 stopped. Rerun after this evidence mutation. |
| Exact final-head GitHub CI, mandatory PostgreSQL/browser/Docker/image | Delivery gate: [draft PR15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15) and the bundled DELIVERY_STATE/ignored local FINAL_VALIDATION report observed final HEAD/run/outcomes; this tracked source checkpoint makes no self-referential CI claim. |

The earlier ac7726e full local pass was 944 passed/4 skipped/358.70s. It validates
that earlier source, before H1-R01 closure, and is not acceptance of the changed
guard/migration. Initial full failures were traced to an unfinished web build
and missing H policy restoration/old57-definition expectations, then corrected.
Two initial drift tests attempted predicates inconsistent with existing fixture
rows; PostgreSQL correctly refused that DDL. The tests now use valid weakened/
literal-altered predicates and restore controls. An attempted focused command
named a nonexistent unit filename and ran no tests; the corrected533 run is the
accepted evidence. None of those failed attempts is counted as PASS.

## Independent review and exact artifacts

Separate clean review checkout:
`C:\Users\alexa\.codex\worktrees\package-g-final-review\Gorgona Booking`,
branch `codex/package-h1-backend-review`. Own fresh PG18.6 cluster51460,
sequential tests, then stop exit0. Root51456 and historical51458 were untouched.

| Artifact | Outcome and original external SHA256 |
|---|---|
| [Initial backend review](INITIAL_REVIEW.md), ac7726e | FAIL / changes required: H1-R01/P2. Missing obligation source CHECK left GET /health/ready200. 107 ordinary PG and109 unit tests PASS; independent external probe1FAIL/2.75s. Original `c46886d0a62bb4b87e2d5b48601643da964f147f52113c66525798d54b0a3a7b`. |
| [Closure review](CLOSURE_REVIEW.md),2d5a8f9 | PASS: H1-R01 closed; 47 PG tests including the original probe and all46 H regressions,109 units, scoped Ruff/format/mypy/diff PASS. No remaining corrective-delta finding. Original `bd2ba036e0618d9100351398aaf53ca74dc7b854f1c77f269b8c320dd73549e7`. |
| [Design/reuse review](DESIGN_REVIEW.md), foundation18e3f5e | Proposed bounded H1 approach reviewed; runtime not tested in this design report. Original `dc14ed829ce305c1d3e4e78d07d2e06eb31c49667825ec8425179a6690b3925f`. |

Repository copies use LF; the final documentation checker records their normalized
SHA256 values separately from the original external files:

| Repository LF copy | SHA256 |
|---|---|
| [INITIAL_REVIEW.md](INITIAL_REVIEW.md) | `c46886d0a62bb4b87e2d5b48601643da964f147f52113c66525798d54b0a3a7b` |
| [CLOSURE_REVIEW.md](CLOSURE_REVIEW.md) | `bd2ba036e0618d9100351398aaf53ca74dc7b854f1c77f269b8c320dd73549e7` |
| [DESIGN_REVIEW.md](DESIGN_REVIEW.md) | `de35f88696d10a56126e2457d95669dcc90cf15db78d0dd732e2f77fbcf4bece` |

Original reports
remain outside Git under the task artifact directory. Independent full-suite,
web/browser and CI checks were NOT TESTED; root/CI supply separate evidence.
Review PASS does not accept FIN-03.

## Observable bounded behavior

- Atomic invoice issue, one obligation/G journal/link and exact receipt replay;
  closed-period refusal leaves draft with no partial issue effect.
- Whole-document SQL checks reject orphan origins, later-transaction filling,
  a late balanced G pair after early IMMEDIATE→DEFERRED and a late prior draft
  line within the draft/issue transaction.
- Real competing issue requests are observed waiting in pg_locks; one200/
  one409, one durable obligation. No sleep-only concurrency claim.
- Insert-only history, USD/JPY/KWD scales, explicit expense/liability and deferred
  income, exact0.10+0.20, treatment attestation, foreign book/party and finance
  role/company restrictions are exercised.
- Permanent receipt replay survives ordinary cache cleanup; minimal recovery,
  OFF history/replay/cancel and late-original sealing remain valid.
- Missing, weakened, unvalidated and literal-altered H CHECKs, an unsupported
  G source extension, damaged triggers/FK/keys/RLS/policies/private privileges
  produce503 and recover after restoration. SQL coupled origin/components reject
  independently when the corresponding column CHECK is absent.
- Current readiness withdrawal blocks H with MODULE_NOT_READY while G still
  works. Real registry keeps FIN-03 planned and finance_documents unavailable.
- Legacy journal reads require explicit upgrade; modern detail/list and G trial
  balance retain invoice origins. Generic H reversal refuses through API and SQL.

## Unverified boundaries

The twelve **complete** H-01..H-12 criteria remain NOT TESTED. Invoice-specific
parts have the bounded proof above; manual accrual, settlements/reserve cap,
external semantic dedup/partial payments, credit/refund/correction, H UI and
admission metadata still need implementation and direct proof. Pure financial
math does not enforce a persisted settlement cap.

Local Docker checks are NOT TESTED; CI must run all three. Optional separate
tenant-site integration is not a platform acceptance dependency. No provider
verification, network charge/refund/webhook, money transmission, Azure change,
production migration/deployment, statutory tax/invoice, load/soak or manual
screen-reader proof. No FIN-03/02 promotion, merge or production activation.

Tools: scoped Git/PowerShell/Python, installed locked project stack, real PG and
OIDC/Chromium harness, GitHub connector and independent agent under the
`evidence-engineering` skill. Technical trigger deferral was verified against
official [PostgreSQL18 SET CONSTRAINTS](https://www.postgresql.org/docs/18/sql-set-constraints.html)
and [CREATE TRIGGER](https://www.postgresql.org/docs/18/sql-createtrigger.html).
See [portable handoff](../../NEXT_AGENT_H1_BACKEND_2026-10-06.md) and
[copyable prompt](../../NEXT_AGENT_PROMPT_H1_BACKEND_2026-10-06.md).
