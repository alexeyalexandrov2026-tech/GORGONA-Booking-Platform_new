import { z } from "zod";
import { escapeCsvCell } from "./csv-export";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const funnelStageKeySchema = z.enum([
  "draft_review",
  "sent_active",
  "won_accepted",
  "invoiced_converted",
]);
export type FunnelStageKey = z.infer<typeof funnelStageKeySchema>;

export const ganttSourceKindSchema = z.enum([
  "mrp_run",
  "eam_wo",
  "kanban_card",
]);
export type GanttSourceKind = z.infer<typeof ganttSourceKindSchema>;

export const biKpiSummarySchema = z.object({
  total_inflow_cents: z.number().int(),
  total_outflow_cents: z.number().int(),
  net_cashflow_cents: z.number().int(),
  gross_margin_pct: z.number(),
  quote_pipeline_cents: z.number().int(),
  quote_win_rate_pct: z.number(),
  commission_saved_cents: z.number().int(),
  fx_net_gain_loss_cents: z.number().int(),
  fleet_avg_health_score: z.number().int(),
  assets_at_risk_count: z.number().int(),
  open_inbox_threads: z.number().int(),
  unread_inbox_messages: z.number().int(),
});
export type BiKpiSummary = z.infer<typeof biKpiSummarySchema>;

export const monthlyCashflowPointSchema = z.object({
  month_key: z.string(),
  month_label: z.string(),
  inflow_cents: z.number().int(),
  outflow_cents: z.number().int(),
  net_cents: z.number().int(),
});
export type MonthlyCashflowPoint = z.infer<typeof monthlyCashflowPointSchema>;

export const salesFunnelStageSchema = z.object({
  stage_key: funnelStageKeySchema,
  label: z.string(),
  count: z.number().int(),
  value_cents: z.number().int(),
  conversion_pct: z.number(),
});
export type SalesFunnelStage = z.infer<typeof salesFunnelStageSchema>;

export const ganttTimelineItemSchema = z.object({
  id: z.string(),
  source: ganttSourceKindSchema,
  code: z.string(),
  title: z.string(),
  status: z.string(),
  priority: z.string(),
  start_date: z.string(),
  end_date: z.string(),
  progress_pct: z.number().int(),
  module_href: z.string(),
});
export type GanttTimelineItem = z.infer<typeof ganttTimelineItemSchema>;

export const fxCurrencyExposureSchema = z.object({
  currency: z.string(),
  entry_count: z.number().int(),
  receivable_usd_cents: z.number().int(),
  payable_usd_cents: z.number().int(),
  cash_usd_cents: z.number().int(),
  net_exposure_usd_cents: z.number().int(),
  unrealized_fx_cents: z.number().int(),
  realized_fx_cents: z.number().int(),
});
export type FxCurrencyExposure = z.infer<typeof fxCurrencyExposureSchema>;

export const biDashboardResponseSchema = z.object({
  period_days: z.number().int(),
  period_start: z.string(),
  period_end: z.string(),
  generated_at: z.string(),
  kpis: biKpiSummarySchema,
  monthly_cashflow: z.array(monthlyCashflowPointSchema),
  sales_funnel: z.array(salesFunnelStageSchema),
  gantt_items: z.array(ganttTimelineItemSchema),
  fx_exposure: z.array(fxCurrencyExposureSchema),
});
export type BiDashboardResponse = z.infer<typeof biDashboardResponseSchema>;

export type BiPeriodDays = 30 | 90 | 180 | 365;

export async function fetchBiDashboard(
  businessId: string,
  periodDays: BiPeriodDays = 90,
): Promise<BiDashboardResponse> {
  const response = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/analytics/bi?period_days=${periodDays}`,
    {
      headers: { Accept: "application/json" },
    },
  );
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
  const parsed = biDashboardResponseSchema.safeParse(data);
  if (!parsed.success) {
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Executive BI API returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export interface GanttBarLayout {
  id: string;
  leftPct: number;
  widthPct: number;
}

export interface GanttTimelineBounds {
  minDate: string;
  maxDate: string;
  totalDays: number;
  bars: Record<string, GanttBarLayout>;
}

function parseIsoDayUtc(iso: string): number {
  const parts = iso.slice(0, 10).split("-").map(Number);
  const year = parts[0];
  const month = parts[1];
  const day = parts[2];
  if (
    year === undefined ||
    month === undefined ||
    day === undefined ||
    Number.isNaN(year) ||
    Number.isNaN(month) ||
    Number.isNaN(day)
  ) {
    return Date.UTC(2026, 0, 1);
  }
  return Date.UTC(year, month - 1, day);
}

export function computeGanttBounds(
  items: readonly GanttTimelineItem[],
): GanttTimelineBounds {
  const first = items[0];
  if (!first) {
    return { minDate: "", maxDate: "", totalDays: 1, bars: {} };
  }
  let minMs = Infinity;
  let maxMs = -Infinity;
  let minIso = first.start_date;
  let maxIso = first.end_date;

  for (const item of items) {
    const s = parseIsoDayUtc(item.start_date);
    const e = Math.max(s, parseIsoDayUtc(item.end_date));
    if (s < minMs) {
      minMs = s;
      minIso = item.start_date;
    }
    if (e > maxMs) {
      maxMs = e;
      maxIso = item.end_date;
    }
  }

  const dayMs = 86_400_000;
  const totalDays = Math.max(1, Math.round((maxMs - minMs) / dayMs) + 1);
  const bars: Record<string, GanttBarLayout> = {};

  for (const item of items) {
    const s = parseIsoDayUtc(item.start_date);
    const e = Math.max(s, parseIsoDayUtc(item.end_date));
    const offsetDays = Math.max(0, Math.round((s - minMs) / dayMs));
    const spanDays = Math.max(1, Math.round((e - s) / dayMs) + 1);
    const leftPct = Math.min(92, (offsetDays / totalDays) * 100);
    const rawWidth = (spanDays / totalDays) * 100;
    const widthPct = Math.max(8, Math.min(100 - leftPct, rawWidth));
    bars[item.id] = {
      id: item.id,
      leftPct: Number(leftPct.toFixed(1)),
      widthPct: Number(widthPct.toFixed(1)),
    };
  }

  return { minDate: minIso, maxDate: maxIso, totalDays, bars };
}

function centsToUsdString(cents: number): string {
  return (cents / 100).toFixed(2);
}

export function buildBoardPackCsv(data: BiDashboardResponse): string {
  const rows: string[] = [];
  const pushRow = (cells: (string | number)[]) => {
    rows.push(cells.map(escapeCsvCell).join(","));
  };

  pushRow([
    "AMARKAL Executive BI Board Pack",
    `Period: ${data.period_start} to ${data.period_end} (${data.period_days}d)`,
    `Generated: ${data.generated_at}`,
  ]);
  pushRow([]);

  pushRow(["SECTION", "METRIC", "VALUE", "NOTES"]);
  pushRow([
    "KPI",
    "Total Inflow (USD)",
    centsToUsdString(data.kpis.total_inflow_cents),
    "Stripe Paid + Issued FIN-03 Receivables",
  ]);
  pushRow([
    "KPI",
    "Total Outflow (USD)",
    centsToUsdString(data.kpis.total_outflow_cents),
    "FIN-03 Payables + Purchase Orders + US Payroll",
  ]);
  pushRow([
    "KPI",
    "Net Cashflow (USD)",
    centsToUsdString(data.kpis.net_cashflow_cents),
    `Gross Margin ${data.kpis.gross_margin_pct.toFixed(1)}%`,
  ]);
  pushRow([
    "KPI",
    "Commercial Quote Pipeline (USD)",
    centsToUsdString(data.kpis.quote_pipeline_cents),
    `Win Rate ${data.kpis.quote_win_rate_pct.toFixed(1)}%`,
  ]);
  pushRow([
    "KPI",
    "0% Commission Savings (USD)",
    centsToUsdString(data.kpis.commission_saved_cents),
    "vs 2.5% legacy platform fee",
  ]);
  pushRow([
    "KPI",
    "Net FX Gain/Loss (USD)",
    centsToUsdString(data.kpis.fx_net_gain_loss_cents),
    "Unrealized + Realized FX",
  ]);
  pushRow([
    "KPI",
    "Fleet Avg Health Score",
    `${data.kpis.fleet_avg_health_score}%`,
    `${data.kpis.assets_at_risk_count} assets at risk`,
  ]);
  pushRow([]);

  pushRow([
    "MONTHLY CASHFLOW",
    "Month",
    "Inflow USD",
    "Outflow USD",
    "Net USD",
  ]);
  for (const pt of data.monthly_cashflow) {
    pushRow([
      "CASHFLOW",
      pt.month_label,
      centsToUsdString(pt.inflow_cents),
      centsToUsdString(pt.outflow_cents),
      centsToUsdString(pt.net_cents),
    ]);
  }
  pushRow([]);

  pushRow(["SALES FUNNEL", "Stage", "Quotes", "Value USD", "Conversion %"]);
  for (const stage of data.sales_funnel) {
    pushRow([
      "FUNNEL",
      stage.label,
      stage.count,
      centsToUsdString(stage.value_cents),
      stage.conversion_pct.toFixed(1),
    ]);
  }
  pushRow([]);

  pushRow([
    "GANTT TIMELINE",
    "Source",
    "Code",
    "Title",
    "Status",
    "Start",
    "End",
    "Progress %",
  ]);
  for (const item of data.gantt_items) {
    pushRow([
      "GANTT",
      item.source,
      item.code,
      item.title,
      item.status,
      item.start_date,
      item.end_date,
      item.progress_pct,
    ]);
  }
  pushRow([]);

  pushRow([
    "FX EXPOSURE",
    "Currency",
    "Entries",
    "Net Exposure USD",
    "Unrealized FX USD",
    "Realized FX USD",
  ]);
  for (const fx of data.fx_exposure) {
    pushRow([
      "FX",
      fx.currency,
      fx.entry_count,
      centsToUsdString(fx.net_exposure_usd_cents),
      centsToUsdString(fx.unrealized_fx_cents),
      centsToUsdString(fx.realized_fx_cents),
    ]);
  }

  return `${rows.join("\r\n")}\r\n`;
}
