import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";

// L7a: the catalog answers of package L, checked by path before a screen reads them.
const salon = "a1111111-1111-4111-8111-111111111111";
const variant = "b1111111-1111-4111-8111-111111111111";
const item = "c1111111-1111-4111-8111-111111111111";
const service = {
  id: variant,
  service_id: "d1111111-1111-4111-8111-111111111111",
  code: "FAKE_COLOUR",
  name: "FAKE colour",
  status: "published",
  price_cents: 9000,
  currency: "USD",
  booking_duration_minutes: 110,
  is_bookable: true,
  revision: 3,
  stages: [
    {
      position: 1,
      kind: "active",
      minutes: 30,
      resources: ["specialist", "chair"],
    },
    {
      position: 2,
      kind: "processing",
      minutes: 60,
      resources: ["chair", "equipment"],
    },
    {
      position: 3,
      kind: "finish",
      minutes: 20,
      resources: ["specialist", "chair"],
    },
  ],
};
const recipe = {
  owner_id: variant,
  owner_revision: 4,
  lines: [{ item_id: item, quantity: "2.5" }],
};

test("a service with stages parses and a stage of an unknown kind is refused", () => {
  const schema = managementResponseSchema(
    `/v1/salons/${salon}/services/${variant}/stages`,
    "PUT",
  );
  expect(schema.parse(service)).toMatchObject({ stages: service.stages });
  const bad = { ...service, stages: [{ ...service.stages[0], kind: "rest" }] };
  expect(schema.safeParse(bad).success).toBe(false);
});

test("a recipe is read and written with its own strict contract", () => {
  for (const method of ["GET", "PUT"]) {
    const schema = managementResponseSchema(
      `/v1/salons/${salon}/services/${variant}/materials`,
      method,
    );
    expect(schema.parse(recipe)).toEqual(recipe);
    expect(schema.safeParse({ ...recipe, extra: 1 }).success).toBe(false);
    expect(
      schema.safeParse({
        ...recipe,
        lines: [{ item_id: item, quantity: "2.5555" }],
      }).success,
    ).toBe(false);
  }
});

test("equipment is a resource kind of the staff list", () => {
  const schema = managementResponseSchema(`/v1/salons/${salon}/staff`, "GET");
  const row = {
    id: item,
    location_id: salon,
    kind: "equipment",
    display_name: "FAKE processor",
    is_active: true,
  };
  expect(schema.safeParse([row]).success).toBe(true);
});
