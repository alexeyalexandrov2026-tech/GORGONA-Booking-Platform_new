# Draft pull request text — H2

Not opened yet when this file was written (2026-10-07). Source branch
`codex/package-h2-settlements`, target `codex/package-h1-persistence`, created
as a draft. Do not merge it and do not enable auto-merge.

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

## Evidence (local, before publication)

- Full suite on `54852b4`: **1041 passed, 4 skipped** (three container tests, one optional tenant-site test), mandatory real PostgreSQL 18.6 and OIDC/Chromium.
- Ruff, format and strict mypy clean on 211 files.
- Web typecheck, lint, format, 69 unit tests and build passed on the slice C tree; no web source changed afterwards.
- Races (70-of-100 reserve in both orders, concurrent partial confirmations, confirm/release/reserve) wait for observed `pg_locks` blockers; no sleep-only claims.
- One test writes confirmations by SQL alone: an exact one commits; an over-reserve amount, unequal allocations, a repeated identity and deletes are rejected.

Exact commands, per-slice numbers, red runs and failed attempts: `docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md`. Handoff: `docs/plan/NEXT_AGENT_H2_2026-10-07.md`.

## Not tested / not done

- Exact-head CI and the three Docker gates had not run before publication; read them on this pull request.
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

🤖 Generated with [Claude Code](https://claude.com/claude-code)
~~~
