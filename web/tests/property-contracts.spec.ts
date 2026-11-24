import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  canManageProperty,
  canReadProperty,
  KEEP_PARTY,
  NO_PARTY,
  contractorWorkLinkSchema,
  formatMinorUnits,
  parentOptions,
  parseMinorUnits,
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

test("lease, term and move-in responses stay strict", () => {
  const path = `/v1/businesses/${uuid(1)}/property`;
  const lease = {
    schema_version: 1,
    lease_id: uuid(8),
    object_id: uuid(2),
    agreement_id: uuid(9),
    agreement_revision: 2,
    document_id: uuid(10),
    document_revision: 1,
    signed_on: "2026-10-01",
    starts_on: "2026-01-01",
    ends_on: "2026-12-31",
    recorded_at: "2031-06-01T10:00:00Z",
  };
  const list = { schema_version: 1, items: [lease], next_cursor: null };
  expect(
    managementResponseSchema(
      `${path}/leases?object_id=${uuid(2)}`,
      "GET",
    ).parse(list),
  ).toEqual(list);
  expect(
    managementResponseSchema(`${path}/leases/${uuid(8)}`, "PUT").parse(lease),
  ).toEqual(lease);
  expect(
    managementResponseSchema(`${path}/leases/${uuid(8)}`, "GET").safeParse({
      ...lease,
      title: "FAKE",
    }).success,
  ).toBe(false);
  const term = {
    schema_version: 1,
    lease_id: uuid(8),
    revision: 2,
    action: "extend",
    agreement_revision: 4,
    document_id: uuid(11),
    document_revision: 1,
    terminated_on: null,
    starts_on: "2026-01-01",
    ends_on: "2027-06-30",
    recorded_at: "2031-06-02T10:00:00Z",
  };
  const history = { schema_version: 1, items: [term], next_before: null };
  expect(
    managementResponseSchema(`${path}/leases/${uuid(8)}/terms`, "GET").parse(
      history,
    ),
  ).toEqual(history);
  expect(
    managementResponseSchema(`${path}/leases/${uuid(8)}/terms`, "POST").parse(
      term,
    ),
  ).toEqual(term);
  const moveIn = {
    schema_version: 1,
    lease_id: uuid(8),
    term_revision: 2,
    moved_in_on: "2026-11-15",
    report: { document_id: uuid(12), revision: 1 },
    photos: [{ document_id: uuid(13), revision: 1 }],
    recorded_by: uuid(4),
    recorded_at: "2031-06-02T10:00:00Z",
  };
  const recorded = managementResponseSchema(
    `${path}/leases/${uuid(8)}/move-in`,
    "PUT",
  );
  expect(recorded.parse(moveIn)).toEqual(moveIn);
  expect(recorded.safeParse({ ...moveIn, photos: [] }).success).toBe(false);
});

test("move-out, maintenance and contractor work order contracts stay strict", () => {
  const path = `/v1/businesses/${uuid(1)}/property`;
  const moveOut = {
    schema_version: 1,
    lease_id: uuid(8),
    term_revision: 2,
    moved_out_on: "2026-12-31",
    condition_summary: "damage_noted",
    note: "Scuffed baseboard in hallway",
    report: { document_id: uuid(14), revision: 1 },
    photos: [{ document_id: uuid(15), revision: 1 }],
    recorded_by: uuid(4),
    recorded_at: "2031-06-05T10:00:00Z",
  };
  const moveOutRoute = managementResponseSchema(
    `${path}/leases/${uuid(8)}/move-out`,
    "PUT",
  );
  expect(moveOutRoute.parse(moveOut)).toEqual(moveOut);
  expect(
    moveOutRoute.safeParse({ ...moveOut, condition_summary: "destroyed" })
      .success,
  ).toBe(false);
  expect(moveOutRoute.safeParse({ ...moveOut, photos: [] }).success).toBe(
    false,
  );

  const req = {
    schema_version: 1,
    request_id: uuid(20),
    object_id: uuid(2),
    location_id: uuid(3),
    object_kind: "unit",
    lease_id: null,
    category: "plumbing",
    priority: "urgent",
    title: "FAKE kitchen leak",
    description: "Leak under sink",
    revision: 3,
    state: "assigned",
    approved_limit_minor: 25050,
    currency: "USD",
    contractor_id: uuid(21),
    recorded_by: uuid(4),
    recorded_at: "2031-06-05T10:00:00Z",
  };
  expect(
    managementResponseSchema(
      `${path}/maintenance?object_id=${uuid(2)}`,
      "GET",
    ).parse({
      schema_version: 1,
      items: [req],
      next_after: null,
    }),
  ).toMatchObject({ items: [req] });
  expect(
    managementResponseSchema(`${path}/maintenance/${uuid(20)}`, "PUT").parse(
      req,
    ),
  ).toEqual(req);
  expect(
    managementResponseSchema(
      `${path}/maintenance/${uuid(20)}/events`,
      "POST",
    ).parse(req),
  ).toEqual(req);

  const event = {
    schema_version: 1,
    request_id: uuid(20),
    revision: 2,
    action: "approve",
    approved_limit_minor: 25050,
    currency: "USD",
    contractor_id: null,
    note: "Approved up to limit",
    recorded_by: uuid(4),
    recorded_at: "2031-06-05T10:05:00Z",
  };
  expect(
    managementResponseSchema(
      `${path}/maintenance/${uuid(20)}/events`,
      "GET",
    ).parse({
      schema_version: 1,
      items: [event],
      next_before: null,
    }),
  ).toMatchObject({ items: [event] });

  const obligation = {
    schema_version: 1,
    request_id: uuid(20),
    number: 1,
    book_id: uuid(22),
    invoice_document_id: uuid(23),
    obligation_id: uuid(24),
    amount_minor: 15000,
    currency: "USD",
    note: "Parts invoice",
    recorded_by: uuid(4),
    recorded_at: "2031-06-05T11:00:00Z",
  };
  expect(
    managementResponseSchema(
      `${path}/maintenance/${uuid(20)}/obligations`,
      "GET",
    ).parse({
      schema_version: 1,
      items: [obligation],
    }),
  ).toMatchObject({ items: [obligation] });

  const company = {
    schema_version: 1,
    request_id: uuid(20),
    revision: 1,
    contractor_id: uuid(21),
    company_id: uuid(25),
    created_by: uuid(4),
    created_at: "2031-06-05T10:10:00Z",
  };
  expect(
    managementResponseSchema(
      `${path}/maintenance/${uuid(20)}/contractor-company`,
      "PUT",
    ).parse(company),
  ).toEqual(company);

  const update = {
    schema_version: 1,
    request_id: uuid(20),
    number: 1,
    kind: "in_progress",
    note: "Shut off valve and replacing trap",
    company_id: uuid(25),
    company_name: "FAKE Plumbing Co",
    grant_id: uuid(26),
    binding_revision: 1,
    recorded_by: uuid(27),
    created_at: "2031-06-05T10:15:00Z",
  };
  expect(
    managementResponseSchema(
      `${path}/maintenance/${uuid(20)}/contractor-work/${uuid(26)}/updates`,
      "POST",
    ).parse(update),
  ).toEqual(update);

  const workOrder = {
    schema_version: 1,
    request_id: uuid(20),
    object_id: uuid(2),
    object_name: "FAKE unit",
    object_kind: "unit",
    location_id: uuid(3),
    category: "plumbing",
    priority: "urgent",
    title: "FAKE kitchen leak",
    description: "Leak under sink",
    state: "assigned",
    revision: 3,
    binding_revision: 1,
    contractor_company_id: uuid(25),
    updates: [update],
  };
  const workOrderRoute = managementResponseSchema(
    `${path}/maintenance/${uuid(20)}/contractor-work/${uuid(26)}`,
    "GET",
  );
  expect(workOrderRoute.parse(workOrder)).toEqual(workOrder);
  // Private budget and lease fields must never appear on the contractor work order view.
  expect(
    workOrderRoute.safeParse({ ...workOrder, approved_limit_minor: 25050 })
      .success,
  ).toBe(false);
  expect(
    workOrderRoute.safeParse({ ...workOrder, lease_id: uuid(8) }).success,
  ).toBe(false);

  expect(
    contractorWorkLinkSchema.parse({
      business: uuid(1),
      request: uuid(20),
      grant: uuid(26),
    }),
  ).toEqual({ business: uuid(1), request: uuid(20), grant: uuid(26) });
  expect(parseMinorUnits("250.50")).toBe(25050);
  expect(parseMinorUnits("100")).toBe(10000);
  expect(parseMinorUnits("0")).toBeNull();
  expect(parseMinorUnits("-5")).toBeNull();
  expect(parseMinorUnits("1.999")).toBeNull();
  expect(formatMinorUnits(25050, "USD")).toBe("250.50 USD");
});
