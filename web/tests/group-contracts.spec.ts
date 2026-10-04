import { test, expect } from "@playwright/test";
import { groupReportSchema, invitationSchema } from "../lib/group-contracts";
import { managementResponseSchema } from "../lib/management-contracts";

const operator = "a1111111-1111-4111-8111-111111111111";
const participant = "b1111111-1111-4111-8111-111111111111";
const group = "c1111111-1111-4111-8111-111111111111";
const invitation = "d1111111-1111-4111-8111-111111111111";
const location = "e1111111-1111-4111-8111-111111111111";
const valid = {
  schema_version: 1,
  business_id: operator,
  group_id: group,
  from_at: "2026-10-01T00:00:00Z",
  until_at: "2026-10-02T00:00:00Z",
  sources: [
    {
      owner_business_id: participant,
      grant_id: invitation,
      grant_revision: 1,
      location_id: location,
    },
  ],
  items: [
    {
      owner_business_id: participant,
      location_id: location,
      legal_entity_id: null,
      legal_entity_assignment: "unassigned",
      status: "CONFIRMED",
      booking_count: 3,
    },
  ],
  excluded_business_ids: [],
  next_cursor: null,
};

test("report rows must belong to a permitted source and branch", () => {
  expect(groupReportSchema.safeParse(valid).success).toBe(true);
  for (const invalid of [
    { ...valid, sources: [] },
    { ...valid, sources: [...valid.sources, ...valid.sources] },
    { ...valid, excluded_business_ids: [participant] },
    { ...valid, items: [...valid.items, ...valid.items] },
    { ...valid, items: [{ ...valid.items[0], owner_business_id: operator }] },
    { ...valid, items: [{ ...valid.items[0], location_id: group }] },
    { ...valid, revenue: 3 },
  ]) {
    expect(groupReportSchema.safeParse(invalid).success).toBe(false);
  }
});
test("consent state and viewer must match their independent company", () => {
  const record = {
    schema_version: 1,
    business_id: participant,
    operator_business_id: operator,
    participant_business_id: participant,
    group_id: group,
    group_name: "FAKE group",
    invitation_id: invitation,
    state: "active",
    revision: 1,
    consent_state: "accepted",
    consent_revision: 1,
    created_at: valid.from_at,
  };
  expect(invitationSchema.safeParse(record).success).toBe(true);
  for (const invalid of [
    { ...record, business_id: group },
    { ...record, consent_revision: 0 },
    { ...record, operator_business_id: participant },
    { ...record, state: "withdrawn" },
  ]) {
    expect(invitationSchema.safeParse(invalid).success).toBe(false);
  }
});
test("management boundary recognizes only explicit group endpoints", () => {
  const path = `/v1/businesses/${operator}/groups/${group}/booking-report`;
  expect(managementResponseSchema(path, "GET").safeParse(valid).success).toBe(
    true,
  );
  expect(() => managementResponseSchema(path, "PUT")).toThrow();
});
