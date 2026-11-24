import { expect, test } from "@playwright/test";
import {
  canManageRestaurant,
  canOperateKitchen,
  canReadRestaurant,
  canRunCompanyFinance,
  canRunService,
  formatMinor,
  parseMajorToMinor,
} from "../lib/restaurant-contracts";

test.describe("restaurant-contracts", () => {
  test("enforces role capabilities and delegation exclusions", () => {
    const base = { status: "active", location_id: null, delegation: null };
    expect(canReadRestaurant({ ...base, role: "artist" })).toBe(true);
    expect(canOperateKitchen({ ...base, role: "artist" })).toBe(true);
    expect(canRunService({ ...base, role: "artist" })).toBe(false);
    expect(canRunService({ ...base, role: "front_desk" })).toBe(true);
    expect(canManageRestaurant({ ...base, role: "front_desk" })).toBe(false);
    expect(canManageRestaurant({ ...base, role: "manager" })).toBe(true);
    expect(canRunCompanyFinance({ ...base, role: "manager" })).toBe(true);
    expect(
      canRunCompanyFinance({ ...base, role: "manager", location_id: "loc-1" }),
    ).toBe(false);
    expect(
      canReadRestaurant({
        ...base,
        role: "owner",
        delegation: {
          grant_id: "g",
          owner_business_id: "b",
          owner_business_name: "B",
          location_id: null,
          permissions: ["booking.read"],
          expires_at: null,
        },
      }),
    ).toBe(false);
    expect(canReadRestaurant(undefined)).toBe(false);
  });

  test("formats and parses minor-unit currency values accurately", () => {
    expect(formatMinor(1590, "USD")).toBe("15.90 USD");
    expect(formatMinor(-150, "USD")).toBe("-1.50 USD");
    expect(formatMinor(0, "EUR")).toBe("0.00 EUR");
    expect(parseMajorToMinor("15.90")).toBe(1590);
    expect(parseMajorToMinor("12")).toBe(1200);
    expect(parseMajorToMinor("-1.5")).toBe(-150);
    expect(parseMajorToMinor("12.345")).toBeNull();
    expect(parseMajorToMinor("abc")).toBeNull();
  });
});
