# Independent review of package G — follow-up at 4961d1a

Status: **CHANGES REQUIRED — one newly reproduced P1 tenant-boundary defect.** The previously reported entity-reselection defect is fixed and independently verified green. The earlier five fixes remain present; all previously reviewed API/SQL/guard source hashes are unchanged between 6735f88 and 4961d1a.

Reviewed source commit: `4961d1a4990c6d5af37a512fc414d1f7714399dc`, base `151472a68d736ef21f68550ec36674eb36efc23c`. The reviewer's isolated checkout stays on its own branch, `codex/package-g-independent-review`, with a copied source snapshot and no reviewer source commits.

Forty-one changed source/test/docs files were copied and SHA256 verified against the implementation checkout. Manifest `snapshot-4961d1a.json` SHA256: `9dfeb11ec0b9ff6026c30564233e4cb54f3b598a9442ca83a567d53d50d7b864`. All 41 manifest hashes matched both checkouts before the additional fault-injection probe.

## New finding

**[P1] Additional permissive ledger policies bypass tenant isolation without failing readiness.**

File: `api/src/gorgona_booking/db/ledger_guard.py`, lines 79–89 (the expected-policy check at the end of `LEDGER_BOUNDARY`).

The guard verifies the approved named `*_tenant_isolation` policy but does not reject additional permissive policies on the eight ledger tables. PostgreSQL combines applicable permissive policies with OR, so preserving the approved policy alone is insufficient. The company-wide restrictive policy checks location scope; it does not restore tenant isolation for an unrestricted runtime session.

Independently reproduced using actual packaged migrations, actual non-owner runtime role, actual API/readiness endpoints and disposable FAKE companies on PostgreSQL 18.6 port 51458:

1. Create a legal entity/book for tenant A through the real ledger fixture/API.
2. As the disposable database owner, add `CREATE POLICY review_extra_ledger_read ON gba.ledger_books FOR SELECT TO public USING (true)`. Keep the approved tenant policy intact.
3. GET `/health/ready`: actual HTTP 200.
4. Authorized GET for tenant A's ledger book: actual HTTP 200, rather than failing closed on the damaged boundary.
5. In a runtime transaction scoped to tenant B, call `assert_location_scope_ready`: it passes.
6. In that transaction, raw SELECT the tenant A book by ID: the tenant A row is returned.

Observed summary: `ready_http=200`, `ledger_http=200`, `foreign_row_visible=True`. The external regression asserting that the foreign row remains invisible fails. The extra policy was dropped in `finally`, and the fixture removed its disposable database. This is privileged policy-drift fault injection; the runtime user did not receive permission to create policies. No cross-tenant HTTP response exposure was asserted: the demonstrated exposure is the database RLS boundary, while health/API readiness accepts the damaged state.

Required correction: reject unapproved permissive policies on all eight ledger tables, including SELECT/INSERT/ALL policies and applicable public/runtime/member-role variants. Keep the approved tenant policy's definition validation. Add a regression for an extra policy while the named approved policy remains unchanged; verify health/ledger readiness becomes 503 and the baseline boundary is restored afterward.

Evidence: `test_extra_ledger_policy.py` and `extra-policy-red-4961d1a.log` outside the repository. FAKE authentication fixture representation was removed from the saved failure log. PostgreSQL reference checked during this review: [Row Security Policies, PostgreSQL 18](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).

## Verified UI correction and current checks

| Check | Observed outcome |
|---|---|
| Fresh web build from 4961d1a | PASS; ledger route, 18 generated static pages |
| Changed document/schema guard unit tests plus real ledger browser harness | PASS: 22 Python tests in 18.16 s |
| Repository desktop/mobile ledger browser cases | PASS: four cases in 14.7 s |
| Exact prior deterministic reselection probe, with both browser surfaces | PASS: four cases in 14.2 s; Python harness PASS in 17.17 s |
| Strict mypy for changed document/schema guard unit test file | PASS: one source file |
| All previously reviewed API/SQL service and guard source hashes | Identical to independently checked 6735f88 snapshot |
| Snapshot integrity and git diff --check | PASS |
| Additional permissive-policy isolation/readiness probe | FAIL: foreign tenant row visible while readiness returns 200 |

The deterministic probe first waits for an existing book's journal-entry form to be visible, selects the same current legal entity value again, and asserts the form stays visible. It failed deterministically on 6735f88 and passes on 4961d1a. The new no-op in the selection handler correctly prevents the unnecessary state clear. Green evidence is retained separately from the earlier red probe.

Fresh browser evidence exercises actual test OIDC/PKCE, HTTP/API and PostgreSQL; balanced entry/reversal/report/period behavior; committed-response loss; reference-only session storage without amount/memo/token payloads; reload and navigation recovery; safe cancellation; and rejection of a delayed original request. Post-browser SQL assertions confirm book/entry/line/period/cancellation counts and reference-only receipts/audits.

The previous independent report records 88 Python tests, 68 web unit tests and scoped static checks at 6735f88. Those results are historical for this follow-up; byte identity supports carrying over review of unchanged API/SQL source, while the changed UI/test paths were rebuilt and exercised freshly as listed above. The entire repository suite was not rerun independently at 4961d1a.

## Boundaries

Only the reviewer's separate server on 51458 was used. The implementation agent's 51456 server was never accessed. The review server is stopped. All fake database and external probe artifacts remain outside the repository. No source edits, commits, pushes, deployment, production migrations, cloud changes or shared fixture execution occurred.

Parent full-suite results and GitHub CI were not independently verified here. Production/staging deployment, performance/soak targets, manual screen-reader acceptance and jurisdiction-specific financial suitability were not tested. This report approves the UI correction only; the reproduced tenant-boundary failure prevents a passing overall independent review at this SHA.
