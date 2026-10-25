// M6a (package M): the transport routes the dispatch board and the trip page use. Lists are read to
// their end through the server's cursor; a command keeps its Idempotency-Key until it succeeds, so a
// retry after a lost answer is the same request.
import { managementFetch } from "./management-api";
import type {
  Clearance,
  Driver,
  DriverList,
  Order,
  OrderList,
  Trip,
  TripList,
  Vehicle,
  VehicleList,
} from "./transport-contracts";

const base = (business: string) => `/v1/businesses/${business}/transport`;
const after = (cursor?: string) =>
  cursor ? `?after=${encodeURIComponent(cursor)}` : "";

async function everyPage<I>(
  read: (
    cursor?: string,
  ) => Promise<{ items: I[]; next_cursor: string | null }>,
): Promise<I[]> {
  const items: I[] = [];
  let cursor: string | undefined;
  for (;;) {
    const page = await read(cursor);
    items.push(...page.items);
    if (!page.next_cursor) return items;
    cursor = page.next_cursor;
  }
}

export const fetchAllTrips = (business: string): Promise<Trip[]> =>
  everyPage((cursor) =>
    managementFetch<TripList>(`${base(business)}/trips${after(cursor)}`),
  );
export const fetchAllDrivers = (business: string): Promise<Driver[]> =>
  everyPage((cursor) =>
    managementFetch<DriverList>(`${base(business)}/drivers${after(cursor)}`),
  );
export const fetchAllVehicles = (business: string): Promise<Vehicle[]> =>
  everyPage((cursor) =>
    managementFetch<VehicleList>(`${base(business)}/vehicles${after(cursor)}`),
  );
export const fetchAllOrders = (business: string): Promise<Order[]> =>
  everyPage((cursor) =>
    managementFetch<OrderList>(`${base(business)}/orders${after(cursor)}`),
  );
export const fetchTrip = (business: string, trip: string): Promise<Trip> =>
  managementFetch<Trip>(`${base(business)}/trips/${trip}`);
export const fetchClearance = (
  business: string,
  trip: string,
): Promise<Clearance> =>
  managementFetch<Clearance>(`${base(business)}/trips/${trip}/clearance`);

const pending = new Map<string, string>();
async function command<T>(
  path: string,
  method: string,
  body: unknown,
): Promise<T> {
  const payload = JSON.stringify(body);
  const signature = `${method} ${path} ${payload}`;
  let key = pending.get(signature);
  if (!key) {
    key = crypto.randomUUID();
    pending.set(signature, key);
  }
  const result = await managementFetch<T>(path, {
    method,
    body: payload,
    headers: { "Idempotency-Key": key },
  });
  pending.delete(signature);
  return result;
}

export type AssignmentBody = {
  schema_version: 1;
  role: "driver" | "truck" | "trailer";
  resource_id: string;
  starts_at?: string;
  replaces: string | null;
};
export const assign = (
  business: string,
  trip: string,
  assignment: string,
  body: AssignmentBody,
): Promise<Trip> =>
  command<Trip>(
    `${base(business)}/trips/${trip}/assignments/${assignment}`,
    "PUT",
    body,
  );

export type EventBody = {
  schema_version: 1;
  source: "dispatcher";
  source_event_id: string;
  stop_position: number;
  kind: string;
  occurred_at: string;
  note: string | null;
  quantities: { leg_position: number; quantity: number }[];
};
export const recordEvent = (
  business: string,
  trip: string,
  body: EventBody,
): Promise<Trip> =>
  command<Trip>(`${base(business)}/trips/${trip}/events`, "POST", body);

// M6b: planning and fleet forms. Each form keeps its record id until the save succeeds.
export type LoadBody = {
  load_id: string;
  description: string;
  quantity: number;
  unit: string;
};
export type OrderBody = {
  schema_version: 1;
  expected_revision: number;
  customer_id: string;
  reference: string;
  loads: LoadBody[];
};
export const saveOrder = (
  business: string,
  order: string,
  body: OrderBody,
): Promise<Order> =>
  command<Order>(`${base(business)}/orders/${order}`, "PUT", body);

export type TripBody = {
  schema_version: 1;
  expected_revision: number;
  location_id: string;
  reference: string;
  stops: {
    kind: "pickup" | "delivery";
    place: string;
    time_zone: string;
    window_start: string;
    window_end: string;
  }[];
  legs: {
    load_id: string;
    quantity: number;
    pickup_stop: number;
    delivery_stop: number;
  }[];
};
export const saveTrip = (
  business: string,
  trip: string,
  body: TripBody,
): Promise<Trip> =>
  command<Trip>(`${base(business)}/trips/${trip}`, "PUT", body);

export const saveDriver = (
  business: string,
  driver: string,
  body: { schema_version: 1; location_id: string; display_name: string },
): Promise<Driver> =>
  command<Driver>(`${base(business)}/drivers/${driver}`, "PUT", body);
export const saveVehicle = (
  business: string,
  vehicle: string,
  body: {
    schema_version: 1;
    location_id: string;
    kind: "truck" | "trailer";
    unit_number: string;
  },
): Promise<Vehicle> =>
  command<Vehicle>(`${base(business)}/vehicles/${vehicle}`, "PUT", body);
