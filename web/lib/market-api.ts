// MARKET-01 Slice 3: typed API client for /marketplace/ with Idempotency-Key mutations.
import { ManagementApiError, managementFetch } from "./management-api";
import {
  BasketCheckoutViewSchema,
  ListingListSchema,
  ListingViewSchema,
  MarketplaceListSchema,
  MarketplaceViewSchema,
  MarketOrderListSchema,
  MarketOrderViewSchema,
  OperatorFeeListSchema,
  PublicStorefrontCatalogSchema,
  SellerConnectionListSchema,
  SellerConnectionViewSchema,
  StorefrontListSchema,
  StorefrontViewSchema,
  type BasketCheckoutView,
  type ConnectionStatus,
  type ListingView,
  type MarketplaceView,
  type MarketOrderView,
  type ModerationStatus,
  type OperatorFeeView,
  type OperatorScope,
  type PublicField,
  type PublicStorefrontCatalog,
  type SellerConnectionView,
  type StorefrontView,
} from "./market-contracts";

const root = (business: string) => `/v1/businesses/${business}/market`;

export function marketError(error: unknown): string {
  if (error instanceof ManagementApiError) {
    return `${error.code}: ${error.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

export async function fetchStorefronts(
  business: string,
): Promise<StorefrontView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/storefronts`);
  return StorefrontListSchema.parse(raw).items;
}

export async function saveStorefront(
  business: string,
  storefrontId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    legal_entity_id: string;
    slug: string;
    display_name: string;
    description?: string | null;
    location_city?: string | null;
    currency: string;
    published_fields: PublicField[];
    is_published: boolean;
  },
): Promise<StorefrontView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/storefronts/${storefrontId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return StorefrontViewSchema.parse(raw);
}

export async function fetchPublicCatalog(
  business: string,
  storefrontId: string,
): Promise<PublicStorefrontCatalog> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/storefronts/${storefrontId}/public-catalog`,
  );
  return PublicStorefrontCatalogSchema.parse(raw);
}

export async function fetchListings(business: string): Promise<ListingView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/listings`);
  return ListingListSchema.parse(raw).items;
}

export async function saveListing(
  business: string,
  listingId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    storefront_id: string;
    sku: string;
    title: string;
    description?: string | null;
    category: string;
    brand?: string | null;
    currency: string;
    price_minor: number;
    available_quantity: number;
    internal_cost_minor: number;
    internal_notes?: string | null;
    published_fields: PublicField[];
    moderation_status: ModerationStatus;
  },
): Promise<ListingView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/listings/${listingId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return ListingViewSchema.parse(raw);
}

export async function fetchMarketplaces(
  business: string,
): Promise<MarketplaceView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/marketplaces`);
  return MarketplaceListSchema.parse(raw).items;
}

export async function saveMarketplace(
  business: string,
  marketplaceId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    slug: string;
    title: string;
    description?: string | null;
    operator_fee_bps: number;
    is_active?: boolean;
  },
): Promise<MarketplaceView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/marketplaces/${marketplaceId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return MarketplaceViewSchema.parse(raw);
}

export async function fetchSellerConnections(
  business: string,
  marketplaceId: string,
): Promise<SellerConnectionView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/marketplaces/${marketplaceId}/sellers`,
  );
  return SellerConnectionListSchema.parse(raw).items;
}

export async function saveSellerConnection(
  business: string,
  marketplaceId: string,
  connectionId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    seller_counterparty_id: string;
    seller_storefront_slug: string;
    granted_scopes: OperatorScope[];
    status: ConnectionStatus;
  },
): Promise<SellerConnectionView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/marketplaces/${marketplaceId}/sellers/${connectionId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return SellerConnectionViewSchema.parse(raw);
}

export async function postBasketCheckout(
  business: string,
  key: string,
  body: {
    location_id: string;
    customer_counterparty_id: string;
    marketplace_id?: string | null;
    currency: string;
    order_date: string;
    items: { listing_id: string; quantity: number }[];
    seller_configs: {
      storefront_id: string;
      book_id: string;
      control_account_id: string;
      revenue_account_id: string;
      seller_counterparty_id?: string | null;
    }[];
  },
): Promise<BasketCheckoutView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/baskets/checkout`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return BasketCheckoutViewSchema.parse(raw);
}

export async function fetchMarketOrders(
  business: string,
): Promise<MarketOrderView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/orders`);
  return MarketOrderListSchema.parse(raw).items;
}

export async function postMarketOrderRefund(
  business: string,
  orderId: string,
  key: string,
  body: {
    refund_minor: number;
    refund_date: string;
    reason: string;
  },
): Promise<MarketOrderView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/orders/${orderId}/refund`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return MarketOrderViewSchema.parse(raw);
}

export async function fetchOperatorFees(
  business: string,
): Promise<OperatorFeeView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/operator-fees`);
  return OperatorFeeListSchema.parse(raw).items;
}
