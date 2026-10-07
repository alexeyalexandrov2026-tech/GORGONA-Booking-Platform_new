# Draft pull request text — H2

Opened once as [draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16) on2026-10-07. Source
`codex/package-h2-settlements`, target `codex/package-h1-persistence`.
Do not open another PR, merge or enable auto-merge. Original docs checkpoint
75c36da CI37573680437 PASS; successor15e8d0c CI37574622979 FAIL was diagnosed
before correcting the ledger UI.
Corrective source `15edbed1d608ada9d0901a7710c00eff28c23e71` fixes a diagnosed ledger refresh race in two web files;
financial Python/SQL and frozen migrations are unchanged from54852b4. [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793) PASS:1044 passed/1 skipped/379.86s;
all3 Docker/image, PG/browser, web69/2.3s and static211 PASS.
Fresh local full:1041 passed/4 skipped/434.68s; focused browser1/17.95s.
Bounded independent UI review PASS; full H2 money/state review remains NOT DONE.
Final documentation delivery is a successor; inspect current-head CI.

## Title

feat(finance): H2 manual accruals, settlement reserves and attested confirmations

## Description

~~~markdown
## Summary

Package H2 backend on top of the delivered H1 invoice backend (#15), behind the still-closed `finance_documents` gate. Draft: not for merge.

Three forward migrations after published `0021`; migrations `0001`–`0021` are byte-identical to the base.

- **`0022` manual accruals** — a second kind of the immutable financial document. Issue writes one new `manual`/`principal` obligation and one balanced `accrual` journal in one transaction. An existing manual G entry is not linked or accrued again.
- **`0023` settlement documents** — prepare, approve, reserve, sent, release, cancel. A reserve posts no money. `gba.obligation_balance` computes A/P/C/R from history; deferred triggers and the service both enforce `P, C, R >= 0` and `P + C + R <= A` at commit. A sent document is released only by an explicit `attested_no_payment` resolution with reason and evidence.
- **`0024` externally attested confirmations** — a partial confirmation moves exactly R → P, keeps the remainder reserved and posts one balanced `payment` journal. Allocations equal the amount exactly. The external identity (book, direction, source account alias, external reference) is unique forever and bound to one `payment_id`, independent of the idempotency key. Attestation is always `manual_attestation`; nothing claims provider verification.

Journal read schema 2 now lists `invoice`, `accrual`, `payment`; write and read schema 1 are unchanged. Generic G reversal refuses every H-owned kind in API and SQL. No dependency, lockfile or permission map change.

## Local evidence and bounded UI correction

- Full suite on `54852b4`: **1041 passed, 4 skipped** (three container tests, one optional tenant-site test), mandatory real PostgreSQL 18.6 and OIDC/Chromium.
- Ruff, format and strict mypy clean on 211 files.
- Corrective source `15edbed1d608ada9d0901a7710c00eff28c23e71`: fresh full **1041 passed/4 skipped/434.68s**, exit0;
  focused real ledger browser **1 passed/17.95s**, exit0. Web typecheck/lint/format,
  69 unit tests and build18 routes PASS; Ruff/format/strict mypy211 PASS.
- After a saved ledger command, controls now wait for the current business/book/tick refresh
  before another command or period read. Failed reads keep writes locked while Refresh allows
  retry. A held real GET deterministically failed the baseline; a delayed GET and an aborted
  GET/retry pass on desktop/mobile. No sleep, retry count or timeout increase.
- Bounded independent exact-15edbed UI source/build/browser review PASS. Full H2 financial
  Python/SQL/money/state review remains NOT DONE.
- Races (70-of-100 reserve in both orders, concurrent partial confirmations, confirm/release/reserve) wait for observed `pg_locks` blockers; no sleep-only claims.
- One test writes confirmations by SQL alone: an exact one commits; an over-reserve amount, unequal allocations, a repeated identity and deletes are rejected.

Exact commands, per-slice numbers, red runs and failed attempts: `docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md`. Handoff: `docs/plan/NEXT_AGENT_H2_2026-10-07.md`.

## Observed publication CI

Draft PR16 targets H1 PR15. Docs checkpoint `75c36dac572c8420aa848d322717420d43555c87`:
[CI37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) completed/success, **1044 passed/1 skipped/381.36s**.
PostgreSQL18.6/OIDC/Chromium/all3 Docker/image, 69 web tests/2.3s, web
typecheck/lint/format/build, Ruff/format211 and strict mypy211 PASS. Remaining
skip is the optional separate tenant-site integration.

Subsequent15e8d0c [CI37574622979](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37574622979)
FAIL:1 failed/1043 passed/1 skipped/392.04s. Ledger period read raced the
post-command book refresh; the next browser case received a cascading closed-month409.
Diagnosed/reported before the two-file source correction15edbed.
Its [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793) PASS:1044 passed/1 skipped/379.86s; PG/browser/all3 Docker/image, web69/2.3s
and static211 PASS. Financial Python/SQL stays byte-identical to54852b4;
final docs are a successor and require their own current-head CI.

## Not tested / not done
- No independent money/state review; only the author's inline review.
- HawkScan not run (no runtime or API key on the author machine).
- Slice A has no recorded red run.
- Small test gaps listed in the evidence file (foreign-key drift on H2 tables, the `opening` legacy variant, settlement recovery while OFF, delete of settlement rows).
- H3 credits, refund obligations and corrections and H4 UI and admission metadata are not implemented.

## Status

FIN-03 and FIN-02 stay `planned`; all twelve complete H acceptance rows stay NOT TESTED; ADR-0024 stays Proposed. `finance_documents` cannot be enabled through the real registry; positive H fixtures override readiness only in tests.

## Decisions for the owner or a reviewer

1. Journal read schema 2 was extended in place instead of creating schema 3 (schema 2 was never merged, deployed or enabled).
2. One authorized person may prepare and approve the same settlement; the view exposes `approved_by_preparer`.
3. A release frees the whole unconfirmed remainder; there is no partial release.
4. A structurally exact confirmation written by SQL alone commits without a command receipt or audit record, as in G and H1.

H2 backend authored with [Claude Code](https://claude.com/claude-code); publication,
ledger UI correction and evidence updated with Codex.
~~~
