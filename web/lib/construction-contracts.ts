import { z } from "zod";

// O7a (package O): strict response contracts of the O1-O2 construction routes (projects, estimate
// versions, the proposal, the contract and change orders). Times arrive in UTC; money in minor units
// of the project currency; quantities as decimal strings with at most 4 places.
const id = z.uuid();
const instant = z.iso.datetime({ offset: true });
const text = (max: number) => z.string().min(1).max(max);
const version = z.number().int().min(0).max(100_000);
const unitAmount = z.number().int().min(0).max(1_000_000_000_000);
const total = z.number().int().min(0);
const signed = z.number().int();
const quantity = z
  .string()
  .regex(/^(0|[1-9]\d{0,8})(\.\d{1,4})?$/)
  .refine((value) => /[1-9]/.test(value));
const currency = z.string().regex(/^[A-Z]{3}$/);
const kind = z.enum(["material", "labor", "equipment", "subcontract", "other"]);
const source = z.enum(["platform", "paper", "email"]);

export const projectSchema = z.strictObject({
  project_id: id,
  revision: z.number().int().positive(),
  number: text(64),
  name: text(200),
  customer_id: id,
  location_id: id,
  site_address: text(500),
  time_zone: text(64),
  currency,
  latest_version: version,
});
export const projectListSchema = z.strictObject({
  items: z.array(projectSchema),
  next_cursor: id.nullable(),
});

export const lineSchema = z.strictObject({
  position: z.number().int().min(1).max(500),
  kind,
  description: text(500),
  phase: text(64),
  quantity,
  unit: text(16),
  unit_cost_minor: unitAmount,
  unit_price_minor: unitAmount,
  material_id: id.nullable(),
  cost_minor: total,
  price_minor: total,
});
const estimateSummary = {
  version: version.min(1),
  based_on: version,
  note: text(1000).nullable(),
  proposed_at: instant.nullable(),
  cost_total_minor: total,
  price_total_minor: total,
};
export const estimateSummarySchema = z.strictObject(estimateSummary);
export const estimateSchema = z.strictObject({
  ...estimateSummary,
  project_id: id,
  currency,
  lines: z.array(lineSchema).min(1).max(500),
});
export const estimateListSchema = z.strictObject({
  items: z.array(estimateSummarySchema),
});

const changeSummary = {
  number: z.number().int().min(1).max(100_000),
  title: text(200),
  reason: text(1000).nullable(),
  days_delta: z.number().int().min(-3650).max(3650),
  state: z.enum(["proposed", "approved", "rejected", "withdrawn"]),
  source: source.nullable(),
  decided_at: instant.nullable(),
  cost_minor: signed,
  price_minor: signed,
};
export const changeOrderSummarySchema = z.strictObject(changeSummary);
export const changeLineSchema = z.strictObject({
  position: z.number().int().min(1).max(200),
  action: z.enum(["add", "remove"]),
  contract_position: z.number().int().min(1).max(500).nullable(),
  kind,
  description: text(500),
  phase: text(64),
  quantity,
  unit: text(16),
  unit_cost_minor: unitAmount,
  unit_price_minor: unitAmount,
  material_id: id.nullable(),
  cost_minor: signed,
  price_minor: signed,
});
export const changeOrderSchema = z.strictObject({
  ...changeSummary,
  project_id: id,
  currency,
  lines: z.array(changeLineSchema).min(1).max(200),
});
export const changeOrderListSchema = z.strictObject({
  items: z.array(changeOrderSummarySchema),
});

export const contractSchema = z.strictObject({
  project_id: id,
  version: version.min(1),
  signatory: text(200),
  source,
  note: text(1000).nullable(),
  recorded_at: instant,
  currency,
  original_cost_minor: total,
  original_price_minor: total,
  approved_cost_minor: signed,
  approved_price_minor: signed,
  approved_days: signed,
  current_cost_minor: signed,
  current_price_minor: signed,
  change_orders: z.array(changeOrderSummarySchema),
});

export type Project = z.infer<typeof projectSchema>;
export type ProjectList = z.infer<typeof projectListSchema>;
export type Line = z.infer<typeof lineSchema>;
export type LineKind = Line["kind"];
export type EstimateSummary = z.infer<typeof estimateSummarySchema>;
export type Estimate = z.infer<typeof estimateSchema>;
export type EstimateList = z.infer<typeof estimateListSchema>;
export type ChangeOrderSummary = z.infer<typeof changeOrderSummarySchema>;
export type ChangeOrder = z.infer<typeof changeOrderSchema>;
export type ChangeOrderList = z.infer<typeof changeOrderListSchema>;
export type Contract = z.infer<typeof contractSchema>;

const project = /^\/construction\/projects\/[0-9a-f-]{36}$/i;
const nested = (tail: string) =>
  new RegExp(`^/construction/projects/[0-9a-f-]{36}${tail}$`, "i");
const routes: [RegExp, string[], z.ZodType][] = [
  [/^\/construction\/projects$/, ["GET"], projectListSchema],
  [project, ["GET", "PUT"], projectSchema],
  [nested("/estimates"), ["GET"], estimateListSchema],
  [nested("/estimates"), ["POST"], estimateSchema],
  [nested("/estimates/\\d+"), ["GET"], estimateSchema],
  [nested("/estimates/\\d+/proposal"), ["POST"], estimateSchema],
  [nested("/contract"), ["GET", "POST"], contractSchema],
  [nested("/change-orders"), ["GET"], changeOrderListSchema],
  [nested("/change-orders"), ["POST"], changeOrderSchema],
  [nested("/change-orders/\\d+"), ["GET"], changeOrderSchema],
  [nested("/change-orders/\\d+/decision"), ["POST"], changeOrderSchema],
];

/** The contract of a construction route under /v1/businesses/{id}, or null for another route. */
export function constructionResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  for (const [pattern, methods, schema] of routes)
    if (pattern.test(suffix) && methods.includes(method)) return schema;
  return null;
}
