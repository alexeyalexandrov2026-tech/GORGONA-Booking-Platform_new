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

// R8b (package R): rate cards (R4a), the quote and the agreement (R4b) and the security (R5a).
const money = z.number().int().min(0);
const code = z.string().regex(/^[A-Z0-9][A-Z0-9_-]{0,31}$/);
const counts = z.record(z.string(), z.number().int().min(0));

export const rateCardSchema = z.strictObject({
  rate_card_id: id,
  class_id: id,
  location_id: id,
  version: revision,
  currency: z.string().regex(/^[A-Z]{3}$/),
  effective_from: instant,
  rates: z.strictObject({
    hour: z.number().int().positive().nullable(),
    day: z.number().int().positive().nullable(),
    week: z.number().int().positive().nullable(),
    month: z.number().int().positive().nullable(),
  }),
  meter_allowance_per_day: z.number().int().min(0).nullable(),
  excess_rate: money.nullable(),
  extras: z.array(
    z.strictObject({
      code,
      name: text(200),
      price: money,
      unit: z.enum(["per_day", "per_rental"]),
    }),
  ),
  created_at: instant,
});
export const rateCardListSchema = z.strictObject({
  items: z.array(rateCardSchema),
});

export const quoteSchema = z.strictObject({
  rate_card_id: id,
  version: revision,
  currency: z.string().regex(/^[A-Z]{3}$/),
  starts_at: instant,
  ends_at: instant,
  counts,
  rental: money,
  rental_days: z.number().int().positive(),
  extras: z.array(
    z.strictObject({
      code,
      quantity: z.number().int().positive(),
      amount: money,
    }),
  ),
  total: money,
  booking_id: id.nullable(),
});

export const agreementVersionSchema = z.strictObject({
  version: revision,
  rate_card_id: id,
  card_version: revision,
  currency: z.string().regex(/^[A-Z]{3}$/),
  starts_at: instant,
  ends_at: instant,
  counts,
  rental: money,
  rental_days: z.number().int().positive(),
  extras: z.array(
    z.strictObject({
      code,
      name: text(200),
      price: money,
      unit: z.enum(["per_day", "per_rental"]),
      quantity: z.number().int().positive(),
      amount: money,
    }),
  ),
  total: money,
  source: z.enum(["platform", "paper", "email"]),
  accepted_by: text(200),
  accepted_at: instant,
  reason: text(500).nullable(),
  created_at: instant,
});
export const agreementSchema = z.strictObject({
  agreement_id: id,
  booking_id: id,
  current_version: revision,
  versions: z.array(agreementVersionSchema),
});

export const securityEventSchema = z.strictObject({
  sequence: revision,
  kind: z.enum(["held", "captured", "released", "expired"]),
  amount: money,
  reference: text(200).nullable(),
  hold_expires_at: instant.nullable(),
  basis: text(500).nullable(),
  occurred_at: instant,
  recorded_by: id,
  provider: z
    .strictObject({ receipt_id: id, intent: text(120), linked_by: id })
    .nullable(),
});
export const securitySchema = z.strictObject({
  security_id: id,
  booking_id: id,
  amount: money,
  currency: z.string().regex(/^[A-Z]{3}$/),
  method: z.enum(["card_hold", "cash", "bank_transfer", "other"]),
  state: z.enum(["requested", "held", "released", "expired"]),
  held: money,
  captured: money,
  released: money,
  expired: money,
  remaining: money,
  events: z.array(securityEventSchema),
});

export type RateCard = z.infer<typeof rateCardSchema>;
export type RateCardList = z.infer<typeof rateCardListSchema>;
export type Quote = z.infer<typeof quoteSchema>;
export type Agreement = z.infer<typeof agreementSchema>;
export type Security = z.infer<typeof securitySchema>;
export type SecurityKind = Security["events"][number]["kind"];
export type SecurityMethod = Security["method"];

// R8c (package R): inspections (R6a), usage (R6b), the settlement (R7a), damage charges and refunds
// (R7b) and the reconciliation (R7c).
const currency = z.string().regex(/^[A-Z]{3}$/);
const severity = z.enum(["minor", "major"]);
export const inspectionsSchema = z.strictObject({
  booking_id: id,
  inspections: z.array(
    z.strictObject({
      inspection_id: id,
      kind: z.enum(["handover", "return"]),
      assignment_id: id,
      unit_id: id,
      meter: count.nullable(),
      level: z.number().int().min(0).max(100).nullable(),
      note: text(1000).nullable(),
      inspected_by: id,
      inspected_at: instant,
      marks: z.array(
        z.strictObject({
          position: revision,
          area: text(100),
          severity,
          note: text(500).nullable(),
          new: z.boolean(),
          photo: z.strictObject({ document_id: id, revision }).nullable(),
        }),
      ),
    }),
  ),
});
export const usageSchema = z.strictObject({
  booking_id: id,
  currency,
  state: z.enum(["not_handed_over", "out", "returned"]),
  period_end: instant,
  rental_days: z.number().int().positive(),
  as_of: instant,
  overdue_seconds: count,
  overdue_hours: count,
  distance: count.nullable(),
  allowance: count.nullable(),
  excess: count.nullable(),
  excess_amount: money.nullable(),
});
export const settlementSchema = z.strictObject({
  booking_id: id,
  agreement_version: revision,
  currency,
  rental_minor: money,
  excess_minor: money,
  late_minor: money,
  late_units: count,
  total_minor: money,
  book_id: id,
  invoice_document_id: id,
  settled_by: id,
  settled_at: instant,
});
export const chargesSchema = z.strictObject({
  booking_id: id,
  damage_charges: z.array(
    z.strictObject({
      number: revision,
      marks: z.array(revision).min(1),
      amount_minor: money,
      reason: text(500),
      book_id: id,
      invoice_document_id: id,
      charged_by: id,
      charged_at: instant,
    }),
  ),
  refunds: z.array(
    z.strictObject({
      number: revision,
      method: z.enum(["credit", "external"]),
      amount_minor: money,
      reason: text(500),
      reference: text(200).nullable(),
      refunded_at: instant.nullable(),
      book_id: id.nullable(),
      credit_document_id: id.nullable(),
      recorded_by: id,
      recorded_at: instant,
    }),
  ),
});
export const reconciliationSchema = z.strictObject({
  booking_id: id,
  currency,
  documents: z.array(
    z.strictObject({
      kind: z.enum(["settlement", "damage_charge"]),
      number: revision.nullable(),
      amount_minor: money,
      book_id: id,
      document_id: id,
      state: z.enum(["draft", "issued"]),
      principal_minor: money,
      paid_minor: money,
      credited_minor: money,
      open_minor: money,
    }),
  ),
  refunds: z.array(
    z.strictObject({
      number: revision,
      method: z.enum(["credit", "external"]),
      amount_minor: money,
      state: z.enum(["recorded", "draft", "issued"]),
      credit_document_id: id.nullable(),
      refund_obligation_minor: money.nullable(),
      refund_paid_minor: money.nullable(),
    }),
  ),
  security: z
    .strictObject({
      state: z.enum(["requested", "held", "released", "expired"]),
      amount: money,
      held: money,
      captured: money,
      released: money,
      expired: money,
      remaining: money,
    })
    .nullable(),
  totals: z.strictObject({
    charged_minor: money,
    invoiced_minor: money,
    paid_minor: money,
    credited_minor: money,
    open_minor: money,
    refunded_external_minor: money,
    refund_owed_minor: money,
  }),
});

export type Inspections = z.infer<typeof inspectionsSchema>;
export type Inspection = Inspections["inspections"][number];
export type Severity = z.infer<typeof severity>;
export type Usage = z.infer<typeof usageSchema>;
export type Settlement = z.infer<typeof settlementSchema>;
export type Charges = z.infer<typeof chargesSchema>;
export type Reconciliation = z.infer<typeof reconciliationSchema>;

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
  [nested(`/classes/${uuid}/rate-cards`), ["GET"], rateCardListSchema],
  [nested(`/classes/${uuid}/rate-cards`), ["POST"], rateCardSchema],
  [nested(`/bookings/${uuid}/quote`), ["GET"], quoteSchema],
  [nested(`/bookings/${uuid}/agreement`), ["GET", "POST"], agreementSchema],
  [nested(`/bookings/${uuid}/security`), ["GET", "POST"], securitySchema],
  [nested(`/bookings/${uuid}/security/events`), ["POST"], securitySchema],
  [nested(`/bookings/${uuid}/inspections`), ["GET", "POST"], inspectionsSchema],
  [nested(`/bookings/${uuid}/usage`), ["GET"], usageSchema],
  [nested(`/bookings/${uuid}/settlement`), ["GET", "POST"], settlementSchema],
  [nested(`/bookings/${uuid}/charges`), ["GET"], chargesSchema],
  [nested(`/bookings/${uuid}/damage-charges`), ["POST"], chargesSchema],
  [nested(`/bookings/${uuid}/refunds`), ["POST"], chargesSchema],
  [nested(`/bookings/${uuid}/reconciliation`), ["GET"], reconciliationSchema],
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
