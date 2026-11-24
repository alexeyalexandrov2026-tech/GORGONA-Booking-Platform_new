// M6a (package M): the transport routes the dispatch board and the trip page use. Lists are read to
// their end through the server's cursor; a command keeps its Idempotency-Key until it succeeds, so a
// retry after a lost answer is the same request.
import { ManagementApiError, managementFetch } from "./management-api";
import type {
  Clearance,
  Driver,
  DriverList,
  Component,
  Order,
  OrderInvoice,
  OrderList,
  Pay,
  Rate,
  Trip,
  TripList,
  Vehicle,
  VehicleList,
} from "./transport-contracts";

export const base = (business: string) =>
  `/v1/businesses/${business}/transport`;
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
export async function command<T>(
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

// M7b: transport money (ADR-0033); a finance member's commands, each with its record id and key.
export const fetchRate = (business: string, order: string): Promise<Rate> =>
  managementFetch<Rate>(`${base(business)}/orders/${order}/rate`);
export const saveRate = (
  business: string,
  order: string,
  body: {
    schema_version: 1;
    expected_revision: number;
    currency: string;
    basis: "fixed" | "per_mile";
    amount: string;
  },
): Promise<Rate> =>
  command<Rate>(`${base(business)}/orders/${order}/rate`, "PUT", body);

/** The order's invoice, or null while it has none. */
export async function fetchOrderInvoice(
  business: string,
  order: string,
): Promise<OrderInvoice | null> {
  try {
    return await managementFetch<OrderInvoice>(
      `${base(business)}/orders/${order}/invoice`,
    );
  } catch (error) {
    if (error instanceof ManagementApiError && error.code === "NOT_FOUND")
      return null;
    throw error;
  }
}
export type OrderInvoiceBody = {
  schema_version: 1;
  book_id: string;
  control_account_id: string;
  revenue_account_id: string;
  invoice_date: string;
  number: string;
  miles: string | null;
  extra_lines: { description: string; amount: string; account_id: string }[];
};
export const createOrderInvoice = (
  business: string,
  order: string,
  body: OrderInvoiceBody,
): Promise<OrderInvoice> =>
  command<OrderInvoice>(
    `${base(business)}/orders/${order}/invoice`,
    "POST",
    body,
  );

export const fetchPay = (business: string, trip: string): Promise<Pay> =>
  managementFetch<Pay>(`${base(business)}/trips/${trip}/pay`);
export type ComponentBody = {
  schema_version: 1;
  counterparty_id: string;
  role: Component["role"];
  currency: string;
  basis: Component["basis"];
  amount: string | null;
  rate: string | null;
  percent: string | null;
  base: string | null;
};
export const saveComponent = (
  business: string,
  trip: string,
  component: string,
  body: ComponentBody,
): Promise<Component> =>
  command<Component>(
    `${base(business)}/trips/${trip}/pay/${component}`,
    "PUT",
    body,
  );
export type AccrueBody = {
  schema_version: 1;
  book_id: string;
  expense_account_id: string;
  payable_account_id: string;
  accrual_date: string;
  number: string;
  miles: string | null;
};
export const accrueComponent = (
  business: string,
  trip: string,
  component: string,
  body: AccrueBody,
): Promise<Component> =>
  command<Component>(
    `${base(business)}/trips/${trip}/pay/${component}/accrue`,
    "POST",
    body,
  );
