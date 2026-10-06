import { z } from "zod";

const id = z.uuid();
const revision = z.number().int().positive();
const instant = z.iso.datetime({ offset: true });
const kind = z.enum(["person", "organization"]);
const state = z.enum(["active", "archived", "merged"]);
export const role = z.enum(["customer", "supplier", "contractor", "partner"]);
const roles = z
  .array(role)
  .max(4)
  .refine((v) => new Set(v).size === v.length);
const basis = z
  .array(z.enum(["email", "phone"]))
  .max(2)
  .refine((v) => new Set(v).size === v.length);
const envelope = { schema_version: z.literal(1), business_id: id };
// The server limits names in Unicode code points, not UTF-16 units.
const name = z
  .string()
  .refine((v) => Array.from(v).length >= 1 && Array.from(v).length <= 200);
const subject = { ...envelope, counterparty_id: id };
const summary = z
  .strictObject({
    counterparty_id: id,
    kind,
    revision,
    display_name: name,
    roles,
    state,
    merged_into: id.nullable(),
  })
  .refine(
    (v) =>
      (v.state === "merged") === (v.merged_into !== null) &&
      v.merged_into !== v.counterparty_id,
  );
export const counterpartySchema = z
  .strictObject({
    ...subject,
    kind,
    revision,
    display_name: name,
    legal_name: z.string().nullable(),
    tax_id: z.string().nullable(),
    registration_number: z.string().nullable(),
    email: z.string().nullable(),
    phone: z.string().nullable(),
    roles,
    state,
    merged_into: id.nullable(),
    created_at: instant,
    contacts: z
      .array(
        z.strictObject({
          position: z.number().int().min(1).max(20),
          name: z.string().min(1),
          job_title: z.string().nullable(),
          email: z.string().nullable(),
          phone: z.string().nullable(),
        }),
      )
      .max(20),
  })
  .refine(
    (v) =>
      (v.state === "merged") === (v.merged_into !== null) &&
      v.merged_into !== v.counterparty_id &&
      v.contacts.every((c, i) => c.position === i + 1),
  );
export const counterpartyListSchema = z
  .strictObject({
    ...envelope,
    items: z.array(summary).max(100),
    next_cursor: id.nullable(),
  })
  .refine(
    (v) =>
      new Set(v.items.map((c) => c.counterparty_id)).size === v.items.length,
  );
export const counterpartyHistorySchema = z.strictObject({
  ...subject,
  items: z
    .array(
      z.strictObject({
        revision,
        state,
        display_name: z.string(),
        created_at: instant,
      }),
    )
    .max(100),
  next_cursor: revision.nullable(),
});
const match = z
  .strictObject({
    counterparty_id: id,
    kind,
    display_name: z.string(),
    state,
    reasons: z
      .array(
        z.enum(["email", "phone", "tax_id", "registration_number", "name"]),
      )
      .min(1)
      .max(5),
    strength: z.enum(["strong", "weak"]),
  })
  .refine(
    (v) =>
      new Set(v.reasons).size === v.reasons.length &&
      (v.strength === "strong") === v.reasons.some((r) => r !== "name"),
  );
export const matchesSchema = z.strictObject({
  ...envelope,
  items: z.array(match).max(100),
});
export const matchDecisionSchema = z
  .strictObject({
    ...subject,
    decision_id: id,
    kind: z.enum(["merged", "distinct", "separated"]),
    other_counterparty_id: id,
    reverses_decision_id: id.nullable(),
    counterparty_revision: revision.nullable(),
    reversed: z.boolean(),
    decided_at: instant,
  })
  .refine(
    (v) =>
      v.counterparty_id !== v.other_counterparty_id &&
      (v.kind === "distinct") === (v.counterparty_revision === null) &&
      (v.kind === "separated") === (v.reverses_decision_id !== null),
  );
export const matchDecisionListSchema = z
  .strictObject({
    ...subject,
    items: z.array(matchDecisionSchema).max(100),
  })
  .refine((v) =>
    v.items.every(
      (d) =>
        d.business_id === v.business_id &&
        [d.counterparty_id, d.other_counterparty_id].includes(
          v.counterparty_id,
        ),
    ),
  );
const booking = z.strictObject({
  booking_id: id,
  starts_at: instant,
  status: z.enum(["HOLD", "CONFIRMED", "CANCELLED", "EXPIRED"]),
  customer_name: z.string().nullable(),
  email: z.string().nullable(),
  phone: z.string().nullable(),
});
const link = z
  .strictObject({
    link_id: id,
    booking_id: id,
    sequence: revision,
    action: z.enum(["linked", "unlinked"]),
    counterparty_id: id,
    basis,
    decided_at: instant,
  })
  .refine((v) => (v.action === "linked") === v.basis.length > 0);
export const bookingCandidatesSchema = z.strictObject({
  ...subject,
  items: z
    .array(
      z.strictObject({ booking, basis: basis.refine((v) => v.length > 0) }),
    )
    .max(100),
});
export const linkedBookingsSchema = z.strictObject({
  ...subject,
  items: z
    .array(
      z.strictObject({
        booking,
        counterparty_id: id,
        sequence: revision,
        basis: basis.refine((v) => v.length > 0),
        decided_at: instant,
        still_matches: z.boolean(),
      }),
    )
    .max(100),
  next_cursor: id.nullable(),
});
export const bookingLinkHistorySchema = z
  .strictObject({
    ...subject,
    items: z.array(link).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => v.items.every((l) => l.counterparty_id === v.counterparty_id));
export const bookingLinkResultSchema = z
  .strictObject({
    ...subject,
    links: z.array(link).min(1).max(50),
  })
  .refine((v) => v.links.every((l) => l.counterparty_id === v.counterparty_id));

export function counterpartyResponseSchema(
  path: string,
  method: string,
): z.ZodType | null {
  if (path === "/counterparties" && method === "GET")
    return counterpartyListSchema;
  if (path === "/counterparties/match-check" && method === "POST")
    return matchesSchema;
  const route =
    /^\/counterparties\/[0-9a-f-]{36}(?:\/(versions|merged-from|duplicates|match-decisions|booking-candidates|bookings|booking-links))?$/i.exec(
      path,
    );
  if (!route) return null;
  const suffix = route[1];
  if (!suffix && ["GET", "PUT"].includes(method)) return counterpartySchema;
  if (method === "GET") {
    switch (suffix) {
      case "versions":
        return counterpartyHistorySchema;
      case "merged-from":
        return counterpartyListSchema;
      case "duplicates":
        return matchesSchema;
      case "match-decisions":
        return matchDecisionListSchema;
      case "booking-candidates":
        return bookingCandidatesSchema;
      case "bookings":
        return linkedBookingsSchema;
      case "booking-links":
        return bookingLinkHistorySchema;
    }
  }
  if (method === "POST" && suffix === "match-decisions")
    return matchDecisionSchema;
  if (method === "POST" && suffix === "booking-links")
    return bookingLinkResultSchema;
  return null;
}

export type Counterparty = z.infer<typeof counterpartySchema>;
export type CounterpartyPage = z.infer<typeof counterpartyListSchema>;
export type CounterpartyHistory = z.infer<typeof counterpartyHistorySchema>;
export type Matches = z.infer<typeof matchesSchema>;
export type MatchDecisions = z.infer<typeof matchDecisionListSchema>;
export type BookingCandidates = z.infer<typeof bookingCandidatesSchema>;
export type LinkedBookings = z.infer<typeof linkedBookingsSchema>;
export type BookingLinkHistory = z.infer<typeof bookingLinkHistorySchema>;
export type ContactInput = {
  name: string;
  job_title: string | null;
  email: string | null;
  phone: string | null;
};
export interface CounterpartyInput {
  schema_version: 1;
  expected_revision: number;
  kind: "person" | "organization";
  display_name: string;
  legal_name: string | null;
  tax_id: string | null;
  registration_number: string | null;
  email: string | null;
  phone: string | null;
  roles: z.infer<typeof role>[];
  archived: boolean;
  contacts: ContactInput[];
}
export type MatchDecisionInput =
  | {
      decision: "merge";
      into_id: string;
      expected_revision: number;
      into_expected_revision: number;
    }
  | { decision: "distinct"; other_id: string }
  | { decision: "separate"; decision_id: string; expected_revision: number };
export type BookingLinkInput =
  | { action: "link"; booking_ids: string[] }
  | { action: "unlink"; booking_id: string; expected_sequence: number };
export type CounterpartyCommand =
  | { type: "save"; id: string; key: string; body: CounterpartyInput }
  | { type: "match"; id: string; key: string; body: MatchDecisionInput }
  | { type: "link"; id: string; key: string; body: BookingLinkInput };
