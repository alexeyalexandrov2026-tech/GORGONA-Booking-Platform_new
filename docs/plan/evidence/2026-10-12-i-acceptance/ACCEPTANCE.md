# Package I — acceptance preparation, 2026-10-12

**Preparation: PASS. Package acceptance: BLOCKED; WORK-01 and CORE-04 remain
`planned`, workforce remains closed outside test fixtures.** This is a fresh
acceptance evidence record for owner review, not an acceptance/readiness decision.
I-01–I-11 pass the cases recorded below. I-12 is conservatively BLOCKED because
the independent source review predates the fourteen fixes; that review exists,
but a second source review of the corrected code has not been performed here.

## Verified source and repository

- Repository: `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`.
- Checkout: `C:/Users/alexa/Documents/ChatGPT/gorgona-package-i`.
- Base/handoff SHA: `c6b8e341a7e88957ee5011e54e9aa06453b31b49` on
  `codex/package-i4-workforce-screens`; local and remote matched before edits.
- Clean start; new local branch `codex/package-i-acceptance` from that exact SHA.
- Last code SHA: `b66eb4140c1101d78e1bd4068eac537aab922b38`. Its sixteen source/test
  SHA256 values match the current Git blobs: [source proof](SOURCE_SHA256.json).
  `b66eb41..c6b8e34` has no changes under api/src, api/tests, api/tools, web, ai,
  infra or .github. Git status stayed clean through the verification run.
- Downloads INVENTORY.md equals the entry handoff, and the attached independent
  review and author response equal their repository copies byte for byte. Their
  instructions were subordinate to the requested acceptance continuation.
- Branch-specific GitHub PR query (`state=all`, head I4) returned zero PRs.
  The acceptance branch is not published. No push, PR, merge or readiness promotion.

## Fresh evidence and exact-source CI

| Check | Observed result | Scope |
|---|---|---|
| Local complete API suite, real PostgreSQL/browser required | **PASS:** 1506 passed, 4 skipped in 1026.84s (0:17:06) | One fresh serial C1 run; skip details below |
| I4 browser inside C1 | **PASS:** one API fixture runs six successful Playwright cases (three phases × desktop/mobile) | Closed registry, enabled fixture and module off; FAKE people/provider over actual loopback OIDC/PKCE, API and PostgreSQL |
| Browser accessibility/layout assertions | **PASS:** existing axe/overflow assertions passed, zero violations in asserted states | 20 axe and 8 overflow calls per viewport; no real screen reader claim |
| Ruff check/format, mypy | **PASS**, exit 0 each | `src tests`; exact commands below, 264 files for format/mypy |
| Web typecheck/lint/format/unit/build | **PASS**, exit 0 each | 102 unit cases; 23 static pages |
| Production dependency audit | **FAIL**, exit 1: `next` (high), `source-map-js` (high) | Current npm response retained in CHECKS.json; no dependencies changed |
| CI of `c6b8e341a7e88957ee5011e54e9aa06453b31b49` | **PASS:** [run 38204334830](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38204334830), push, completed/success | Job 114664366391; 1509 passed / 1 skipped / 595.96 s; 102 web unit, 23 pages, 267 format/mypy files |
| Containers in that CI | **PASS:** production image built and pytest passed with GBA_REQUIRE_CONTAINER=1 | Local container checks were skipped; these are separate scopes |
| Exact-SHA CI of the final local documentation commit | **NOT TESTED** | New branch remains local; source CI above is not relabelled as acceptance-commit CI |
| Disposable cluster shutdown | **PASS** | Own data directory and port checked before pg_ctl stop; no other cluster touched |

CI was read from the public run/jobs REST endpoints, then the actual job log was
retrieved through the GitHub connector. [CI_EVIDENCE.json](CI_EVIDENCE.json) retains
the run/commit identifiers and log excerpts. This fresh read supersedes the old
handoff's missing CI result. The optional tenant-site skip is not a Booking
product requirement, as required by AGENTS.md and the current master plan.

The full run started at `2026-10-12T04:57:03.344860+00:00` and the complete verification
sequence finished at `2026-10-12T05:14:42.913649+00:00` (UTC). Python 3.14.6, Node
24.18.0, npm 11.16.0, PostgreSQL 18.6; Python package versions are in CHECKS.json.
The web export was built before C1 and was not rebuilt while C1 ran.

## Matrix I-01–I-12

Each row comes from cases actually executed in C1, extracted from its JUnit
report, not from historical validation records or collection. Selections and
every selected node/status are in [CHECKS.json](CHECKS.json). Rows overlap; their
counts must not be added. File-wide selections include additional checks beyond
the short description. A PASS applies to these tested cases, not untested paths.

| Row | Tested scenario | Exact command and observed count | Result |
|---|---|---|---|
| I-01 | Atomic shift/assignment/occupancy and rollback of head, version, audit and receipt; conflicting swap rolls back both sides | C1; 3 passed cases | **PASS** |
| I-02 | Two cross-branch managers assign overlapping shifts: one success, one typed conflict; API and direct SQL, observed pg_locks wait | C1; 2 passed cases | **PASS** |
| I-03 | Missing, future and revoked skills refuse assignment/replacement in API and SQL | C1; 10 passed cases | **PASS** |
| I-04 | Handover/swap/pickup require consent then manager approval, apply atomically and reject stale facts/terminal transitions | C1; 10 passed cases | **PASS** |
| I-05 | Pickup/withdraw/manual reassignment/opposite swap races, API and SQL; actual waits and one order without deadlock | C1; 10 passed cases | **PASS** |
| I-06 | Immutable shift/assignment/change history, recorded cancellation, allocations released without deletion | C1; 15 passed cases | **PASS** |
| I-07 | Three corrections retain the complete authored/reasoned chain and latest approved version; later pending/declined versions keep its interval/mark | C1; 6 passed cases | **PASS** |
| I-08 | Clock-in/correction/approval races, repeat receipts, one stable-user entry and non-overlapping effective intervals | C1; 23 passed cases | **PASS** |
| I-09 | Role, branch, tenant, delegate/support and own-approval boundaries; visibility and participant-only request-shift read | C1; 21 passed cases | **PASS** |
| I-10 | Direct SQL invariants and damaged schema/policies/functions refusing routes with 503 | C1; 152 passed cases | **PASS** |
| I-11 | Closed readiness/module-off history and own closure; staff-kind isolation, booking/reservation/CORE-04 regressions and upgrades | C1; 146 passed cases | **PASS** |
| I-12 | Fresh desktop/mobile browser, recovery, axe/overflow, full/static/web checks and exact-source CI; independent re-review of fixes pending | C1; 20 passed cases | **BLOCKED** |

The race bodies were read: I-02, I-05, I-08 and recovery tests require observed
waiters in `pg_locks`; recovery matches the top-level transaction holding that
key's receipt. SQL boundary checks exercise the restricted runtime role;
immutability checks also exercise the owner role. Trusted
application context (`gba.user_id`) remains a documented SQL trust boundary,
not direct SQL-client authentication.

## Commands

The commands below are the actual child commands of the private local wrapper.
`C1` is the command referenced in every matrix row. The wrapper invocation was:

```powershell
& 'C:/Users/alexa/.codex/worktrees/package-g-ledger-review/Gorgona Booking/api/.venv/Scripts/python.exe' 'C:/Users/alexa/AppData/Local/GorgonaBookingTests/i-acceptance-20261012-c6b8e34/run_acceptance.py'
```

For API commands it supplied PYTHONPATH=<checkout>/api/src;<checkout>/api,
PYTHONDONTWRITEBYTECODE=1, GBA_REQUIRE_POSTGRES=1 and GBA_REQUIRE_BROWSER=1;
GBA_TEST_ADMIN_DSN was generated in memory and never printed or saved in Git.
Node 24 was first in PATH. Local container-required flags were not set. The
machine's MSIX filesystem redirects LocalAppData to its private LocalCache;
CHECKS.json records the actual resolved artifact paths.

| ID | Working directory under checkout | Exact command | Result |
|---|---|---|---|
| web-build | `web` | `"C:\Program Files\nodejs\npm.cmd" run build` | **PASS**, exit 0; 7.57 s |
| C1 | `api` | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m pytest -p no:cacheprovider --basetemp C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i-acceptance-20261012-c6b8e34\pytest-tmp-full -q -ra --tb=short --capture=tee-sys --junitxml=C:\Users\alexa\AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\GorgonaBookingTests\i-acceptance-20261012-c6b8e34\pytest-full.xml` | **PASS**, exit 0; 1028.45 s |
| ruff-check | `api` | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m ruff check src tests` | **PASS**, exit 0; 0.18 s |
| ruff-format | `api` | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m ruff format --check src tests` | **PASS**, exit 0; 0.15 s |
| mypy | `api` | `"C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe" -m mypy src tests` | **PASS**, exit 0; 1.45 s |
| web-typecheck | `web` | `"C:\Program Files\nodejs\npm.cmd" run typecheck` | **PASS**, exit 0; 1.76 s |
| web-lint | `web` | `"C:\Program Files\nodejs\npm.cmd" run lint` | **PASS**, exit 0; 11.78 s |
| web-format | `web` | `"C:\Program Files\nodejs\npm.cmd" run format:check` | **PASS**, exit 0; 2.25 s |
| web-unit | `web` | `"C:\Program Files\nodejs\npm.cmd" run test:unit` | **PASS**, exit 0; 2.19 s |
| web-audit | `web` | `"C:\Program Files\nodejs\npm.cmd" audit --omit=dev --json` | **FAIL**, exit 1; 1.52 s |

Source proof command: the same Python executable ran
`C:/Users/alexa/AppData/Local/GorgonaBookingTests/i-acceptance-20261012-c6b8e34/check_sources.py`.
It hashed bytes from `git show HEAD:<path>` for the 16 author-response rows and
checked the code-only diff; **PASS: 16/16, zero code changes**. Blob hashing
avoids confusing checkout CRLF with source changes.

The wrapper created a new SCRAM/checksummed UTF-8 cluster with `initdb`, then
`pg_ctl start -D <own data> -l <own log> -w -o "-p <free port> -c max_connections=400 -c listen_addresses=127.0.0.1"`.
Exact arguments/port and exit codes are in CHECKS.json; password-file contents
are excluded. The password file was removed immediately after initdb.
An initial bootstrap wrapper stalled after successful pg_ctl startup on an
inherited Windows pipe. Before tests, its own process/server were stopped after
directory/port verification. The wrapper was changed to use a file handle for
pg_ctl output and a fresh data-retry directory. No product source was changed;
the retained bootstrap-first-attempt.json is outside Git. Only the second,
complete run supplies C1 evidence.

## Review boundary and owner decisions

The [original independent review](../2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW.md)
covers `a806380`; the [author response](../2026-10-11-i4-shift-visibility/AUTHOR_RESPONSE.md)
records fourteen fixes in `b66eb41` and two documented choices. Fresh regression
tests pass here, including all cases of test_workforce_review_fixes.py. This is
independent re-execution of tests, not a second independent source review. A
hash match proves which code was checked, not its correctness. I-12 therefore
does not inherit an unqualified independent-review PASS for the corrected tree.

Owner decisions remain:

1. Explicit approval of the working package I plan and Proposed ADR-0025.
2. Package acceptance and any WORK-01 readiness promotion in a separate commit;
   no promotion is authorized by this preparation request.
3. CORE-04's F acceptance versus `planned` code registry discrepancy.
4. PR creation/publication and the order of the unmerged branch stack; the
   2026-10-11 permission covers I4 only, not this acceptance branch.
5. Company-wide default for shift visibility (currently per branch; new branches
   start visible), and retaining the API refusal of new swaps while hidden.
6. F4: cancelled-key protection lasts while its receipt lives (24 hours), not
   forever. N5: colleague reads limit each request to 62 days but allow arbitrary
   past/future dates. Also the role exposed in the branch-manager directory.

## NOT TESTED and deployment boundaries

Local skips (not PASS):

- `tests/container/test_container_image.py::test_migration_job_is_explicit_and_idempotent`: BLOCKED: container verification requires GBA_REQUIRE_CONTAINER=1.
- `tests/container/test_container_image.py::test_image_runs_non_root_without_baked_secrets`: BLOCKED: container verification requires GBA_REQUIRE_CONTAINER=1.
- `tests/container/test_container_image.py::test_api_container_serves_health_web_and_a_real_booking`: BLOCKED: container verification requires GBA_REQUIRE_CONTAINER=1.
- `tests/integration/test_tenant_site_embedding.py::test_tenant_site_embeds_the_real_wizard`: BLOCKED: tenant-site verification requires GBA_REQUIRE_TENANT_SITE=1.

In the workforce browser runs, four other specs per phase are filtered by phase;
all six intended phase/viewport cases execute across the three invocations.

Not newly exercised: an actual screen reader; the browser's effective-version
outside-schedule mark, adding a company-wide member without a home profile,
lost response to changing Privacy, 5xx/unreadable saved record, and lists beyond
one page (including >20 versions/requests and paged locations); a clock change
inside a shift in the browser. These are not relabelled PASS by broader tests.
The corresponding API/contract cases may pass without proving the browser path.

Second independent source review of the fixes, HawkScan, load/soak, deployment,
production, Azure/provider/real-money actions remain **NOT TESTED**. Local
container skips remain NOT TESTED even though exact-source CI container checks
passed. The external tenant website remains separate, optional and untested.
The dependency audit FAIL is an open inherited production/security boundary.

## Documentation change and completion checks

Only documentation/evidence changed: this ACCEPTANCE.md, CHECKS.json,
SOURCE_SHA256.json, CI_EVIDENCE.json, PACKAGE_I_PLAN_2026-10-09.md,
GORGONA_IMPLEMENTATION_STATUS.md, CLOUD_CODE_HANDOFF.md and
NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md. Migrations 0001–0035, dependency
locks, source, tests and readiness/module code are unchanged. No CodeRabbit.

Final documentation validation ran through the same Python executable and the
private `validate_docs.py` helper: **PASS: 8 UTF-8 files, 5 Markdown files,
3 JSON files, 166 existing local link targets, 12 matching matrix rows and
16 matching source hashes; `git diff --check` exit 0; zero runtime changes.**
The changed-file set is exactly the eight named files. Limited plaintext DSN/key
pattern checks found zero matches; this is not a full security audit. Both owned
cluster PID files are absent. The complete documentation diff was inspected,
and the validator is rerun after final documentation edits and after commit.
The final documentation commit's SHA is read from Git; it cannot self-reference.
