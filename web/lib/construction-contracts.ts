import { z } from "zod";
import { constructionAcceptanceResponseSchema } from "./construction-acceptance-contracts";
import { customerAcceptanceResponseSchema } from "./construction-customer-acceptance-contracts";
import { reconciliationSchema } from "./construction-reconciliation-contracts";
import { warrantyResponseSchema } from "./construction-warranty-contracts";
import { invoiceSchema } from "./financial-contracts";
import { minorUnits } from "./ledger-contracts";

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

export const customerProposalLinkSchema = z
  .strictObject({
    business: id,
    project: id,
    grant: id,
  })
  .transform(({ business, project, grant }) => ({
    business: business.toLowerCase(),
    project: project.toLowerCase(),
    grant: grant.toLowerCase(),
  }));

export type CustomerProposalLink = z.output<typeof customerProposalLinkSchema>;

const customerProposalSchema = z.strictObject({
  schema_version: z.literal(1),
  project_id: id,
  version: version.positive(),
  customer_generation: z.number().int().positive(),
  currency,
  proposed_at: instant,
  price_total_minor: total,
  accepted: z.boolean(),
  lines: z
    .array(
      z.strictObject({
        position: z.number().int().min(1).max(500),
        description: text(500),
        phase: text(64),
        quantity,
        unit: text(16),
        unit_price_minor: unitAmount,
        price_minor: total,
      }),
    )
    .min(1)
    .max(500),
});

export type CustomerProposal = z.infer<typeof customerProposalSchema>;

const customerChangeSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    number: z.number().int().min(1).max(100_000),
    customer_generation: z.number().int().positive(),
    title: text(200),
    reason: text(1000).nullable(),
    currency,
    days_delta: z.number().int().min(-3650).max(3650),
    price_minor: signed,
    state: z.enum(["proposed", "approved", "rejected", "withdrawn"]),
    decided_at: instant.nullable(),
    lines: z
      .array(
        z
          .strictObject({
            position: z.number().int().min(1).max(200),
            action: z.enum(["add", "remove"]),
            contract_position: z.number().int().min(1).max(500).nullable(),
            description: text(500),
            phase: text(64),
            quantity,
            unit: text(16),
            unit_price_minor: unitAmount,
            price_minor: signed,
          })
          .refine((line) =>
            line.action === "add"
              ? line.contract_position === null && line.price_minor >= 0
              : line.contract_position !== null && line.price_minor <= 0,
          ),
      )
      .min(1)
      .max(200),
  })
  .refine(
    (change) => (change.state === "proposed") === (change.decided_at === null),
  );

export type CustomerChange = z.infer<typeof customerChangeSchema>;
export type CustomerChangeAnswer = {
  schema_version: 1;
  decision: "approved" | "rejected";
  expected_customer_generation: number;
  note: string | null;
};

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

export const costKindSchema = z.enum([
  "stock_write_off",
  "payable",
  "time_entry",
]);
export type CostKind = z.infer<typeof costKindSchema>;

export const costLinkSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    number: z.number().int().positive(),
    kind: costKindSchema,
    change_order: changeOrder,
    position,
    amount_minor: z.number().int().positive(),
    currency,
    note: text(500).nullable(),
    attempt: z.number().int().positive(),
    stock_document_id: id.nullable(),
    stock_line_no: z.number().int().min(1).max(100).nullable(),
    book_id: id.nullable(),
    document_id: id.nullable(),
    document_revision: z.number().int().positive().nullable(),
    line_id: id.nullable(),
    time_entry_id: id.nullable(),
    time_entry_revision: z.number().int().positive().nullable(),
    worked_microseconds: z.number().int().positive().nullable(),
    rate_per_hour_minor: z.number().int().min(1).max(1_000_000_000).nullable(),
    linked_at: instant,
    reversal: z
      .strictObject({ reason: text(500), reversed_at: instant })
      .nullable(),
  })
  .refine((value) => {
    const fields: Record<CostKind, unknown[]> = {
      stock_write_off: [value.stock_document_id, value.stock_line_no],
      payable: [
        value.book_id,
        value.document_id,
        value.document_revision,
        value.line_id,
      ],
      time_entry: [
        value.time_entry_id,
        value.time_entry_revision,
        value.worked_microseconds,
        value.rate_per_hour_minor,
      ],
    };
    return Object.entries(fields).every(([kind, group]) =>
      group.every((field) => (field !== null) === (kind === value.kind)),
    );
  }, "Inconsistent cost source.");

export const costLinkListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    items: z.array(costLinkSchema),
  })
  .refine(
    (value) =>
      value.items.every((item) => item.project_id === value.project_id) &&
      new Set(value.items.map((item) => item.number)).size ===
        value.items.length,
    "Inconsistent project costs.",
  );

export type CostLink = z.infer<typeof costLinkSchema>;
export type CostLinkList = z.infer<typeof costLinkListSchema>;

export const retainageRateSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    revision: version,
    rate_bp: z.int().min(0).max(5000),
    recorded_at: instant.nullable(),
  })
  .refine((v) =>
    v.revision === 0
      ? v.rate_bp === 0 && v.recorded_at === null
      : v.recorded_at !== null,
  );

const billingMoney = {
  billed_to_date_minor: total,
  this_period_minor: total.min(1),
  retained_minor: total,
  due_minor: total.min(1),
};
const billingItem = {
  ...billingMoney,
  number: z.int().positive(),
  period_end: z.iso.date(),
};
const documentState = z.enum(["draft", "issued"]);
const billingSummary = z
  .strictObject({
    ...billingItem,
    invoice_state: documentState,
    retainage_state: documentState.nullable(),
  })
  .refine(
    (v) =>
      v.this_period_minor - v.retained_minor === v.due_minor &&
      v.retained_minor > 0 === (v.retainage_state !== null),
  );
export const payApplicationListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    currency,
    contract_minor: total,
    billed_to_date_minor: total,
    retained_minor: total,
    due_minor: total,
    remaining_minor: total,
    items: z.array(billingSummary),
  })
  .refine((v) => {
    let billed = 0;
    let retained = 0;
    let period = "";
    for (const [index, item] of v.items.entries()) {
      if (
        item.number !== index + 1 ||
        item.period_end <= period ||
        item.billed_to_date_minor - billed !== item.this_period_minor
      )
        return false;
      billed = item.billed_to_date_minor;
      retained += item.retained_minor;
      period = item.period_end;
    }
    return (
      billed === v.billed_to_date_minor &&
      retained === v.retained_minor &&
      billed - retained === v.due_minor &&
      v.contract_minor - billed === v.remaining_minor
    );
  });

const billingQuantity = z.string().regex(/^(0|[1-9]\d{0,8})(\.\d{1,4})?$/);
const payLine = z
  .strictObject({
    change_order: changeOrder,
    position,
    phase: text(64),
    description: text(500),
    unit: text(16),
    quantity: billingQuantity,
    contract_minor: total,
    completed: billingQuantity,
    value_to_date_minor: total,
    previous_minor: total,
    this_period_minor: signed,
  })
  .refine(
    (v) => v.value_to_date_minor - v.previous_minor === v.this_period_minor,
  );
export const payApplicationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    project_id: id,
    currency,
    ...billingItem,
    rate_revision: version.min(1).nullable(),
    rate_bp: z.int().min(0).max(5000),
    previous_billed_minor: total,
    lines: z.array(payLine).min(1),
    invoice: invoiceSchema,
    retainage: invoiceSchema.nullable(),
    recorded_at: instant,
  })
  .refine((v) => {
    const { invoice, retainage } = v;
    return (
      v.billed_to_date_minor - v.previous_billed_minor ===
        v.this_period_minor &&
      v.this_period_minor - v.retained_minor === v.due_minor &&
      (v.rate_revision !== null || v.rate_bp === 0) &&
      (BigInt(v.this_period_minor) * BigInt(v.rate_bp)) / 10000n ===
        BigInt(v.retained_minor) &&
      new Set(v.lines.map((line) => `${line.change_order}:${line.position}`))
        .size === v.lines.length &&
      v.lines.reduce((sum, line) => sum + line.value_to_date_minor, 0) ===
        v.billed_to_date_minor &&
      invoice.direction === "receivable" &&
      invoice.kind === "invoice" &&
      invoice.currency === v.currency &&
      minorUnits(invoice.total, invoice.minor_units) === BigInt(v.due_minor) &&
      (retainage
        ? retainage.kind === "manual_accrual" &&
          retainage.direction === "receivable" &&
          retainage.book_id === invoice.book_id &&
          retainage.business_id === invoice.business_id &&
          retainage.counterparty_id === invoice.counterparty_id &&
          retainage.currency === v.currency &&
          retainage.due_date === null &&
          retainage.control_account_id !== invoice.control_account_id &&
          minorUnits(retainage.total, retainage.minor_units) ===
            BigInt(v.retained_minor)
        : v.retained_minor === 0)
    );
  });

export type RetainageRate = z.infer<typeof retainageRateSchema>;
export type PayApplicationList = z.infer<typeof payApplicationListSchema>;
export type PayApplication = z.infer<typeof payApplicationSchema>;

const billingRoute =
  /^\/construction\/projects\/([0-9a-f-]{36})\/(retainage|pay-applications)(?:\/(\d+))?$/i;

function billingResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  const match = billingRoute.exec(suffix);
  if (!match) return null;
  const [, projectId, kind, number] = match;
  if (kind === "retainage")
    return !number && (method === "GET" || method === "PUT")
      ? retainageRateSchema.refine((v) => v.project_id === projectId)
      : null;
  if (!number && method === "GET")
    return payApplicationListSchema.refine((v) => v.project_id === projectId);
  if (method === (number ? "GET" : "POST"))
    return payApplicationSchema.refine(
      (v) =>
        v.project_id === projectId && (!number || v.number === Number(number)),
    );
  return null;
}

const costRoute =
  /^\/construction\/projects\/([0-9a-f-]{36})\/costs(?:\/(\d+)(\/reversal)?)?$/i;

function costResponseSchema(suffix: string, method: string): z.ZodType | null {
  const match = costRoute.exec(suffix);
  if (!match) return null;
  const [, projectId, number, reversal] = match;
  if (!number && method === "GET") {
    return costLinkListSchema.refine((value) => value.project_id === projectId);
  }
  if (
    (!number && method === "POST") ||
    (number && method === (reversal ? "POST" : "GET"))
  ) {
    return costLinkSchema.refine(
      (value) =>
        value.project_id === projectId &&
        (!number || value.number === Number(number)) &&
        (!reversal || value.reversal !== null),
    );
  }
  return null;
}

const reconciliationRoute =
  /^\/construction\/projects\/([0-9a-f-]{36})\/reconciliation$/i;
const customerProposalRoute =
  /^\/construction\/projects\/([0-9a-f-]{36})\/customer-proposal\/[0-9a-f-]{36}$/i;
const customerChangeRoute =
  /^\/construction\/projects\/([0-9a-f-]{36})\/change-orders\/(\d+)\/customer-answer\/[0-9a-f-]{36}$/i;

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
  const customerAcceptance = customerAcceptanceResponseSchema(suffix, method);
  if (customerAcceptance) return customerAcceptance;
  const customerChange = customerChangeRoute.exec(suffix);
  if (customerChange && (method === "GET" || method === "POST"))
    return customerChangeSchema.refine(
      (value) =>
        value.project_id === customerChange[1] &&
        value.number === Number(customerChange[2]) &&
        (method === "GET" ||
          value.state === "approved" ||
          value.state === "rejected"),
    );
  const proposal = customerProposalRoute.exec(suffix);
  if (proposal && (method === "GET" || method === "POST"))
    return customerProposalSchema.refine(
      (value) =>
        value.project_id === proposal[1] &&
        (method === "GET" || value.accepted),
    );
  const cost = costResponseSchema(suffix, method);
  if (cost) return cost;
  const billing = billingResponseSchema(suffix, method);
  if (billing) return billing;
  const acceptance = constructionAcceptanceResponseSchema(suffix, method);
  if (acceptance) return acceptance;
  const reconciliation = reconciliationRoute.exec(suffix);
  if (reconciliation && method === "GET")
    return reconciliationSchema.refine(
      (value) => value.project_id === reconciliation[1],
    );
  const warranty = warrantyResponseSchema(suffix, method);
  if (warranty) return warranty;
  for (const [pattern, methods, schema] of routes)
    if (pattern.test(suffix) && methods.includes(method)) return schema;
  return null;
}
