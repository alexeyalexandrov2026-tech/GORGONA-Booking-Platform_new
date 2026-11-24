# MARKET-01 Slice 3 — `/marketplace/` 3-Tab Operations UI & Real-Browser E2E

Date: 2026-11-21
ADR: `docs/adr/0040-storefronts-and-multi-seller-marketplaces.md`
Parent plan: `docs/plan/PACKAGE_MARKET01_PLAN_2026-11-21.md`

## Scope
- Route: `/marketplace/` inside `ManagementLayout` (navigation item `"Marketplace"`, gated by `MARKET_READ` / `MARKET_MANAGE`).
- Strict Zod contracts (`web/lib/market-contracts.ts`) registered in `management-contracts.ts` and unit-tested (`web/tests/market-contracts.spec.ts`).
- Typed API client (`web/lib/market-api.ts`) with mandatory `Idempotency-Key` on every mutation.
- 3 accessible, responsive tabs (`role="tablist"`, `ArrowLeft`/`ArrowRight` keyboard navigation, mobile 390px zero-overflow layout):
  1. **Storefronts & Publishing**: business storefronts with explicit `published_fields` allow-list checkboxes, listings with private `internal_cost_minor`/`internal_notes` separated from `published_fields`, and live Public Catalog Projection viewer proving strict allow-list intersection (`storefront.published_fields ∩ listing.published_fields`).
  2. **Client-Operated Marketplaces**: create client-operated marketplaces displaying `gorgona_commission_bps = 0` (0.00% GORGONA transaction commission), connect independent seller storefronts with explicit scopes, revoke connections, and surface `MARKET_STATE_INVALID` on attempted reactivation.
  3. **Multi-Seller Checkout & Settlement**: multi-seller basket checkout with per-seller ledger book selection, negative proof rejecting cross-seller book commingling, split single-seller orders with distinct FIN-03 receivable invoices, partial refund FIN-03 credit notes, and zero-GORGONA-commission operator fee ledger.
- Real-browser Chromium Playwright E2E (`web/tests/market.spec.ts` + `api/tests/integration/test_market_browser.py`) across `desktop` and `mobile` (390px) viewports with `@axe-core/playwright` zero-violation check and direct PostgreSQL 18 read-back.
