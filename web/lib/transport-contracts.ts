import { z } from "zod";

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

const trip = /^\/transport\/trips\/[0-9a-f-]{36}$/i;
const assignment =
  /^\/transport\/trips\/[0-9a-f-]{36}\/assignments\/[0-9a-f-]{36}$/i;

/** The response contract of a transport route under /v1/businesses/{id}, or null. */
export function transportResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  if (suffix === "/transport/trips" && method === "GET") return tripListSchema;
  if (trip.test(suffix) && method === "GET") return tripSchema;
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
