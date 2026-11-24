# Design: REST-01 Slice 4 — Split Billing, FIN-03 Invoices & Coordinated Refunds (2026-11-21)

Aligned with `docs/adr/0037-restaurant-tables-menu-kitchen-checks.md` and `docs/plan/PACKAGE_REST01_PLAN_2026-11-20.md`.

## Acceptance Invariants
- **Exact Total Conservation**: A check with `subtotal_minor > 0` and zero draft lines can be split once (`by_items` or `by_amounts`, `1..20` shares). A deferred constraint trigger guarantees `sum(share.amount_minor) = check.subtotal_minor` with zero rounding drift; for `by_items`, every non-voided line is assigned to exactly one share and each share equals the exact sum of its assigned lines. Once split, check lines cannot be added or voided.
- **Per-Share `FIN-03` Invoicing**: Each share can be billed once into `FIN-03` (`financial_documents.save_draft`, `direction='receivable'`, same currency, exact `share.amount_minor`, optional distinct customer counterparty per share). DB trigger checks the linked invoice document matches the share's exact minor-unit amount and currency.
- **Coordinated Refunds (`FIN-03` Credit Notes & External Refunds)**: Append-only numbered refunds (`1, 2, 3...`) against a billed share support `method='credit'` (creating a `FIN-03` credit note draft against the share's issued invoice obligation) or `method='external'` (attested external refund), with optional `returned_line_id`. DB trigger enforces per-share and check-wide refund ceilings (excluding voided credit notes) and validates credit-note obligation provenance.
- **Derived Reconciliation (`GET /checks/{check_id}/reconciliation`)**: Derives live `FIN-03` invoice/credit states and `gba.obligation_balance` figures (principal, paid, credited, open, refund obligation) alongside `STOCK-01` consumption status without introducing a second ledger.

## Schema (`0133_restaurant_split_billing_and_refunds.sql`)
Adds 5 branch-scoped tables with tenant RLS, restrictive branch RLS (`-- Restaurant billing branch scope:`), invoker-rights triggers only, and `require_enabled_module('restaurant')`:
1. `gba.restaurant_check_splits`
2. `gba.restaurant_check_split_shares`
3. `gba.restaurant_check_split_share_lines`
4. `gba.restaurant_check_bills`
5. `gba.restaurant_check_refunds`

Also updates `gba.guard_restaurant_check_line()` to reject line additions/voids after a check is split.
