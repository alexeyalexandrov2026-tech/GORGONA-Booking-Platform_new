# Independent review of package G — follow-up at 6735f88

Status: **CHANGES REQUIRED — one remaining P2 finding.** The five original findings have been addressed in the reviewed snapshot; independent regression checks confirm the database and boundary fixes. Browser acceptance remains incomplete because of the entity-reselection defect below.

Reviewed source commit: `6735f88e63c0057a1bbcfd3f2320f2347f0a97bd`, compared with base `151472a68d736ef21f68550ec36674eb36efc23c`.

Independent branch/check-out: `codex/package-g-independent-review`, `C:\Users\alexa\.codex\worktrees\package-g-independent-review\Gorgona Booking`. The checkout stays on the base commit with a copied review snapshot; no reviewer source edits or commits were made. Forty changed source/test/docs files were copied and SHA256 checked against the implementation checkout. Final manifest: `snapshot-6735f88.json`; SHA256 `d59a4743bebf409a6933f958721bab0db7eae9f08ad3ce9d4db2f48db31af2e5`. Earlier pre-fix and intermediate manifests are retained separately.

## Remaining finding

**[P2] Reselecting the current legal entity clears the loaded book permanently.**

- File: `web/components/ledger.tsx`, lines 386–399; dependent book-loading effect at line 204.
- Trigger: wait for the existing book's `Post journal entry` form to be visible; read the current `Legal entity` select value; select that same value again; expect the form to remain visible.
- Actual: the selection handler clears `book`, accounts, entry and period state even though the selected entity and `bookId` did not change. The loading effect therefore does not run again. Book settings and financial forms disappear until a ledger refresh/remount.
- Impact: reproducible UI state loss and a timing-dependent failure in the desktop recovery acceptance test. When the original load is still in progress, it can refill the cleared state and hide the defect.
- Smallest fix: return immediately if the selected entity equals the current entity before clearing book state; add the deterministic same-value selection assertion.
- Independent evidence: the original four-case browser run had three PASS and one desktop recovery FAIL. A separate deterministic browser probe first confirmed that the form was loaded, then selected the unchanged value; the required visibility assertion failed after 2 seconds. Both probes used rebuilt reviewed web source, actual test OIDC/PKCE, actual HTTP/API and actual PostgreSQL.
- Evidence files: `acceptance-followup.log`, `deterministic-red.log`, `deterministic-tests/ledger-deterministic.spec.ts`, `deterministic.config.cjs`, `deterministic-results/`. The deterministic probe and subprocess redirection plugin live outside the repository; original source/tests were not modified.

## Independent checks

| Check | Observed outcome |
|---|---|
| Initial focused follow-up Python tests | PASS: 56 tests, 20.56 s |
| Latest ledger/contracts/location-boundary tests after scope-marker fix | PASS: 88 Python tests; combined browser harness failed on the P2 issue above |
| Original ledger browser cases | Three PASS; desktop recovery FAIL; total four cases |
| Deterministic existing-book reselection probe | Expected red: first normal scenario PASS; same-value reselection FAIL after previously visible form |
| Web unit suite | PASS: 68 tests, 1.5 s |
| Independent web production build | PASS; ledger route and 18 generated static pages |
| Web typecheck, lint and formatting | PASS |
| Scoped Python Ruff | PASS |
| Strict mypy for ledger service/contracts/API and database guards | PASS: five source files |
| Final copied snapshot checks and git diff --check | PASS |

The PostgreSQL regressions exercised the original/reversal append rejection after early constraint checks, unsupported isolation rejection, meaningful literal-whitespace guard detection, real API recovery/cancellation and delayed-original prevention, concurrent post/cancel ordering, actor scoping, disabled-module recovery, and restoration of damaged location scope. Review also inspected rights and tenant/legal-entity/currency boundaries, typed minimal recovery references, receipt matching/fallback queries, actual per-row report math and schema validation, and selection/render guards. No additional concrete defects were identified in those reviewed paths.

Recovery storage contains minimal typed actor/business/book/operation references, never full financial command bodies, amounts, memos or tokens. Browser tests verify absence of sensitive payloads, response-loss recovery after reload, preserved entity choice, navigation recovery, and refusal of the delayed original after cancellation; desktop recovery completion remains blocked by the reported selection defect in this snapshot.

## Boundaries

All independent PostgreSQL checks used only the reviewer's separate loopback server on port 51458, with disposable FAKE data and the actual packaged migrations. The implementation agent's port 51456 was never accessed. The reviewer's server is stopped, with evidence retained outside the repository. No deployment, production migration, cloud action, source mutation, commit, push or shared fixture run occurred.

The parent's full suite, GitHub CI and draft PR status are not independent validation in this report. Full repository acceptance, production/staging deployment, performance/soak targets, manual screen-reader acceptance and jurisdiction-specific financial compliance were not tested independently. The forthcoming reselection fix and later commits require a short separate follow-up; this report does not approve production release.
