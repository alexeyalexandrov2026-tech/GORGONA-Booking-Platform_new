# ADR-0040: Business Storefronts, GORGONA Marketplace Discovery, and Multi-Seller Marketplaces (`MARKET-01`)

- **Status**: Proposed (Stage 7 implementation; `MARKET-01` remains `planned`, `storefronts` remains `enableable=False` until formal acceptance and owner approval)
- **Date**: 2026-11-21
- **Master Plan References**: `docs/plan/GORGONA_MASTER_PLAN.md` §11.3, §11.3.1, §12.2, §13 Stage 7, §14.1.1 (`MARKET-01`)

## Context
GORGONA supports three storefront/marketplace scenarios (§11.3):
1. **Business storefront**: a company publishes selected brand, branch, product/service, price, and availability data.
2. **GORGONA marketplace**: cross-company discovery by category and geography leading to checkout at the chosen seller.
3. **Client-operated marketplace**: an operator business curates connected independent sellers under explicit delegated scopes (publication, customer service, reporting) without taking ownership of seller data or commingling customer funds.

## Decision
1. **Strict Explicit Field Projection («Публикуются только выбранные поля»)**:
   - Storefronts (`gba.market_storefronts`) and listings (`gba.market_listings`) store an explicit `published_fields text[]` allow-list restricted to approved public fields (`title`, `description`, `price`, `currency`, `category`, `availability`, `location_city`, `brand`, `sku`).
   - Private fields (`internal_cost_minor`, `internal_notes`, `legal_entity_id`, and any field not in the storefront ∩ listing `published_fields` set) are **never** emitted by public catalog/storefront projection responses.
2. **Single-Seller Order & Payment Ownership («каждый заказ и платеж относятся к одному продавцу»)**:
   - Every listing belongs to exactly one seller (`tenant_id`) and one `legal_entity_id`.
   - A multi-seller checkout basket (`gba.market_baskets`) is deterministically split into separate single-seller orders (`gba.market_orders`), each tied to exactly one seller `tenant_id`, one `legal_entity_id`, and one `FIN-03` receivable invoice/checkout in that seller's own ledger book.
   - Zero GORGONA transaction commission (`gorgona_commission_bps = 0` enforced by `CHECK` constraint). Operator commercial fees (if contracted) are recorded as separate seller-billed obligations, never withheld from customer payments (§11.3.1).
3. **Preservation of Stage 1 Ownership & Group Model**:
   - Independent sellers retain their own `tenant_id`; operator connections (`gba.marketplace_seller_connections`) use explicit revocable scopes (`publish`, `orders_read`, `reports_read`). Revoking a seller connection immediately blocks operator publication or reporting access.
   - Invoker-rights SQL only (zero `SECURITY DEFINER`), tenant RLS + restrictive branch RLS on every branch-scoped table, and `require_module_write_enabled('storefronts')` write gates.
