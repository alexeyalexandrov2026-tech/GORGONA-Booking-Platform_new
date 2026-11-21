# Package Plan — `MARKET-01`: Business Storefronts, Marketplace Discovery & Multi-Seller Orders (2026-11-21)

Aligned with `docs/plan/GORGONA_MASTER_PLAN.md` §11.3, §11.3.1, §13 Stage 7, §14.1.1 (`MARKET-01`), and `docs/adr/0040-storefronts-and-multi-seller-marketplaces.md`.

## Acceptance Criterion (`MARKET-01`)
> «Публикуются только выбранные поля; каждый заказ и платеж относятся к одному продавцу»
> «модель владельцев и групп этапа 1 сохранена; нет общего неразделенного платежа»

## Slice Breakdown

| Slice | Branch | Migration | Scope |
|---|---|---|---|
| **Slice 1** | `codex/package-market-01-storefronts-and-publishing` | `0141_market_storefronts_and_publishing.sql` | Update `storefronts` module (`MODULE_REGISTRY_VERSION=11`, `Readiness.IMPLEMENTED`, `enableable=False`) & permissions (`MARKET_READ`, `MARKET_MANAGE`, `PERMISSIONS_VERSION=20`); storefronts (`market_storefronts`), seller listings with private vs explicit `published_fields` allow-list (`market_listings`), moderation & strict public projection, and client-operated marketplaces (`marketplaces`, `marketplace_seller_connections`) with `gorgona_commission_bps = 0` and revocable scopes. |
| **Slice 2** | `codex/package-market-01-orders-and-settlement` | `0142_market_orders_and_settlement.sql` | Multi-seller basket split (`market_baskets`), strictly single-seller orders & lines (`market_orders`, `market_order_lines`) posting real seller `FIN-03` receivable invoices (`financial_documents.save_draft` + `issue_document`), customer refunds posting `FIN-03` credit notes (`credit_notes.save_draft`), and separate seller-billed operator fee records (`market_operator_fees`) without commingled payments. |
| **Slice 3** | `codex/package-market-01-ui` | *(none)* | `/marketplace/` 3-tab UI (`web/components/marketplace.tsx`, `web/lib/marketplace-contracts.ts`, `web/lib/marketplace-api.ts`) + real Chromium desktop & mobile (`390px`) Playwright E2E verifying explicit field-projection publishing, multi-seller basket split into single-seller orders/invoices, `axe-core`, and PostgreSQL 18 read-back. |
