import { expect, test } from "@playwright/test";
import {
  counterpartySchema,
  counterpartyListSchema,
  matchesSchema,
  matchDecisionSchema,
  bookingLinkResultSchema,
  matchDecisionListSchema,
} from "../lib/counterparty-contracts";
import { managementResponseSchema } from "../lib/management-contracts";

const business = "00000000-0000-4000-8000-000000000001";
const subject = "00000000-0000-4000-8000-000000000002";
const other = "00000000-0000-4000-8000-000000000003";
const envelope = { schema_version: 1, business_id: business };
const card = {
  ...envelope,
  counterparty_id: subject,
  kind: "person",
  revision: 1,
  display_name: "FAKE Person",
  legal_name: null,
  tax_id: null,
  registration_number: null,
  email: null,
  phone: null,
  roles: ["customer"],
  state: "active",
  merged_into: null,
  contacts: [],
  created_at: "2026-10-05T12:00:00Z",
};

test("card responses reject extra fields, invalid states and noncontiguous contacts", () => {
  expect(counterpartySchema.safeParse(card).success).toBe(true);
  for (const change of [
    { merged_from: [] },
    { state: "merged" },
    { schema_version: true },
    { revision: 1.1 },
    { roles: ["customer", "customer"] },
    {
      contacts: [
        {
          position: 2,
          name: "FAKE",
          job_title: null,
          email: null,
          phone: null,
        },
      ],
    },
  ])
    expect(counterpartySchema.safeParse({ ...card, ...change }).success).toBe(
      false,
    );
});

test("matches disclose strong versus weak reasons without assuming identity", () => {
  const item = {
    counterparty_id: subject,
    kind: "person",
    display_name: "FAKE",
    state: "active",
    reasons: ["name"],
    strength: "weak",
  };
  expect(matchesSchema.safeParse({ ...envelope, items: [item] }).success).toBe(
    true,
  );
  expect(
    matchesSchema.safeParse({
      ...envelope,
      items: [{ ...item, strength: "strong" }],
    }).success,
  ).toBe(false);
  expect(
    matchesSchema.safeParse({
      ...envelope,
      items: [{ ...item, reasons: ["phone"], strength: "strong" }],
    }).success,
  ).toBe(true);
});

test("decisions have a version for merges and an explicit pair and reversal", () => {
  const decision = {
    ...envelope,
    decision_id: other,
    kind: "merged",
    counterparty_id: subject,
    other_counterparty_id: other,
    reverses_decision_id: null,
    counterparty_revision: 2,
    reversed: false,
    decided_at: card.created_at,
  };
  expect(matchDecisionSchema.safeParse(decision).success).toBe(true);
  expect(
    matchDecisionSchema.safeParse({ ...decision, counterparty_revision: null })
      .success,
  ).toBe(false);
  expect(
    matchDecisionSchema.safeParse({
      ...decision,
      other_counterparty_id: subject,
    }).success,
  ).toBe(false);
  expect(
    matchDecisionListSchema.safeParse({
      ...envelope,
      counterparty_id: subject,
      items: [{ ...decision, business_id: other }],
    }).success,
  ).toBe(false);
});

test("list identities are unique and link receipts belong to the requested card", () => {
  const summary = {
    counterparty_id: subject,
    kind: "person",
    display_name: "FAKE",
    revision: 1,
    state: "active",
    merged_into: null,
    roles: [],
  };
  expect(
    counterpartyListSchema.safeParse({
      ...envelope,
      items: [summary, summary],
      next_cursor: null,
    }).success,
  ).toBe(false);
  const link = {
    link_id: other,
    booking_id: other,
    counterparty_id: other,
    sequence: 1,
    action: "linked",
    basis: ["email"],
    decided_at: card.created_at,
  };
  expect(
    bookingLinkResultSchema.safeParse({
      ...envelope,
      counterparty_id: subject,
      links: [link],
    }).success,
  ).toBe(false);
  expect(
    bookingLinkResultSchema.safeParse({
      ...envelope,
      counterparty_id: other,
      links: [{ ...link, basis: [] }],
    }).success,
  ).toBe(false);
});

test("every supported route selects a contract and unsupported methods fail closed", () => {
  const base = `/v1/businesses/${business}/counterparties`;
  for (const [path, method] of [
    [base, "GET"],
    [`${base}/match-check`, "POST"],
    [`${base}/${subject}`, "PUT"],
    [`${base}/${subject}`, "GET"],
    ...[
      "versions",
      "merged-from",
      "duplicates",
      "match-decisions",
      "booking-candidates",
      "bookings",
      "booking-links",
    ].map((suffix) => [`${base}/${subject}/${suffix}?limit=50`, "GET"]),
    [`${base}/${subject}/match-decisions`, "POST"],
    [`${base}/${subject}/booking-links`, "POST"],
  ])
    expect(() => managementResponseSchema(path!, method!)).not.toThrow();
  expect(() =>
    managementResponseSchema(`${base}/${subject}`, "DELETE"),
  ).toThrow();
  expect(() =>
    managementResponseSchema(`${base}/anything-else`, "GET"),
  ).toThrow();
});
