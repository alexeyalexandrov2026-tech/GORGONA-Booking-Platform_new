# K5a-fix — verified review findings, local validation

**PASS for this bounded local slice.** Branch `codex/package-k5a-review-fixes`, parent `59c54a0`
(the K5a review record), source commit `76f776447b0b4fcb1699047aa2fa496531ee6b34`. [CHECKS.json](CHECKS.json) was generated before
the source commit and binds source blobs (including the runbook), commands, exit codes and log
digests. Published for CI only on 2026-10-20 (no PR). Findings: [K5a review](../2026-10-19-k5a-review/REVIEW.md). Executor:
Claude, inline, after the owner's decisions of 2026-10-19: fix findings 1, 2, 3, 5, 7, 10, 11, 13
and 14 in one slice, failing tests first; finding 4: only a `compromise` revocation of a
verification config blocks money, `rotation` and `retired` do not.

## What changed

- `db/migrations/0055_provider_review_fixes.sql` (new, K): `decide_provider_event` decides a
  refund event that failed or was canceled, and a success of the same refund, as
  `conflicting_facts` in either order (2); both revocation guards take the advisory key of the
  company ledger lock (`gba.lock_ledger`, 0020) that every application and link holds, so a
  revocation waits for them and later ones see it (7). The receipt roles that revoke have no right
  to call `gba.lock_ledger`, so the key is taken directly. The receipt guard reads 0055.
- `db/migrations/0056_provider_money_review_fixes.sql` (new, H): helpers `provider_reference_ids`
  (word tokens under the H identity key), `effective_payment_amount`, `provider_manual_payment`
  (not voided, names the ID) and `provider_operation_payment` (the not voided provider or linked
  payment of an operation); BEFORE INSERT trigger `external_payments_provider_identity` refuses a
  manual payment naming an operation whose money counts (1); `assert_provider_payment` and
  `enforce_provider_payment_link` block only a compromised config (4), use the helper name check
  (5, 13) and an effective refund cap (11). The financial guard reads 0056.
- Service: the manual confirmation refuses such a reference with `PROVIDER_OPERATION_APPLIED` or
  `PROVIDER_OPERATION_LINKED` (operation and payment named); applying, the SQL state and the link
  candidates use the same helpers; a SQL refusal of a link or an acknowledgement is
  `PROVIDER_LINK_MISMATCH` / `PROVIDER_ATTENTION_NOT_NEEDED` with reason `facts` (10); the
  application counter is recorded only after authorization (3).
- API and web: the financial overview names `timezone` (the business zone); the strict web contract
  requires it and the provider apply form defaults its posting date to today in that zone (14).
  Runbook: revocation reasons, the new refusals, `facts`, the counter.
- Tests: `test_k5a_review_fixes.py` (new, 18); the exact overview case gains `timezone`; a K3b
  case now records its manual payment without the ID (finding 1 refuses the old order); the
  browser harness passes the business zone and checks the default date; a web contract case.

Migrations 0001–0054 unchanged; next **0057**. No dependency, provider call, entry point,
readiness or Azure change.

## Findings and evidence

| # | Finding | Tests | Result |
|---|---|---|---|
| 1 | A manual payment naming an applied or linked operation | `test_a_manual_payment_cannot_name_an_applied_operation`, `test_sql_refuses_a_manual_payment_naming_an_applied_operation`, `test_a_manual_payment_cannot_name_a_linked_operation`, `test_after_a_void_the_money_may_be_recorded_by_hand` | PASS |
| 2 | A refund failure and success, either order | `test_a_refund_failure_after_its_success_is_a_conflict`, `test_a_refund_success_after_its_failure_is_a_conflict` | PASS |
| 3 | Counter only after authorization | `test_a_refused_foreign_application_is_not_counted` | PASS |
| 4 | Only `compromise` blocks (owner decision) | `test_a_routine_key_revocation_keeps_earlier_operations_usable` ×2, `test_a_routine_key_revocation_keeps_linking_possible`, `test_a_compromised_key_still_blocks_linking`, K3a revocation case | PASS |
| 5 | A voided manual payment no longer blocks | `test_a_voided_manual_payment_no_longer_blocks_the_operation` | PASS |
| 7 | A revocation waits for an application in progress (observed `pg_locks` wait) | `test_a_revocation_waits_for_an_application_in_progress` ×2 | PASS |
| 10 | SQL refusals of a link and an acknowledgement are typed | `test_a_link_refused_by_sql_is_a_typed_refusal`, `test_an_acknowledgement_refused_by_sql_is_a_typed_refusal` | PASS |
| 11a | The cap follows a corrected parent | `test_the_refund_cap_follows_the_corrected_parent` | PASS |
| 11b | A voided refund no longer counts | none: H refuses voiding a refund payment, so no voided refund exists | NOT TESTED |
| 13 | Case and invisible characters do not hide an ID | case 1 (upper case, zero-width space) | PASS |
| 14 | Default posting date in the business zone | `test_the_overview_names_the_business_time_zone`, web contract case, browser date check (desktop and mobile) | PASS |

Finding 7 is proven with the ledger lock held by a runtime transaction, the same lock every
application and link takes first; a revocation in another session waits on it in `pg_locks`. The
runtime has no UPDATE right on K rows, so a `FOR SHARE` lock was not possible.

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 527 passed in 577.17s (0:09:37) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2250 passed, 4 skipped in 1868.37s (0:31:08); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 332 source files |
| Web typecheck, lint, format, unit (122 passed), build | PASS |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| K CI | PASS: published for CI only on 2026-10-20 by the owner's word; run 39371433810 for `7b08507` SUCCESS (read once). CHECKS.json predates the push (`published: false`) |

New cases 18, regression cases 509 (see CHECKS.json).

## Failures kept in the record

- **red-1** on `59c54a0`: 18 failed, 5 passed. Product RED for 15 cases. Test defects: a second
  manual payment repeated the first one's alias and reference (H identity); H refuses correcting a
  payment an issued credit depends on; H refuses voiding a refund payment (finding 11b removed,
  NOT TESTED). red-2: 17 failed, 5 passed (a correction dated before its original, test defect).
  red-3: the corrected-parent case failed because the over-cap refund was applied (product RED).
- **Web red**: the overview contract case failed (the strict schema had no `timezone`).
- **full-1, product defect**: 8 failed, 2242 passed, 4 skipped. The receipt roles that revoke
  (writer, group) have no EXECUTE on `gba.lock_ledger`; 0055 now takes the same advisory key
  directly, after the reason check, without a privilege change. dev-3: 99 passed. The revocation
  and routing modules joined the focused list.
- **focused-2, test defect**: 1 failed, 423 passed. The browser harness read the business zone from
  an owner session without the company context (UTC) while the form correctly showed the New York
  date (the run was at 02:00 UTC). Also found then: `run_gates.py` had CRLF line endings, so the
  focused-list edits never applied and gates-1/2 focused ran the K3b list; fixed before gates-3.
  dev-4: 19 passed, browser 6 passed with differing UTC and New York dates.
- **dev-1**: 2 failed, 168 passed. Test defects: an owner query without the company context saw no
  locations (UTC); a K3b case recorded a manual payment naming an applied operation, which finding 1
  now refuses. dev-2: 4 passed (browser K4a/K4b/K3b 6 passed, H4 passed).

## Limits

Findings 6, 8, 9, 12 and 15 stay open as recorded in the review. The name check still scans the
book's manual payments per operation (finding 6, not measured). The manual financial editors still
default to the UTC date. No K0 step, publishing or deployment. FIN-02 planned; ADR-0027 Proposed.
