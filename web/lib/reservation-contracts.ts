import { z } from "zod";

const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
// The server limits text in Unicode code points, not UTF-16 units.
const text = (min: number, max: number) =>
  z.string().refine((v) => {
    const length = Array.from(v).length;
    return length >= min && length <= max;
  });

export const reservationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    reservation_id: id,
    location_id: id,
    // Empty when every reserved resource moved out of the caller's branch.
    resource_ids: z.array(id).max(10),
    starts_at: instant,
    ends_at: instant,
    purpose: text(1, 200).nullable(),
    status: z.enum(["active", "cancelled"]),
    created_at: instant,
    cancelled_at: instant.nullable(),
  })
  .refine(
    (v) =>
      Date.parse(v.starts_at) < Date.parse(v.ends_at) &&
      (v.status === "cancelled") === (v.cancelled_at !== null) &&
      new Set(v.resource_ids).size === v.resource_ids.length,
  );
export const reservationListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: id,
    items: z.array(reservationSchema).max(200),
  })
  .refine(
    (v) =>
      new Set(v.items.map((r) => r.reservation_id)).size === v.items.length,
  );

export function reservationResponseSchema(
  path: string,
  method: string,
): z.ZodType | null {
  if (path === "/resource-reservations")
    return method === "GET" ? reservationListSchema : null;
  const route = /^\/resource-reservations\/[0-9a-f-]{36}(\/cancel)?$/i.exec(
    path,
  );
  if (!route) return null;
  if (!route[1] && ["GET", "PUT"].includes(method)) return reservationSchema;
  if (route[1] && method === "POST") return reservationSchema;
  return null;
}

export type Reservation = z.infer<typeof reservationSchema>;
export type ReservationPage = z.infer<typeof reservationListSchema>;
export type ReservationCommand =
  | {
      type: "create";
      id: string;
      key: string;
      body: {
        schema_version: 1;
        location_id: string;
        resource_ids: string[];
        starts_at: string;
        ends_at: string;
        purpose: string | null;
      };
    }
  | { type: "cancel"; id: string; key: string; body: { schema_version: 1 } };
