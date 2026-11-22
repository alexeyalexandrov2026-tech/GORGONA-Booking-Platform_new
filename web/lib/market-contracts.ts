// MARKET-01 Slice 3 (ADR-0040): strict Zod contracts for /marketplace/ UI.
import { z } from "zod";

export type MembershipSummary = {
  role: string;
  delegated?: boolean;
  delegation?: unknown;
};

const uuid = z.string().uuid();
const isoDateTime = z.string().min(1);
const currency = z.string().regex(/^[A-Z]{3}$/);

export const PublicFieldSchema = z.enum([
  "title",
  "description",
  "price",
  "currency",
  "category",
  "availability",
  "location_city",
  "brand",
  "sku",
]);
export type PublicField = z.infer<typeof PublicFieldSchema>;

export const ALL_PUBLIC_FIELDS: readonly PublicField[] = [
  "title",
  "description",
  "price",
  "currency",
  "category",
  "availability",
  "location_city",
  "brand",
  "sku",
] as const;

export const ModerationStatusSchema = z.enum([
  "draft",
  "pending_review",
  "published",
  "suspended",
  "archived",
]);
export type ModerationStatus = z.infer<typeof ModerationStatusSchema>;

export const OperatorScopeSchema = z.enum([
  "publish",
  "orders_read",
  "reports_read",
]);
export type OperatorScope = z.infer<typeof OperatorScopeSchema>;

export const ConnectionStatusSchema = z.enum([
  "pending",
  "active",
  "suspended",
  "revoked",
]);
export type ConnectionStatus = z.infer<typeof ConnectionStatusSchema>;

export const MarketOrderStatusSchema = z.enum([
  "confirmed",
  "fulfilled",
  "partially_refunded",
  "refunded",
]);
export type MarketOrderStatus = z.infer<typeof MarketOrderStatusSchema>;

export const StorefrontViewSchema = z
  .object({
    schema_version: z.literal(1),
    storefront_id: uuid,
    location_id: uuid,
    legal_entity_id: uuid,
    slug: z.string(),
    display_name: z.string(),
    description: z.string().nullable(),
    location_city: z.string().nullable(),
    currency,
    published_fields: z.array(PublicFieldSchema),
    is_published: z.boolean(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type StorefrontView = z.infer<typeof StorefrontViewSchema>;

export const StorefrontListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(StorefrontViewSchema),
  })
  .strict();

export const ListingViewSchema = z
  .object({
    schema_version: z.literal(1),
    listing_id: uuid,
    location_id: uuid,
    storefront_id: uuid,
    legal_entity_id: uuid,
    sku: z.string(),
    title: z.string(),
    description: z.string().nullable(),
    category: z.string(),
    brand: z.string().nullable(),
    currency,
    price_minor: z.number().int(),
    available_quantity: z.number().int(),
    internal_cost_minor: z.number().int(),
    internal_notes: z.string().nullable(),
    published_fields: z.array(PublicFieldSchema),
    moderation_status: ModerationStatusSchema,
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type ListingView = z.infer<typeof ListingViewSchema>;

export const ListingListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(ListingViewSchema),
  })
  .strict();

export const PublicListingProjectionSchema = z
  .object({
    schema_version: z.literal(1),
    listing_id: uuid,
    storefront_slug: z.string(),
    seller_display_name: z.string(),
    published_fields: z.array(PublicFieldSchema),
    fields: z.record(
      z.string(),
      z.union([z.string(), z.number(), z.boolean(), z.null()]),
    ),
  })
  .strict();
export type PublicListingProjection = z.infer<
  typeof PublicListingProjectionSchema
>;

export const PublicStorefrontCatalogSchema = z
  .object({
    schema_version: z.literal(1),
    storefront_slug: z.string(),
    display_name: z.string(),
    published_fields: z.array(PublicFieldSchema),
    items: z.array(PublicListingProjectionSchema),
  })
  .strict();
export type PublicStorefrontCatalog = z.infer<
  typeof PublicStorefrontCatalogSchema
>;

export const MarketplaceViewSchema = z
  .object({
    schema_version: z.literal(1),
    marketplace_id: uuid,
    location_id: uuid,
    slug: z.string(),
    title: z.string(),
    description: z.string().nullable(),
    gorgona_commission_bps: z.literal(0),
    operator_fee_bps: z.number().int(),
    is_active: z.boolean(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type MarketplaceView = z.infer<typeof MarketplaceViewSchema>;

export const MarketplaceListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(MarketplaceViewSchema),
  })
  .strict();

export const SellerConnectionViewSchema = z
  .object({
    schema_version: z.literal(1),
    connection_id: uuid,
    location_id: uuid,
    marketplace_id: uuid,
    seller_counterparty_id: uuid,
    seller_storefront_slug: z.string(),
    granted_scopes: z.array(OperatorScopeSchema),
    status: ConnectionStatusSchema,
    revoked_at: isoDateTime.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type SellerConnectionView = z.infer<typeof SellerConnectionViewSchema>;

export const SellerConnectionListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(SellerConnectionViewSchema),
  })
  .strict();

export const MarketOrderLineViewSchema = z
  .object({
    schema_version: z.literal(1),
    order_line_id: uuid,
    order_id: uuid,
    line_no: z.number().int(),
    listing_id: uuid,
    quantity: z.number().int(),
    unit_price_minor: z.number().int(),
    line_total_minor: z.number().int(),
  })
  .strict();
export type MarketOrderLineView = z.infer<typeof MarketOrderLineViewSchema>;

export const MarketOrderViewSchema = z
  .object({
    schema_version: z.literal(1),
    order_id: uuid,
    location_id: uuid,
    basket_id: uuid,
    storefront_id: uuid,
    legal_entity_id: uuid,
    customer_counterparty_id: uuid,
    marketplace_id: uuid.nullable(),
    order_number: z.string(),
    currency,
    total_minor: z.number().int(),
    refunded_minor: z.number().int(),
    status: MarketOrderStatusSchema,
    book_id: uuid,
    control_account_id: uuid,
    revenue_account_id: uuid,
    invoice_document_id: uuid,
    invoice_line_id: uuid,
    obligation_id: uuid,
    credit_note_document_id: uuid.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
    lines: z.array(MarketOrderLineViewSchema),
  })
  .strict();
export type MarketOrderView = z.infer<typeof MarketOrderViewSchema>;

export const MarketOrderListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(MarketOrderViewSchema),
  })
  .strict();

export const BasketCheckoutViewSchema = z
  .object({
    schema_version: z.literal(1),
    basket_id: uuid,
    location_id: uuid,
    customer_counterparty_id: uuid,
    marketplace_id: uuid.nullable(),
    currency,
    split_order_count: z.number().int(),
    orders: z.array(MarketOrderViewSchema),
  })
  .strict();
export type BasketCheckoutView = z.infer<typeof BasketCheckoutViewSchema>;

export const OperatorFeeViewSchema = z
  .object({
    schema_version: z.literal(1),
    fee_id: uuid,
    location_id: uuid,
    marketplace_id: uuid,
    order_id: uuid,
    seller_counterparty_id: uuid,
    currency,
    gorgona_commission_minor: z.literal(0),
    operator_fee_minor: z.number().int(),
    status: z.enum(["accrued", "invoiced", "waived"]),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type OperatorFeeView = z.infer<typeof OperatorFeeViewSchema>;

export const OperatorFeeListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(OperatorFeeViewSchema),
  })
  .strict();

export function marketResponseSchema(
  subpath: string,
  method: string,
): z.ZodType | null {
  const path = subpath.split("?")[0] ?? "";
  if (!path.startsWith("/market/")) return null;
  const rest = path.slice("/market/".length);
  const m = method.toUpperCase();
  if (rest === "storefronts" && m === "GET") return StorefrontListSchema;
  if (/^storefronts\/[^/]+$/.test(rest) && (m === "GET" || m === "PUT")) {
    return StorefrontViewSchema;
  }
  if (/^storefronts\/[^/]+\/public-catalog$/.test(rest) && m === "GET") {
    return PublicStorefrontCatalogSchema;
  }
  if (rest === "listings" && m === "GET") return ListingListSchema;
  if (/^listings\/[^/]+$/.test(rest) && (m === "GET" || m === "PUT")) {
    return ListingViewSchema;
  }
  if (rest === "marketplaces" && m === "GET") return MarketplaceListSchema;
  if (/^marketplaces\/[^/]+$/.test(rest) && m === "PUT") {
    return MarketplaceViewSchema;
  }
  if (/^marketplaces\/[^/]+\/sellers$/.test(rest) && m === "GET") {
    return SellerConnectionListSchema;
  }
  if (/^marketplaces\/[^/]+\/sellers\/[^/]+$/.test(rest) && m === "PUT") {
    return SellerConnectionViewSchema;
  }
  if (rest === "baskets/checkout" && m === "POST") {
    return BasketCheckoutViewSchema;
  }
  if (rest === "orders" && m === "GET") return MarketOrderListSchema;
  if (/^orders\/[^/]+$/.test(rest) && m === "GET") return MarketOrderViewSchema;
  if (/^orders\/[^/]+\/refund$/.test(rest) && m === "POST") {
    return MarketOrderViewSchema;
  }
  if (rest === "operator-fees" && m === "GET") return OperatorFeeListSchema;
  return null;
}

export function formatMarketMinor(minor: number, curr = "USD"): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100);
  const cents = String(abs % 100).padStart(2, "0");
  return `${sign}${whole}.${cents} ${curr}`;
}

export function canReadMarket(member: MembershipSummary | undefined): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation)) {
    return false;
  }
  return ["owner", "manager", "front_desk", "artist"].includes(member.role);
}

export function canManageMarket(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation)) {
    return false;
  }
  return member.role === "owner" || member.role === "manager";
}
