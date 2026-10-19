import { z } from "zod";
import { managementFetch, ManagementApiError } from "./management-api";
import {
  invoiceSchema,
  invoiceListSchema,
  creditSchema,
  creditListSchema,
  obligationSchema,
  obligationListSchema,
  settlementSchema,
  settlementListSchema,
  paymentSchema,
  financialOverviewSchema,
  financialStatusSchema,
  financialCommandSchema,
  providerOperationListSchema,
  providerConnectionListSchema,
  providerClearingAccountSchema,
  providerOperationDetailSchema,
  providerAttentionListSchema,
  providerAcknowledgementSchema,
  providerLinkResultSchema,
  type FinancialCommand,
  type FinancialReference,
  type ProviderOperation,
} from "./financial-contracts";

const base = (business: string) =>
  `/v1/businesses/${business}/financial-documents`;
const bookBase = (business: string, book: string) =>
  `${base(business)}/books/${book}`;
export function parseFinancialResponse<
  T extends { business_id: string; book_id?: string },
>(schema: z.ZodType<T>, value: unknown, business: string, book?: string): T {
  const result = schema.parse(value);
  if (result.business_id !== business || (book && result.book_id !== book))
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load these financial records safely.",
    );
  return result;
}
async function read<T extends { business_id: string; book_id?: string }>(
  business: string,
  schema: z.ZodType<T>,
  path: string,
  book?: string,
  init?: RequestInit,
): Promise<T> {
  return parseFinancialResponse(
    schema,
    await managementFetch(path, init),
    business,
    book,
  );
}
function exact(actual: string | number, expected: string | number) {
  if (actual !== expected)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected financial record or saved version.",
    );
}
const query = (after?: string) =>
  after ? `?after=${encodeURIComponent(after)}` : "";
export const fetchFinancialOverview = (business: string) =>
  read(business, financialOverviewSchema, `${base(business)}/overview`);
export const fetchInvoices = (
  business: string,
  book: string,
  kind: "invoice" | "manual_accrual",
  after?: string,
) =>
  read(
    business,
    invoiceListSchema,
    `${bookBase(business, book)}/${kind === "invoice" ? "invoices" : "accruals"}${query(after)}`,
    book,
  );
export async function fetchInvoice(
  business: string,
  book: string,
  subject: string,
  kind: "invoice" | "manual_accrual",
  revision?: number,
) {
  const result = await read(
    business,
    invoiceSchema,
    `${bookBase(business, book)}/${kind === "invoice" ? "invoices" : "accruals"}/${subject}${revision ? `?revision=${revision}` : ""}`,
    book,
  );
  exact(result.document_id, subject);
  exact(result.kind, kind);
  if (revision) exact(result.revision, revision);
  return result;
}
export const fetchCredits = (business: string, book: string, after?: string) =>
  read(
    business,
    creditListSchema,
    `${bookBase(business, book)}/credits${query(after)}`,
    book,
  );
export async function fetchCredit(
  business: string,
  book: string,
  subject: string,
  revision?: number,
) {
  const result = await read(
    business,
    creditSchema,
    `${bookBase(business, book)}/credits/${subject}${revision ? `?revision=${revision}` : ""}`,
    book,
  );
  exact(result.document_id, subject);
  if (revision) exact(result.revision, revision);
  return result;
}
export const fetchObligations = (
  business: string,
  book: string,
  after?: string,
) =>
  read(
    business,
    obligationListSchema,
    `${bookBase(business, book)}/obligations${query(after)}`,
    book,
  );
export async function fetchObligation(
  business: string,
  book: string,
  subject: string,
) {
  const result = await read(
    business,
    obligationSchema,
    `${bookBase(business, book)}/obligations/${subject}`,
    book,
  );
  exact(result.obligation_id, subject);
  return result;
}
export const fetchSettlements = (
  business: string,
  book: string,
  after?: string,
) =>
  read(
    business,
    settlementListSchema,
    `${bookBase(business, book)}/settlements${query(after)}`,
    book,
  );
export const fetchProviderOperations = (
  business: string,
  book: string,
  state?: ProviderOperation["state"],
  after?: string,
) => {
  // Short pages keep the phone view usable; the cursor reaches every row.
  const params = new URLSearchParams({ limit: "20" });
  if (state) params.set("state", state);
  if (after) params.set("after", after);
  const search = params.toString();
  return read(
    business,
    providerOperationListSchema,
    `${bookBase(business, book)}/provider-operations${search ? `?${search}` : ""}`,
    book,
  );
};
export const fetchProviderConnections = (
  business: string,
  book: string,
  after?: string,
) =>
  read(
    business,
    providerConnectionListSchema,
    `${bookBase(business, book)}/provider-connections${query(after)}`,
    book,
  );
/** Registered once; repeating the same account is safe and returns the registration. */
export async function registerClearingAccount(
  business: string,
  book: string,
  connection: string,
  account: string,
) {
  const result = await read(
    business,
    providerClearingAccountSchema,
    `${bookBase(business, book)}/provider-connections/${connection}/clearing-account`,
    book,
    {
      method: "PUT",
      body: JSON.stringify({ schema_version: 1, account_id: account }),
    },
  );
  exact(result.connection_id, connection);
  exact(result.account_id, account);
  return result;
}
export async function fetchProviderOperation(
  business: string,
  book: string,
  operation: string,
) {
  const result = await read(
    business,
    providerOperationDetailSchema,
    `${bookBase(business, book)}/provider-operations/${operation}`,
    book,
  );
  exact(result.operation.operation_id, operation);
  return result;
}
export const fetchProviderAttention = (
  business: string,
  book: string,
  after?: string,
) =>
  read(
    business,
    providerAttentionListSchema,
    `${bookBase(business, book)}/provider-attention${query(after)}`,
    book,
  );
/** Recorded once; the same note again is safe and returns the record (K4b). */
export async function acknowledgeProviderEvent(
  business: string,
  book: string,
  event: string,
  note: string,
) {
  const result = await read(
    business,
    providerAcknowledgementSchema,
    `${bookBase(business, book)}/provider-attention/${event}/acknowledgement`,
    book,
    { method: "PUT", body: JSON.stringify({ schema_version: 1, note }) },
  );
  exact(result.item.event_id, event);
  return result;
}
/** K3b: link an observed operation to its manual payment; the same request again is safe. */
export async function linkProviderOperation(
  business: string,
  book: string,
  operation: string,
  payment: string,
  note: string,
) {
  const result = await read(
    business,
    providerLinkResultSchema,
    `${bookBase(business, book)}/provider-operations/${operation}/link`,
    book,
    {
      method: "PUT",
      body: JSON.stringify({ schema_version: 1, payment_id: payment, note }),
    },
  );
  exact(result.operation.operation_id, operation);
  exact(result.link.payment_id, payment);
  return result;
}
export async function fetchSettlement(
  business: string,
  book: string,
  subject: string,
) {
  const result = await read(
    business,
    settlementSchema,
    `${bookBase(business, book)}/settlements/${subject}`,
    book,
  );
  exact(result.settlement_id, subject);
  return result;
}
export async function fetchPayment(
  business: string,
  book: string,
  subject: string,
  settlement: string,
) {
  const result = await read(
    business,
    paymentSchema,
    `${bookBase(business, book)}/payments/${subject}`,
    book,
  );
  exact(result.payment_id, subject);
  exact(result.settlement_id, settlement);
  return result;
}

export async function executeFinancialCommand(
  business: string,
  input: FinancialCommand,
) {
  const command = financialCommandSchema.parse(input);
  const root = bookBase(business, command.book);
  const init = {
    headers: { "Idempotency-Key": command.key },
    body: JSON.stringify(command.body),
  };
  if (
    command.operation.startsWith("invoice_") ||
    command.operation.startsWith("accrual_")
  ) {
    const kind = command.operation.startsWith("invoice_")
      ? "invoice"
      : "manual_accrual";
    const draft = command.operation.endsWith("_draft");
    const result = await read(
      business,
      invoiceSchema,
      `${root}/${kind === "invoice" ? "invoices" : "accruals"}/${command.subject}${draft ? "" : "/issue"}`,
      command.book,
      { ...init, method: draft ? "PUT" : "POST" },
    );
    exact(result.document_id, command.subject);
    exact(result.kind, kind);
    if ("expected_revision" in command.body)
      exact(result.revision, command.body.expected_revision + 1);
    return result;
  }
  if (command.operation.startsWith("credit_")) {
    const draft = command.operation === "credit_draft";
    const result = await read(
      business,
      creditSchema,
      `${root}/credits/${command.subject}${draft ? "" : command.operation === "credit_issue" ? "/issue" : "/void"}`,
      command.book,
      { ...init, method: draft ? "PUT" : "POST" },
    );
    exact(result.document_id, command.subject);
    if ("expected_revision" in command.body)
      exact(result.revision, command.body.expected_revision + 1);
    return result;
  }
  const prepare = command.operation === "settlement_prepare";
  let suffix = prepare
    ? ""
    : `/${command.operation.slice("settlement_".length)}`;
  if (command.operation === "settlement_provider_confirm")
    suffix = `/provider-confirmations/${command.payment}`;
  else if ("payment" in command)
    suffix = `/confirmations/${command.payment}${command.operation === "settlement_confirm" ? "" : command.operation === "settlement_payment_void" ? "/void" : "/correct"}`;
  const result = await read(
    business,
    settlementSchema,
    `${root}/settlements/${command.subject}${suffix}`,
    command.book,
    { ...init, method: prepare ? "PUT" : "POST" },
  );
  exact(result.settlement_id, command.subject);
  if ("expected_sequence" in command.body)
    exact(result.sequence, command.body.expected_sequence + 1);
  return result;
}
export async function resolveFinancialCommand(
  business: string,
  key: string,
  reference: FinancialReference,
  cancel = false,
) {
  const result = await read(
    business,
    financialStatusSchema,
    `${base(business)}/commands/${encodeURIComponent(key)}/${cancel ? "cancel" : "resolve"}`,
    undefined,
    { method: "POST", body: JSON.stringify(reference) },
  );
  exact(result.key, key);
  exact(result.operation, reference.operation);
  return result;
}
