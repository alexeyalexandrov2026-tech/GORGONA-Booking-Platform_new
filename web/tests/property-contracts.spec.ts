import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  canManageProperty,
  canReadProperty,
  KEEP_PARTY,
  NO_PARTY,
  parentOptions,
  propertyBody,
  propertyHistorySchema,
  propertyListSchema,
  propertyRevisionSchema,
  propertyViewSchema,
} from "../lib/property-contracts";

// PROPERTY-01 (catalog screen): strict contracts of the catalog routes, the command body (an
// omitted party keeps its value, null clears it) and who sees which part of the screen. FAKE data.
const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const base = `/v1/businesses/${uuid(1)}/property/objects`;
const view = {
  schema_version: 1,
  object_id: uuid(2),
  location_id: uuid(3),
  kind: "parcel",
  name: "FAKE parcel",
  parent_id: null,
  revision: 1,
  recorded_at: "2031-06-01T10:00:00Z",
} as const;
const saved = {
  ...view,
  recorded_by: uuid(4),
  owner_id: uuid(5),
  manager_id: null,
};

test("catalog responses are strict", () => {
  expect(propertyViewSchema.parse(view)).toEqual(view);
  expect(propertyRevisionSchema.parse(saved)).toEqual(saved);
  expect(
    propertyListSchema.parse({
      schema_version: 1,
      items: [view],
      next_cursor: null,
    }).items,
  ).toHaveLength(1);
  expect(
    propertyHistorySchema.parse({
      schema_version: 1,
      items: [saved],
      next_cursor: 1,
    }).next_cursor,
  ).toBe(1);
  // Private party fields never belong to the public view.
  expect(propertyViewSchema.safeParse(saved).success).toBe(false);
  expect(propertyViewSchema.safeParse({ ...view, kind: "room" }).success).toBe(
    false,
  );
  expect(propertyViewSchema.safeParse({ ...view, revision: 0 }).success).toBe(
    false,
  );
});

test("each catalog route has its contract", () => {
  const list = { schema_version: 1, items: [view], next_cursor: null };
  const history = { schema_version: 1, items: [saved], next_cursor: null };
  expect(managementResponseSchema(base, "GET").parse(list)).toEqual(list);
  expect(
    managementResponseSchema(`${base}?after=${uuid(2)}`, "GET").parse(list),
  ).toEqual(list);
  expect(
    managementResponseSchema(`${base}/${uuid(2)}`, "GET").parse(view),
  ).toEqual(view);
  expect(
    managementResponseSchema(`${base}/${uuid(2)}`, "PUT").parse(saved),
  ).toEqual(saved);
  expect(
    managementResponseSchema(`${base}/${uuid(2)}/history?after=1`, "GET").parse(
      history,
    ),
  ).toEqual(history);
  expect(
    managementResponseSchema(`${base}/${uuid(2)}`, "GET").safeParse(saved)
      .success,
  ).toBe(false);
});

test("an omitted party keeps its value and null clears only that role", () => {
  const edit = {
    expectedRevision: 2,
    locationId: uuid(3),
    kind: "unit" as const,
    name: "  FAKE unit  ",
    parentId: uuid(6),
  };
  expect(
    propertyBody({ ...edit, owner: KEEP_PARTY, manager: KEEP_PARTY }),
  ).toEqual({
    schema_version: 1,
    expected_revision: 2,
    location_id: uuid(3),
    kind: "unit",
    name: "FAKE unit",
    parent_id: uuid(6),
  });
  const cleared = propertyBody({
    ...edit,
    owner: KEEP_PARTY,
    manager: NO_PARTY,
  });
  expect(cleared).toHaveProperty("manager_id", null);
  expect(cleared).not.toHaveProperty("owner_id");
  expect(
    propertyBody({ ...edit, owner: uuid(7), manager: KEEP_PARTY }),
  ).toMatchObject({ owner_id: uuid(7) });
  // A new object has no stored party to keep or clear; "none" is simply omitted.
  const created = propertyBody({
    ...edit,
    expectedRevision: 0,
    kind: "parcel",
    owner: NO_PARTY,
    manager: uuid(8),
  });
  expect(created).not.toHaveProperty("owner_id");
  expect(created).toMatchObject({ parent_id: null, manager_id: uuid(8) });
});

test("parents follow the hierarchy within one branch", () => {
  const parcel = { ...view, object_id: uuid(10) };
  const elsewhere = { ...view, object_id: uuid(11), location_id: uuid(99) };
  const building = {
    ...view,
    object_id: uuid(12),
    kind: "building" as const,
    parent_id: uuid(10),
  };
  const items = [parcel, elsewhere, building];
  expect(parentOptions(items, "parcel", uuid(3))).toEqual([]);
  expect(parentOptions(items, "building", uuid(3))).toEqual([parcel]);
  expect(parentOptions(items, "unit", uuid(3))).toEqual([building]);
  expect(parentOptions(items, "unit", "")).toEqual([]);
  expect(parentOptions(items, "building", uuid(3), uuid(10))).toEqual([]);
});

test("company-wide owners and managers manage; a branch member only reads", () => {
  const active = { status: "active", location_id: null };
  expect(canManageProperty({ ...active, role: "owner" })).toBe(true);
  expect(canManageProperty({ ...active, role: "manager" })).toBe(true);
  const scoped = { ...active, role: "manager", location_id: uuid(3) };
  expect(canReadProperty(scoped)).toBe(true);
  expect(canManageProperty(scoped)).toBe(false);
  expect(canReadProperty({ ...active, role: "staff" })).toBe(false);
  expect(canReadProperty({ ...active, role: "owner", status: "invited" })).toBe(
    false,
  );
  expect(
    canReadProperty({ ...active, role: "manager", delegation: { id: 1 } }),
  ).toBe(false);
  expect(canReadProperty(undefined)).toBe(false);
});

test("operations parse strict listing and schedule projections", () => {
  const path = `/v1/businesses/${uuid(1)}/property`;
  const listing = {
    schema_version: 1,
    object_id: uuid(2),
    location_id: uuid(3),
    kind: "unit",
    revision: 1,
    state: "published",
    headline: "FAKE listing",
    description: null,
    monthly_rent: 125050,
    currency: "USD",
    available_from: "2032-01-10",
    recorded_at: "2031-06-01T10:00:00Z",
  };
  const listingRead = managementResponseSchema(
    `${path}/listings/${uuid(2)}`,
    "GET",
  );
  expect(listingRead?.safeParse(listing).success).toBe(true);
  expect(
    listingRead?.safeParse({ ...listing, monthly_rent: 1.5 }).success,
  ).toBe(false);
  const showing = {
    schema_version: 1,
    showing_id: uuid(4),
    object_id: uuid(2),
    location_id: uuid(3),
    host_resource_id: null,
    starts_at: "2032-01-12T15:00:00Z",
    ends_at: "2032-01-12T16:00:00Z",
    recorded_at: "2031-06-01T10:00:00Z",
    cancelled_at: null,
    status: "active",
  };
  const showingWrite = managementResponseSchema(
    `${path}/showings/${uuid(4)}`,
    "PUT",
  );
  expect(showingWrite?.safeParse(showing).success).toBe(true);
  expect(
    showingWrite?.safeParse({ ...showing, prospect_id: uuid(5) }).success,
  ).toBe(false);
});
