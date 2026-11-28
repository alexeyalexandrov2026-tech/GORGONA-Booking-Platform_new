import { z } from "zod";
import { escapeCsvCell } from "./csv-export";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const accountTypeSchema = z.enum([
  "checking",
  "savings",
  "credit_card",
  "treasury",
]);
export type AccountType = z.infer<typeof accountTypeSchema>;

export const connectionModeSchema = z.enum([
  "statement_upload",
  "plaid_sandbox",
  "plaid_production",
]);
export type ConnectionMode = z.infer<typeof connectionModeSchema>;

export const txDirectionSchema = z.enum(["credit", "debit"]);
export type TxDirection = z.infer<typeof txDirectionSchema>;

export const sourceFormatSchema = z.enum([
  "ofx",
  "qfx",
  "qbo",
  "csv",
  "plaid",
  "manual",
]);
export type SourceFormat = z.infer<typeof sourceFormatSchema>;

export const reconciliationStatusSchema = z.enum([
  "unmatched",
  "suggested",
  "reconciled",
  "excluded",
]);
export type ReconciliationStatus = z.infer<typeof reconciliationStatusSchema>;

export const matchedEntityKindSchema = z.enum([
  "invoice",
  "purchase_order",
  "payment_session",
  "payroll_run",
  "fx_entry",
  "manual_category",
]);
export type MatchedEntityKind = z.infer<typeof matchedEntityKindSchema>;

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

export const bankAccountViewSchema = z.object({
  id: z.string(),
  institution_name: z.string(),
  account_name: z.string(),
  account_mask: z.string(),
  account_type: accountTypeSchema,
  currency: currencyCodeSchema,
  connection_mode: connectionModeSchema,
  current_balance_cents: z.number().int(),
  last_synced_at: z.string().nullable(),
  is_active: z.boolean(),
  unmatched_count: z.number().int(),
  suggested_count: z.number().int(),
  reconciled_count: z.number().int(),
});
export type BankAccountView = z.infer<typeof bankAccountViewSchema>;

export const plaidInstitutionSchema = z.object({
  id: z.string(),
  name: z.string(),
  rail: z.string(),
});

export const plaidStatusViewSchema = z.object({
  configured: z.boolean(),
  source: z.enum(["none", "tenant_vault_byok", "platform_env"]),
  plaid_env: z.enum(["sandbox", "production"]),
  client_id_hint: z.string().nullable(),
  updated_at: z.string().nullable(),
  supported_institutions: z.array(plaidInstitutionSchema),
});
export type PlaidStatusView = z.infer<typeof plaidStatusViewSchema>;

export const bankFeedsSummarySchema = z.object({
  accounts: z.array(bankAccountViewSchema),
  total_balance_cents: z.number().int(),
  total_transactions: z.number().int(),
  unmatched_count: z.number().int(),
  suggested_count: z.number().int(),
  reconciled_count: z.number().int(),
  excluded_count: z.number().int(),
  reconciliation_rate_pct: z.number(),
  plaid_status: plaidStatusViewSchema,
});
export type BankFeedsSummary = z.infer<typeof bankFeedsSummarySchema>;

export const parsedBankTxPreviewSchema = z.object({
  external_tx_id: z.string(),
  posted_date: z.string(),
  description: z.string(),
  merchant_name: z.string(),
  direction: txDirectionSchema,
  amount_cents: z.number().int(),
  category_hint: z.string(),
});

export const bankStatementImportResponseSchema = z.object({
  detected_format: sourceFormatSchema,
  dry_run: z.boolean(),
  parsed_count: z.number().int(),
  imported_count: z.number().int(),
  duplicate_skipped_count: z.number().int(),
  suggested_match_count: z.number().int(),
  detected_balance_cents: z.number().int().nullable(),
  errors: z.array(z.string()),
  preview: z.array(parsedBankTxPreviewSchema),
});
export type BankStatementImportResponse = z.infer<
  typeof bankStatementImportResponseSchema
>;

export const bankTransactionViewSchema = z.object({
  id: z.string(),
  bank_account_id: z.string(),
  account_label: z.string(),
  external_tx_id: z.string(),
  posted_date: z.string(),
  description: z.string(),
  merchant_name: z.string(),
  direction: txDirectionSchema,
  amount_cents: z.number().int(),
  currency: currencyCodeSchema,
  category_hint: z.string(),
  source_format: sourceFormatSchema,
  reconciliation_status: reconciliationStatusSchema,
  matched_entity_kind: matchedEntityKindSchema.nullable(),
  matched_entity_id: z.string().nullable(),
  matched_entity_label: z.string(),
  match_confidence: z.number().int(),
  reconciled_at: z.string().nullable(),
  notes: z.string(),
});
export type BankTransactionView = z.infer<typeof bankTransactionViewSchema>;

export const plaidSandboxSyncResponseSchema = z.object({
  account: bankAccountViewSchema,
  imported_count: z.number().int(),
  duplicate_skipped_count: z.number().int(),
  suggested_match_count: z.number().int(),
  message: z.string(),
});
export type PlaidSandboxSyncResponse = z.infer<
  typeof plaidSandboxSyncResponseSchema
>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/banking`;
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
      "US Bank Feeds API returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchBankFeedsSummary(
  businessId: string,
): Promise<BankFeedsSummary> {
  const res = await authorizedResponse(`${base(businessId)}/summary`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, bankFeedsSummarySchema);
}

export async function createBankAccount(
  businessId: string,
  input: {
    institution_name: string;
    account_name: string;
    account_mask: string;
    account_type: AccountType;
    currency: CurrencyCode;
    current_balance_cents: number;
  },
): Promise<BankAccountView> {
  const res = await authorizedResponse(`${base(businessId)}/accounts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, bankAccountViewSchema);
}

export async function importBankStatement(
  businessId: string,
  accountId: string,
  input: {
    source_format: "auto" | "ofx" | "qfx" | "qbo" | "csv";
    raw_content: string;
    dry_run: boolean;
  },
): Promise<BankStatementImportResponse> {
  const res = await authorizedResponse(
    `${base(businessId)}/accounts/${encodeURIComponent(accountId)}/import`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return readJson(res, bankStatementImportResponseSchema);
}

export async function fetchBankTransactions(
  businessId: string,
  params?: {
    account_id?: string;
    reconciliation_status?: ReconciliationStatus;
  },
): Promise<BankTransactionView[]> {
  const sp = new URLSearchParams();
  if (params?.account_id) sp.set("account_id", params.account_id);
  if (params?.reconciliation_status) {
    sp.set("reconciliation_status", params.reconciliation_status);
  }
  const qs = sp.toString();
  const res = await authorizedResponse(
    `${base(businessId)}/transactions${qs ? `?${qs}` : ""}`,
    {
      headers: { Accept: "application/json" },
    },
  );
  return readJson(res, z.array(bankTransactionViewSchema));
}

export async function reconcileBankTransaction(
  businessId: string,
  txId: string,
  input: {
    action: "confirm_match" | "manual_category" | "exclude" | "unmatch";
    matched_entity_kind?: MatchedEntityKind | null;
    matched_entity_id?: string | null;
    matched_entity_label?: string | null;
    category_hint?: string | null;
    notes?: string;
  },
): Promise<BankTransactionView> {
  const res = await authorizedResponse(
    `${base(businessId)}/transactions/${encodeURIComponent(txId)}/reconcile`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return readJson(res, bankTransactionViewSchema);
}

export async function savePlaidCredentials(
  businessId: string,
  input: {
    plaid_env: "sandbox" | "production";
    client_id: string;
    secret: string;
  },
): Promise<PlaidStatusView> {
  const res = await authorizedResponse(
    `${base(businessId)}/plaid/credentials`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return readJson(res, plaidStatusViewSchema);
}

export async function syncPlaidSandboxFeed(
  businessId: string,
  input: {
    institution_name: string;
    account_name: string;
    account_mask: string;
  },
): Promise<PlaidSandboxSyncResponse> {
  const res = await authorizedResponse(
    `${base(businessId)}/plaid/sandbox-sync`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return readJson(res, plaidSandboxSyncResponseSchema);
}

export function buildBankFeedCsv(txs: readonly BankTransactionView[]): string {
  const headers = [
    "Posted Date",
    "Bank Account",
    "Direction",
    "Amount",
    "Currency",
    "Description",
    "Merchant",
    "Category",
    "Source",
    "Reconciliation Status",
    "Matched Record",
    "Confidence %",
    "External Tx ID",
  ];
  const rows = [headers.map(escapeCsvCell).join(",")];
  for (const tx of txs) {
    const signed =
      (tx.direction === "debit" ? -tx.amount_cents : tx.amount_cents) / 100;
    rows.push(
      [
        tx.posted_date,
        tx.account_label,
        tx.direction,
        signed.toFixed(2),
        tx.currency,
        tx.description,
        tx.merchant_name,
        tx.category_hint,
        tx.source_format,
        tx.reconciliation_status,
        tx.matched_entity_label,
        tx.match_confidence,
        tx.external_tx_id,
      ]
        .map(escapeCsvCell)
        .join(","),
    );
  }
  return `${rows.join("\r\n")}\r\n`;
}

export const SAMPLE_CHASE_CSV = `Posting Date,Description,Amount,Type,Balance
11/26/2026,STRIPE US PAYOUT ACH SETTLEMENT,"$18,450.00",ACH_CREDIT,"$148,250.00"
11/25/2026,ACH WIRE IN NORTHSTAR COLD LOGISTICS,"$9,600.00",ACH_CREDIT,"$129,800.00"
11/24/2026,PILOT FLYING J FLEET DIESEL #04,"-$2,185.00",DEBIT,"$120,200.00"
11/23/2026,GUSTO US PAYROLL BIWEEKLY RUN,"-$6,420.00",ACH_DEBIT,"$122,385.00"`;

export const SAMPLE_WELLS_FARGO_OFX = `OFXHEADER:100
DATA:OFXSGML
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <BANKTRANLIST>
          <STMTTRN>
            <TRNTYPE>CREDIT
            <DTPOSTED>20261126120000[-5:EST]
            <TRNAMT>11400.00
            <FITID>WF-20261126-001
            <NAME>ACME FREIGHT BROKERS LLC
            <MEMO>INVOICE SETTLEMENT ACH
          </STMTTRN>
          <STMTTRN>
            <TRNTYPE>DEBIT
            <DTPOSTED>20261125120000[-5:EST]
            <TRNAMT>-1490.00
            <FITID>WF-20261125-002
            <NAME>GRAINGER INDUSTRIAL SUPPLY
            <MEMO>PO WAREHOUSE PARTS
          </STMTTRN>
        </BANKTRANLIST>
        <LEDGERBAL>
          <BALAMT>158160.00
        </LEDGERBAL>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>`;
