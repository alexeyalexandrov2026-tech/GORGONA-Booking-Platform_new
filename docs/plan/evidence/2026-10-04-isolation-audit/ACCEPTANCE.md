# GORGONA E0 — independent isolation audit, 2026-10-04

Code commit: 4ad645fc27a2334f55e5c7c47ee1e3de8eede3a5, branch
codex/package-e-isolation-audit, [draft PR #6](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/6)
into codex/universal-business-foundation. Base: 2f1638011987e06923468b64600de1d1f4a14020.
The 14 E0 files match the owner's supplied snapshot byte-for-byte. The owner
checkout and its 19 dirty/untracked paths were preserved. No migration is added.

A manager in several businesses now reads the booking state and owner fact of
the authorized business. A platform operator's ownership elsewhere cannot satisfy
go-live. Related membership/host/tenant lookups carry explicit business predicates
without changing the intentional discovery policies. Web readiness accepts the
real items response and validates its states; the three save functions return
the typed Readiness contract.

## Direct evidence

| Check | Exact observed outcome |
|---|---|
| Clean-base local suite | PASS: 527 passed, 4 skipped, 188.66 s, exit 0 on 2f16380; PostgreSQL18.6 and browsers required |
| Regression before fixes | Expected FAIL, exit 1: 7 failed / 4 passed, 4.08 s; 6 behavioral failures and 1 conservative SQL-scan failure with 15 findings. Two defensive integration cases and two scanner checks were already green, not reproduced exploits |
| Web regression before fix | Expected FAIL: 1 failed, exit 1, Unrecognized management response contract for GET readiness |
| Focused after fixes | PASS: 30 passed, 10.04 s, exit 0; cross-company API, invitations, onboarding and SQL scanner |
| Full final local suite | PASS: 538 passed, 4 skipped, 193.26 s, exit 0, mandatory PostgreSQL18.6 and browser harnesses |
| Web | PASS: typecheck, ESLint, Prettier, 42 unit tests / 986 ms, 14-page build; no UI layout changes |
| Python static | PASS: Ruff format/check, strict mypy 153 files, exit 0 |
| Published code push CI | PASS: [run37260931380](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37260931380), job111607810225 on the exact code SHA; 541 passed, 1 skipped, 104.95 s; web42/852 ms, mypy153; container gates executed |
| Published code PR CI | PASS: [run37260950208](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37260950208), job111607867761 on the same code SHA; 541 passed, 1 skipped, 111.70 s; web42/1.2 s, mypy153; all steps succeeded |
| Diff / snapshot | PASS: git diff --check exit 0; all 14 E0 file bytes equal the supplied owner copy |

Local skips are three container gates without Docker and the optional external
tenant-site gate. A skip is not PASS. The full suite includes actual browser flows
through test-only OIDC/PKCE, HTTP and PostgreSQL, including branch, delegation,
groups and configuration with desktop/mobile automated accessibility checks.
The E0 readiness-boundary regression is an API/contract check, not a newly added UI
editor or a full manual WCAG, screen-reader, localization or RTL certification.

## Audit and source boundaries

Permissive RLS policy alternatives combine with OR; a company-specific lookup
on a discovery-readable table still needs its authorized company predicate.
Reference: [PostgreSQL18 row-security documentation](https://www.postgresql.org/docs/18/ddl-rowsecurity.html),
consulted 2026-10-04. This fix reuses the existing authorization and transaction
context. The static scanner is a conservative linter, not a SQL parser or a
runtime security boundary; direct PostgreSQL/API regression remains the evidence.

Review in this run was performed by the implementing agent. The independent
Agent Teams reviewer examined the separate existing load tool; it did not review
E0. Code Tytor review was attempted but blocked by reauthentication. Source
review reported in the supplied Package E handoff is prior evidence, not a new
independent review. CodeRabbit skips draft PR review.

## Remaining readiness

- Load tool is unchanged and reproduced false PASS with both confirmations 422,
  accepts invalid inputs, mixes phase windows and can select overlapping slots.
  Fix it before using results for OPS-02. Scale/latency targets are NOT TESTED.
- Full npm audit FAIL: 5 high development findings in one braces chain; production
  audit PASS with zero findings. Official patched version is currently None:
  [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
  No dependency downgrade, suppression or new package was applied.
- Azure read-only audit: staging environment Failed, no Container App; PostgreSQL18
  Ready/private, Key Vault private with RBAC/purge protection. Last failed creation
  on 2026-10-01 reports ManagedEnvironmentCapacityHeavyUsageError. No cloud changes,
  secrets retrieval, capacity retry or end-to-end Azure acceptance were performed.
- E1–E3, real providers/IdP, antivirus, industry pilots, load, restore and production
  remain unverified. The original Package E archive and complete context capsule
  are preserved under the owner's Desktop/handoff777 directory.
