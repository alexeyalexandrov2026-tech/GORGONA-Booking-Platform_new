import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  assignmentListSchema,
  assignmentSchema,
  availabilitySchema,
  bookingListSchema,
  bookingSchema,
  canManageRental,
  classListSchema,
  classSchema,
  unitListSchema,
  unitSchema,
} from "../lib/rental-contracts";
import {
  agreementSchema,
  quoteSchema,
  rateCardListSchema,
  rateCardSchema,
  securitySchema,
} from "../lib/rental-contracts";
import {
  chargesSchema,
  inspectionsSchema,
  reconciliationSchema,
  settlementSchema,
  usageSchema,
} from "../lib/rental-contracts";

// R8a (package R): strict response contracts of the R1-R3a rental routes the screens read, and who
// sees the rental screen. FAKE data only.
const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const business = uuid(1);
const base = `/v1/businesses/${business}/rental`;
const at = "2031-06-01T10:00:00Z";
const klass = {
  class_id: uuid(2),
  revision: 1,
  code: "FAKE-VAN",
  name: "FAKE cargo van",
  meter_kind: "odometer",
  attributes: [
    { key: "seats", label: "Seats", type: "number", required: true },
  ],
  updated_at: at,
};
const unit = {
  unit_id: uuid(3),
  revision: 1,
  class_id: uuid(2),
  identifier: "FAKE-U-1",
  location_id: uuid(4),
  state: "active",
  values: { seats: "3" },
  updated_at: at,
};
const booking = {
  booking_id: uuid(5),
  number: 1,
  class_id: uuid(2),
  customer_id: uuid(6),
  pickup_location_id: uuid(4),
  return_location_id: uuid(4),
  starts_at: at,
  ends_at: "2031-06-03T10:00:00Z",
  note: null,
  booked_at: at,
  cancellation: null,
};
const availability = {
  class_id: uuid(2),
  location_id: uuid(4),
  starts_at: at,
  ends_at: "2031-06-03T10:00:00Z",
  units: 2,
  booked: 1,
  available: 1,
};
const assignment = {
  assignment_id: uuid(7),
  booking_id: uuid(5),
  unit_id: uuid(3),
  starts_at: at,
  ends_at: "2031-06-03T10:00:00Z",
  assigned_at: at,
  release: null,
};

test("rental responses parse strictly", () => {
  expect(classSchema.parse(klass)).toEqual(klass);
  expect(
    classListSchema.parse({ items: [klass], next_cursor: null }).items,
  ).toHaveLength(1);
  expect(unitSchema.parse(unit)).toEqual(unit);
  expect(
    unitListSchema.parse({ items: [unit], next_cursor: uuid(9) }).next_cursor,
  ).toBe(uuid(9));
  expect(bookingSchema.parse(booking)).toEqual(booking);
  const cancelled = {
    ...booking,
    note: "FAKE note",
    cancellation: { reason: "FAKE plans changed", cancelled_at: at },
  };
  expect(bookingSchema.parse(cancelled)).toEqual(cancelled);
  expect(
    bookingListSchema.parse({ items: [booking], next_cursor: null }).items,
  ).toHaveLength(1);
  expect(availabilitySchema.parse(availability)).toEqual(availability);
  const replaced = {
    ...assignment,
    release: { reason: "replaced", released_at: at },
  };
  expect(assignmentSchema.parse(replaced)).toEqual(replaced);
  expect(
    assignmentListSchema.parse({ items: [assignment, replaced] }).items,
  ).toHaveLength(2);
});

test("unknown fields and bad values are refused", () => {
  for (const [schema, value] of [
    [classSchema, { ...klass, extra: 1 }],
    [classSchema, { ...klass, meter_kind: "fuel" }],
    [classSchema, { ...klass, code: "" }],
    [unitSchema, { ...unit, state: "lost" }],
    [unitSchema, { ...unit, class_id: "nope" }],
    [bookingSchema, { ...booking, number: 0 }],
    [bookingSchema, { ...booking, starts_at: "2031-06-01" }],
    [bookingSchema, { ...booking, cancellation: { reason: "x" } }],
    [availabilitySchema, { ...availability, available: -1 }],
    [
      assignmentSchema,
      { ...assignment, release: { reason: "lost", released_at: at } },
    ],
  ] as const)
    expect(schema.safeParse(value).success).toBe(false);
});

test("the management client knows every rental route the screens use", () => {
  const cases: [string, string, unknown][] = [
    [`${base}/classes`, "GET", { items: [klass], next_cursor: null }],
    [`${base}/classes/${uuid(2)}`, "GET", klass],
    [`${base}/classes/${uuid(2)}`, "PUT", klass],
    [`${base}/units`, "GET", { items: [unit], next_cursor: null }],
    [`${base}/units/${uuid(3)}`, "PUT", unit],
    [`${base}/bookings`, "GET", { items: [booking], next_cursor: null }],
    [`${base}/bookings`, "POST", booking],
    [`${base}/bookings/${uuid(5)}`, "GET", booking],
    [`${base}/bookings/${uuid(5)}/cancellation`, "POST", booking],
    [`${base}/availability`, "GET", availability],
    [`${base}/bookings/${uuid(5)}/assignments`, "GET", { items: [assignment] }],
    [`${base}/bookings/${uuid(5)}/assignment`, "POST", assignment],
  ];
  for (const [path, method, body] of cases) {
    const schema = managementResponseSchema(path, method);
    expect(schema, `${method} ${path}`).not.toBeNull();
    expect(schema?.safeParse(body).success, `${method} ${path}`).toBe(true);
  }
});

test("only active owners and managers who are not delegates see the rental screen", () => {
  expect(canManageRental({ role: "owner", status: "active" })).toBe(true);
  expect(canManageRental({ role: "manager", status: "active" })).toBe(true);
  expect(canManageRental({ role: "front_desk", status: "active" })).toBe(false);
  expect(canManageRental({ role: "owner", status: "invited" })).toBe(false);
  expect(
    canManageRental({
      role: "owner",
      status: "active",
      delegation: { grant_id: uuid(8) },
    }),
  ).toBe(false);
  expect(canManageRental(undefined)).toBe(false);
});

// R8b (package R): rate cards, the quote, the agreement and the security.
const card = {
  rate_card_id: uuid(10),
  class_id: uuid(2),
  location_id: uuid(4),
  version: 1,
  currency: "USD",
  effective_from: at,
  rates: { hour: null, day: 5000, week: null, month: null },
  meter_allowance_per_day: 100,
  excess_rate: 25,
  extras: [
    {
      code: "child_seat",
      name: "FAKE child seat",
      price: 500,
      unit: "per_day",
    },
  ],
  created_at: at,
};
const quote = {
  rate_card_id: uuid(10),
  version: 1,
  currency: "USD",
  starts_at: at,
  ends_at: "2031-06-03T10:00:00Z",
  counts: { day: 2 },
  rental: 10000,
  rental_days: 2,
  extras: [],
  total: 10000,
  booking_id: uuid(5),
};
test("rental customer documents distinguish pending terms from receipts", () => {
  const path = `${base}/bookings/${booking.booking_id}/customer-proposal/${uuid(12)}`;
  const receipt = {
    schema_version: 1,
    status: "accepted",
    booking_id: booking.booking_id,
    agreement_id: uuid(11),
    version: 1,
    review_hash: "0".repeat(64),
    accepted_at: at,
  };
  const pending = {
    schema_version: 1,
    status: "pending",
    booking_id: booking.booking_id,
    pickup_location_id: booking.pickup_location_id,
    return_location_id: booking.return_location_id,
    binding_revision: 1,
    class_name: klass.name,
    pickup: { name: "FAKE branch", timezone: "UTC" },
    return_location: null,
    quote,
    review_hash: receipt.review_hash,
  };
  const view = managementResponseSchema(path, "GET");
  expect(view.parse(pending)).toEqual(pending);
  expect(view.parse(receipt)).toEqual(receipt);
  expect(view.safeParse({ ...pending, note: "internal" }).success).toBe(false);
  expect(view.safeParse({ ...receipt, review_hash: "unknown" }).success).toBe(
    false,
  );
  const reply = managementResponseSchema(path, "POST");
  expect(reply.parse(receipt)).toEqual(receipt);
  expect(reply.safeParse(pending).success).toBe(false);
});

test("rental change routes validate public terms, receipts and extras", () => {
  const staffPath = `${base}/bookings/${booking.booking_id}/customer-changes`;
  const path = `${staffPath}/1/${uuid(12)}`;
  const offer = {
    schema_version: 1,
    status: "pending",
    booking_id: booking.booking_id,
    revision: 1,
    agreement_version: 1,
    binding_revision: 1,
    reason: "FAKE new seat",
    review_hash: "0".repeat(64),
    quote: {
      ...quote,
      total: 11_000,
      extras: [{ code: "child_seat", quantity: 1, amount: 1_000 }],
    },
  };
  const publicOffer = {
    ...offer,
    pickup_timezone: "UTC",
    extra_names: { child_seat: "FAKE seat" },
  };
  const receipt = {
    schema_version: 1,
    status: "accepted",
    booking_id: booking.booking_id,
    agreement_id: uuid(11),
    revision: 1,
    agreement_version: 2,
    review_hash: offer.review_hash,
    accepted_at: at,
  };
  const read = managementResponseSchema(path, "GET");
  expect(read.parse(publicOffer)).toEqual(publicOffer);
  expect(read.parse(receipt)).toEqual(receipt);
  expect(read.safeParse(offer).success).toBe(false);
  expect(
    read.safeParse({ ...publicOffer, review_hash: "changed" }).success,
  ).toBe(false);
  const write = managementResponseSchema(path, "POST");
  expect(write.parse(receipt)).toEqual(receipt);
  expect(write.safeParse(publicOffer).success).toBe(false);
  expect(managementResponseSchema(staffPath, "GET").parse(null)).toBeNull();
  expect(managementResponseSchema(staffPath, "PUT").parse(offer)).toEqual(
    offer,
  );
});

test("rental problem report routes validate lists and reports", () => {
  const staffPath = `${base}/bookings/${booking.booking_id}/problems`;
  const customerPath = `${staffPath.replace("/problems", "/customer-problems")}/${uuid(12)}`;
  const phone = {
    schema_version: 1,
    booking_id: booking.booking_id,
    number: 1,
    kind: "breakdown",
    description: "FAKE flat tyre",
    occurred_at: at,
    source: "phone",
    reported_by: "FAKE Renter",
    company_id: null,
    company_name: null,
    recorded_at: at,
  };
  const platform = {
    ...phone,
    number: 2,
    kind: "damage",
    source: "platform",
    reported_by: null,
    company_id: uuid(13),
    company_name: "FAKE Customer Company",
  };
  const list = {
    schema_version: 1,
    booking_id: booking.booking_id,
    items: [phone, platform],
  };
  const mine = { ...list, items: [platform], binding_revision: 1 };
  expect(managementResponseSchema(staffPath, "GET").parse(list)).toEqual(list);
  expect(managementResponseSchema(staffPath, "POST").parse(phone)).toEqual(
    phone,
  );
  expect(managementResponseSchema(customerPath, "GET").parse(mine)).toEqual(
    mine,
  );
  expect(
    managementResponseSchema(customerPath, "POST").parse(platform),
  ).toEqual(platform);
  const write = managementResponseSchema(staffPath, "POST");
  for (const broken of [
    { ...phone, reported_by: null },
    { ...phone, company_id: uuid(13) },
    { ...platform, reported_by: "FAKE Renter" },
    { ...platform, company_id: null },
    { ...phone, company_name: "FAKE Customer Company" },
    { ...phone, company_name: "" },
    { ...phone, kind: "flood" },
    { ...phone, source: "fax" },
    { ...phone, description: "" },
    { ...phone, number: 0 },
    { ...phone, grant_id: uuid(12) },
  ])
    expect(write.safeParse(broken).success).toBe(false);
  const read = managementResponseSchema(customerPath, "GET");
  expect(read.safeParse(list).success).toBe(false);
  expect(read.safeParse({ ...mine, items: [phone] }).success).toBe(false);
  // A platform report keeps working when the session cannot read the grant's company name.
  const unnamed = { ...platform, company_name: null };
  expect(write.parse(unnamed)).toEqual(unnamed);
});

test("rental text limits count characters as the API does, not UTF-16 units", () => {
  // R-09 review: the API accepts 2000 characters; an emoji is one character but two UTF-16 units.
  const path = `${base}/bookings/${booking.booking_id}/problems`;
  const report = {
    schema_version: 1,
    booking_id: booking.booking_id,
    number: 1,
    kind: "other",
    description: "\u{1F697}".repeat(2000),
    occurred_at: at,
    source: "phone",
    reported_by: "\u{1F600}".repeat(200),
    company_id: null,
    company_name: null,
    recorded_at: at,
  };
  expect("\u{1F697}".repeat(2000).length).toBe(4000);
  const write = managementResponseSchema(path, "POST");
  expect(write.parse(report)).toEqual(report);
  expect(
    write.safeParse({ ...report, description: "\u{1F697}".repeat(2001) })
      .success,
  ).toBe(false);
  expect(
    write.safeParse({ ...report, reported_by: "\u{1F600}".repeat(201) })
      .success,
  ).toBe(false);
});

const agreement = {
  agreement_id: uuid(11),
  booking_id: uuid(5),
  current_version: 1,
  versions: [
    {
      version: 1,
      rate_card_id: uuid(10),
      card_version: 1,
      currency: "USD",
      starts_at: at,
      ends_at: "2031-06-03T10:00:00Z",
      counts: { day: 2 },
      rental: 10000,
      rental_days: 2,
      extras: [
        {
          code: "child_seat",
          name: "FAKE child seat",
          price: 500,
          unit: "per_day",
          quantity: 1,
          amount: 1000,
        },
      ],
      total: 11000,
      source: "paper",
      accepted_by: "FAKE Renter",
      accepted_at: at,
      reason: null,
      created_at: at,
    },
  ],
};
const security = {
  security_id: uuid(12),
  booking_id: uuid(5),
  amount: 20000,
  currency: "USD",
  method: "card_hold",
  state: "held",
  held: 20000,
  captured: 3000,
  released: 0,
  expired: 0,
  remaining: 17000,
  events: [
    {
      sequence: 1,
      kind: "held",
      amount: 20000,
      reference: "FAKE-TERM-1",
      hold_expires_at: null,
      basis: null,
      occurred_at: at,
      recorded_by: uuid(13),
      provider: null,
    },
    {
      sequence: 2,
      kind: "captured",
      amount: 3000,
      reference: null,
      hold_expires_at: null,
      basis: "FAKE scratch",
      occurred_at: at,
      recorded_by: uuid(13),
      provider: {
        receipt_id: uuid(14),
        intent: "pi_FAKE1",
        linked_by: uuid(13),
      },
    },
  ],
};

test("R8b responses parse strictly and refuse bad values", () => {
  expect(rateCardSchema.parse(card)).toEqual(card);
  expect(rateCardListSchema.parse({ items: [card] }).items).toHaveLength(1);
  expect(quoteSchema.parse(quote)).toEqual(quote);
  expect(
    quoteSchema.parse({ ...quote, booking_id: null }).booking_id,
  ).toBeNull();
  expect(agreementSchema.parse(agreement)).toEqual(agreement);
  expect(securitySchema.parse(security)).toEqual(security);
  for (const [schema, value] of [
    [rateCardSchema, { ...card, currency: "usd" }],
    [rateCardSchema, { ...card, extra: true }],
    [quoteSchema, { ...quote, total: -1 }],
    [agreementSchema, { ...agreement, current_version: 0 }],
    [securitySchema, { ...security, state: "lost" }],
    [securitySchema, { ...security, method: "crypto" }],
  ] as const)
    expect(schema.safeParse(value).success).toBe(false);
});

test("the management client knows every R8b rental route", () => {
  const cases: [string, string, unknown][] = [
    [`${base}/classes/${uuid(2)}/rate-cards`, "GET", { items: [card] }],
    [`${base}/classes/${uuid(2)}/rate-cards`, "POST", card],
    [`${base}/bookings/${uuid(5)}/quote`, "GET", quote],
    [`${base}/bookings/${uuid(5)}/agreement`, "GET", agreement],
    [`${base}/bookings/${uuid(5)}/agreement`, "POST", agreement],
    [`${base}/bookings/${uuid(5)}/security`, "GET", security],
    [`${base}/bookings/${uuid(5)}/security`, "POST", security],
    [`${base}/bookings/${uuid(5)}/security/events`, "POST", security],
  ];
  for (const [path, method, body] of cases) {
    const schema = managementResponseSchema(path, method);
    expect(schema, `${method} ${path}`).not.toBeNull();
    expect(schema?.safeParse(body).success, `${method} ${path}`).toBe(true);
  }
});

// R8c (package R): inspections (R6a), usage (R6b), the settlement (R7a), damage charges and refunds
// (R7b) and the reconciliation (R7c).
const mark = {
  position: 1,
  area: "FAKE rear door",
  severity: "major",
  note: "FAKE dent",
  new: true,
  photo: { document_id: uuid(20), revision: 1 },
};
const inspections = {
  booking_id: uuid(5),
  inspections: [
    {
      inspection_id: uuid(21),
      kind: "handover",
      assignment_id: uuid(22),
      unit_id: uuid(3),
      meter: 1000,
      level: 80,
      note: null,
      inspected_by: uuid(13),
      inspected_at: at,
      marks: [
        {
          ...mark,
          area: "FAKE bumper",
          severity: "minor",
          new: false,
          photo: null,
        },
      ],
    },
    {
      inspection_id: uuid(23),
      kind: "return",
      assignment_id: uuid(22),
      unit_id: uuid(3),
      meter: 1300,
      level: null,
      note: "FAKE back on time",
      inspected_by: uuid(13),
      inspected_at: at,
      marks: [mark],
    },
  ],
};
const usage = {
  booking_id: uuid(5),
  currency: "USD",
  state: "returned",
  period_end: "2031-06-03T10:00:00Z",
  rental_days: 2,
  as_of: at,
  overdue_seconds: 0,
  overdue_hours: 0,
  distance: 300,
  allowance: 200,
  excess: 100,
  excess_amount: 2500,
};
const settlement = {
  booking_id: uuid(5),
  agreement_version: 1,
  currency: "USD",
  rental_minor: 10000,
  excess_minor: 2500,
  late_minor: 0,
  late_units: 0,
  total_minor: 12500,
  book_id: uuid(24),
  invoice_document_id: uuid(25),
  settled_by: uuid(13),
  settled_at: at,
};
const charges = {
  booking_id: uuid(5),
  damage_charges: [
    {
      number: 1,
      marks: [1],
      amount_minor: 8000,
      reason: "FAKE dent",
      book_id: uuid(24),
      invoice_document_id: uuid(26),
      charged_by: uuid(13),
      charged_at: at,
    },
  ],
  refunds: [
    {
      number: 1,
      method: "external",
      amount_minor: 1000,
      reason: "FAKE goodwill",
      reference: "FAKE-REF-1",
      refunded_at: at,
      book_id: null,
      credit_document_id: null,
      recorded_by: uuid(13),
      recorded_at: at,
    },
  ],
};
const reconciliation = {
  booking_id: uuid(5),
  currency: "USD",
  documents: [
    {
      kind: "settlement",
      number: null,
      amount_minor: 12500,
      book_id: uuid(24),
      document_id: uuid(25),
      state: "draft",
      principal_minor: 0,
      paid_minor: 0,
      credited_minor: 0,
      open_minor: 0,
    },
    {
      kind: "damage_charge",
      number: 1,
      amount_minor: 8000,
      book_id: uuid(24),
      document_id: uuid(26),
      state: "issued",
      principal_minor: 8000,
      paid_minor: 3000,
      credited_minor: 0,
      open_minor: 5000,
    },
  ],
  refunds: [
    {
      number: 1,
      method: "external",
      amount_minor: 1000,
      state: "recorded",
      credit_document_id: null,
      refund_obligation_minor: null,
      refund_paid_minor: null,
    },
  ],
  security: {
    state: "held",
    amount: 20000,
    held: 20000,
    captured: 0,
    released: 0,
    expired: 0,
    remaining: 20000,
  },
  totals: {
    charged_minor: 20500,
    invoiced_minor: 8000,
    paid_minor: 3000,
    credited_minor: 0,
    open_minor: 5000,
    refunded_external_minor: 1000,
    refund_owed_minor: 0,
  },
};

test("R8c responses parse strictly and refuse bad values", () => {
  expect(inspectionsSchema.parse(inspections)).toEqual(inspections);
  expect(usageSchema.parse(usage)).toEqual(usage);
  expect(
    usageSchema.parse({ ...usage, state: "out", distance: null, excess: null })
      .distance,
  ).toBeNull();
  expect(settlementSchema.parse(settlement)).toEqual(settlement);
  expect(chargesSchema.parse(charges)).toEqual(charges);
  expect(reconciliationSchema.parse(reconciliation)).toEqual(reconciliation);
  expect(
    reconciliationSchema.parse({ ...reconciliation, security: null }).security,
  ).toBeNull();
  for (const [schema, value] of [
    [inspectionsSchema, { ...inspections, extra: 1 }],
    [
      inspectionsSchema,
      {
        ...inspections,
        inspections: [{ ...inspections.inspections[0], kind: "pickup" }],
      },
    ],
    [usageSchema, { ...usage, state: "lost" }],
    [settlementSchema, { ...settlement, total_minor: -1 }],
    [
      chargesSchema,
      { ...charges, refunds: [{ ...charges.refunds[0], method: "cash" }] },
    ],
    [
      reconciliationSchema,
      {
        ...reconciliation,
        documents: [{ ...reconciliation.documents[0], state: "void" }],
      },
    ],
  ] as const)
    expect(schema.safeParse(value).success).toBe(false);
});

test("the management client knows every R8c rental route", () => {
  const booking = `${base}/bookings/${uuid(5)}`;
  const cases: [string, string, unknown][] = [
    [`${booking}/inspections`, "GET", inspections],
    [`${booking}/inspections`, "POST", inspections],
    [`${booking}/usage`, "GET", usage],
    [`${booking}/settlement`, "GET", settlement],
    [`${booking}/settlement`, "POST", settlement],
    [`${booking}/charges`, "GET", charges],
    [`${booking}/damage-charges`, "POST", charges],
    [`${booking}/refunds`, "POST", charges],
    [`${booking}/reconciliation`, "GET", reconciliation],
  ];
  for (const [path, method, body] of cases) {
    const schema = managementResponseSchema(path, method);
    expect(schema, `${method} ${path}`).not.toBeNull();
    expect(schema?.safeParse(body).success, `${method} ${path}`).toBe(true);
  }
});
