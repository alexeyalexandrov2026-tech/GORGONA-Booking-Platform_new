import { expect, test } from "@playwright/test";
import { withDependencies } from "../lib/delegation-contracts";
import { managementResponseSchema } from "../lib/management-contracts";

// Explicit fixture values for boundary tests, never business defaults.
const owner = "a1111111-1111-4111-8111-111111111111";
const serving = "b1111111-1111-4111-8111-111111111111";
const grantId = "c1111111-1111-4111-8111-111111111111";
const membershipId = "d1111111-1111-4111-8111-111111111111";
const userId = "e1111111-1111-4111-8111-111111111111";
const terms = {
  revision: 2,
  state: "active",
  effective_state: "active",
  purpose: "FAKE call-centre bookings",
  permissions: ["booking.read", "booking.write", "catalog.read", "staff.read"],
  location_id: null,
  valid_from: "2026-10-04T12:00:00Z",
  valid_until: "2026-11-04T12:00:00Z",
};
const grant = {
  schema_version: 1,
  business_id: owner,
  grant_id: grantId,
  grantee_business_id: serving,
  current_revision: 2,
  created_at: "2026-10-04T12:00:00Z",
  delegates: [
    {
      designation_id: membershipId,
      user_id: userId,
      designated_at: "2026-10-04T12:01:00Z",
    },
  ],
  ...terms,
};
const incoming = {
  schema_version: 1,
  business_id: serving,
  grant_id: grantId,
  grantor_business_id: owner,
  delegates: [
    {
      designation_id: grantId,
      membership_id: membershipId,
      user_id: userId,
      display_name: "FAKE dispatcher",
      designated_at: "2026-10-04T12:01:00Z",
    },
  ],
  ...terms,
};
const outgoing = `/v1/businesses/${owner}/delegations`;
const received = `/v1/businesses/${serving}/incoming-delegations`;

test("outgoing delegation responses are strict and owned by the business", () => {
  for (const [path, method] of [
    [`${outgoing}/${grantId}`, "GET"],
    [`${outgoing}/${grantId}?revision=1`, "GET"],
    [`${outgoing}/${grantId}`, "PUT"],
    [`${outgoing}/${grantId}/revoke`, "POST"],
  ]) {
    const schema = managementResponseSchema(path!, method!);
    expect(schema.parse(grant)).toEqual(grant);
    for (const unsafe of [
      { ...grant, grantee_business_id: owner },
      { ...grant, revision: 3 },
      { ...grant, permissions: ["booking.write"] },
      { ...grant, permissions: ["booking.read", "booking.read"] },
      { ...grant, permissions: ["business.manage"] },
      { ...grant, state: "draft" },
      { ...grant, tenant_id: owner },
    ])
      expect(schema.safeParse(unsafe).success).toBe(false);
  }
  const page = managementResponseSchema(`${outgoing}?after=${grantId}`, "GET");
  const list = {
    schema_version: 1,
    business_id: owner,
    items: [grant],
    next_cursor: grantId,
  };
  expect(page.parse(list)).toEqual(list);
  expect(page.safeParse({ ...list, items: [grant, grant] }).success).toBe(
    false,
  );
  expect(page.safeParse({ ...list, business_id: serving }).success).toBe(false);
});

test("received delegations list only grants for this business", () => {
  for (const method of ["PUT", "DELETE"]) {
    const schema = managementResponseSchema(
      `${received}/${grantId}/delegates/${membershipId}`,
      method,
    );
    expect(schema.parse(incoming)).toEqual(incoming);
    expect(
      schema.safeParse({ ...incoming, grantor_business_id: serving }).success,
    ).toBe(false);
    expect(
      schema.safeParse({
        ...incoming,
        delegates: [incoming.delegates[0], incoming.delegates[0]],
      }).success,
    ).toBe(false);
  }
  const page = managementResponseSchema(received, "GET");
  const list = {
    schema_version: 1,
    business_id: serving,
    items: [incoming],
    next_cursor: null,
  };
  expect(page.parse(list)).toEqual(list);
  expect(page.safeParse({ ...list, business_id: owner }).success).toBe(false);
});

test("profile of the signed-in person carries current delegations", () => {
  const schema = managementResponseSchema("/v1/me", "GET");
  const me = {
    user_id: userId,
    display_name: "FAKE dispatcher",
    platform_roles: [],
    memberships: [],
  };
  expect(schema.parse(me)).toEqual({ ...me, delegations: [] });
  const access = {
    schema_version: 1,
    business_id: owner,
    serving_business_id: serving,
    grant_id: grantId,
    revision: 2,
    purpose: "FAKE call-centre bookings",
    permissions: ["booking.read", "catalog.read", "staff.read"],
    location_id: null,
    valid_until: "2026-11-04T12:00:00Z",
  };
  expect(schema.parse({ ...me, delegations: [access] })).toEqual({
    ...me,
    delegations: [access],
  });
  expect(
    schema.safeParse({
      ...me,
      delegations: [{ ...access, permissions: ["members.manage"] }],
    }).success,
  ).toBe(false);
});

test("unknown delegation operations fail closed", () => {
  for (const [path, method] of [
    [outgoing, "PUT"],
    [`${outgoing}/${grantId}`, "DELETE"],
    [`${outgoing}/${grantId}/revoke`, "GET"],
    [`${outgoing}/not-an-id`, "GET"],
    [received, "PUT"],
    [`${received}/${grantId}`, "GET"],
    [`${received}/${grantId}/delegates/${membershipId}`, "POST"],
  ])
    expect(() => managementResponseSchema(path!, method!)).toThrow(
      "Unrecognized business response contract",
    );
});

test("booking changes always include the reads they depend on", () => {
  expect(withDependencies(["booking.write"])).toEqual([
    "booking.read",
    "booking.write",
    "catalog.read",
    "staff.read",
  ]);
  expect(withDependencies(["staff.read", "booking.read"])).toEqual([
    "booking.read",
    "staff.read",
  ]);
});
