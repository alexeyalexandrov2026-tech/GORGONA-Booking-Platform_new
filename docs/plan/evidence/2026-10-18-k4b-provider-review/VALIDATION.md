# K4b provider review, attention and runbook — local validation

**PASS for this bounded local slice.** Branch `codex/package-k4b-provider-review`, parent
`45f15df`, source commit `60a12e14d461ef3d9a9b6dbca8e35c25f402055d`. [CHECKS.json](CHECKS.json)
was generated before the source commit and binds source blobs (including the runbook), commands,
exit codes and log digests. Not published. Design: [K4b](../../PACKAGE_K4B_DESIGN_2026-10-18.md).
Executor: Claude, inline, after the owner's decisions of 2026-10-18: conflict detail with the
differing fields and both values; an acknowledgement with a required note (answer "make sure is
done"); counters with the company identifier; runbook in English.

## What changed

- `db/migrations/0053_provider_attention_acknowledgements.sql` (new, K): one permanent
  acknowledgement per decision **without** an operation (note 1–500, single line; `created_by` a
  user; FORCE RLS with tenant and company policies; runtime select and insert of four columns;
  check, immutable and no-truncate triggers). `db/provider_receipt_guard.py` reads it.
- `business/provider_review.py` (new): operation detail (events, decisions, deliveries; a
  differing delivery names each fact field with both values), the attention list (attested
  undecided events and decisions without an operation, with the provider object ID and any
  acknowledgement) and `acknowledge` (same note returns the record; another note
  `PROVIDER_ATTENTION_ACKNOWLEDGED`; an event of an operation or an undecided one
  `PROVIDER_ATTENTION_NOT_NEEDED`). `provider_payments.load_operation` shares the list's state.
- `api/financial_documents.py`: `GET …/provider-operations/{id}`, `GET …/provider-attention`,
  `PUT …/provider-attention/{event}/acknowledgement`; the apply route counts its result.
- `observability.py`, `providers/receipt_worker.py`: counters `gorgona.provider_receipt_decisions`
  (outcome, reason, tenant_id) and `gorgona.provider_applications` (result, tenant_id).
- Web: strict contracts and routes; "Details" on each operation row, the detail with "What
  disagrees", the "Needs attention" section with the acknowledgement form.
- `docs/runbooks/PROVIDER_OPERATIONS.md` (new, English) and `tests/unit/test_provider_runbook.py`.
- Tests: `test_provider_review.py` (new, 17), the runbook test (3), the browser harness gains a
  desktop/mobile review case and synthetic seeds (a differing delivery, a decision without an
  operation, an undecided event); location and upgrade lists name the new table.

Migrations 0001–0052 unchanged; next **0054**. No dependency, provider call, worker entry point,
readiness or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| R-01 | Every event, decision and delivery in order; unknown or foreign operation not found | `test_the_detail_lists_every_event_decision_and_delivery`, `test_an_unknown_or_foreign_operation_is_not_found` | PASS |
| R-02 | A differing delivery names exactly the fields and both values | `test_a_differing_delivery_names_its_fields_and_both_values`, `test_conflicting_events_show_their_decisions`; browser "What disagrees" | PASS |
| R-03 | No raw body, signature, secret reference, verification config or key | the same detail test; browser text check | PASS |
| R-04 | Attention lists undecided events and decisions without an operation, across pages, nothing else | `test_attention_lists_undecided_events_and_decisions_without_an_operation` (one-row pages) | PASS |
| R-05 | Acknowledgement: note required, once, append-only, company scoped, guarded, no money | `test_an_acknowledgement_needs_a_note_and_is_given_once`, `test_an_event_of_an_operation_is_not_acknowledged`, `test_sql_cannot_change_or_forge_an_acknowledgement`, `test_damaged_acknowledgement_controls_fail_with_503` ×3; browser and database rows | PASS |
| R-06 | Counters by outcome/reason and result, with the company and no payload values | `test_decisions_and_applications_are_counted_with_the_company` | PASS |
| R-07 | Finance rights; branch, front desk, artist and foreign company refused | `test_review_routes_keep_company_finance_permissions` ×4, `test_another_company_cannot_read_or_acknowledge` | PASS |
| R-08 | Desktop and mobile browser with axe; no side scroll | `test_k4a_real_browser_provider_operations` (review case on both projects) | PASS |
| R-09 | The runbook covers every state and refusal code; links resolve | `test_provider_runbook.py` ×3 | PASS |
| R-10 | Existing K4a/K3a/H browser and API tests and the full suite | focused-1, full-1 | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 345 passed in 502.38s (0:08:22) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2212 passed, 4 skipped in 2388.14s (0:39:48); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 330 source files |
| Web typecheck, lint, format, unit (121 passed), build | PASS |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop; no `postmaster.pid` left |
| K CI | NOT TESTED for K4b (not published); K4a run 39185366331 SUCCESS |

New cases 20, regression cases 325 (see CHECKS.json).

## Failures kept in the record

- **red-1, product RED** on `45f15df`: 15 failed, 2 passed (no 0053 table, no routes; the two
  404 cases passed through the missing route). Web: 2 failed, 27 passed; the route-contract case
  passed falsely while the schemas did not exist.
- **dev-1, test defect**: 1 failed, 160 passed. The metric test repeated an application on the
  settlement it had already confirmed (`FINANCIAL_STATE_INVALID`); it now repeats on a second
  reserved settlement.
- **runbook unit, test defect**: the code census also counted the generic
  `FINANCIAL_STATE_INVALID`; it is limited to `PROVIDER_` codes.

## Limits

An undecided event cannot be acknowledged; it waits for its decision (no worker entry point yet).
Counters are exported only where telemetry is configured; no alerts or dashboards. Linking manual
payments (K3b), provider retrieval (K2b, needs K0), fees, payouts, other currencies and deployment
remain open. FIN-02 planned; ADR-0027 Proposed.
