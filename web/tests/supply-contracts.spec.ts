import { expect, test } from "@playwright/test";
import {
  GoodsOwnerListSchema,
  OrderReturnListSchema,
  OrderShipmentListSchema,
  TradeOrderListSchema,
  WorkOrderListSchema,
  canManageSupply,
  canReadSupply,
  canWorkSupply,
  formatSupplyMinor,
  supplyResponseSchema,
} from "../lib/supply-contracts";

const SAMPLE_UUID = "0195b3c4-7d8e-7000-8000-000000000001";

test("supplyResponseSchema resolves WMS, manufacturing, and trade routes", () => {
  expect(supplyResponseSchema("/supply/owners", "GET")).toBe(
    GoodsOwnerListSchema,
  );
  expect(supplyResponseSchema("/supply/work-orders", "GET")).toBe(
    WorkOrderListSchema,
  );
  expect(supplyResponseSchema("/supply/orders", "GET")).toBe(
    TradeOrderListSchema,
  );
  expect(
    supplyResponseSchema(`/supply/orders/${SAMPLE_UUID}/shipments`, "GET"),
  ).toBe(OrderShipmentListSchema);
  expect(
    supplyResponseSchema(`/supply/orders/${SAMPLE_UUID}/returns`, "GET"),
  ).toBe(OrderReturnListSchema);
  expect(supplyResponseSchema("/projects/matters", "GET")).toBeNull();
});

test("supply role gates reject delegated memberships and format currency minor units", () => {
  expect(canReadSupply(undefined)).toBe(false);
  expect(canReadSupply({ role: "owner", delegated: true })).toBe(false);
  expect(canReadSupply({ role: "manager", delegation: { id: "1" } })).toBe(
    false,
  );
  expect(canWorkSupply({ role: "front_desk" })).toBe(true);
  expect(canManageSupply({ role: "front_desk" })).toBe(false);
  expect(canManageSupply({ role: "manager" })).toBe(true);
  expect(formatSupplyMinor(35000, "USD")).toBe("350.00 USD");
});
