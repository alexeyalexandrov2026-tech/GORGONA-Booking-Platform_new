import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

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

export const overtimeRuleSchema = z.enum([
  "flsa_weekly_40",
  "california_daily_8_12",
  "union_cba_custom",
]);
export type OvertimeRule = z.infer<typeof overtimeRuleSchema>;

export const filingStatusSchema = z.enum([
  "single",
  "married_joint",
  "head_of_household",
]);
export type FilingStatus = z.infer<typeof filingStatusSchema>;

export const payrollProfileSchema = z.object({
  id: z.string(),
  employee_code: z.string(),
  full_name: z.string(),
  email: z.string().nullable().optional(),
  work_state: z.string(),
  pay_type: z.enum(["hourly", "salaried"]),
  base_rate_cents: z.number().int(),
  overtime_rule: overtimeRuleSchema,
  union_local_code: z.string(),
  union_dues_cents: z.number().int(),
  union_ot_multiplier_bps: z.number().int(),
  union_doubletime_bps: z.number().int(),
  health_insurance_pretax_cents: z.number().int(),
  retirement_401k_bps: z.number().int(),
  filing_status: filingStatusSchema,
  state_tax_override_bps: z.number().int().nullable().optional(),
  external_payroll_provider: z.enum([
    "none",
    "gusto",
    "check_embedded",
    "adp",
    "rippling",
  ]),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type PayrollProfile = z.infer<typeof payrollProfileSchema>;

export const payrollRunLineSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  profile_id: z.string(),
  employee_name: z.string(),
  work_state: z.string(),
  regular_hours_milli: z.number().int(),
  overtime_hours_milli: z.number().int(),
  doubletime_hours_milli: z.number().int(),
  bonus_cents: z.number().int(),
  regular_pay_cents: z.number().int(),
  overtime_pay_cents: z.number().int(),
  doubletime_pay_cents: z.number().int(),
  gross_pay_cents: z.number().int(),
  pretax_health_cents: z.number().int(),
  pretax_401k_cents: z.number().int(),
  federal_income_tax_cents: z.number().int(),
  state_income_tax_cents: z.number().int(),
  social_security_cents: z.number().int(),
  medicare_cents: z.number().int(),
  union_dues_cents: z.number().int(),
  net_pay_cents: z.number().int(),
  employer_fica_cents: z.number().int(),
  employer_futa_suta_cents: z.number().int(),
  compliance_notes: z.string(),
});
export type PayrollRunLine = z.infer<typeof payrollRunLineSchema>;

export const payrollRunSchema = z.object({
  id: z.string(),
  run_number: z.string(),
  period_start: z.string(),
  period_end: z.string(),
  pay_date: z.string(),
  status: z.enum(["draft", "approved", "exported_to_provider", "void"]),
  total_gross_cents: z.number().int(),
  total_employee_taxes_cents: z.number().int(),
  total_employer_taxes_cents: z.number().int(),
  total_deductions_cents: z.number().int(),
  total_net_cents: z.number().int(),
  export_provider: z.enum(["csv_adp_gusto", "gusto_api", "check_embedded"]),
  approved_at: z.string().nullable().optional(),
  notes: z.string(),
  lines: z.array(payrollRunLineSchema),
  created_at: z.string(),
});
export type PayrollRun = z.infer<typeof payrollRunSchema>;

export const fxRateSchema = z.object({
  id: z.string(),
  base_currency: currencyCodeSchema,
  quote_currency: z.string(),
  rate_micros: z.number().int(),
  source: z.enum(["manual", "ecb_feed", "fed_h10", "treasury"]),
  effective_at: z.string(),
  updated_at: z.string(),
});
export type FxRate = z.infer<typeof fxRateSchema>;

export const fxLedgerEntrySchema = z.object({
  id: z.string(),
  entry_number: z.string(),
  entry_date: z.string(),
  description: z.string(),
  counterparty_name: z.string(),
  currency: currencyCodeSchema,
  amount_minor: z.number().int(),
  entry_kind: z.enum(["receivable", "payable", "cash_balance"]),
  booking_rate_micros: z.number().int(),
  booked_usd_cents: z.number().int(),
  current_rate_micros: z.number().int(),
  revalued_usd_cents: z.number().int(),
  fx_gain_loss_cents: z.number().int(),
  status: z.enum(["open", "settled"]),
  settled_rate_micros: z.number().int().nullable().optional(),
  realized_fx_gain_loss_cents: z.number().int(),
  settled_at: z.string().nullable().optional(),
  created_at: z.string(),
});
export type FxLedgerEntry = z.infer<typeof fxLedgerEntrySchema>;

export const taxRegimeSchema = z.enum([
  "us_sales_tax",
  "eu_vat",
  "uk_vat",
  "ca_gst_hst",
  "mx_iva",
  "ch_mwst",
  "au_gst",
]);
export type TaxRegime = z.infer<typeof taxRegimeSchema>;

export const reportingStandardSchema = z.enum([
  "US_GAAP",
  "IFRS_EU",
  "UK_FRS102",
  "ASPE_CA",
  "NIF_MX",
]);
export type ReportingStandard = z.infer<typeof reportingStandardSchema>;

export const taxProfileSchema = z.object({
  id: z.string(),
  country_code: z.string(),
  region_label: z.string(),
  tax_regime: taxRegimeSchema,
  tax_name: z.string(),
  standard_rate_bps: z.number().int(),
  reduced_rate_bps: z.number().int(),
  reverse_charge_b2b: z.boolean(),
  tax_registration_id: z.string(),
  default_currency: currencyCodeSchema,
  reporting_standard: reportingStandardSchema,
  is_default: z.boolean(),
  is_active: z.boolean(),
});
export type TaxProfile = z.infer<typeof taxProfileSchema>;

export const taxPreviewSchema = z.object({
  subtotal_minor: z.number().int(),
  tax_minor: z.number().int(),
  total_minor: z.number().int(),
  applied_rate_bps: z.number().int(),
  reverse_charge_applied: z.boolean(),
  tax_label: z.string(),
  reporting_standard: reportingStandardSchema,
});
export type TaxPreview = z.infer<typeof taxPreviewSchema>;

export const paymentRailSchema = z.object({
  id: z.string(),
  rail_code: z.enum([
    "stripe_us_ach_card",
    "sepa_instant_eu",
    "uk_faster_payments",
    "ca_interac_eft",
    "mx_spei",
    "ch_qr_bill",
    "au_payid_becs",
    "swift_wire",
  ]),
  display_name: z.string(),
  country_code: z.string(),
  currency: currencyCodeSchema,
  settlement_instructions: z.string(),
  iban_or_routing_masked: z.string(),
  is_enabled: z.boolean(),
});
export type PaymentRail = z.infer<typeof paymentRailSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/global-finance`;
}

async function readJson<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  let data: unknown;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
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
      "Global Finance & Payroll API returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchPayrollProfiles(
  businessId: string,
): Promise<PayrollProfile[]> {
  const res = await authorizedResponse(`${base(businessId)}/payroll/profiles`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(payrollProfileSchema));
}

export async function createPayrollProfile(
  businessId: string,
  input: {
    employee_code: string;
    full_name: string;
    email?: string | null;
    work_state: string;
    pay_type: "hourly" | "salaried";
    base_rate_cents: number;
    overtime_rule: OvertimeRule;
    union_local_code: string;
    union_dues_cents: number;
    health_insurance_pretax_cents: number;
    retirement_401k_bps: number;
    filing_status: FilingStatus;
    external_payroll_provider:
      "none" | "gusto" | "check_embedded" | "adp" | "rippling";
  },
): Promise<PayrollProfile> {
  const res = await authorizedResponse(`${base(businessId)}/payroll/profiles`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, payrollProfileSchema);
}

export async function fetchPayrollRuns(
  businessId: string,
): Promise<PayrollRun[]> {
  const res = await authorizedResponse(`${base(businessId)}/payroll/runs`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(payrollRunSchema));
}

export async function createPayrollRun(
  businessId: string,
  input: {
    period_start: string;
    period_end: string;
    pay_date: string;
    export_provider: "csv_adp_gusto" | "gusto_api" | "check_embedded";
    notes: string;
    entries: {
      profile_id: string;
      daily_hours_milli: number[];
      bonus_cents: number;
    }[];
  },
): Promise<PayrollRun> {
  const res = await authorizedResponse(`${base(businessId)}/payroll/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, payrollRunSchema);
}

export async function transitionPayrollRun(
  businessId: string,
  runId: string,
  action: "approve" | "export" | "void",
): Promise<PayrollRun> {
  const res = await authorizedResponse(
    `${base(businessId)}/payroll/runs/${encodeURIComponent(runId)}/transition`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ action }),
    },
  );
  return readJson(res, payrollRunSchema);
}

export async function fetchFxRates(businessId: string): Promise<FxRate[]> {
  const res = await authorizedResponse(`${base(businessId)}/fx/rates`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(fxRateSchema));
}

export async function upsertFxRate(
  businessId: string,
  input: {
    base_currency: CurrencyCode;
    rate_micros: number;
    source: "manual" | "ecb_feed" | "fed_h10" | "treasury";
  },
): Promise<{ rate: FxRate; revalued_open_entries: number }> {
  const res = await authorizedResponse(`${base(businessId)}/fx/rates`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(
    res,
    z.object({
      rate: fxRateSchema,
      revalued_open_entries: z.number().int(),
    }),
  );
}

export async function fetchFxEntries(
  businessId: string,
): Promise<FxLedgerEntry[]> {
  const res = await authorizedResponse(`${base(businessId)}/fx/entries`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(fxLedgerEntrySchema));
}

export async function createFxEntry(
  businessId: string,
  input: {
    description: string;
    counterparty_name: string;
    currency: CurrencyCode;
    amount_minor: number;
    entry_kind: "receivable" | "payable" | "cash_balance";
  },
): Promise<FxLedgerEntry> {
  const res = await authorizedResponse(`${base(businessId)}/fx/entries`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, fxLedgerEntrySchema);
}

export async function settleFxEntry(
  businessId: string,
  entryId: string,
  settlementRateMicros: number,
): Promise<FxLedgerEntry> {
  const res = await authorizedResponse(
    `${base(businessId)}/fx/entries/${encodeURIComponent(entryId)}/settle`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ settlement_rate_micros: settlementRateMicros }),
    },
  );
  return readJson(res, fxLedgerEntrySchema);
}

export async function fetchTaxProfiles(
  businessId: string,
): Promise<TaxProfile[]> {
  const res = await authorizedResponse(`${base(businessId)}/tax-profiles`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(taxProfileSchema));
}

export async function previewInternationalTax(
  businessId: string,
  input: {
    profile_id: string;
    subtotal_minor: number;
    is_b2b_cross_border: boolean;
    use_reduced_rate: boolean;
  },
): Promise<TaxPreview> {
  const res = await authorizedResponse(`${base(businessId)}/tax-preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, taxPreviewSchema);
}

export async function fetchPaymentRails(
  businessId: string,
): Promise<PaymentRail[]> {
  const res = await authorizedResponse(`${base(businessId)}/payment-rails`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(paymentRailSchema));
}
