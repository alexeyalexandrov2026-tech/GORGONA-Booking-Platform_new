import { expect, test } from "@playwright/test";
import { quoteSchema, type Bootstrap } from "../lib/contracts";
import {
  addOnOffered,
  selectionOf,
  servicesOffered,
  servingAll,
  stageText,
} from "../lib/visit";

// L7c (package L): pure helpers of the customer site's visit of several services.
const ids = {
  gel: "b1111111-1111-4111-8111-111111111111",
  base: "b2222222-2222-4222-8222-222222222222",
  style: "b3333333-3333-4333-8333-333333333333",
  euro: "b4444444-4444-4444-8444-444444444444",
  massage: "c1111111-1111-4111-8111-111111111111",
  french: "c2222222-2222-4222-8222-222222222222",
  serviceA: "d1111111-1111-4111-8111-111111111111",
  serviceB: "d2222222-2222-4222-8222-222222222222",
  location: "e1111111-1111-4111-8111-111111111111",
};
const variant = (
  id: string,
  name: string,
  service_id: string,
  provides: string[],
  currency = "USD",
) => ({
  id,
  service_id,
  service_name: "FAKE service",
  name,
  price_cents: 1000,
  currency,
  duration_minutes: 30,
  provides,
});
const addOn = (
  id: string,
  name: string,
  provides: string[],
  requires: string[] = [],
  conflicts_with: string[] = [],
) => ({
  id,
  name,
  price_cents: 500,
  currency: "USD",
  duration_minutes: 10,
  provides,
  requires,
  conflicts_with,
});
const catalog: Pick<Bootstrap, "variants" | "add_ons"> = {
  variants: [
    variant(ids.gel, "FAKE gel", ids.serviceA, ["PEDICURE", "GEL"]),
    variant(ids.base, "FAKE base", ids.serviceA, ["PEDICURE"]),
    variant(ids.style, "FAKE style", ids.serviceB, ["STYLE"]),
    variant(ids.euro, "FAKE euro", ids.serviceB, ["EURO"], "EUR"),
  ],
  add_ons: [
    addOn(ids.massage, "FAKE massage", ["MASSAGE"]),
    addOn(ids.french, "FAKE french", ["FRENCH"], ["GEL"]),
  ],
};

test("a one-service selection has no extra_lines (byte-identical to before)", () => {
  const body = selectionOf(
    ids.location,
    [{ variant_id: ids.gel, add_on_ids: [ids.massage] }],
    null,
  );
  expect(JSON.stringify(body)).toBe(
    JSON.stringify({
      location_id: ids.location,
      variant_id: ids.gel,
      add_on_ids: [ids.massage],
      resource_id: null,
    }),
  );
});

test("a visit sends its further services in order", () => {
  const body = selectionOf(
    ids.location,
    [
      { variant_id: ids.gel, add_on_ids: [] },
      { variant_id: ids.style, add_on_ids: [ids.massage] },
      { variant_id: ids.base, add_on_ids: [] },
    ],
    "f1111111-1111-4111-8111-111111111111",
  );
  expect(body.variant_id).toBe(ids.gel);
  expect(body.extra_lines).toEqual([
    { variant_id: ids.style, add_on_ids: [ids.massage] },
    { variant_id: ids.base, add_on_ids: [] },
  ]);
});

test("a further line offers services not yet chosen, in the visit's currency", () => {
  const lines = [
    { variant_id: ids.gel, add_on_ids: [] },
    { variant_id: "", add_on_ids: [] },
  ];
  expect(servicesOffered(catalog, lines, 1).map((v) => v.id)).toEqual([
    ids.base,
    ids.style,
  ]);
  // The first line itself may still choose any service.
  expect(servicesOffered(catalog, lines, 0)).toHaveLength(4);
});

test("add-ons are judged across the whole visit", () => {
  const visit = [
    { variant_id: ids.base, add_on_ids: [] },
    { variant_id: ids.style, add_on_ids: [ids.massage] },
  ];
  // The massage is already chosen on another line.
  expect(addOnOffered(catalog, visit, 0, ids.massage)).toBe(false);
  expect(addOnOffered(catalog, visit, 1, ids.massage)).toBe(true);
  // The french needs gel, which no line provides yet.
  expect(addOnOffered(catalog, visit, 1, ids.french)).toBe(false);
  const withGel = [
    { variant_id: ids.style, add_on_ids: [] },
    { variant_id: ids.gel, add_on_ids: [] },
  ];
  // A requirement may be met by any line of the visit.
  expect(addOnOffered(catalog, withGel, 0, ids.french)).toBe(true);
});

test("only specialists serving every service are offered", () => {
  const artists = [
    {
      id: "a1",
      name: "A1",
      location_id: ids.location,
      service_ids: [ids.serviceA, ids.serviceB],
    },
    {
      id: "a2",
      name: "A2",
      location_id: ids.location,
      service_ids: [ids.serviceA],
    },
  ];
  expect(
    servingAll(artists, ids.location, [ids.serviceA]).map((a) => a.id),
  ).toEqual(["a1", "a2"]);
  expect(
    servingAll(artists, ids.location, [ids.serviceA, ids.serviceB]).map(
      (a) => a.id,
    ),
  ).toEqual(["a1"]);
  expect(servingAll(artists, "elsewhere", [ids.serviceA])).toEqual([]);
});

test("stages are told in plain words", () => {
  expect(stageText("active")).toBe("With your specialist");
  expect(stageText("processing")).toBe(
    "Processing — your specialist is free meanwhile",
  );
  expect(stageText("finish")).toBe("Finish");
});

test("a two-service version 2 quote parses strictly", () => {
  const visit = {
    version: 2,
    currency: "USD",
    total_cents: 9500,
    booking_duration_minutes: 140,
    lines: [
      {
        kind: "variant",
        id: ids.gel,
        code: "FAKE_GEL",
        name: "FAKE gel",
        price_cents: 6500,
        duration_minutes: 110,
        revision: 1,
      },
      {
        kind: "variant",
        id: ids.style,
        code: "FAKE_STYLE",
        name: "FAKE style",
        price_cents: 3000,
        duration_minutes: 30,
        revision: 1,
      },
    ],
    stages: [
      { kind: "active", minutes: 30, resources: ["specialist", "chair"] },
      { kind: "processing", minutes: 60, resources: ["chair", "equipment"] },
      { kind: "finish", minutes: 20, resources: ["specialist", "chair"] },
      { kind: "active", minutes: 30, resources: ["specialist"] },
    ],
  };
  expect(quoteSchema.parse(visit)).toEqual(visit);
  expect(quoteSchema.safeParse({ ...visit, extra_lines: [] }).success).toBe(
    false,
  );
});

// L8 decision 62 (review R9): five services of up to ten stages each.
test("a visit quote of more than ten stages parses; more than fifty is refused", () => {
  const stage = (kind: "active" | "processing") => ({
    kind,
    minutes: 10,
    resources: kind === "active" ? ["specialist"] : ["chair"],
  });
  const quote = (count: number) => ({
    version: 2,
    currency: "USD",
    total_cents: 1000,
    booking_duration_minutes: 10 * count,
    lines: [
      {
        kind: "variant",
        id: ids.gel,
        code: "FAKE_GEL",
        name: "FAKE gel",
        price_cents: 1000,
        duration_minutes: 10 * count,
        revision: 1,
      },
    ],
    stages: Array.from({ length: count }, (_, i) =>
      stage(i % 2 ? "processing" : "active"),
    ),
  });
  expect(quoteSchema.safeParse(quote(11)).success).toBe(true);
  expect(quoteSchema.safeParse(quote(50)).success).toBe(true);
  expect(quoteSchema.safeParse(quote(51)).success).toBe(false);
});
