import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const b2cItemKindSchema = z.enum([
  "product",
  "service",
  "package",
  "digital",
]);
export type B2CItemKind = z.infer<typeof b2cItemKindSchema>;

export const promoDiscountKindSchema = z.enum(["percent", "fixed_cents"]);
export type PromoDiscountKind = z.infer<typeof promoDiscountKindSchema>;

export const storefrontConfigSchema = z.object({
  configured: z.boolean(),
  public_slug: z.string().nullable().optional(),
  store_name: z.string().nullable().optional(),
  tagline: z.string().default(""),
  hero_image_url: z.string().nullable().optional(),
  accent_hex: z.string().default("#111111"),
  support_email: z.string().nullable().optional(),
  is_published: z.boolean().default(false),
  show_services: z.boolean().default(true),
  allow_promo_codes: z.boolean().default(true),
  updated_at: z.string().nullable().optional(),
});
export type StorefrontConfig = z.infer<typeof storefrontConfigSchema>;

export const storefrontItemSchema = z.object({
  id: z.string(),
  sku: z.string(),
  title: z.string(),
  category: z.string(),
  item_kind: b2cItemKindSchema,
  description: z.string(),
  price_cents: z.number().int(),
  compare_at_cents: z.number().int().nullable().optional(),
  currency: z.literal("USD"),
  image_url: z.string().nullable().optional(),
  stock_qty: z.number().int().nullable().optional(),
  is_active: z.boolean(),
  display_order: z.number().int(),
});
export type StorefrontItem = z.infer<typeof storefrontItemSchema>;

export const promoCodeSchema = z.object({
  id: z.string(),
  code: z.string(),
  discount_kind: promoDiscountKindSchema,
  discount_value: z.number().int(),
  min_subtotal_cents: z.number().int(),
  max_redemptions: z.number().int().nullable().optional(),
  redemptions_count: z.number().int(),
  expires_at: z.string().nullable().optional(),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type PromoCode = z.infer<typeof promoCodeSchema>;

export const b2cOrderSchema = z.object({
  id: z.string(),
  order_number: z.string(),
  customer_name: z.string(),
  customer_email: z.string(),
  items: z.array(z.record(z.string(), z.unknown())),
  subtotal_cents: z.number().int(),
  discount_cents: z.number().int(),
  total_cents: z.number().int(),
  promo_code: z.string().nullable().optional(),
  currency: z.literal("USD"),
  status: z.enum([
    "checkout_open",
    "paid",
    "fulfilled",
    "cancelled",
    "refunded",
  ]),
  stripe_session_id: z.string().nullable().optional(),
  checkout_url: z.string().nullable().optional(),
  created_at: z.string(),
});
export type B2COrder = z.infer<typeof b2cOrderSchema>;

export const publicShopCatalogSchema = z.object({
  public_slug: z.string(),
  store_name: z.string(),
  tagline: z.string(),
  hero_image_url: z.string().nullable().optional(),
  accent_hex: z.string(),
  support_email: z.string().nullable().optional(),
  allow_promo_codes: z.boolean(),
  items: z.array(storefrontItemSchema),
});
export type PublicShopCatalog = z.infer<typeof publicShopCatalogSchema>;

export const publicQuoteCartSchema = z.object({
  lines: z.array(
    z.object({
      item_id: z.string(),
      sku: z.string(),
      title: z.string(),
      unit_price_cents: z.number().int(),
      quantity: z.number().int(),
      line_total_cents: z.number().int(),
    }),
  ),
  subtotal_cents: z.number().int(),
  discount_cents: z.number().int(),
  total_cents: z.number().int(),
  applied_promo_code: z.string().nullable().optional(),
  promo_message: z.string().nullable().optional(),
});
export type PublicQuoteCart = z.infer<typeof publicQuoteCartSchema>;

function builderBase(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/storefront-builder`;
}

async function parseJson<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  let data: unknown;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail =
      data &&
      typeof data === "object" &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (HTTP ${response.status}).`;
    throw new ManagementApiError("REQUEST_FAILED", detail, response.status);
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "B2C Storefront returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchStorefrontConfig(
  businessId: string,
): Promise<StorefrontConfig> {
  const res = await authorizedResponse(`${builderBase(businessId)}/config`, {
    headers: { Accept: "application/json" },
  });
  return parseJson(res, storefrontConfigSchema);
}

export async function saveStorefrontConfig(
  businessId: string,
  input: {
    public_slug: string;
    store_name: string;
    tagline: string;
    hero_image_url?: string | null;
    accent_hex: string;
    support_email?: string | null;
    is_published: boolean;
    show_services: boolean;
    allow_promo_codes: boolean;
  },
): Promise<StorefrontConfig> {
  const res = await authorizedResponse(`${builderBase(businessId)}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return parseJson(res, storefrontConfigSchema);
}

export async function fetchStorefrontItems(
  businessId: string,
): Promise<StorefrontItem[]> {
  const res = await authorizedResponse(`${builderBase(businessId)}/items`, {
    headers: { Accept: "application/json" },
  });
  return parseJson(res, z.array(storefrontItemSchema));
}

export async function createStorefrontItem(
  businessId: string,
  input: {
    sku: string;
    title: string;
    category: string;
    item_kind: B2CItemKind;
    description: string;
    price_cents: number;
    compare_at_cents?: number | null;
    stock_qty?: number | null;
  },
): Promise<StorefrontItem> {
  const res = await authorizedResponse(`${builderBase(businessId)}/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return parseJson(res, storefrontItemSchema);
}

export async function deleteStorefrontItem(
  businessId: string,
  itemId: string,
): Promise<void> {
  await authorizedResponse(
    `${builderBase(businessId)}/items/${encodeURIComponent(itemId)}`,
    { method: "DELETE" },
  );
}

export async function syncServicesToStorefront(
  businessId: string,
): Promise<{ synced_count: number }> {
  const res = await authorizedResponse(
    `${builderBase(businessId)}/sync-services`,
    { method: "POST", headers: { Accept: "application/json" } },
  );
  return parseJson(res, z.object({ synced_count: z.number().int() }));
}

export async function fetchStorefrontPromos(
  businessId: string,
): Promise<PromoCode[]> {
  const res = await authorizedResponse(`${builderBase(businessId)}/promos`, {
    headers: { Accept: "application/json" },
  });
  return parseJson(res, z.array(promoCodeSchema));
}

export async function createStorefrontPromo(
  businessId: string,
  input: {
    code: string;
    discount_kind: PromoDiscountKind;
    discount_value: number;
    min_subtotal_cents: number;
    max_redemptions?: number | null;
  },
): Promise<PromoCode> {
  const res = await authorizedResponse(`${builderBase(businessId)}/promos`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return parseJson(res, promoCodeSchema);
}

export async function deleteStorefrontPromo(
  businessId: string,
  promoId: string,
): Promise<void> {
  await authorizedResponse(
    `${builderBase(businessId)}/promos/${encodeURIComponent(promoId)}`,
    { method: "DELETE" },
  );
}

export async function fetchB2COrders(businessId: string): Promise<B2COrder[]> {
  const res = await authorizedResponse(`${builderBase(businessId)}/orders`, {
    headers: { Accept: "application/json" },
  });
  return parseJson(res, z.array(b2cOrderSchema));
}

export async function fetchPublicShopCatalog(
  slug: string,
): Promise<PublicShopCatalog> {
  const res = await fetch(`/v1/public/shop/${encodeURIComponent(slug)}`, {
    headers: { Accept: "application/json" },
  });
  return parseJson(res, publicShopCatalogSchema);
}

export async function quotePublicShopCart(
  slug: string,
  items: { item_id: string; quantity: number }[],
  promoCode?: string,
): Promise<PublicQuoteCart> {
  const res = await fetch(
    `/v1/public/shop/${encodeURIComponent(slug)}/quote-cart`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        items,
        promo_code: promoCode?.trim() || undefined,
      }),
    },
  );
  return parseJson(res, publicQuoteCartSchema);
}

export async function submitPublicShopCheckout(
  slug: string,
  input: {
    customer_name: string;
    customer_email: string;
    items: { item_id: string; quantity: number }[];
    promo_code?: string;
  },
): Promise<B2COrder> {
  const res = await fetch(
    `/v1/public/shop/${encodeURIComponent(slug)}/checkout`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return parseJson(res, b2cOrderSchema);
}
