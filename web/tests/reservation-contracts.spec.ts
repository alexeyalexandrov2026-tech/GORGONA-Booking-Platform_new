import { expect, test } from "@playwright/test";
import {
  reservationListSchema,
  reservationSchema,
} from "../lib/reservation-contracts";
import { managementResponseSchema } from "../lib/management-contracts";

const business = "00000000-0000-4000-8000-000000000001";
const subject = "00000000-0000-4000-8000-000000000002";
const location = "00000000-0000-4000-8000-000000000003";
const resource = "00000000-0000-4000-8000-000000000004";
const reservation = {
  schema_version: 1,
  business_id: business,
  reservation_id: subject,
  location_id: location,
  resource_ids: [resource],
  starts_at: "2026-10-06T14:00:00Z",
  ends_at: "2026-10-06T15:00:00Z",
  purpose: "FAKE training",
  status: "active",
  created_at: "2026-10-05T12:00:00Z",
  cancelled_at: null,
};

test("a reservation is consistent: interval, cancellation and resources", () => {
  expect(reservationSchema.safeParse(reservation).success).toBe(true);
  expect(
    reservationSchema.safeParse({
      ...reservation,
      status: "cancelled",
      cancelled_at: "2026-10-05T13:00:00Z",
    }).success,
  ).toBe(true);
  for (const change of [
    { ends_at: "2026-10-06T14:00:00Z" },
    { status: "cancelled" },
    { cancelled_at: "2026-10-05T13:00:00Z" },
    { resource_ids: [resource, resource] },
    { purpose: "" },
    { status: "held" },
    { customer: "FAKE" },
  ])
    expect(
      reservationSchema.safeParse({ ...reservation, ...change }).success,
    ).toBe(false);
  const page = {
    schema_version: 1,
    business_id: business,
    items: [reservation],
  };
  expect(reservationListSchema.safeParse(page).success).toBe(true);
  expect(
    reservationListSchema.safeParse({
      ...page,
      items: [reservation, reservation],
    }).success,
  ).toBe(false);
});

test("reservation routes have JSON contracts; unknown methods are refused", () => {
  const root = `/v1/businesses/${business}`;
  for (const [path, method] of [
    [`${root}/resource-reservations/${subject}`, "GET"],
    [`${root}/resource-reservations/${subject}`, "PUT"],
    [`${root}/resource-reservations/${subject}/cancel`, "POST"],
  ] as const)
    expect(
      managementResponseSchema(path, method).safeParse(reservation).success,
    ).toBe(true);
  expect(
    managementResponseSchema(
      `${root}/resource-reservations?starts=a&ends=b`,
      "GET",
    ).safeParse({ schema_version: 1, business_id: business, items: [] })
      .success,
  ).toBe(true);
  for (const [path, method] of [
    [`${root}/resource-reservations/${subject}`, "DELETE"],
    [`${root}/resource-reservations`, "POST"],
    [`${root}/resource-reservations/${subject}/confirm`, "POST"],
  ] as const)
    expect(() => managementResponseSchema(path, method)).toThrow(
      "Unrecognized business response contract",
    );
});
