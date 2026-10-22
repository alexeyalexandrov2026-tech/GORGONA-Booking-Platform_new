import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";

// L7b1: the visit desk reads a completion, never through the plain booking contract.
const salon = "a1111111-1111-4111-8111-111111111111";
const booking = "b1111111-1111-4111-8111-111111111111";
const completion = {
  booking_id: booking,
  location_id: "c1111111-1111-4111-8111-111111111111",
  completed_at: "2026-10-22T15:00:00Z",
  completed_by: "d1111111-1111-4111-8111-111111111111",
  materials: [
    {
      item_id: "e1111111-1111-4111-8111-111111111111",
      planned: "2.5",
      actual: "3.0",
    },
  ],
  stock_document_id: null,
  consumption_posted_at: null,
};

test("completion, consumption and the completion read share one strict contract", () => {
  for (const [suffix, method] of [
    ["complete", "POST"],
    ["consumption", "POST"],
    ["completion", "GET"],
  ] as const) {
    const schema = managementResponseSchema(
      `/v1/salons/${salon}/bookings/${booking}/${suffix}`,
      method,
    );
    expect(schema.parse(completion)).toEqual(completion);
    expect(schema.safeParse({ ...completion, extra: true }).success).toBe(
      false,
    );
    expect(
      schema.safeParse({ ...completion, materials: [{ item_id: booking }] })
        .success,
    ).toBe(false);
  }
});

// L7b2a: the visit invoice, the visit commission and a specialist's commission plan.
const book = "f1111111-1111-4111-8111-111111111111";
const doc = "f2222222-2222-4222-8222-222222222222";
const party = "f3333333-3333-4333-8333-333333333333";
const account = "f4444444-4444-4444-8444-444444444444";
const owed = "f5555555-5555-4555-8555-555555555555";
const document = (kind: string, direction: string) => ({
  schema_version: 1,
  business_id: salon,
  book_id: book,
  document_id: doc,
  kind,
  revision: 2,
  state: "issued",
  direction,
  counterparty_id: party,
  counterparty_revision: 1,
  currency: "USD",
  minor_units: 2,
  invoice_date: "2026-10-22",
  due_date: null,
  control_account_id: account,
  title: "Visit",
  number: "FAKE-V-1",
  lines: [
    {
      line_id: owed,
      counter_account_id: account,
      description: "FAKE base",
      amount: "50.00",
    },
  ],
  total: "50.00",
  entry_id: owed,
  obligation_id: owed,
  issued_on: "2026-10-22",
  attestation: "confirmed_account_treatment",
  created_at: "2026-10-22T15:00:00Z",
});
const obligation = {
  schema_version: 1,
  business_id: salon,
  book_id: book,
  obligation_id: owed,
  source_kind: "invoice",
  source_id: doc,
  source_revision: 2,
  component: "principal",
  counterparty_id: party,
  counterparty_revision: 1,
  direction: "receivable",
  currency: "USD",
  minor_units: 2,
  control_account_id: account,
  principal: "50.00",
  paid: "50.00",
  credited: "0.00",
  reserved: "0.00",
  available: "0.00",
  created_at: "2026-10-22T15:00:00Z",
};

test("the visit invoice is an invoice and, once issued, its obligation", () => {
  const view = {
    booking_id: booking,
    book_id: book,
    document_id: doc,
    invoice: document("invoice", "receivable"),
    obligation,
  };
  for (const method of ["GET", "POST"]) {
    const schema = managementResponseSchema(
      `/v1/salons/${salon}/bookings/${booking}/invoice`,
      method,
    );
    expect(schema.parse(view)).toEqual(view);
    expect(schema.parse({ ...view, obligation: null })).toBeTruthy();
    expect(schema.safeParse({ ...view, extra: 1 }).success).toBe(false);
  }
});

test("the visit commission is a payable accrual with the tips held", () => {
  const view = {
    booking_id: booking,
    book_id: book,
    document_id: doc,
    accrual: document("manual_accrual", "payable"),
    tips_account_id: null,
    tips: "0.00",
  };
  const schema = managementResponseSchema(
    `/v1/salons/${salon}/bookings/${booking}/commission`,
    "GET",
  );
  expect(schema.parse(view)).toEqual(view);
  expect(schema.safeParse({ ...view, tips: "x" }).success).toBe(false);
});

test("a commission plan has rules of a percentage or an amount", () => {
  const plan = {
    resource_id: account,
    counterparty_id: party,
    currency: "USD",
    revision: 2,
    updated_at: "2026-10-22T15:00:00Z",
    rules: [
      { service_id: null, percent: "10.00", amount: null },
      { service_id: party, percent: null, amount: "5.00" },
    ],
  };
  for (const method of ["GET", "PUT"]) {
    const schema = managementResponseSchema(
      `/v1/salons/${salon}/staff/${account}/commission`,
      method,
    );
    expect(schema.parse(plan)).toEqual(plan);
    expect(
      schema.safeParse({
        ...plan,
        rules: [{ service_id: null, percent: "10.00", amount: "1.00" }],
      }).success,
    ).toBe(false);
  }
});
