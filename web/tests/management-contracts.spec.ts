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
