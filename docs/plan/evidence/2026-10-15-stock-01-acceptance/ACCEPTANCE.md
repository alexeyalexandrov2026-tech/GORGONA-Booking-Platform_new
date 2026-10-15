# STOCK-01 — technical acceptance evidence, 2026-10-15

**PASS: all J-01–J-14 evidence rows**, against implementation/documentation head `aedbb982a696052d606499f737b1754fce362b6a`
on `codex/package-j-review2-fixes`. Exact-commit [CI run 157](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38693973265)
completed successfully. Full local: **1748 passed, 4 skipped in 1448.82s (0:24:08)**. The source bytes of
that full run match this head. [Machine record](ACCEPTANCE.json),
[part-2 validation](../2026-10-14-j5-j6-review-fixes-part2/VALIDATION.md).

This records technical evidence only. STOCK-01 remains `planned`, the inventory readiness
lock stays closed, and ADR-0026 remains Proposed. Promoting readiness needs the owner's
separate explicit word. Main stays fedd0f115f24aad52f6256298296e8c5123fb427; no PR/merge/deployment.
The acceptance documentation commit adds no source change and needs its own exact-head
CI read after publication; that result is a separate receipt from the implementation CI.
The final exact-head receipt is retained at `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-jr2p2-20261014-abbdfeb/ci-acceptance.json`
and must name the actual final HEAD with status completed/conclusion success. Its public
run URL is also returned in the final delivery message; it is generated after this document
commit, so it is intentionally retained with the run evidence outside Git.

## Matrix

### J-01 — PASS

Atomic receipt, movement, costing, balanced journal, audit and replay receipt; refused postings roll back.

- [test_receipts_post_movements_cost_and_one_journal_entry](../../../../api/tests/integration/test_stock.py)
- [test_sql_receipt_needs_every_part_and_its_exact_journal](../../../../api/tests/integration/test_stock.py)
- [test_refused_receipts_leave_no_parts](../../../../api/tests/integration/test_stock.py)
- [test_sql_write_off_needs_the_average_and_its_exact_journal](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_sql_return_carries_exactly_the_amounts_of_the_database](../../../../api/tests/integration/test_stock_returns.py)
- [test_sql_transfer_needs_both_movements_and_carries_no_money](../../../../api/tests/integration/test_stock_transfers.py)

### J-02 — PASS

SQL enforces document/line/owner/transaction provenance and refuses orphan or foreign rows and stock journal entries.

- [test_sql_keeps_documents_whole_and_stock_entries_owned](../../../../api/tests/integration/test_stock.py)
- [test_sql_return_carries_exactly_the_amounts_of_the_database](../../../../api/tests/integration/test_stock_returns.py)
- [test_gap10_a_return_never_moves_another_owners_stock_by_sql](../../../../api/tests/integration/test_stock_acceptance.py)

### J-03 — PASS

Identical-key replay returns the same document; changed bodies are refused; contenders wait in pg_locks and post once.

- [test_receipt_command_is_idempotent](../../../../api/tests/integration/test_stock.py)
- [test_two_requests_with_one_key_post_one_document](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_two_transfer_requests_with_one_key_post_one_document](../../../../api/tests/integration/test_stock_review_fixes.py)

### J-04 — PASS

Overspending is refused in API and SQL; concurrent final-balance writers have one winner after observed locking.

- [test_write_off_never_takes_more_than_its_owner_holds_in_the_place](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_two_write_offs_of_the_last_balance_have_one_winner](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_two_transfers_of_the_last_balance_have_one_winner](../../../../api/tests/integration/test_stock_transfers.py)

### J-05 — PASS

Legal entities, stock and books stay separate; book/rules are required for money documents.

- [test_refused_receipts_leave_no_parts](../../../../api/tests/integration/test_stock.py)
- [test_write_off_never_takes_more_than_its_owner_holds_in_the_place](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_receipts_post_movements_cost_and_one_journal_entry](../../../../api/tests/integration/test_stock.py)
- [test_gap10_a_return_never_moves_another_owners_stock_by_sql](../../../../api/tests/integration/test_stock_acceptance.py)

### J-06 — PASS

Moving-average costs, deterministic half-up rounding, zero residual value and reconciliation hold.

- [test_write_off_leaves_at_the_moving_average_and_posts_one_entry](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_write_off_rounding_follows_the_running_average_and_repeats](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_every_kind_of_document_extends_its_history](../../../../api/tests/integration/test_stock_running_totals.py)
- [test_shares_are_rounded_once_and_a_completed_line_returns_its_whole_amount](../../../../api/tests/integration/test_stock_returns.py)

### J-07 — PASS

Closed/future/pre-book dates are refused; closing and posting serialize in both orders, API and SQL.

- [test_refused_receipts_leave_no_parts](../../../../api/tests/integration/test_stock.py)
- [test_period_close_and_write_off_take_one_order](../../../../api/tests/integration/test_stock_write_offs.py)

### J-08 — PASS

Source-line return limits, two return directions, moving average/difference postings and exact final shares hold, including races.

- [test_return_to_supplier_leaves_at_average_cost_and_posts_the_price_difference](../../../../api/tests/integration/test_stock_returns.py)
- [test_return_of_a_write_off_comes_back_at_its_share_of_the_cost](../../../../api/tests/integration/test_stock_returns.py)
- [test_return_keeps_its_limits_and_its_shape](../../../../api/tests/integration/test_stock_returns.py)
- [test_two_returns_of_the_last_quantity_have_one_winner](../../../../api/tests/integration/test_stock_returns.py)
- [test_shares_are_rounded_once_and_a_completed_line_returns_its_whole_amount](../../../../api/tests/integration/test_stock_returns.py)

### J-09 — PASS

Transfers move two quantities atomically without money/ownership changes; opposite transfers and branch limits hold.

- [test_transfer_moves_quantity_without_touching_cost_or_the_books](../../../../api/tests/integration/test_stock_transfers.py)
- [test_sql_transfer_needs_both_movements_and_carries_no_money](../../../../api/tests/integration/test_stock_transfers.py)
- [test_opposite_transfers_wait_in_one_order_and_both_pass](../../../../api/tests/integration/test_stock_transfers.py)
- [test_branch_manager_transfers_inside_the_branch_only](../../../../api/tests/integration/test_stock_transfers.py)
- [test_two_transfers_into_a_new_balance_wait_and_chain](../../../../api/tests/integration/test_stock_running_totals.py)

### J-10 — PASS

Immutable histories and identity/unit/scale/account restrictions hold; generic stock-entry reversal is refused.

- [test_sql_keeps_documents_whole_and_stock_entries_owned](../../../../api/tests/integration/test_stock.py)
- [test_posting_rules_are_versioned_and_checked](../../../../api/tests/integration/test_stock.py)
- [test_sql_keeps_versions_ordered_authored_and_immutable](../../../../api/tests/integration/test_inventory.py)
- [test_archived_material_and_place_take_no_receipt_and_still_write_off](../../../../api/tests/integration/test_stock_write_offs.py)

### J-11 — PASS

Exact quantity/currency text, scale/range rejection, zero-total documents and accumulated overflow refusals hold in API/SQL.

- [test_refused_receipts_leave_no_parts](../../../../api/tests/integration/test_stock.py)
- [test_counts_are_exact_decimal_strings](../../../../api/tests/unit/test_stock_contracts.py)
- [test_receipts_post_movements_cost_and_one_journal_entry](../../../../api/tests/integration/test_stock.py)
- [test_write_off_line_value_stays_in_the_supported_range](../../../../api/tests/integration/test_stock_write_offs.py)
- [test_gap10_accumulated_totals_stay_in_range_with_a_named_refusal](../../../../api/tests/integration/test_stock_acceptance.py)

### J-12 — PASS

Staff/support/delegates/other companies are refused; branch managers read own quantities only and post transfers only.

- [test_branch_scope_rights_and_hidden_amounts](../../../../api/tests/integration/test_stock.py)
- [test_staff_support_and_other_companies_are_refused](../../../../api/tests/integration/test_inventory.py)
- [test_j12_a_delegate_of_another_company_reaches_no_inventory_route](../../../../api/tests/integration/test_stock_acceptance.py)
- [test_only_a_company_wide_finance_member_posts_a_return](../../../../api/tests/integration/test_stock_returns.py)
- [test_branch_manager_transfers_inside_the_branch_only](../../../../api/tests/integration/test_stock_transfers.py)

### J-13 — PASS

Finance dependency, disabled/revoked gates, history/recovery, damaged-schema refusal, receipt-vs-bill clearing, and full-platform regression hold.

- [test_inventory_cannot_be_published_without_finance](../../../../api/tests/integration/test_inventory.py)
- [test_disabled_inventory_keeps_stock_reads_and_refuses_documents](../../../../api/tests/integration/test_stock.py)
- [test_j13_revoked_readiness_refuses_new_actions_and_keeps_history_and_recovery](../../../../api/tests/integration/test_stock_acceptance.py)
- [test_discards_are_limited_and_settling_works_with_the_module_off](../../../../api/tests/integration/test_inventory_commands.py)
- [test_damaged_inventory_schema_refuses_reads_and_writes](../../../../api/tests/integration/test_inventory_guards.py)
- [test_damaged_stock_schema_refuses_reads_and_writes](../../../../api/tests/integration/test_stock_guards.py)
- [test_j13_a_purchase_and_its_bill_leave_nothing_on_the_receipt_account](../../../../api/tests/integration/test_stock_acceptance.py)

### J-14 — PASS

Real desktop/mobile browsers with OIDC/PKCE and PostgreSQL, axe, recovery, complete catalogues; static/full checks and exact-commit CI; prior independent reviews.

- [test_materials_real_browser_before_and_after_books](../../../../api/tests/integration/test_materials_browser.py)
- [test_stock_documents_real_browser](../../../../api/tests/integration/test_stock_documents_browser.py)

## Review and limits

The independent [J1–J4 review](../2026-10-13-j-review/REVIEW.md) and
[J5/J6 review](../2026-10-14-j5-j6-review/REVIEW.md) are preserved. Their actionable
Package J findings are fixed and covered, including H1 by immutable migration 0043.
No additional independent reviewer was spawned during this inline continuation.

- L1: intermediate histories backfilled by 0042 are approximate; authoritative final
  totals reconcile. Transaction start order does not establish historical commit order.
- L4: cancellation tombstones expire after 24 hours; commands arriving after expiry can execute.
- Earlier L6: migrations 0037/0042 need a maintenance window and coordinated schema/app
  deployment. No deployment or production migration is authorized.
- The platform-wide current-user/current-tenant function body guard is outside this package.
- Review-2 gaps 3–5 (additional performance/upgrade/cancellation races) remain recorded;
  this acceptance makes no claim that these extra cases were newly tested.
- Additional pre-existing UI follow-up observed by code inspection: archived materials
  and places are filtered from outbound selectors too, although supported outbound API
  operations exist. This behavior was preserved within the requested part-2 boundary;
  an archived-outbound browser scenario is NOT TESTED. This evidence is scoped to the
  named acceptance cases, not a claim that every possible UI workflow is complete.
- Runtime npm audit: 0. Development-only audit: FAIL, 5 existing high findings, unchanged.
- Local container and optional external-site checks are NOT TESTED (four pytest skips);
  the GitHub job requires actual container/browser checks. Production/Azure are NOT TESTED.
- This evidence verifies the named workflows and regressions; deployment readiness is a separate gate.

The complete suite supplies booking, FIN-01, FIN-03 and workforce regression evidence;
individual XML cases mapped above were required to pass without skips. All race claims
refer to tests that observe an actual pg_locks wait. Byte digests and exact commands are
in the part-2 CHECKS.json and retained run folder. Temporary clusters were stopped.
