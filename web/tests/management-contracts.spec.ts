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

const groupId = "a9999999-9999-4999-8999-999999999999";
const groupsPath = `/v1/businesses/${businessId}/groups`;
const ownMembership = {
  membership_id: "a8888888-8888-4888-8888-888888888888",
  member_business_id: businessId,
  member_name: null,
  status: "invited",
  revision: 1,
  invited_at: "2026-10-04T12:00:00Z",
  decided_at: null,
  ended_at: null,
};
const memberView = {
  schema_version: 1,
  group_id: groupId,
  organizer_business_id: servicerId,
  organizer_name: "FAKE Holding Organizer",
  code: "FAKE_HOLDING",
  name: "FAKE Holding",
  role: "member",
  memberships: [ownMembership],
  created_at: "2026-10-04T12:00:00Z",
};

test("group lists never show a member other businesses' memberships", () => {
  const schema = managementResponseSchema(groupsPath, "GET");
  const page = {
    schema_version: 1,
    business_id: businessId,
    items: [memberView],
    next_cursor: null,
  };
  expect(schema.parse(page)).toEqual(page);
  expect(
    schema.safeParse({
      ...page,
      items: [
        {
          ...memberView,
          memberships: [
            ownMembership,
            { ...ownMembership, member_business_id: departmentId },
          ],
        },
      ],
    }).success,
  ).toBe(false);
});

for (const [suffix, method] of [
  ["", "GET"],
  ["", "PUT"],
  ["/accept", "POST"],
  ["/decline", "POST"],
  ["/leave", "POST"],
  [`/members/${servicerId}`, "PUT"],
  [`/members/${servicerId}/remove`, "POST"],
]) {
  test(`management boundary recognizes group ${method}${suffix}`, () => {
    const schema = managementResponseSchema(
      `${groupsPath}/${groupId}${suffix}`,
      method!,
    );
    expect(schema.parse(memberView)).toEqual(memberView);
    expect(
      schema.safeParse({ ...memberView, permissions: ["booking.read"] })
        .success,
    ).toBe(false);
  });
}

test("unknown group operations still fail closed", () => {
  for (const [path, method] of [
    [`${groupsPath}/${groupId}`, "DELETE"],
    [`${groupsPath}/${groupId}/accept`, "PUT"],
    [`${groupsPath}/${groupId}/members/${servicerId}`, "POST"],
    [`${groupsPath}/${groupId}/members/${servicerId}/remove`, "PUT"],
    [`${groupsPath}/${groupId}/share`, "POST"],
  ])
    expect(() => managementResponseSchema(path!, method!)).toThrow(
      "Unrecognized business response contract",
    );
});

const configurationPath = `/v1/businesses/${businessId}/configuration`;
const version = {
  schema_version: 1,
  business_id: businessId,
  version: 2,
  state: "published",
  revision: 3,
  profile_revision: 1,
  registry_version: 1,
  module_ids: ["booking_resources"],
  created_at: "2026-10-04T12:00:00Z",
  validation: { registry_version: 1, problems: [], warnings: [] },
  validated_at: "2026-10-04T12:01:00Z",
  published_at: "2026-10-04T12:02:00Z",
  superseded_at: null,
  superseded_by_version: null,
};

test("configuration views keep the published version consistent", () => {
  const schema = managementResponseSchema(configurationPath, "GET");
  const view = {
    schema_version: 1,
    business_id: businessId,
    registry_version: 1,
    baseline: false,
    published: version,
    latest: version,
    effective_module_ids: ["organization", "users_access", "booking_resources"],
  };
  expect(schema.parse(view)).toEqual(view);
  for (const broken of [
    { ...view, baseline: true },
    { ...view, published: { ...version, state: "draft" } },
    { ...view, latest: { ...version, business_id: servicerId } },
    { ...view, enabled_for: ["all"] },
  ])
    expect(schema.safeParse(broken).success).toBe(false);
});

for (const [suffix, method] of [
  ["/draft", "PUT"],
  ["/versions/2", "GET"],
  ["/versions/2/validate", "POST"],
  ["/versions/2/publish", "POST"],
]) {
  test(`management boundary recognizes configuration ${method}${suffix}`, () => {
    const schema = managementResponseSchema(
      `${configurationPath}${suffix}`,
      method!,
    );
    expect(schema.parse(version)).toEqual(version);
    expect(
      schema.safeParse({ ...version, permissions: ["business.manage"] })
        .success,
    ).toBe(false);
    expect(schema.safeParse({ ...version, state: "active" }).success).toBe(
      false,
    );
  });
}

test("module catalog never offers a core module as a choice", () => {
  const schema = managementResponseSchema(
    `/v1/businesses/${businessId}/module-catalog`,
    "GET",
  );
  const core = {
    id: "organization",
    name: "Organization and structure",
    kind: "core",
    depends_on: [],
    readiness: "technically_verified",
    enableable: false,
    limits: "FAKE limits",
    stops: "Always on.",
  };
  const catalog = {
    schema_version: 1,
    registry_version: 1,
    minimum_readiness: "technically_verified",
    modules: [core],
  };
  expect(schema.parse(catalog)).toEqual(catalog);
  expect(
    schema.safeParse({ ...catalog, modules: [{ ...core, enableable: true }] })
      .success,
  ).toBe(false);
  expect(schema.safeParse({ ...catalog, modules: [core, core] }).success).toBe(
    false,
  );
});

test("unknown configuration operations still fail closed", () => {
  for (const [path, method] of [
    [`${configurationPath}`, "PUT"],
    [`${configurationPath}/versions/2`, "DELETE"],
    [`${configurationPath}/versions/0/publish`, "POST"],
    [`${configurationPath}/versions/2/publish`, "PUT"],
    [`${configurationPath}/versions/2/rollback`, "POST"],
    [`${configurationPath}/draft`, "POST"],
  ])
    expect(() => managementResponseSchema(path!, method!)).toThrow(
      "Unrecognized business response contract",
    );
});
