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

// O7b: the budget, commitments, schedule, daily reports and completed quantities (O3a, O4a).
const day = z.iso.date();
const done = z.string().regex(/^(0|[1-9]\d{0,8})(\.\d{1,4})?$/);
const percent = z.string().regex(/^\d{1,3}\.\d{2}$/);
const changeOrder = z.number().int().min(1).max(100_000).nullable();
const position = z.number().int().min(1).max(500);
const figures = {
  budget_minor: signed,
  committed_minor: signed,
  uncommitted_minor: signed,
  over_committed: z.boolean(),
  actual_minor: signed,
  remaining_minor: signed,
  over_budget: z.boolean(),
};
export const budgetLineSchema = z.strictObject({
  change_order: changeOrder,
  position,
  phase: text(64),
  kind,
  description: text(500),
  unit: text(16),
  quantity: done,
  unit_cost_minor: unitAmount,
  ...figures,
});
export const budgetSchema = z.strictObject({
  project_id: id,
  currency,
  budget_minor: signed,
  committed_minor: signed,
  uncommitted_minor: signed,
  actual_minor: signed,
  remaining_minor: signed,
  lines: z.array(budgetLineSchema),
  phases: z.array(z.strictObject({ phase: text(64), ...figures })),
});
const commitmentSummary = {
  number: z.number().int().min(1).max(100_000),
  revision: z.number().int().min(1),
  kind: z.enum(["subcontract", "purchase_order"]),
  counterparty_id: id,
  state: z.enum(["open", "cancelled"]),
  title: text(200),
  reference: text(64).nullable(),
  note: text(1000).nullable(),
  revised_at: instant,
  total_minor: total,
};
export const commitmentSummarySchema = z.strictObject(commitmentSummary);
export const commitmentSchema = z.strictObject({
  ...commitmentSummary,
  project_id: id,
  currency,
  lines: z.array(
    z.strictObject({
      change_order: changeOrder,
      position,
      amount_minor: z.number().int().min(1),
    }),
  ),
});
export const commitmentListSchema = z.strictObject({
  items: z.array(commitmentSummarySchema),
});
export const scheduleSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: id,
  revision: z.number().int().min(0),
  note: text(1000).nullable(),
  recorded_at: instant.nullable(),
  planned_finish: day.nullable(),
  phases: z.array(
    z.strictObject({
      phase: text(64),
      planned_start: day,
      planned_finish: day,
      depends_on: z.array(text(64)),
      conflict: z.boolean(),
      critical: z.boolean(),
      percent,
    }),
  ),
  unscheduled: z.array(text(64)),
});
export const dailyReportSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: id,
  report_date: day,
  revision: z.number().int().min(1),
  weather: text(200).nullable(),
  notes: text(4000).nullable(),
  crew: z.array(
    z.strictObject({
      position: z.number().int().min(1).max(50),
      label: text(64),
      headcount: z.number().int().min(1).max(1000),
      counterparty_id: id.nullable(),
    }),
  ),
  photos: z.array(
    z.strictObject({
      position: z.number().int().min(1).max(50),
      document_id: id,
      revision: z.number().int().min(1),
      file_id: id.nullable(),
      media_type: z.string().max(200).nullable(),
    }),
  ),
  recorded_at: instant,
});
export const dailyReportListSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: id,
  items: z.array(
    z.strictObject({
      report_date: day,
      revision: z.number().int().min(1),
      weather: text(200).nullable(),
      headcount: z.number().int().min(0),
      photo_count: z.number().int().min(0),
      recorded_at: instant,
    }),
  ),
});
export const measurementSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: id,
  number: z.number().int().min(1),
  change_order: changeOrder,
  position,
  measured_on: day,
  quantity_to_date: done,
  note: text(500).nullable(),
  recorded_at: instant,
});
export const measurementListSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: id,
  items: z.array(measurementSchema),
});
const value = { contract_minor: total, completed_minor: total, percent };
export const progressSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: id,
  currency,
  ...value,
  lines: z.array(
    z.strictObject({
      change_order: changeOrder,
      position,
      phase: text(64),
      kind,
      description: text(500),
      unit: text(16),
      quantity: done,
      completed: done,
      unit_price_minor: unitAmount,
      ...value,
    }),
  ),
  phases: z.array(z.strictObject({ phase: text(64), ...value })),
});

export type Budget = z.infer<typeof budgetSchema>;
export type BudgetLine = z.infer<typeof budgetLineSchema>;
export type CommitmentSummary = z.infer<typeof commitmentSummarySchema>;
export type Commitment = z.infer<typeof commitmentSchema>;
export type Schedule = z.infer<typeof scheduleSchema>;
export type DailyReport = z.infer<typeof dailyReportSchema>;
export type DailyReportList = z.infer<typeof dailyReportListSchema>;
export type Measurement = z.infer<typeof measurementSchema>;
export type Progress = z.infer<typeof progressSchema>;

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
  [nested("/budget"), ["GET"], budgetSchema],
  [nested("/commitments"), ["GET"], commitmentListSchema],
  [nested("/commitments"), ["POST"], commitmentSchema],
  [nested("/commitments/\\d+"), ["GET", "PUT"], commitmentSchema],
  [nested("/schedule"), ["GET", "PUT"], scheduleSchema],
  [nested("/daily-reports"), ["GET"], dailyReportListSchema],
  [
    nested("/daily-reports/\\d{4}-\\d{2}-\\d{2}"),
    ["GET", "PUT"],
    dailyReportSchema,
  ],
  [nested("/progress"), ["GET"], progressSchema],
  [nested("/progress"), ["POST"], measurementSchema],
  [nested("/progress/measurements"), ["GET"], measurementListSchema],
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
