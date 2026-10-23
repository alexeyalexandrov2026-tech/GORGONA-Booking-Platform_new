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

// L7b2b: prepaid balances (list, sale) and a redemption from the desk.
const prepaidId = "f6666666-6666-4666-8666-666666666666";
const prepaid = {
  prepaid_id: prepaidId,
  kind: "package",
  counterparty_id: party,
  variant_id: account,
  units: 2,
  remaining_units: 1,
  value: "100.00",
  remaining_value: "50.00",
  currency: "USD",
  usable: true,
  sale: document("invoice", "receivable"),
};

test("prepaid balances list in pages and a sale answers one balance", () => {
  const list = { items: [prepaid], next_cursor: prepaidId };
  const read = managementResponseSchema(`/v1/salons/${salon}/prepaid`, "GET");
  expect(read.parse(list)).toEqual(list);
  expect(read.parse({ items: [], next_cursor: null })).toBeTruthy();
  expect(read.safeParse({ ...list, extra: 1 }).success).toBe(false);
  const sold = managementResponseSchema(`/v1/salons/${salon}/prepaid`, "POST");
  expect(sold.parse(prepaid)).toEqual(prepaid);
  const certificate = {
    ...prepaid,
    kind: "certificate",
    variant_id: null,
    units: null,
    remaining_units: null,
  };
  expect(sold.parse(certificate)).toEqual(certificate);
  // A package names its service and units; a certificate neither.
  expect(sold.safeParse({ ...prepaid, variant_id: null }).success).toBe(false);
  expect(sold.safeParse({ ...certificate, units: 1 }).success).toBe(false);
  expect(sold.safeParse({ ...prepaid, remaining_units: 3 }).success).toBe(
    false,
  );
});

test("a redemption is an issued credit note of the visit and the balance after it", () => {
  const credit = {
    schema_version: 1,
    business_id: salon,
    book_id: book,
    document_id: doc,
    revision: 2,
    state: "issued",
    credited_obligation_id: owed,
    direction: "receivable",
    counterparty_id: party,
    counterparty_revision: 1,
    currency: "USD",
    minor_units: 2,
    credit_date: "2026-10-22",
    due_date: null,
    control_account_id: account,
    title: "Prepaid redemption",
    number: "FAKE-R-1",
    lines: [
      {
        line_id: owed,
        credited_line_id: owed,
        counter_account_id: account,
        description: "Prepaid redemption",
        amount: "50.00",
        reason: "Prepaid redemption",
        reference_entry_id: null,
      },
    ],
    total: "50.00",
    entry_id: owed,
    issued_on: "2026-10-22",
    attestation: "confirmed_account_treatment",
    applied: "50.00",
    refund: "0.00",
    refund_control_account_id: null,
    refund_obligation_id: null,
    created_at: "2026-10-22T15:00:00Z",
    void_entry_id: null,
    voided_on: null,
    void_reason: null,
    void_evidence_source: null,
  };
  const view = {
    booking_id: booking,
    prepaid_id: prepaidId,
    units: 1,
    amount: "50.00",
    credit,
    prepaid,
  };
  const schema = managementResponseSchema(
    `/v1/salons/${salon}/bookings/${booking}/redeem`,
    "POST",
  );
  expect(schema.parse(view)).toEqual(view);
  expect(schema.safeParse({ ...view, units: 2 }).success).toBe(false);
  expect(
    schema.safeParse({ ...view, credit: { ...credit, total: "1.00" } }).success,
  ).toBe(false);
});
