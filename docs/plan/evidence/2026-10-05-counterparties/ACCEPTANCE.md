# GORGONA E1 — counterparties, contacts and matching, 2026-10-05

Implementation branch: `codex/package-e1-counterparties`, based on
`bbe6ecd80d8827ca94a63f15587704ffc22dba62` (Package E0). The separate draft PR
targets `codex/package-e-isolation-audit`; E0 PR #6 is not merged. The owner
checkout is preserved. Code SHA and exact CI results are recorded after publication.

**Current gate: IMPLEMENTED; CI pending.** The real registry refuses publication
of `counterparties` with `MODULE_NOT_READY`. Test-only registry overrides allow
the real draft → validate → publish workflow, not simulated module state. A
separate acceptance commit may promote readiness only after green code CI.

## Implemented boundary

Migration `0015_counterparties.sql` adds five FORCE-RLS tables: immutable
identities, append-only card versions and contacts, duplicate decisions and
manual booking-link events. API and web contracts have schema version 1; command
receipts contain references only. Permission map version 4 gives company-wide
owners/managers counterparty access. Branch-limited members, delegates, platform
support, front desk, artists and other businesses cannot access this module.

Matching suggests normalized identifiers; names are weak evidence and never
merge automatically. Merge, distinct and separation decisions are explicit.
Merge moves no source records; current relationships have their own endpoint,
so historical views and idempotent replies remain immutable. The database couples
each merge/separation to one exact card revision in the same transaction and
rejects staged cycles/chains and multiple decisions for the same revision.
Booking links require a current matching basis and manual confirmation;
`booking_customers` snapshots stay unchanged.

All five tables check enabled module state under the publication lock. Reads,
history and command replay remain available when disabled; new writes fail.
Readiness and company-wide handlers check 34 access definitions, the booking
gate and five optional-module gates, including exact arguments and function
metadata. Gate functions must be VOLATILE: a query after waiting for a publication
lock needs a fresh snapshot, as described by the consulted
[PostgreSQL 18 function-volatility documentation](https://www.postgresql.org/docs/18/xfunc-volatility.html).

## Direct evidence

| Check | Exact observed outcome |
|---|---|
| Fresh unchanged E0 baseline | PASS: 538 passed, 4 skipped, 219.17 s, exit 0; mandatory PostgreSQL 18.6 and browsers |
| Missing E1 API regression | Expected FAIL: 6 failed, 4.90 s, exit 1 (missing routes); then 6 passed, 4.99 s, exit 0 |
| Focused cards/configuration/location suite | PASS: 70 passed, 37.64 s, exit 0 |
| Staged SQL merge cycle/chain regression | Expected FAIL: 2 failed, 3.87 s; after fix 2 passed, 2.27 s, exit 0 |
| Gate volatility mutation | Expected FAIL: 2 failed, 2.01 s; after guard fix 2 passed, 1.98 s, exit 0 |
| Duplicate decisions for one revision | Expected FAIL: 1 failed, 2.68 s; after fix, decision/group cases 2 passed, 2.27 s, exit 0 |
| New contract unit tests | PASS: 21 passed, 0.21 s, exit 0 |
| Real desktop/mobile browser harness | PASS: 1 pytest harness, 13.78 s; 2 Playwright scenarios, 10.2 s; real HTTP/PostgreSQL and test-only OIDC/PKCE |
| Full E1 local suite | PASS: 595 passed, 4 skipped, 248.75 s, exit 0; fresh export and mandatory PostgreSQL/browser; before adding the final readiness-refusal test |
| Real readiness refusal without registry override | PASS: 1 passed, 1.89 s, exit 0; validates `MODULE_NOT_READY`, refused publication and disabled writes |
| Web | PASS: typecheck, ESLint, Prettier, 47 unit tests (1.2 s), 15-page production export; all exit 0 |
| Python static after final test addition | PASS: Ruff format/check, 163 files; strict mypy 163 files; exit 0 |
| Published code CI | NOT TESTED yet: publication pending; no local container PASS claimed |

The full browser suite includes retry with the same key after a lost response,
revision conflicts requiring reload, merge/separate, confirmed link/unlink,
history, module-disable reads, mobile overflow and keyboard focus. Axe reported
zero violations in the checked page states. This is automated accessibility
evidence, not a complete manual screen-reader/WCAG certification.

Local skips: three container tests (Docker unavailable) and one optional external
tenant-site test. PostgreSQL and browser tests were required, not skipped.
Container gates must execute in CI on the exact published SHA.

An extra readiness test first had an incorrect expected HTTP status (409 instead
of the existing 422 `CONFIGURATION_STATE_INVALID`); only the test assertion was
corrected. That failure is not evidence of a product defect.

## Independent review

The separate `counterparty_security_review` agent reviewed source without modifying
this checkout or using the shared database. Its findings led to immutable replay,
decision/version coupling, fresh merge-target details, graph, volatility and unique
decision fixes with executor regressions above. Final bounded recheck found no
remaining grounded high-risk issue in the reviewed source. Reviewer checks:
synthetic replay, guard parameter consistency, permission assertions, parsing and
diff whitespace. PostgreSQL execution, concurrency and browser evidence belong
to the executor, not the reviewer.

Reviewed migration SHA256:
`E7185458B201D9B57BA7534303DEBF25BE859154E22E761E681791A8F7C7CBD2`.

## Remaining boundaries

- E2 documents/files and E3 contracts remain planned. No file scanner, uploads,
  signatures, consents, retention/erasure, import or provider integration is claimed.
- Stage 1 remains partial; CORE-04 shared occupancy and all full industry cycles
  remain planned. The 39 industry profiles and 28 acceptance criteria are retained.
- Real IdP/providers, Azure end-to-end, load, restore/RPO/RTO, pilots and production
  are NOT TESTED. No merge, deployment, production migration or cloud change occurred.
- E0's development-dependency findings and load-harness failure are historical
  unresolved evidence, not a fresh dependency/cloud audit in E1.
- API/Python/web checks do not verify the separate AI package or production AI.
