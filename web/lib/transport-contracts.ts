import { z } from "zod";
import { brokerageResponseSchema } from "./brokerage-contracts";
import { invoiceSchema, obligationSchema } from "./financial-contracts";

// M6a (package M): strict response contracts of the transport routes the dispatch board and the trip
// page read. Times arrive in UTC; each stop names its own time zone for display.
const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const count = z.number().int().min(0).max(1_000_000);
const cursor = id.nullable();
const unique = <T>(items: T[], key: (item: T) => string) =>
  new Set(items.map(key)).size === items.length;

export const stopSchema = z.strictObject({
  position: z.number().int().min(1).max(50),
  kind: z.enum(["pickup", "delivery"]),
  place: z.string().min(1).max(300),
  time_zone: z.string().min(1).max(64),
  window_start: instant,
  window_end: instant,
});
export const legSchema = z.strictObject({
  position: z.number().int().min(1).max(100),
  load_id: id,
  quantity: count,
  pickup_stop: z.number().int().min(1).max(50),
  delivery_stop: z.number().int().min(1).max(50),
  loaded: count,
  delivered: count,
  refused: count,
  damaged: count,
});
export const assignmentSchema = z.strictObject({
  assignment_id: id,
  role: z.enum(["driver", "truck", "trailer"]),
  resource_id: id,
  starts_at: instant,
  ends_at: instant.nullable(),
  replaces: id.nullable(),
});
export const eventSchema = z.strictObject({
  event_id: id,
  stop_position: z.number().int().min(1).max(50),
  kind: z.enum([
    "arrived",
    "departed",
    "loaded",
    "delivered",
    "refused",
    "damaged",
    "exception",
  ]),
  occurred_at: instant,
  source: z.string().min(1).max(32),
  source_event_id: z.string().min(1).max(200),
  note: z.string().max(500).nullable(),
  quantities: z.array(
    z.strictObject({
      leg_position: z.number().int().min(1).max(100),
      quantity: count,
    }),
  ),
});
export const tripSchema = z.strictObject({
  trip_id: id,
  location_id: id,
  reference: z.string().min(1).max(64),
  status: z.enum(["planned", "in_transit"]),
  revision: z.number().int().positive(),
  stops: z.array(stopSchema).max(50),
  legs: z.array(legSchema).max(100),
  assignments: z.array(assignmentSchema),
  events: z.array(eventSchema),
});
export const tripListSchema = z
  .strictObject({ items: z.array(tripSchema).max(50), next_cursor: cursor })
  .refine((v) => unique(v.items, (x) => x.trip_id));
export const driverSchema = z.strictObject({
  driver_id: id,
  location_id: id,
  display_name: z.string().min(1).max(200),
  resource_id: id,
});
export const driverListSchema = z
  .strictObject({ items: z.array(driverSchema).max(50), next_cursor: cursor })
  .refine((v) => unique(v.items, (x) => x.driver_id));
export const vehicleSchema = z.strictObject({
  vehicle_id: id,
  location_id: id,
  kind: z.enum(["truck", "trailer"]),
  unit_number: z.string().min(1).max(32),
  resource_id: id,
});
export const vehicleListSchema = z
  .strictObject({ items: z.array(vehicleSchema).max(50), next_cursor: cursor })
  .refine((v) => unique(v.items, (x) => x.vehicle_id));
// M6b: orders with their loads and how much of each is already planned on trips.
export const loadSchema = z.strictObject({
  load_id: id,
  position: z.number().int().min(1).max(50),
  description: z.string().min(1).max(500),
  quantity: z.number().int().min(1).max(1_000_000),
  unit: z.string().min(1).max(32),
  weight_grams: z.number().int().min(0).nullable(),
  shipper_id: id.nullable(),
  consignee_id: id.nullable(),
  planned: count,
});
export const orderSchema = z.strictObject({
  order_id: id,
  revision: z.number().int().positive(),
  customer_id: id,
  reference: z.string().min(1).max(64),
  loads: z.array(loadSchema).min(1).max(50),
});
export const orderListSchema = z
  .strictObject({ items: z.array(orderSchema).max(50), next_cursor: cursor })
  .refine((v) => unique(v.items, (x) => x.order_id));
// M7b: the money of ADR-0033 (M7a routes).
const decimal = z.string().regex(/^(0|[1-9][0-9]*)(\.[0-9]{1,3})?$/);
const rateVersion = z.strictObject({
  revision: z.number().int().positive(),
  currency: z.string().regex(/^[A-Z]{3}$/),
  basis: z.enum(["fixed", "per_mile"]),
  amount: decimal,
  created_at: instant,
});
export const rateSchema = z.strictObject({
  order_id: id,
  current: rateVersion.nullable(),
  versions: z.array(rateVersion),
});
export const orderInvoiceSchema = z.strictObject({
  order_id: id,
  book_id: id,
  document_id: id,
  rate_revision: z.number().int().positive(),
  miles: z
    .string()
    .regex(/^[0-9]+\.[0-9]$/)
    .nullable(),
  invoice: invoiceSchema,
  obligation: obligationSchema.nullable(),
});
export const componentSchema = z.strictObject({
  component_id: id,
  trip_id: id,
  counterparty_id: id,
  role: z.enum(["driver", "owner_operator", "dispatch_fee", "other"]),
  currency: z.string().regex(/^[A-Z]{3}$/),
  basis: z.enum(["fixed", "per_mile", "percent"]),
  amount: decimal.nullable(),
  rate: decimal.nullable(),
  percent: z
    .string()
    .regex(/^[0-9]{1,3}(\.[0-9]{1,2})?$/)
    .nullable(),
  base: decimal.nullable(),
  accrual: z
    .strictObject({
      book_id: id,
      document_id: id,
      miles: z
        .string()
        .regex(/^[0-9]+\.[0-9]$/)
        .nullable(),
      accrual: invoiceSchema,
      obligation: obligationSchema.nullable(),
    })
    .nullable(),
});
export const paySchema = z
  .strictObject({ trip_id: id, components: z.array(componentSchema).max(200) })
  .refine((v) => unique(v.components, (x) => x.component_id));
const outcome = z.enum(["cleared", "not_cleared", "unknown"]);
export const clearanceSchema = z.strictObject({
  trip_id: id,
  at: instant,
  status: outcome,
  profile: z
    .strictObject({ code: z.string(), revision: z.number().int() })
    .nullable(),
  roles: z.array(
    z.strictObject({
      role: z.enum(["driver", "truck", "trailer"]),
      resource_id: id.nullable(),
      status: outcome,
      reasons: z.array(z.string().min(1).max(64)).max(10),
    }),
  ),
});

export type Stop = z.infer<typeof stopSchema>;
export type Leg = z.infer<typeof legSchema>;
export type Assignment = z.infer<typeof assignmentSchema>;
export type TripEvent = z.infer<typeof eventSchema>;
export type Trip = z.infer<typeof tripSchema>;
export type TripList = z.infer<typeof tripListSchema>;
export type Driver = z.infer<typeof driverSchema>;
export type DriverList = z.infer<typeof driverListSchema>;
export type Vehicle = z.infer<typeof vehicleSchema>;
export type VehicleList = z.infer<typeof vehicleListSchema>;
export type Clearance = z.infer<typeof clearanceSchema>;
export type Rate = z.infer<typeof rateSchema>;
export type OrderInvoice = z.infer<typeof orderInvoiceSchema>;
export type Component = z.infer<typeof componentSchema>;
export type Pay = z.infer<typeof paySchema>;
export type Load = z.infer<typeof loadSchema>;
export type Order = z.infer<typeof orderSchema>;
export type OrderList = z.infer<typeof orderListSchema>;

const trip = /^\/transport\/trips\/[0-9a-f-]{36}$/i;
const assignment =
  /^\/transport\/trips\/[0-9a-f-]{36}\/assignments\/[0-9a-f-]{36}$/i;

/** The response contract of a transport route under /v1/businesses/{id}, or null. */
export function transportResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  const brokerage = brokerageResponseSchema(suffix, method);
  if (brokerage) return brokerage;
  if (suffix === "/transport/trips" && method === "GET") return tripListSchema;
  if (trip.test(suffix) && (method === "GET" || method === "PUT"))
    return tripSchema;
  if (
    /^\/transport\/orders\/[0-9a-f-]{36}\/rate$/i.test(suffix) &&
    (method === "GET" || method === "PUT")
  )
    return rateSchema;
  if (
    /^\/transport\/orders\/[0-9a-f-]{36}\/invoice$/i.test(suffix) &&
    (method === "GET" || method === "POST")
  )
    return orderInvoiceSchema;
  if (
    /^\/transport\/trips\/[0-9a-f-]{36}\/pay$/i.test(suffix) &&
    method === "GET"
  )
    return paySchema;
  if (
    (/^\/transport\/trips\/[0-9a-f-]{36}\/pay\/[0-9a-f-]{36}$/i.test(suffix) &&
      method === "PUT") ||
    (/^\/transport\/trips\/[0-9a-f-]{36}\/pay\/[0-9a-f-]{36}\/accrue$/i.test(
      suffix,
    ) &&
      method === "POST")
  )
    return componentSchema;
  if (suffix === "/transport/orders" && method === "GET")
    return orderListSchema;
  if (
    /^\/transport\/orders\/[0-9a-f-]{36}$/i.test(suffix) &&
    (method === "GET" || method === "PUT")
  )
    return orderSchema;
  if (
    /^\/transport\/drivers\/[0-9a-f-]{36}$/i.test(suffix) &&
    (method === "GET" || method === "PUT")
  )
    return driverSchema;
  if (
    /^\/transport\/vehicles\/[0-9a-f-]{36}$/i.test(suffix) &&
    (method === "GET" || method === "PUT")
  )
    return vehicleSchema;
  if (
    /^\/transport\/trips\/[0-9a-f-]{36}\/events$/i.test(suffix) &&
    method === "POST"
  )
    return tripSchema;
  if (assignment.test(suffix) && method === "PUT") return tripSchema;
  if (
    /^\/transport\/trips\/[0-9a-f-]{36}\/assignments\/[0-9a-f-]{36}\/end$/i.test(
      suffix,
    ) &&
    method === "POST"
  )
    return tripSchema;
  if (
    /^\/transport\/trips\/[0-9a-f-]{36}\/clearance$/i.test(suffix) &&
    method === "GET"
  )
    return clearanceSchema;
  if (suffix === "/transport/drivers" && method === "GET")
    return driverListSchema;
  if (suffix === "/transport/vehicles" && method === "GET")
    return vehicleListSchema;
  return null;
}
