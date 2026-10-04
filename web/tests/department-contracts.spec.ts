import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";

const businessId = "a1111111-1111-4111-8111-111111111111";
const departmentId = "d1111111-1111-4111-8111-111111111111";
const collection = `/v1/businesses/${businessId}/departments`;
const department = {
  schema_version: 1,
  business_id: businessId,
  department_id: departmentId,
  code: "FAKE_DEPARTMENT",
  name: "FAKE Contract Test Department",
  revision: 2,
  state: "draft",
  parent_department_id: null,
  location_id: null,
  legal_entity_id: null,
  created_at: "2026-10-04T12:00:00Z",
};

test("department collection rejects mixed businesses and duplicate identities", () => {
  const schema = managementResponseSchema(collection, "GET");
  const page = {
    schema_version: 1,
    business_id: businessId,
    items: [department],
    next_cursor: null,
  };
  expect(schema.parse(page)).toEqual(page);
  expect(
    schema.safeParse({ ...page, items: [department, department] }).success,
  ).toBe(false);
  expect(
    schema.safeParse({
      ...page,
      items: [{ ...department, business_id: departmentId }],
    }).success,
  ).toBe(false);
});

for (const method of ["GET", "PUT"]) {
  test(`department ${method} validates nullable references and strict versions`, () => {
    const schema = managementResponseSchema(
      `${collection}/${departmentId}?revision=2`,
      method,
    );
    expect(schema.parse(department)).toEqual(department);
    for (const changes of [
      { state: "published" },
      { parent_department_id: "bad-id" },
      { revision: "2" },
      { employee_permissions: ["admin"] },
    ])
      expect(schema.safeParse({ ...department, ...changes }).success).toBe(
        false,
      );
  });
}

test("unsupported department routes fail closed", () => {
  for (const [path, method] of [
    [collection, "PUT"],
    [`${collection}/${departmentId}`, "DELETE"],
    [`${collection}/${departmentId}/publish`, "POST"],
  ])
    expect(() => managementResponseSchema(path!, method!)).toThrow();
});
