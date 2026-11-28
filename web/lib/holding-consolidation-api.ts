import { z } from "zod";
import { escapeCsvCell } from "./csv-export";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const entityRoleSchema = z.enum([
  "parent_holding",
  "operating_subsidiary",
  "spv",
  "regional_branch",
]);
export type EntityRole = z.infer<typeof entityRoleSchema>;

export const currencyCodeSchema = z.enum([
  "USD",
  "EUR",
  "GBP",
  "CAD",
  "MXN",
  "CHF",
  "AUD",
  "JPY",
]);
export type CurrencyCode = z.infer<typeof currencyCodeSchema>;

export const intercompanyTxKindSchema = z.enum([
  "intercompany_service",
  "inventory_transfer",
  "management_fee",
  "intercompany_loan",
  "cost_allocation",
  "dividend",
]);
export type IntercompanyTxKind = z.infer<typeof intercompanyTxKindSchema>;

export const intercompanyStatusSchema = z.enum([
  "posted",
  "eliminated",
  "void",
]);
export type IntercompanyStatus = z.infer<typeof intercompanyStatusSchema>;

export const subsidiaryViewSchema = z.object({
  id: z.string(),
  entity_code: z.string(),
  legal_name: z.string(),
  entity_role: entityRoleSchema,
  jurisdiction_country: z.string(),
  jurisdiction_state: z.string(),
  functional_currency: currencyCodeSchema,
  ownership_bps: z.number().int(),
  tax_id_masked: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type SubsidiaryView = z.infer<typeof subsidiaryViewSchema>;

export const entitySnapshotViewSchema = z.object({
  id: z.string(),
  subsidiary_id: z.string(),
  period_key: z.string(),
  revenue_minor: z.number().int(),
  cogs_minor: z.number().int(),
  opex_minor: z.number().int(),
  cash_minor: z.number().int(),
  ar_minor: z.number().int(),
  ap_minor: z.number().int(),
  inventory_minor: z.number().int(),
  fixed_assets_minor: z.number().int(),
  debt_minor: z.number().int(),
  equity_minor: z.number().int(),
  notes: z.string(),
  updated_at: z.string(),
});
export type EntitySnapshotView = z.infer<typeof entitySnapshotViewSchema>;

export const intercompanyTxViewSchema = z.object({
  id: z.string(),
  tx_number: z.string(),
  period_key: z.string(),
  tx_date: z.string(),
  source_subsidiary_id: z.string(),
  source_code: z.string(),
  source_name: z.string(),
  target_subsidiary_id: z.string(),
  target_code: z.string(),
  target_name: z.string(),
  tx_kind: intercompanyTxKindSchema,
  currency: currencyCodeSchema,
  amount_minor: z.number().int(),
  fx_rate_micros: z.number().int(),
  usd_equivalent_cents: z.number().int(),
  description: z.string(),
  source_entry_label: z.string(),
  target_entry_label: z.string(),
  status: intercompanyStatusSchema,
  eliminated_at: z.string().nullable(),
});
export type IntercompanyTxView = z.infer<typeof intercompanyTxViewSchema>;

export const entityConsolidatedRowSchema = z.object({
  subsidiary_id: z.string(),
  entity_code: z.string(),
  legal_name: z.string(),
  entity_role: entityRoleSchema,
  jurisdiction: z.string(),
  functional_currency: currencyCodeSchema,
  fx_rate_micros: z.number().int(),
  ownership_pct: z.number(),
  revenue_usd_cents: z.number().int(),
  cogs_usd_cents: z.number().int(),
  opex_usd_cents: z.number().int(),
  net_income_usd_cents: z.number().int(),
  controlling_net_income_cents: z.number().int(),
  nci_net_income_cents: z.number().int(),
  cash_usd_cents: z.number().int(),
  total_assets_usd_cents: z.number().int(),
  total_liabilities_usd_cents: z.number().int(),
  equity_usd_cents: z.number().int(),
});
export type EntityConsolidatedRow = z.infer<typeof entityConsolidatedRowSchema>;

export const consolidatedStatementColumnSchema = z.object({
  revenue_cents: z.number().int(),
  cogs_cents: z.number().int(),
  gross_profit_cents: z.number().int(),
  opex_cents: z.number().int(),
  net_income_cents: z.number().int(),
  controlling_interest_net_income_cents: z.number().int(),
  nci_net_income_cents: z.number().int(),
  cash_cents: z.number().int(),
  ar_cents: z.number().int(),
  inventory_cents: z.number().int(),
  fixed_assets_cents: z.number().int(),
  total_assets_cents: z.number().int(),
  ap_cents: z.number().int(),
  debt_cents: z.number().int(),
  total_liabilities_cents: z.number().int(),
  equity_cents: z.number().int(),
});
export type ConsolidatedStatementColumn = z.infer<
  typeof consolidatedStatementColumnSchema
>;

export const dueToDueFromPairSchema = z.object({
  creditor_code: z.string(),
  creditor_name: z.string(),
  debtor_code: z.string(),
  debtor_name: z.string(),
  net_due_usd_cents: z.number().int(),
  tx_count: z.number().int(),
});

export const tradeOrderKindSchema = z.enum([
  "raw_materials",
  "finished_goods",
  "intercompany_service",
  "equipment_transfer",
]);
export type TradeOrderKind = z.infer<typeof tradeOrderKindSchema>;

export const transferPricingMethodSchema = z.enum([
  "cup_market",
  "cost_plus",
  "resale_minus",
  "agreed_contract",
]);
export type TransferPricingMethod = z.infer<typeof transferPricingMethodSchema>;

export const tradeOrderStatusSchema = z.enum([
  "mirrored_open",
  "shipped_received",
  "invoiced_eliminated",
  "void",
]);
export type TradeOrderStatus = z.infer<typeof tradeOrderStatusSchema>;

export const tradeOrderActionSchema = z.enum([
  "ship_receive",
  "invoice_eliminate",
  "update_unsold",
  "void",
]);
export type TradeOrderAction = z.infer<typeof tradeOrderActionSchema>;

export const intercompanyTradeOrderViewSchema = z.object({
  id: z.string(),
  sales_order_number: z.string(),
  mirror_po_number: z.string(),
  period_key: z.string(),
  order_date: z.string(),
  seller_subsidiary_id: z.string(),
  seller_code: z.string(),
  seller_name: z.string(),
  buyer_subsidiary_id: z.string(),
  buyer_code: z.string(),
  buyer_name: z.string(),
  trade_kind: tradeOrderKindSchema,
  transfer_pricing_method: transferPricingMethodSchema,
  item_sku: z.string(),
  item_description: z.string(),
  quantity_milli: z.number().int(),
  currency: currencyCodeSchema,
  unit_transfer_price_minor: z.number().int(),
  seller_unit_cost_minor: z.number().int(),
  total_transfer_minor: z.number().int(),
  total_seller_cost_minor: z.number().int(),
  intercompany_profit_minor: z.number().int(),
  buyer_unsold_inventory_bps: z.number().int(),
  fx_rate_micros: z.number().int(),
  transfer_usd_cents: z.number().int(),
  upii_usd_cents: z.number().int(),
  status: tradeOrderStatusSchema,
  linked_intercompany_tx_id: z.string().nullable(),
  notes: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type IntercompanyTradeOrderView = z.infer<
  typeof intercompanyTradeOrderViewSchema
>;

export const holdingOverviewResponseSchema = z.object({
  period_key: z.string(),
  reporting_currency: z.literal("USD"),
  subsidiaries: z.array(subsidiaryViewSchema),
  snapshots: z.array(entitySnapshotViewSchema),
  intercompany_transactions: z.array(intercompanyTxViewSchema),
  intercompany_trade_orders: z
    .array(intercompanyTradeOrderViewSchema)
    .default([]),
  total_upii_eliminated_usd_cents: z.number().int().default(0),
  per_entity_usd: z.array(entityConsolidatedRowSchema),
  pre_elimination: consolidatedStatementColumnSchema,
  eliminations: consolidatedStatementColumnSchema,
  consolidated: consolidatedStatementColumnSchema,
  due_to_due_from_matrix: z.array(dueToDueFromPairSchema),
  fx_rates_micros: z.record(z.string(), z.number().int()),
});
export type HoldingOverviewResponse = z.infer<
  typeof holdingOverviewResponseSchema
>;

export const seedSampleHoldingResponseSchema = z.object({
  period_key: z.string(),
  subsidiaries_seeded: z.number().int(),
  snapshots_seeded: z.number().int(),
  intercompany_seeded: z.number().int(),
  message: z.string(),
});
export type SeedSampleHoldingResponse = z.infer<
  typeof seedSampleHoldingResponseSchema
>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/holding`;
}

async function readJson<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const detail =
      data &&
      typeof data === "object" &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (HTTP ${response.status}).`;
    throw new ManagementApiError("REQUEST_FAILED", detail, response.status);
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Holding Consolidation API returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchHoldingOverview(
  businessId: string,
  periodKey: string,
): Promise<HoldingOverviewResponse> {
  const res = await authorizedResponse(
    `${base(businessId)}/overview?period_key=${encodeURIComponent(periodKey)}`,
    { headers: { Accept: "application/json" } },
  );
  return readJson(res, holdingOverviewResponseSchema);
}

export async function createSubsidiary(
  businessId: string,
  input: {
    entity_code: string;
    legal_name: string;
    entity_role: EntityRole;
    jurisdiction_country: string;
    jurisdiction_state: string;
    functional_currency: CurrencyCode;
    ownership_bps: number;
    tax_id_masked: string;
  },
): Promise<SubsidiaryView> {
  const res = await authorizedResponse(`${base(businessId)}/subsidiaries`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, subsidiaryViewSchema);
}

export async function upsertEntitySnapshot(
  businessId: string,
  input: {
    subsidiary_id: string;
    period_key: string;
    revenue_minor: number;
    cogs_minor: number;
    opex_minor: number;
    cash_minor: number;
    ar_minor: number;
    ap_minor: number;
    inventory_minor: number;
    fixed_assets_minor: number;
    debt_minor: number;
    equity_minor: number;
    notes: string;
  },
): Promise<EntitySnapshotView> {
  const res = await authorizedResponse(`${base(businessId)}/snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, entitySnapshotViewSchema);
}

export async function createIntercompanyTx(
  businessId: string,
  input: {
    period_key: string;
    source_subsidiary_id: string;
    target_subsidiary_id: string;
    tx_kind: IntercompanyTxKind;
    currency: CurrencyCode;
    amount_minor: number;
    description: string;
    auto_eliminate: boolean;
  },
): Promise<IntercompanyTxView> {
  const res = await authorizedResponse(`${base(businessId)}/intercompany`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, intercompanyTxViewSchema);
}

export async function updateIntercompanyStatus(
  businessId: string,
  txId: string,
  status: IntercompanyStatus,
): Promise<IntercompanyTxView> {
  const res = await authorizedResponse(
    `${base(businessId)}/intercompany/${encodeURIComponent(txId)}/status`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ status }),
    },
  );
  return readJson(res, intercompanyTxViewSchema);
}

export async function createIntercompanyTradeOrder(
  businessId: string,
  input: {
    period_key: string;
    seller_subsidiary_id: string;
    buyer_subsidiary_id: string;
    trade_kind: TradeOrderKind;
    transfer_pricing_method: TransferPricingMethod;
    item_sku: string;
    item_description: string;
    quantity_milli: number;
    currency: CurrencyCode;
    unit_transfer_price_minor: number;
    seller_unit_cost_minor: number;
    buyer_unsold_inventory_bps: number;
    auto_invoice_and_eliminate: boolean;
    notes?: string;
  },
): Promise<IntercompanyTradeOrderView> {
  const res = await authorizedResponse(`${base(businessId)}/trade-orders`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, intercompanyTradeOrderViewSchema);
}

export async function transitionIntercompanyTradeOrder(
  businessId: string,
  orderId: string,
  input: {
    action: TradeOrderAction;
    buyer_unsold_inventory_bps?: number;
  },
): Promise<IntercompanyTradeOrderView> {
  const res = await authorizedResponse(
    `${base(businessId)}/trade-orders/${encodeURIComponent(orderId)}/transition`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return readJson(res, intercompanyTradeOrderViewSchema);
}

export async function seedSampleHoldingGroup(
  businessId: string,
  periodKey: string,
): Promise<SeedSampleHoldingResponse> {
  const res = await authorizedResponse(
    `${base(businessId)}/seed-sample-group?period_key=${encodeURIComponent(periodKey)}`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
    },
  );
  return readJson(res, seedSampleHoldingResponseSchema);
}

function centsStr(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function buildConsolidatedHoldingCsv(
  data: HoldingOverviewResponse,
): string {
  const rows: string[] = [];
  const push = (cells: (string | number)[]) => {
    rows.push(cells.map(escapeCsvCell).join(","));
  };

  push([
    "AMARKAL Multi-Entity Consolidated Financial Pack",
    `Period: ${data.period_key}`,
    `Reporting Currency: ${data.reporting_currency}`,
  ]);
  push([]);
  push([
    "STATEMENT LINE",
    "PRE-ELIMINATION USD",
    "INTERCOMPANY ELIMINATIONS USD",
    "CONSOLIDATED USD",
  ]);
  const lines: [string, keyof ConsolidatedStatementColumn][] = [
    ["Revenue", "revenue_cents"],
    ["Cost of Goods Sold (COGS)", "cogs_cents"],
    ["Gross Profit", "gross_profit_cents"],
    ["Operating Expenses (OpEx)", "opex_cents"],
    ["Consolidated Net Income", "net_income_cents"],
    [
      "Attributable to Parent (Controlling Interest)",
      "controlling_interest_net_income_cents",
    ],
    ["Non-Controlling Interest (Minority NCI)", "nci_net_income_cents"],
    ["Cash & Equivalents", "cash_cents"],
    ["Accounts Receivable (Net of Due From)", "ar_cents"],
    ["Inventory", "inventory_cents"],
    ["Fixed Assets", "fixed_assets_cents"],
    ["Total Consolidated Assets", "total_assets_cents"],
    ["Accounts Payable (Net of Due To)", "ap_cents"],
    ["Debt & Intercompany Notes (Net)", "debt_cents"],
    ["Total Consolidated Liabilities", "total_liabilities_cents"],
    ["Consolidated Equity", "equity_cents"],
  ];
  for (const [label, key] of lines) {
    push([
      label,
      centsStr(data.pre_elimination[key]),
      centsStr(data.eliminations[key]),
      centsStr(data.consolidated[key]),
    ]);
  }
  push([]);
  push([
    "SUBSIDIARY CODE",
    "LEGAL NAME",
    "JURISDICTION",
    "CURRENCY",
    "OWNERSHIP %",
    "REVENUE USD",
    "NET INCOME USD",
    "CONTROLLING NI USD",
    "NCI USD",
    "TOTAL ASSETS USD",
  ]);
  for (const e of data.per_entity_usd) {
    push([
      e.entity_code,
      e.legal_name,
      e.jurisdiction,
      e.functional_currency,
      e.ownership_pct.toFixed(2),
      centsStr(e.revenue_usd_cents),
      centsStr(e.net_income_usd_cents),
      centsStr(e.controlling_net_income_cents),
      centsStr(e.nci_net_income_cents),
      centsStr(e.total_assets_usd_cents),
    ]);
  }
  return `${rows.join("\r\n")}\r\n`;
}
