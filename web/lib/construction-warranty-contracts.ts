import { z } from "zod";

const id = z.uuid();
const date = z.iso.date();
const instant = z.iso.datetime({ offset: true });
const positive = z.int().positive();
const amount = z.int().nonnegative();
const str = (size: number) =>
  z.string().refine((value) => {
    const length = Array.from(value).length;
    return length >= 1 && length <= size;
  });
export const warrantyStateSchema = z.enum([
  "open",
  "repaired",
  "closed",
  "rejected",
]);
export type WarrantyState = z.infer<typeof warrantyStateSchema>;
export const warrantyMoves: Record<WarrantyState, readonly WarrantyState[]> = {
  open: ["repaired", "rejected"],
  repaired: ["closed", "open"],
  closed: [],
  rejected: [],
};

const summary = {
  number: positive,
  title: str(120),
  phase: str(64).nullable(),
  raised_on: date,
  state: warrantyStateSchema,
  repair_minor: amount,
};
const warrantyClaimSchema = z
  .strictObject({
    ...summary,
    schema_version: z.literal(1),
    project_id: id,
    description: str(4000).nullable(),
    location: str(200).nullable(),
    reported_by: str(200),
    events: z.array(
      z.strictObject({
        sequence: positive,
        state: warrantyStateSchema,
        note: str(1000).nullable(),
        recorded_at: instant,
      }),
    ),
    repairs: z.array(
      z.strictObject({
        cost_link: positive,
        amount_minor: positive,
        reversed: z.boolean(),
        recorded_at: instant,
      }),
    ),
    recorded_at: instant,
  })
  .refine((value) => {
    let state: WarrantyState = "open";
    for (const [index, event] of value.events.entries()) {
      if (
        event.sequence !== index + 1 ||
        !warrantyMoves[state].includes(event.state)
      )
        return false;
      if (
        (event.state === "rejected" || event.state === "open") &&
        event.note === null
      )
        return false;
      state = event.state;
    }
    return (
      state === value.state &&
      new Set(value.repairs.map((repair) => repair.cost_link)).size ===
        value.repairs.length &&
      value.repairs.reduce(
        (sum, repair) => sum + (repair.reversed ? 0 : repair.amount_minor),
        0,
      ) === value.repair_minor
    );
  });

const warrantyListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    currency: z.string().regex(/^[A-Z]{3}$/),
    warranty_starts_on: date.nullable(),
    warranty_ends_on: date.nullable(),
    repair_minor: amount,
    items: z.array(z.strictObject(summary)),
  })
  .refine((value) => {
    const { warranty_starts_on: start, warranty_ends_on: end } = value;
    if (!start || !end)
      return (
        start === null &&
        end === null &&
        value.items.length === 0 &&
        value.repair_minor === 0
      );
    return (
      start < end &&
      value.items.every(
        (item, index) =>
          item.number === index + 1 &&
          start <= item.raised_on &&
          item.raised_on <= end,
      ) &&
      value.items.reduce((sum, item) => sum + item.repair_minor, 0) ===
        value.repair_minor
    );
  });

export type WarrantyClaim = z.infer<typeof warrantyClaimSchema>;
export type WarrantyList = z.infer<typeof warrantyListSchema>;
export type WarrantyClaimBody = {
  schema_version: 1;
  title: string;
  description: string | null;
  phase: string | null;
  location: string | null;
  reported_by: string;
  raised_on: string;
};
export type WarrantyEventBody = {
  schema_version: 1;
  expected_sequence: number;
  state: WarrantyState;
  note: string | null;
};

const path =
  /^\/construction\/projects\/([0-9a-f-]{36})\/warranty-claims(?:\/(\d+)(\/(?:events|repairs))?)?$/i;
export function warrantyResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  const match = path.exec(suffix);
  if (!match) return null;
  const [, projectId, number, action] = match;
  if (!number && method === "GET")
    return warrantyListSchema.refine((value) => value.project_id === projectId);
  if (method === (!number || action ? "POST" : "GET"))
    return warrantyClaimSchema.refine(
      (value) =>
        value.project_id === projectId &&
        (!number || value.number === Number(number)),
    );
  return null;
}
