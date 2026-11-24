import { z } from "zod";

const day = z.iso
  .date()
  .refine((value) => value >= "2000-01-01" && value <= "2100-12-31");
const instant = z.iso.datetime({ offset: true });
const hash = z.string().regex(/^[0-9a-f]{64}$/);
const quantity = z.string().regex(/^(0|[1-9]\d{0,8})(\.\d{1,4})?$/);
const factFields = {
  number: z.number().int().min(1).max(1000),
  scope: z.enum(["phase", "final"]),
  phase: z.string().min(1).max(64).nullable(),
  accepted_on: day,
  signatory: z.string().min(1).max(200),
  source: z.enum(["platform", "paper", "email"]),
  warranty_ends_on: day.nullable(),
  recorded_at: instant,
};
function validScope(value: {
  scope: "phase" | "final";
  phase: string | null;
  warranty_ends_on: string | null;
  accepted_on: string;
}): boolean {
  return value.scope === "phase"
    ? value.phase !== null && value.warranty_ends_on === null
    : value.phase === null &&
        value.warranty_ends_on !== null &&
        value.warranty_ends_on > value.accepted_on;
}
const fact = z.strictObject(factFields).refine(validScope);
const reviewSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: z.uuid(),
  customer_generation: z.number().int().positive(),
  customer_company_revision: z.number().int().nonnegative(),
  currency: z.string().regex(/^[A-Z]{3}$/),
  site_today: day,
  fully_billed: z.boolean(),
  open_items: z.number().int().nonnegative(),
  lines: z.array(
    z.strictObject({
      change_order: z.number().int().positive().nullable(),
      position: z.number().int().positive(),
      description: z.string().min(1).max(500),
      phase: z.string().min(1).max(64),
      quantity,
      unit: z.string().min(1).max(16),
      unit_price_minor: z.number().int().nonnegative(),
      price_minor: z.number().int(),
      completed_quantity: quantity,
      measured_on: day.nullable(),
    }),
  ),
  phases: z.array(
    z.strictObject({
      phase: z.string().min(1).max(64),
      finished: z.boolean(),
      open_items: z.number().int().nonnegative(),
      billed_in_full: z.boolean(),
    }),
  ),
  accepted: z.array(fact),
  review_hash: hash,
});
const receiptSchema = z
  .strictObject({
    ...factFields,
    source: z.literal("platform"),
    schema_version: z.literal(1),
    project_id: z.uuid(),
    note: z.string().min(1).max(1000).nullable(),
    review_hash: hash,
  })
  .refine(validScope);

export type CustomerWorkReview = z.infer<typeof reviewSchema>;
export type CustomerWorkReceipt = z.infer<typeof receiptSchema>;
export type CustomerWorkAnswer = {
  schema_version: 1;
  expected_customer_generation: number;
  expected_review_hash: string;
  signatory: string;
  accepted_on: string;
  note: string | null;
} & (
  | { scope: "phase"; phase: string; warranty_ends_on: null }
  | { scope: "final"; phase: null; warranty_ends_on: string }
);

const route =
  /^\/construction\/projects\/([0-9a-f-]{36})\/customer-acceptance\/[0-9a-f-]{36}$/i;
export function customerAcceptanceResponseSchema(
  path: string,
  method: string,
): z.ZodType | null {
  const match = route.exec(path);
  if (!match) return null;
  if (method === "GET")
    return reviewSchema.refine((value) => value.project_id === match[1]);
  if (method === "POST")
    return receiptSchema.refine((value) => value.project_id === match[1]);
  return null;
}
