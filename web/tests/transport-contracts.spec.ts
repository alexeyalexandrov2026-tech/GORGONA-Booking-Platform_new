import { expect, test } from "@playwright/test";
import { managementResponseSchema } from "../lib/management-contracts";
import {
  clearanceSchema,
  driverListSchema,
  tripListSchema,
  tripSchema,
  vehicleListSchema,
  orderListSchema,
  orderInvoiceSchema,
  paySchema,
  rateSchema,
  orderSchema,
} from "../lib/transport-contracts";
import { describeAccess, TRANSPORT_ACTIONS } from "../lib/delegation-contracts";
import {
  legOpen,
  stopWindowFields,
  stopWindowInstants,
} from "../lib/transport-rules";

// M6a (package M): strict response contracts of the transport routes the board and trip page read.
const uuid = (n: number) =>
  `00000000-0000-4000-8000-${n.toString().padStart(12, "0")}`;
const business = uuid(1);
const trip = {
  trip_id: uuid(2),
  location_id: uuid(3),
  reference: "FAKE-TR-1",
  status: "in_transit",
  revision: 1,
  stops: [
    {
      position: 1,
      kind: "pickup",
      place: "FAKE dock, Chicago",
      time_zone: "America/Chicago",
      window_start: "2031-06-02T13:00:00Z",
      window_end: "2031-06-02T15:00:00Z",
    },
  ],
  legs: [
    {
      position: 1,
      load_id: uuid(4),
      quantity: 10,
      pickup_stop: 1,
      delivery_stop: 2,
      loaded: 10,
      delivered: 7,
      refused: 2,
      damaged: 1,
    },
  ],
  assignments: [
    {
      assignment_id: uuid(5),
      role: "truck",
      resource_id: uuid(6),
      starts_at: "2031-06-02T13:00:00Z",
      ends_at: null,
      replaces: null,
    },
  ],
  events: [
    {
      event_id: uuid(7),
      stop_position: 1,
      kind: "loaded",
      occurred_at: "2031-06-02T14:00:00Z",
      source: "dispatcher",
      source_event_id: "FAKE-1",
      note: null,
      quantities: [{ leg_position: 1, quantity: 10 }],
    },
  ],
};
const driver = {
  driver_id: uuid(8),
  location_id: uuid(3),
  display_name: "FAKE Driver",
  resource_id: uuid(9),
};
const vehicle = {
  vehicle_id: uuid(10),
  location_id: uuid(3),
  kind: "truck",
  unit_number: "FAKE-T1",
  resource_id: uuid(11),
};
const clearance = {
  trip_id: uuid(2),
  at: "2031-06-02T13:00:00Z",
  status: "unknown",
  profile: { code: "US_PROPERTY_70_8", revision: 1 },
  roles: [
    {
      role: "driver",
      resource_id: uuid(9),
      status: "unknown",
      reasons: ["stale_duty_data"],
    },
  ],
};

test("a trip parses and refuses unknown, missing or impossible fields", () => {
  expect(tripSchema.parse(trip)).toEqual(trip);
  expect(() => tripSchema.parse({ ...trip, extra: true })).toThrow();
  const { events: _events, ...missing } = trip;
  void _events;
  expect(() => tripSchema.parse(missing)).toThrow();
  expect(() => tripSchema.parse({ ...trip, status: "lost" })).toThrow();
  expect(() =>
    tripSchema.parse({
      ...trip,
      legs: [{ ...trip.legs[0], delivered: -1 }],
    }),
  ).toThrow();
});

test("lists carry a cursor and at most 50 distinct items", () => {
  const page = { items: [trip], next_cursor: trip.trip_id };
  expect(tripListSchema.parse(page)).toEqual(page);
  expect(() =>
    tripListSchema.parse({ items: [trip, trip], next_cursor: null }),
  ).toThrow();
  expect(() =>
    tripListSchema.parse({
      items: Array.from({ length: 51 }, (_, n) => ({
        ...trip,
        trip_id: uuid(100 + n),
      })),
      next_cursor: null,
    }),
  ).toThrow();
  expect(
    driverListSchema.parse({ items: [driver], next_cursor: null }).items,
  ).toEqual([driver]);
  expect(
    vehicleListSchema.parse({ items: [vehicle], next_cursor: null }).items,
  ).toEqual([vehicle]);
  expect(() =>
    vehicleListSchema.parse({
      items: [{ ...vehicle, kind: "van" }],
      next_cursor: null,
    }),
  ).toThrow();
});

test("clearance has exactly three outcomes", () => {
  expect(clearanceSchema.parse(clearance)).toEqual(clearance);
  expect(() =>
    clearanceSchema.parse({ ...clearance, status: "probably" }),
  ).toThrow();
  expect(() =>
    clearanceSchema.parse({ ...clearance, profile: undefined }),
  ).toThrow();
});

test("transport routes have response contracts", () => {
  const route = (suffix: string, method = "GET") =>
    managementResponseSchema(
      `/v1/businesses/${business}/transport${suffix}`,
      method,
    );
  expect(route("/trips")).toBe(tripListSchema);
  expect(route(`/trips/${uuid(2)}`)).toBe(tripSchema);
  expect(route(`/trips/${uuid(2)}/events`, "POST")).toBe(tripSchema);
  expect(route(`/trips/${uuid(2)}/assignments/${uuid(5)}`, "PUT")).toBe(
    tripSchema,
  );
  expect(route(`/trips/${uuid(2)}/assignments/${uuid(5)}/end`, "POST")).toBe(
    tripSchema,
  );
  expect(route(`/trips/${uuid(2)}/clearance?at=x`)).toBe(clearanceSchema);
  expect(route("/drivers?after=x")).toBe(driverListSchema);
  expect(route("/vehicles")).toBe(vehicleListSchema);
});

// M6b: orders are paged like trips; the grant list states rights in words.
const order = {
  order_id: uuid(20),
  revision: 2,
  customer_id: uuid(21),
  reference: "FAKE-SO-1",
  loads: [
    {
      load_id: uuid(22),
      position: 1,
      description: "FAKE pallets",
      quantity: 10,
      unit: "pallet",
      weight_grams: null,
      shipper_id: null,
      consignee_id: null,
      planned: 10,
    },
  ],
};

test("orders are strict and paged with a cursor", () => {
  expect(orderSchema.parse(order)).toEqual(order);
  expect(() => orderSchema.parse({ ...order, extra: 1 })).toThrow();
  const page = { items: [order], next_cursor: uuid(20) };
  expect(orderListSchema.parse(page)).toEqual(page);
  expect(() => orderListSchema.parse({ items: [order] })).toThrow();
  expect(() =>
    orderListSchema.parse({ items: [order, order], next_cursor: null }),
  ).toThrow();
  expect(
    managementResponseSchema(
      `/v1/businesses/${business}/transport/orders`,
      "GET",
    ),
  ).toBe(orderListSchema);
  for (const method of ["GET", "PUT"])
    expect(
      managementResponseSchema(
        `/v1/businesses/${business}/transport/orders/${uuid(20)}`,
        method,
      ),
    ).toBe(orderSchema);
  for (const suffix of [
    `trips/${uuid(2)}`,
    `drivers/${uuid(5)}`,
    `vehicles/${uuid(6)}`,
  ])
    expect(
      managementResponseSchema(
        `/v1/businesses/${business}/transport/${suffix}`,
        "PUT",
      ),
    ).not.toBeNull();
});

test("grant rights are stated in words", () => {
  expect(
    describeAccess([
      "booking.read",
      "booking.write",
      "catalog.read",
      "staff.read",
    ]),
  ).toBe("Manage bookings");
  expect(
    describeAccess(["transport.read", "transport.assign", "transport.events"]),
  ).toBe("Transport: view, assign crews, record stop events");
  expect(
    describeAccess([
      "booking.read",
      "catalog.read",
      "staff.read",
      "transport.read",
      "transport.plan",
    ]),
  ).toBe("View bookings; Transport: view, plan trips");
});

// M7b: the money routes of M7a.
test("transport money responses are strict and routed", () => {
  const rate = {
    order_id: uuid(30),
    current: {
      revision: 1,
      currency: "USD",
      basis: "per_mile",
      amount: "2.35",
      created_at: "2026-10-25T12:00:00Z",
    },
    versions: [
      {
        revision: 1,
        currency: "USD",
        basis: "per_mile",
        amount: "2.35",
        created_at: "2026-10-25T12:00:00Z",
      },
    ],
  };
  expect(rateSchema.parse(rate)).toEqual(rate);
  expect(() => rateSchema.parse({ ...rate, extra: 1 })).toThrow();
  const pay = {
    trip_id: uuid(2),
    components: [
      {
        component_id: uuid(31),
        trip_id: uuid(2),
        counterparty_id: uuid(32),
        role: "dispatch_fee",
        currency: "USD",
        basis: "percent",
        amount: null,
        rate: null,
        percent: "7.5",
        base: "1250.00",
        accrual: null,
      },
    ],
  };
  expect(paySchema.parse(pay)).toEqual(pay);
  expect(() =>
    paySchema.parse({
      ...pay,
      components: [{ ...pay.components[0], role: "captain" }],
    }),
  ).toThrow();
  const base = `/v1/businesses/${business}/transport`;
  for (const method of ["GET", "PUT"])
    expect(
      managementResponseSchema(`${base}/orders/${uuid(30)}/rate`, method),
    ).toBe(rateSchema);
  for (const method of ["GET", "POST"])
    expect(
      managementResponseSchema(`${base}/orders/${uuid(30)}/invoice`, method),
    ).toBe(orderInvoiceSchema);
  expect(managementResponseSchema(`${base}/trips/${uuid(2)}/pay`, "GET")).toBe(
    paySchema,
  );
  for (const [suffix, method] of [
    [`/trips/${uuid(2)}/pay/${uuid(31)}`, "PUT"],
    [`/trips/${uuid(2)}/pay/${uuid(31)}/accrue`, "POST"],
  ] as const)
    expect(managementResponseSchema(base + suffix, method)).not.toBeNull();
});

// Package M review fixes R-02 and R-04 (docs/plan/PACKAGE_M_REVIEW_FIXES_2026-10-26.md).
test("a leg loaded short is closed once its pickup is departed", () => {
  const short = {
    quantity: 10,
    loaded: 8,
    delivered: 8,
    refused: 0,
    damaged: 0,
    pickup_stop: 1,
  };
  expect(legOpen(short, [{ kind: "loaded", stop_position: 1 }])).toBe(2);
  expect(
    legOpen(short, [
      { kind: "loaded", stop_position: 1 },
      { kind: "departed", stop_position: 2 },
    ]),
  ).toBe(2);
  expect(legOpen(short, [{ kind: "departed", stop_position: 1 }])).toBe(0);
  expect(
    legOpen({ ...short, delivered: 5 }, [
      { kind: "departed", stop_position: 1 },
    ]),
  ).toBe(3);
});

test("a stop window survives editing exactly", () => {
  const zone = "America/Chicago";
  for (const [start, end] of [
    // Monday 08:00 to Wednesday 17:00.
    ["2026-10-26T13:00:00.000Z", "2026-10-28T22:00:00.000Z"],
    // A zero-length window.
    ["2026-10-26T13:00:00.000Z", "2026-10-26T13:00:00.000Z"],
    // 22:00 CDT to 06:00 CST across the 2026-11-01 change.
    ["2026-11-01T03:00:00.000Z", "2026-11-01T12:00:00.000Z"],
  ] as const) {
    const fields = stopWindowFields(start, end, zone);
    expect(
      stopWindowInstants(
        fields.date,
        fields.from,
        fields.endDate,
        fields.to,
        zone,
      ),
    ).toEqual({ start, end });
  }
  // A new overnight window without an end date closes on the next local day.
  expect(stopWindowInstants("2026-10-31", "22:00", "", "06:00", zone)).toEqual({
    start: "2026-11-01T03:00:00.000Z",
    end: "2026-11-01T12:00:00.000Z",
  });
});

test("a grant says planning is API only while the screen cannot plan", () => {
  expect(new Map(TRANSPORT_ACTIONS).get("transport.plan")).toBe(
    "Plan trips (API only)",
  );
});
