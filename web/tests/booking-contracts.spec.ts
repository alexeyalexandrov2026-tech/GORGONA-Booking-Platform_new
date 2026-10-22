import { expect, test } from "@playwright/test";
import { quoteSchema } from "../lib/contracts";

// L2b (package L): the public quote is version 1 without stages or version 2 with them.
const line = {
  kind: "variant",
  id: "b1111111-1111-4111-8111-111111111111",
  code: "FAKE_GEL",
  name: "FAKE gel",
  price_cents: 6500,
  duration_minutes: 110,
  revision: 1,
};
const plain = {
  version: 1,
  currency: "USD",
  total_cents: 6500,
  booking_duration_minutes: 110,
  lines: [line],
};
const stages = [
  { kind: "active", minutes: 30, resources: ["specialist", "chair"] },
  { kind: "processing", minutes: 60, resources: ["chair", "equipment"] },
  { kind: "finish", minutes: 20, resources: ["specialist", "chair"] },
];

test("a version 1 quote parses without stages", () => {
  expect(quoteSchema.parse(plain)).toEqual(plain);
});

test("a version 2 quote parses with its stages", () => {
  const staged = { ...plain, version: 2, stages };
  expect(quoteSchema.parse(staged)).toEqual(staged);
});

test("mixed or unknown quote shapes are refused", () => {
  expect(quoteSchema.safeParse({ ...plain, stages }).success).toBe(false);
  expect(quoteSchema.safeParse({ ...plain, version: 2 }).success).toBe(false);
  expect(
    quoteSchema.safeParse({
      ...plain,
      version: 2,
      stages: [{ kind: "rest", minutes: 10, resources: ["specialist"] }],
    }).success,
  ).toBe(false);
  expect(
    quoteSchema.safeParse({
      ...plain,
      version: 2,
      stages: [{ kind: "active", minutes: 10, resources: ["desk"] }],
    }).success,
  ).toBe(false);
  expect(quoteSchema.safeParse({ ...plain, version: 3 }).success).toBe(false);
});
