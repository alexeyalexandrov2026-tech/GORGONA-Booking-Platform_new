import { expect, test } from "@playwright/test";
import {
  formatMarketMinor,
  marketResponseSchema,
  MarketplaceViewSchema,
  OperatorFeeViewSchema,
  PublicStorefrontCatalogSchema,
} from "../lib/market-contracts";

const UID = "0196f800-0000-7000-8000-000000000001";
const NOW = "2026-10-10T12:00:00Z";

test("marketResponseSchema routes all MARKET-01 endpoints and rejects unknown paths", () => {
  expect(marketResponseSchema("/market/storefronts", "GET")).toBeTruthy();
  expect(
    marketResponseSchema(`/market/storefronts/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(
    marketResponseSchema(`/market/storefronts/${UID}/public-catalog`, "GET"),
  ).toBeTruthy();
  expect(marketResponseSchema("/market/listings", "GET")).toBeTruthy();
  expect(marketResponseSchema(`/market/listings/${UID}`, "PUT")).toBeTruthy();
  expect(marketResponseSchema("/market/marketplaces", "GET")).toBeTruthy();
  expect(
    marketResponseSchema(`/market/marketplaces/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(
    marketResponseSchema(`/market/marketplaces/${UID}/sellers`, "GET"),
  ).toBeTruthy();
  expect(
    marketResponseSchema(`/market/marketplaces/${UID}/sellers/${UID}`, "PUT"),
  ).toBeTruthy();
  expect(marketResponseSchema("/market/baskets/checkout", "POST")).toBeTruthy();
  expect(marketResponseSchema("/market/orders", "GET")).toBeTruthy();
  expect(
    marketResponseSchema(`/market/orders/${UID}/refund`, "POST"),
  ).toBeTruthy();
  expect(marketResponseSchema("/market/operator-fees", "GET")).toBeTruthy();
  expect(marketResponseSchema("/market/unknown", "GET")).toBeNull();
});

test("zero GORGONA commission is strictly enforced by MarketplaceView and OperatorFeeView", () => {
  const mp = MarketplaceViewSchema.parse({
    schema_version: 1,
    marketplace_id: UID,
    location_id: UID,
    slug: "midwest-b2b",
    title: "Midwest B2B",
    description: null,
    gorgona_commission_bps: 0,
    operator_fee_bps: 300,
    is_active: true,
    revision: 1,
    recorded_by: UID,
    recorded_at: NOW,
  });
  expect(mp.gorgona_commission_bps).toBe(0);
  expect(() =>
    MarketplaceViewSchema.parse({ ...mp, gorgona_commission_bps: 10 }),
  ).toThrow();

  const fee = OperatorFeeViewSchema.parse({
    schema_version: 1,
    fee_id: UID,
    location_id: UID,
    marketplace_id: UID,
    order_id: UID,
    seller_counterparty_id: UID,
    currency: "USD",
    gorgona_commission_minor: 0,
    operator_fee_minor: 1200,
    status: "accrued",
    recorded_by: UID,
    recorded_at: NOW,
  });
  expect(fee.gorgona_commission_minor).toBe(0);
  expect(() =>
    OperatorFeeViewSchema.parse({ ...fee, gorgona_commission_minor: 1 }),
  ).toThrow();

  const cat = PublicStorefrontCatalogSchema.parse({
    schema_version: 1,
    storefront_slug: "alpha-shop",
    display_name: "Alpha Shop",
    published_fields: ["title", "price", "currency"],
    items: [
      {
        schema_version: 1,
        listing_id: UID,
        storefront_slug: "alpha-shop",
        seller_display_name: "Alpha Shop",
        published_fields: ["title", "price", "currency"],
        fields: { title: "Motor", price: 20000, currency: "USD" },
      },
    ],
  });
  expect(cat.items).toHaveLength(1);
  expect(formatMarketMinor(40000, "USD")).toBe("400.00 USD");
});
