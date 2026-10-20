# K5b — open K5a review findings and manual editor dates: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-k5b-open-findings`, parent
`1b89958` (the owner's decision to postpone K0c), source commit
`58cf561d0f2d065ad44dac850182fdd61d3fae20`. [CHECKS.json](CHECKS.json) was written before the source
commit; it binds every source blob, the exact commands, exit codes and log digests of every phase,
including the failures below. Nothing is published; no real provider event, key, account or
readiness change is involved.

Naming: this slice is "K5b (open findings)". The K5 plan's step 5, exact-head CI and the evidence
record, keeps its role under the name **K5-CI**.

## Owner decision

2026-10-20: no Stripe registration for now, so K0c was postponed and FIN-02 stays `planned`; the
open findings of the [K5a review](../2026-10-19-k5a-review/REVIEW.md) that need no provider and the
UTC default of the manual financial editors are fixed locally with the same process.

## What changed

| Finding | Change |
|---|---|
| 6 | 0059 (K): index `provider_event_inbox_connection` on `(tenant_id, connection_id)` for the operation list, state reads and link check; the receipt guard approves it |
| 9 (IR-03) | 0059: the runtime loses INSERT on `provider_event_inbox` and `provider_event_deliveries`; only the receipt writer records them (the runtime still reads); guard updated |
| 8 | 0060 (H): `provider_payment_links_require_workflow` (`gba.require_financial_workflow`: ledger lock, finance, counterparties and finance_documents enabled, else `GBM01`); before, only the Python route checked the modules |
| 15 | 0060: `enforce_provider_payment_link` is the 0056 body with `pg_catalog.abs`; no other `gba` function calls an unqualified `abs` |
| 12 | The Stripe decoder takes a charge's amount from `amount_captured` (strict, required), never the authorized `amount`; a partial capture now agrees with its PaymentIntent and applies the captured amount |
| Dates | Invoice, issue, credit, credit void, payment and correction editors default to today in the business time zone (empty while the zone is unknown), never the UTC date |

Tests that archived receipts through the runtime pool now use the receipt-writer pool (its fixture
moved to `test_provider_event_inbox` and is re-exported); runtime-only actions stay on the runtime.

## Gates

| Gate | Exact observed outcome |
|---|---|
| New cases | 6 (`test_k5b_open_findings` 5, `test_provider_review_fixes_upgrade` 1) plus the new unit case for finding 12 and the date checks in the H4 browser test |
| Final focused (44 files) | PASS: 775 passed in 841.46s (0:14:01) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2315 passed, 4 skipped in 2410.31s (0:40:10) |
| Ruff, format, strict mypy, web typecheck, lint, format, unit, build | PASS |
| Runtime npm audit | PASS: 0 |
| Upgrade 0058 → 0060 on a nonempty database | PASS: every row unchanged; index, grants and trigger present |

## Failures kept in the record

1. **red-1, product RED.** On `1b89958` with the new tests: 7 failed, 96 passed, each for its finding:
   unit 1000 instead of 600; index missing; the SQL link with finance off was not refused; the
   runtime still had column INSERT; the partial capture was a conflict (409 `needs_review`); an
   unqualified `abs`; the H4 browser showed `2026-10-20` (UTC) instead of `2026-10-19` (New York).
2. **dev-1, test defect.** 3 failed, 443 passed: the inbox snapshot test counted journal entries
   inside the writer's transaction; the writer correctly cannot read journals. The runtime counts
   them now.
3. **dev-2.** 775 passed (all 44 focused files).

## Limits and what is next

- Finding 15: only the unqualified `abs` is fixed; the ISK/UGX scale and currencies missing from
  `gba.currencies` remain recorded limits while only USD is admitted.
- Finding 6: the plan uses the index (EXPLAIN with sequential scans off); no timing at production volume.
- K0c (real Stripe test run) resumed after this slice: see the [handoff](../../NEXT_AGENT_PACKAGE_K5B_2026-10-20.md).
- Not published: the new branch needs the owner's word. FIN-02 and STOCK-01 stay `planned`.
