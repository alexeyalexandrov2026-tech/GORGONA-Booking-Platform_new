# K4a finance screen for provider operations — local validation

**PASS for this bounded local slice.** Branch `codex/package-k4a-provider-screen`, parent
`c1ff170`, source commit `374f60c2adb04060bd69c526dbf14b687c52698c`. [CHECKS.json](CHECKS.json)
was generated before the source commit and binds source blobs, commands, exit codes and log
digests. Not published. Design: [K4a](../../PACKAGE_K4A_DESIGN_2026-10-18.md). Executor: Claude,
inline, after the owner's decisions of 2026-10-18: applying starts from the reserved settlement;
the clearing account is registered in the screen after a confirmation step; a later conflict
shows a marker and a manual review instruction (detail in K4b).

## What changed

- `business/provider_payments.py`, `business/settlement_contracts.py`,
  `api/financial_documents.py`: the operation state is computed in SQL over the named facts, so
  `GET …/provider-operations?state=` is complete across cursor pages; new state `revoked` (not
  applied, connection or verification config revoked); new `GET …/provider-connections` (cursor;
  connection id, `acct_…` id, revoked flag, clearing account; never a key, secret reference or
  verification config)
- `web/lib/financial-contracts.ts`: strict schemas for both lists and the clearing account (a
  state must match its payment and amount; a payment is `pi_…` without parent, a refund `re_…`
  with one), the command `settlement_provider_confirm` (no amount, date, account or attestation)
  and closed routes; `financial-recovery.ts` recovers it as `settlement_confirm`, the receipt the
  server records; `financial-api.ts` calls (20-row pages); `management-api.ts` keeps the server's
  refusal details
- `web/components/provider-operations.tsx` (new): the "Provider operations" tab (connections,
  clearing account form with a confirmation checkbox, state filter, "Load more", conflict marker
  and instruction) and the apply form opened from a reserved settlement (fitting `observed`
  operations only, amount read-only, allocations must add up); every K3a refusal in plain words
  with its code
- `web/components/financial-workspace.tsx`: the tab, the "Apply provider operation" button, the
  provider form draft kept while the book reloads, and the obligations table scroll area as a
  named keyboard-focusable region
- Tests: `test_provider_screen.py` (new, 9), `test_k4a_browser.py` (new, desktop and mobile with
  `web/tests/provider-operations.spec.ts` and the npm script `test:management:provider`), 4 web
  contract cases

No migration (0001–0052 unchanged, next 0053), dependency, provider call, worker entry point,
readiness or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| U-01 | Every operation through the cursor; server-side state filter complete across pages | `test_the_state_filter_lists_every_matching_operation_across_pages`, `test_an_unknown_state_filter_is_refused`; browser: 28 rows over two pages, 22 `not_final` over two pages | PASS |
| U-02 | No "paid", "verified" or "payout" label; non-applicable states explain and offer no action | `test_a_revoked_connection_lists_its_operations_as_revoked`; browser list text and no buttons in rows; contract case | PASS |
| U-03 | Only fitting observed operations; amount read-only; allocations must add up | browser: apply form, no amount field, mismatch refused before sending; contract case for the command | PASS |
| U-04 | Applying shows the confirmation and the operation as applied; one payment | browser: settlement confirmed, operation `Applied … payment …`; database: one provenance row each | PASS |
| U-05 | Refusals in plain words, input kept, no false success | browser: `PROVIDER_PAYMENT_LINK_REQUIRED` message, allocation kept; database: no provenance for it | PASS |
| U-06 | Lost response blocks mutations; retry with the same key; no second payment | browser: response aborted after the server committed, recovery shown, retry recorded; database: 6 payments in the book | PASS |
| U-07 | Missing clearing account shown; registration needs confirmation; once | `test_connections_show_the_clearing_account_and_no_secret`; browser registration per project; database account; K3a `test_the_clearing_account_is_registered_once_and_is_never_a_control` | PASS |
| U-08 | Conflict marker with the manual review instruction; no action | browser: `applied_with_conflict` filter, marker, no buttons | PASS |
| U-09 | Finance rights; foreign company; no secret in the connection read | `test_provider_screen_reads_keep_company_finance_permissions` ×4, `test_another_company_cannot_read_the_connections`, secret checks | PASS |
| U-10 | Real desktop and mobile, axe zero violations, no side scroll | `test_k4a_real_browser_provider_operations` (2 Playwright projects; axe on the list, registration, conflict view, form, mismatch, recovery and refusal) | PASS |
| U-11 | Existing finance browser, web contracts, static and full suite | focused-1, full-1, static-1 (web unit 118 passed) | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 352 passed in 419.21s (0:06:59) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2192 passed, 4 skipped in 1782.61s (0:29:42); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 327 source files |
| Web typecheck, lint, format, unit (118 passed), build | PASS |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop; no `postmaster.pid` left |
| K CI | NOT TESTED (not published) |

New cases 10 (plus 4 web contract cases), regression cases 342 (see CHECKS.json).

## Failures kept in the record

- **red-1, product RED** on `c1ff170`: 8 failed, 1 passed (no `provider-connections` route, no
  state filter; the foreign-company case already passed through a 404). Web contract spec: 4
  failed, 22 passed (no provider schemas or command).
- **dev-2, test defect and product defect**: the browser case failed on both projects. Desktop: a
  `status` locator matched three elements. Mobile: axe `scrollable-region-focusable` on the
  existing obligations table, which overflows a phone once more rows exist. Both fixed.
- **dev-3, product defect against U-05**: after a refusal the workspace reloads the book and the
  apply form came back empty. The workspace now keeps the provider form draft per settlement and
  sequence. dev-4: browser passed; dev-5: 105 passed.

## Limits

The conflict marker does not yet say which delivery disagrees; recovery views, redacted metrics
and the runbook are K4b. The manual H payment form still loses its input when a refusal reloads
the book (existing behaviour, not changed here). The state filter computes each operation's
state; no index for it yet. Linking earlier manual payments (K3b), provider retrieval (K2b, needs
K0), fees, payouts, other currencies, a worker entry point and deployment remain open. FIN-02
planned; ADR-0027 Proposed.
