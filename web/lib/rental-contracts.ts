import { z } from "zod";

// R8a (package R): strict response contracts of the R1-R3a rental routes the screens read
// (classes, units, bookings, availability and unit assignments). Times arrive in UTC.
const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const text = (max: number) => z.string().min(1).max(max);
const revision = z.number().int().positive();
const count = z.number().int().min(0);

export const attributeSchema = z.strictObject({
  key: z.string().regex(/^[a-z][a-z0-9_]{0,31}$/),
  label: text(100),
  type: z.enum(["text", "number", "boolean"]),
  required: z.boolean(),
});
export const classSchema = z.strictObject({
  class_id: id,
  revision,
  code: z.string().regex(/^[A-Z0-9][A-Z0-9_-]{0,31}$/),
  name: text(200),
  meter_kind: z.enum(["none", "odometer", "hours"]),
  attributes: z.array(attributeSchema).max(50),
  updated_at: instant,
});
export const classListSchema = z.strictObject({
  items: z.array(classSchema),
  next_cursor: id.nullable(),
});

export const unitSchema = z.strictObject({
  unit_id: id,
  revision,
  class_id: id,
  identifier: text(64),
  location_id: id,
  state: z.enum(["active", "retired"]),
  values: z.record(z.string(), text(500)),
  updated_at: instant,
});
export const unitListSchema = z.strictObject({
  items: z.array(unitSchema),
  next_cursor: id.nullable(),
});

export const bookingSchema = z.strictObject({
  booking_id: id,
  number: z.number().int().positive(),
  class_id: id,
  customer_id: id,
  pickup_location_id: id,
  return_location_id: id,
  starts_at: instant,
  ends_at: instant,
  note: text(1000).nullable(),
  booked_at: instant,
  cancellation: z
    .strictObject({ reason: text(500), cancelled_at: instant })
    .nullable(),
});
export const bookingListSchema = z.strictObject({
  items: z.array(bookingSchema),
  next_cursor: id.nullable(),
});

export const availabilitySchema = z.strictObject({
  class_id: id,
  location_id: id,
  starts_at: instant,
  ends_at: instant,
  units: count,
  booked: count,
  available: count,
});

export const assignmentSchema = z.strictObject({
  assignment_id: id,
  booking_id: id,
  unit_id: id,
  starts_at: instant,
  ends_at: instant,
  assigned_at: instant,
  release: z
    .strictObject({
      reason: z.enum(["replaced", "cancelled"]),
      released_at: instant,
    })
    .nullable(),
});
export const assignmentListSchema = z.strictObject({
  items: z.array(assignmentSchema),
});

export type RentalClass = z.infer<typeof classSchema>;
export type ClassList = z.infer<typeof classListSchema>;
export type MeterKind = RentalClass["meter_kind"];
export type Unit = z.infer<typeof unitSchema>;
export type UnitList = z.infer<typeof unitListSchema>;
export type Booking = z.infer<typeof bookingSchema>;
export type BookingList = z.infer<typeof bookingListSchema>;
export type Availability = z.infer<typeof availabilitySchema>;
export type Assignment = z.infer<typeof assignmentSchema>;
export type AssignmentList = z.infer<typeof assignmentListSchema>;

const nested = (tail: string) => new RegExp(`^/rental${tail}$`, "i");
const uuid = "[0-9a-f-]{36}";
const routes: [RegExp, string[], z.ZodType][] = [
  [nested("/classes"), ["GET"], classListSchema],
  [nested(`/classes/${uuid}`), ["GET", "PUT"], classSchema],
  [nested("/units"), ["GET"], unitListSchema],
  [nested(`/units/${uuid}`), ["GET", "PUT"], unitSchema],
  [nested("/bookings"), ["GET"], bookingListSchema],
  [nested("/bookings"), ["POST"], bookingSchema],
  [nested(`/bookings/${uuid}`), ["GET"], bookingSchema],
  [nested(`/bookings/${uuid}/cancellation`), ["POST"], bookingSchema],
  [nested("/availability"), ["GET"], availabilitySchema],
  [nested(`/bookings/${uuid}/assignments`), ["GET"], assignmentListSchema],
  [nested(`/bookings/${uuid}/assignment`), ["POST"], assignmentSchema],
];

/** The contract of a rental route under /v1/businesses/{id}, or null for another route. */
export function rentalResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  const path = suffix.split("?")[0] ?? "";
  for (const [pattern, methods, schema] of routes)
    if (pattern.test(path) && methods.includes(method)) return schema;
  return null;
}

/** R8a decision 1: rental rights belong to active owners and managers who are not delegates.
 * The server still decides every read and command; this only avoids a screen it refuses. */
export function canManageRental(
  member: { role: string; status: string; delegation?: unknown } | undefined,
): boolean {
  return (
    member?.status === "active" &&
    !member.delegation &&
    ["owner", "manager"].includes(member.role)
  );
}
