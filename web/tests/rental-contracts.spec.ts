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
