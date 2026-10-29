import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  authoritySchema,
  carrierPaySchema,
  carrierProfileSchema,
  confirmationSchema,
  eligibilitySchema,
  marginSchema,
  reasonText,
  tenderListSchema,
  tenderSchema,
  uncoveredLegs,
} from "../lib/brokerage-contracts";

// N6 (package N): strict response contracts of the brokerage routes and the rule of the board.
const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const business = uuid(1);
const base = `/v1/businesses/${business}/transport`;

const authorityVersion = {
  revision: 1,
  jurisdiction: "US",
  authority_number: "MC-FAKE-1",
  bond_reference: "BMC84-FAKE",
  status: "active",
  effective_from: "2031-01-01",
  expires_on: null,
  source: "fmcsa",
  checked_on: "2031-06-01",
  created_at: "2031-06-01T10:00:00Z",
};
const profileVersion = {
  revision: 1,
  jurisdiction: "US",
  authority_number: "MC-FAKE-2",
  liability_expires_on: "2032-01-01",
  cargo_expires_on: null,
  safety_rating: "satisfactory",
  source: "fmcsa",
  checked_on: "2031-06-01",
  created_at: "2031-06-01T10:00:00Z",
};
const tender = {
  tender_id: uuid(5),
  trip_id: uuid(6),
  legs: [2],
  counterparty_id: uuid(7),
  currency: "USD",
  basis: "fixed",
  amount: "900.00",
  terms: "FAKE terms",
  offered_at: "2031-06-02T10:00:00Z",
  expires_at: "2031-06-03T10:00:00Z",
  state: "accepted",
  answers: [
    { kind: "accepted", source: "phone", occurred_at: "2031-06-02T11:00:00Z" },
  ],
};
const version = {
  revision: 1,
  basis: "fixed",
  amount: "900.00",
  terms: "FAKE terms",
  document_id: null,
  proposed_at: "2031-06-02T11:00:00Z",
  state: "agreed",
  answer: {
    kind: "agreed",
    source: "phone",
    occurred_at: "2031-06-02T11:00:00Z",
  },
};
const margin = {
  order_id: uuid(8),
  currency: "USD",
  revenue: "1500.00",
  carrier_cost: "900.00",
  margin: "600.00",
  tenders: [{ tender_id: uuid(5), amount: "900.00" }],
  shared: [],
};

test("brokerage responses are strict", () => {
  const authority = { current: authorityVersion, versions: [authorityVersion] };
  expect(authoritySchema.parse(authority)).toEqual(authority);
  expect(() => authoritySchema.parse({ ...authority, extra: 1 })).toThrow();
  const profile = {
    counterparty_id: uuid(7),
    current: profileVersion,
    versions: [profileVersion],
  };
  expect(carrierProfileSchema.parse(profile)).toEqual(profile);
  expect(() =>
    carrierProfileSchema.parse({
      ...profile,
      current: { ...profileVersion, safety_rating: "good" },
    }),
  ).toThrow();
  const eligible = {
    on: "2031-06-02",
    eligible: false,
    reasons: ["no_profile"],
  };
  expect(eligibilitySchema.parse(eligible)).toEqual(eligible);
  expect(tenderSchema.parse(tender)).toEqual(tender);
  expect(() => tenderSchema.parse({ ...tender, state: "lost" })).toThrow();
  expect(() => tenderListSchema.parse({ items: [tender, tender] })).toThrow();
  const confirmation = {
    tender_id: uuid(5),
    currency: "USD",
    in_force: version,
    versions: [version],
  };
  expect(confirmationSchema.parse(confirmation)).toEqual(confirmation);
  expect(marginSchema.parse(margin)).toEqual(margin);
  expect(() => marginSchema.parse({ ...margin, margin: 600 })).toThrow();
  expect(() =>
    carrierPaySchema.parse({ tender_id: uuid(5), revision: 1 }),
  ).toThrow();
});

test("the management contract knows the brokerage routes", () => {
  const routes: [string, string, unknown][] = [
    [`${base}/broker-authority`, "GET", authoritySchema],
    [`${base}/broker-authority`, "PUT", authoritySchema],
    [`${base}/broker-authority/eligibility`, "GET", eligibilitySchema],
    [`${base}/carriers/${uuid(7)}/profile`, "PUT", carrierProfileSchema],
    [`${base}/carriers/${uuid(7)}/eligibility`, "GET", eligibilitySchema],
    [`${base}/trips/${uuid(6)}/tenders`, "GET", tenderListSchema],
    [`${base}/tenders/${uuid(5)}`, "PUT", tenderSchema],
    [`${base}/tenders/${uuid(5)}/answers`, "POST", tenderSchema],
    [`${base}/tenders/${uuid(5)}/rate-confirmation`, "PUT", confirmationSchema],
    [
      `${base}/tenders/${uuid(5)}/rate-confirmation/2/answers`,
      "POST",
      confirmationSchema,
    ],
    [`${base}/tenders/${uuid(5)}/accrual`, "POST", carrierPaySchema],
    [`${base}/orders/${uuid(8)}/margin`, "GET", marginSchema],
  ];
  for (const [path, method, schema] of routes)
    expect(managementResponseSchema(path, method)).toBe(schema);
});

test("the board lists only the legs without an accepted tender", () => {
  const legs = [{ position: 1 }, { position: 2 }, { position: 3 }];
  const items = [
    { ...tender, legs: [2], state: "accepted" as const },
    { ...tender, tender_id: uuid(9), legs: [1], state: "declined" as const },
    { ...tender, tender_id: uuid(10), legs: [3], state: "offered" as const },
  ];
  expect(uncoveredLegs(legs, items)).toEqual([1, 3]);
  expect(uncoveredLegs(legs, [])).toEqual([1, 2, 3]);
});

test("refusal reasons are said in words", () => {
  expect(reasonText("no_authority")).toBe("no broker authority is recorded");
  expect(reasonText("liability_expired")).toBe("liability insurance expired");
  expect(reasonText("cargo_unknown")).toBe("cargo insurance unknown");
  expect(reasonText("something_new")).toBe("something new");
});
