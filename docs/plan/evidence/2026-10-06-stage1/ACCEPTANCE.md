# GORGONA stage 1 — common business foundation: technical closure, 2026-10-06

Branch `claude/stage1-closure` on top of package F (`ed7884e`, draft PR #11).
Disposable PostgreSQL 18.6 cluster 127.0.0.1:51455 only; no production action.

**Gate: stage 1 technically complete within its stated limits.** Master plan §13
requires CORE-01–04 and that a small business, a network and a hybrid company pass
scenarios without duplication or data leakage. Every criterion below has passing
tests and exact-SHA CI; the three company scenarios now run end to end through all
stage 1 modules in one test file. This is a technical PASS only: no industry pilot,
production approval or migration is implied (§14.1.1: only a technical PASS admits
the next technical stage).

## Criteria

| ID | Status | Evidence (exact acceptance) | Limits that stay open |
|---|---|---|---|
| CORE-01 | PASS | 39 stable IDs, 20 NAICS sectors, several profiles per business, `business_id == tenant_id == salon_id` ([plan audit](../../GORGONA_PLAN_AUDIT_2026-10-04.md)); `tests/unit/test_business_profiles.py` | Selecting a profile enables no industry workflow |
| CORE-02 | PASS | Profiles and configuration publication `5320c4a` ([evidence](../2026-10-04-configuration/ACCEPTANCE.md)); one-winner races for counterparties, documents, contracts, reservations (E1–F evidence) | Custom fields and configurable processes are planned |
| CORE-03 | PASS for existing modules | Legal entities `d97924f`, departments `5b3c00b`, delegation `ed370c6`, groups `6a81dfd` ([groups](../2026-10-04-groups/ACCEPTANCE.md)) | Dispatcher authority and offline drafts arrive with TMS (stage 3, TMS-02) |
| CORE-04 | PASS | Shared occupancy and staff reservations `bf3645d`/`ed7884e` ([evidence](../2026-10-05-occupancy/ACCEPTANCE.md)) | Capacity above 1 and rentals deferred by owner decision |

Modules delivered in stage 1: profiles, configuration and module registry, legal
entity drafts, branches, departments, roles, delegation, groups, counterparties with
contacts and matching (E1), documents and files (E2), contracts (E3), shared
occupancy with staff reservations (F).

## Company scenarios (new, `api/tests/integration/test_stage1_scenarios.py`)

| Scenario | What is proven |
|---|---|
| Small business (one profile) | One card is customer and supplier; its booking link, document, agreed contract and the e-mail match check all point to the same record; a reservation over the booked slot is refused (one occupancy table); audit details and idempotency receipts contain no e-mail, titles or file names |
| Network of independent companies | A group and an active delegation connect two companies; the other company's owner gets 403 on every counterparty, document, file, contract and reservation route of the first; its own lists and stage 1 tables contain only its own rows; no foreign occupancy row is visible |
| Hybrid company (three profiles, two branches) | One counterparty list across profiles; a branch-limited manager reserves only in the own branch, cannot see other-branch reservations (404) nor company-wide records (403); a branch SQL session sees none of the nine company-wide tables and only its own occupancy; bookings and reservations of both branches share one occupancy table |

## Results

| Check | Exact observed outcome |
|---|---|
| Contracts in-flight notice (red) | Expected FAIL: the "result uncertain" notice was visible while the save request was still in flight (`toHaveCount(0)` timed out) |
| Same check after fix (`7d93cf0`) | PASS: contracts, documents and counterparty browser harnesses 3 passed / 33.62 s |
| Stage 1 scenarios | PASS: 3 scenarios plus booking concurrency, 11 passed / 25.33 s |
| First full suite on this branch | FAIL 5 / 782 passed: environment only — after a reboot the restarted cluster had `max_connections = 100`, and `test_booking_concurrency.py` opens about 100 connections (`remaining connection slots are reserved`). Restarted with `max_connections = 400`; the same tests passed |
| Final full local suite | PASS: **790 passed / 4 skipped / 303.39 s**, exit 0; PostgreSQL and browsers mandatory; skips: 3 Docker gates (required in CI) and the external tenant-site gate |
| Web | PASS: typecheck, ESLint, Prettier, 63 unit tests, 17-page export |
| Python static | PASS: Ruff format/check, strict mypy, 186 files |

## Still open after stage 1 (not regressions)

- Production migrations 0015–0019 and the per-company `backfill-occupancy`:
  NOT TESTED outside disposable databases; need the owner's explicit authorization.
- No malware scanner: file uploads stay refused in staging/production.
- Author columns (`created_by`, `decided_by`, `uploaded_by`) are not checked against
  membership in SQL (E1–F); the API always sets them from the authenticated user.
- Azure, providers, load (OPS-02), restore, pilots and manual screen-reader
  acceptance: NOT TESTED.

Next technical stage per §13: stage 2 (finance, workforce and basic material
operations: FIN-01–03, STOCK-01, WORK-01) — plan and ADR first, code only after the
owner's decisions.
