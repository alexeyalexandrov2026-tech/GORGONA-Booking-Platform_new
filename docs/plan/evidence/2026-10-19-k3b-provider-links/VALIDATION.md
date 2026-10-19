# K3b links of earlier manual payments — local validation

**PASS for this bounded local slice.** Branch `codex/package-k3b-provider-links`, parent
`199eada`, source commit `8bb2eb43e16a05092065a09bee8082733737fe1f`. [CHECKS.json](CHECKS.json)
was generated before the source commit and binds source blobs (including the runbook), commands,
exit codes and log digests. Not published. Design: [K3b](../../PACKAGE_K3B_DESIGN_2026-10-19.md).
Executor: Claude, inline, after the owner's decisions of 2026-10-19: link only; amount, currency
and direction exactly equal, dates at most 3 days apart; one to one; a linked payment may still be
voided or corrected, the link stays and a void returns the operation to review.

## What changed

- `db/migrations/0054_provider_payment_links.sql` (new, H): `provider_payment_links` — one per
  manual payment, operation unique per company, success event, note, `created_by`,
  `created_transaction`; FORCE RLS with tenant isolation and company scope; runtime select and
  insert of six columns; immutable, lock and check triggers. `enforce_provider_payment_link`
  locks the ledger and the operation row and rechecks the decided operation, the book and
  connection, revocation, the amount, currency, direction, the 3-day date window, the reference
  naming the ID, and that the operation is not applied. `db/financial_guard.py` reads 0054.
- `business/provider_payments.py`: the SQL state gains `needs_link` (a manual payment of the book
  names the ID) and `linked` (link holds: not voided, same amount; otherwise `needs_review`);
  applying a linked operation is refused (`PROVIDER_OPERATION_LINKED`).
- `business/provider_review.py`: `link` (same payment and note return the link; another payment or
  note `PROVIDER_OPERATION_LINKED`; `PROVIDER_LINK_MISMATCH` with a reason); the operation detail
  lists the manual payments naming the ID and the link. Route `PUT …/provider-operations/{id}/link`.
- Web: strict contracts and route; the link form in the operation detail; the apply form never
  offers a `needs_link` operation. Runbook: two states, two codes, a link section.
- Tests: `test_provider_links.py` (new, 20); the browser harness gains a mismatching manual
  payment and a desktop/mobile link case; the K4a browser refusal step now shows a server refusal
  through `route.fulfill` (the operation it used is no longer offered); definitions 68; location and
  upgrade lists; runbook census.

Migrations 0001–0053 unchanged; next **0055**. No dependency, provider call, worker entry point,
readiness or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| L-01 | A blocked operation is `needs_link`; server filter | `test_a_blocked_operation_is_listed_as_needs_link` | PASS |
| L-02 | One link, no journal, no payment or settlement change; `linked` | `test_linking_moves_no_money_and_marks_the_operation_linked` | PASS |
| L-03 | Mismatches refuse with a reason; not observed; applied | `test_a_payment_that_does_not_match_is_not_linked` ×3 (amount, date, reference), `test_a_voided_payment_is_not_linked`, `test_an_operation_that_is_not_observed_is_not_linked`, `test_an_applied_operation_is_not_linked` | PASS |
| L-04 | One link per operation; concurrent links wait (observed lock wait) and one wins | `test_an_operation_links_to_one_payment_only`, `test_two_links_of_one_operation_wait_and_one_wins` | PASS |
| L-05 | A linked operation is never applied | `test_a_linked_operation_is_never_applied` | PASS |
| L-06 | SQL cannot forge, change or delete a link; guard drift 503 | `test_sql_cannot_forge_or_change_a_link`, `test_sql_cannot_link_a_payment_that_does_not_match`, `test_a_damaged_link_control_fails_with_503` | PASS |
| L-07 | Void of a linked payment returns the operation to review; the link stays | `test_a_voided_linked_payment_returns_the_operation_to_review` | PASS |
| L-08 | Finance rights; foreign company | `test_linking_keeps_company_finance_permissions` ×4, `test_another_company_cannot_link` | PASS |
| L-09 | Desktop and mobile browser with axe | `test_k4a_real_browser_provider_operations` (link case on both projects) | PASS |
| L-10 | Runbook; K3a, K4a, K4b, H and the full suite | runbook census, focused-1, full-1 | PASS |

Direction and currency mismatches are refused in SQL and Python but have no dedicated test (USD
only and no refund fixture here): NOT TESTED.

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 424 passed in 622.38s (0:10:22) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2232 passed, 4 skipped in 2272.05s (0:37:52); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 331 source files |
| Web typecheck, lint, format, unit (122 passed), build | PASS |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| K CI | NOT TESTED for K3b (not published); K4a and K4b CI SUCCESS |

New cases 20, regression cases 404 (see CHECKS.json).

## Failures kept in the record

- **red-1, product RED** on `199eada`: 19 failed, 1 passed (no 0054 table, no route; the
  foreign-company case passed through the missing route).
- **dev-1, test defect**: 3 failed, 177 passed. Two manual payments with the same alias and
  reference violate the H identity (`FINANCIAL_SOURCE_ALREADY_RECORDED`); the extra payments name
  the ID in other references. dev-2: 20 passed; dev-3 browser 6 passed.
- **Web red**: NOT TESTED as a separate run; the K3b web contract case was written with the schemas.

## Limits

No automatic linking; only manual payments whose reference names the ID are candidates. Moving
money between the bank and the clearing account stays a manual ledger entry. No provider retrieval
(K2b, needs K0), no worker entry point, publishing or deployment. FIN-02 planned; ADR-0027 Proposed.
