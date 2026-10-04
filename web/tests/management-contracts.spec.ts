import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";

// Explicit fixture values for boundary tests, never business defaults.
const businessId = "a1111111-1111-4111-8111-111111111111";
const entityId = "e1111111-1111-4111-8111-111111111111";
const collection = `/v1/businesses/${businessId}/legal-entities`;
const entity = {
  schema_version: 1,
  business_id: businessId,
  legal_entity_id: entityId,
  code: "FAKE_LLC",
  legal_name: "FAKE Contract Test LLC",
  revision: 2,
  state: "draft",
  created_at: "2026-10-04T12:00:00Z",
};

test("management boundary recognizes paginated legal-entity lists", () => {
  const page = {
    schema_version: 1,
    business_id: businessId,
    items: [entity],
    next_cursor: "FAKE_LLC",
  };
  const schema = managementResponseSchema(`${collection}?after=FAKE_A`, "GET");
  expect(schema.parse(page)).toEqual(page);
  expect(schema.safeParse({ ...page, items: [entity, entity] }).success).toBe(
    false,
  );
  expect(
    schema.safeParse({
      ...page,
      items: [
        { ...entity, business_id: "b1111111-1111-4111-8111-111111111111" },
      ],
    }).success,
  ).toBe(false);
});

for (const [method, query] of [
  ["GET", ""],
  ["GET", "?revision=2"],
  ["PUT", ""],
]) {
  test(`management boundary recognizes legal-entity ${method}${query}`, () => {
    const schema = managementResponseSchema(
      `${collection}/${entityId}${query}`,
      method!,
    );
    expect(schema.parse(entity)).toEqual(entity);
    expect(schema.safeParse({ ...entity, state: "active" }).success).toBe(
      false,
    );
    expect(
      schema.safeParse({ ...entity, registration_verified: true }).success,
    ).toBe(false);
  });
}

test("unknown legal-entity operations still fail closed", () => {
  for (const [path, method] of [
    [collection, "PUT"],
    [`${collection}/${entityId}`, "DELETE"],
    [`${collection}/${entityId}/publish`, "PUT"],
    [`${collection}/not-an-id`, "GET"],
  ])
    expect(() => managementResponseSchema(path!, method!)).toThrow(
      "Unrecognized business response contract",
    );
});

const departmentId = "d1111111-1111-4111-8111-111111111111";
const departments = `/v1/businesses/${businessId}/departments`;
const department = {
  schema_version: 1,
  business_id: businessId,
  department_id: departmentId,
  code: "FAKE_OPS",
  name: "FAKE Contract Test Operations",
  parent_department_id: null,
  legal_entity_id: entityId,
  location_id: null,
  archived: false,
  revision: 3,
  state: "draft",
  created_at: "2026-10-04T12:00:00Z",
};

test("management boundary recognizes paginated department lists", () => {
  const page = {
    schema_version: 1,
    business_id: businessId,
    items: [department],
    next_cursor: null,
  };
  const schema = managementResponseSchema(`${departments}?after=FAKE_A`, "GET");
  expect(schema.parse(page)).toEqual(page);
  expect(
    schema.safeParse({ ...page, items: [department, department] }).success,
  ).toBe(false);
  expect(
    schema.safeParse({
      ...page,
      items: [
        { ...department, business_id: "b1111111-1111-4111-8111-111111111111" },
      ],
    }).success,
  ).toBe(false);
});

for (const [method, query] of [
  ["GET", ""],
  ["GET", "?revision=3"],
  ["PUT", ""],
]) {
  test(`management boundary recognizes department ${method}${query}`, () => {
    const schema = managementResponseSchema(
      `${departments}/${departmentId}${query}`,
      method!,
    );
    expect(schema.parse(department)).toEqual(department);
    for (const changed of [
      { state: "published" },
      { parent_department_id: departmentId },
      { archived: "false" },
      { head_user_id: departmentId },
    ])
      expect(schema.safeParse({ ...department, ...changed }).success).toBe(
        false,
      );
    const missingLink: Record<string, unknown> = { ...department };
    delete missingLink.location_id;
    expect(schema.safeParse(missingLink).success).toBe(false);
  });
}

test("unknown department operations still fail closed", () => {
  for (const [path, method] of [
    [departments, "PUT"],
    [`${departments}/${departmentId}`, "DELETE"],
    [`${departments}/${departmentId}/archive`, "POST"],
    [`${departments}/not-an-id`, "GET"],
  ])
    expect(() => managementResponseSchema(path!, method!)).toThrow(
      "Unrecognized business response contract",
    );
});

const grantId = "f1111111-1111-4111-8111-111111111111";
const servicerId = "b2222222-2222-4222-8222-222222222222";
const grants = `/v1/businesses/${businessId}/delegations`;
const grant = {
  schema_version: 1,
  grant_id: grantId,
  owner_business_id: businessId,
  owner_name: "FAKE Owner Business",
  servicer_business_id: servicerId,
  servicer_name: "FAKE Dispatch Business",
  permissions: ["booking.read", "booking.write"],
  location_id: null,
  expires_at: "2026-11-04T12:00:00Z",
  status: "active",
  expired: false,
  revision: 2,
  revoked_by_side: null,
  delegates: [
    {
      user_id: "c3333333-3333-4333-8333-333333333333",
      display_name: "FAKE Delegate",
      added_at: "2026-10-04T12:00:00Z",
    },
  ],
  created_at: "2026-10-04T12:00:00Z",
};

test("management boundary recognizes delegation lists for either party", () => {
  const page = {
    schema_version: 1,
    business_id: businessId,
    items: [grant],
    next_cursor: null,
  };
  const schema = managementResponseSchema(grants, "GET");
  expect(schema.parse(page)).toEqual(page);
  expect(schema.safeParse({ ...page, items: [grant, grant] }).success).toBe(
    false,
  );
  // A list for one business never carries a relationship it is not part of.
  expect(schema.safeParse({ ...page, business_id: departmentId }).success).toBe(
    false,
  );
});

for (const [suffix, method] of [
  ["", "GET"],
  ["", "PUT"],
  ["/accept", "POST"],
  ["/decline", "POST"],
  ["/revoke", "POST"],
  ["/delegates", "PUT"],
]) {
  test(`management boundary recognizes delegation ${method}${suffix}`, () => {
    const schema = managementResponseSchema(
      `${grants}/${grantId}${suffix}`,
      method!,
    );
    expect(schema.parse(grant)).toEqual(grant);
    for (const changed of [
      { permissions: ["members.manage"] },
      { status: "revoked" },
      { revoked_by_side: "owner" },
      { servicer_business_id: businessId },
      { shared_account: true },
    ])
      expect(schema.safeParse({ ...grant, ...changed }).success).toBe(false);
  });
}

test("unknown delegation operations still fail closed", () => {
  for (const [path, method] of [
    [`${grants}/${grantId}`, "DELETE"],
    [`${grants}/${grantId}/delegates`, "POST"],
    [`${grants}/${grantId}/accept`, "PUT"],
    [`${grants}/${grantId}/suspend`, "POST"],
    [`${grants}/not-an-id`, "GET"],
  ])
    expect(() => managementResponseSchema(path!, method!)).toThrow(
      "Unrecognized business response contract",
    );
});

test("account view lists delegated businesses separately from memberships", () => {
  const schema = managementResponseSchema("/v1/me", "GET");
  const me = {
    user_id: "c3333333-3333-4333-8333-333333333333",
    display_name: "FAKE Delegate",
    platform_roles: [],
    memberships: [
      {
        salon_id: servicerId,
        salon_name: "FAKE Dispatch Business",
        role: "front_desk",
        status: "active",
        location_id: null,
      },
    ],
    delegations: [
      {
        business_id: businessId,
        business_name: "FAKE Owner Business",
        grant_id: grantId,
        servicer_business_id: servicerId,
        servicer_name: "FAKE Dispatch Business",
        permissions: ["booking.read"],
        location_id: null,
        expires_at: "2026-11-04T12:00:00Z",
      },
    ],
  };
  expect(schema.parse(me)).toEqual(me);
  expect(
    schema.safeParse({
      ...me,
      delegations: [{ ...me.delegations[0], role: "owner" }],
    }).success,
  ).toBe(false);
  expect(
    managementResponseSchema(`/v1/salons/${servicerId}/members`, "GET").parse(
      [],
    ),
  ).toEqual([]);
});
