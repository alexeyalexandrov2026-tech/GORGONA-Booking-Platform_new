import { z } from "zod";
import { ManagementApiError, managementFetch } from "./management-api";
import {
  accountListSchema,
  accountSchema,
  bookSchema,
  entryListSchema,
  entrySchema,
  ledgerOverviewSchema,
  periodSchema,
  trialBalanceSchema,
  type LedgerCommand,
  commandStatusSchema,
  type CommandReference,
} from "./ledger-contracts";

const base = (business: string) => `/v1/businesses/${business}/ledger`;
export async function resolveLedgerCommand(
  business: string,
  key: string,
  reference: CommandReference,
  cancel = false,
) {
  const result = await read(
    business,
    commandStatusSchema,
    `${base(business)}/commands/${encodeURIComponent(key)}/${cancel ? "cancel" : "resolve"}`,
    undefined,
    { method: "POST", body: JSON.stringify(reference) },
  );
  if (result.key !== key || result.operation !== reference.operation)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected recovered ledger command.",
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
  const result = schema.parse(await managementFetch(path, init));
  if (result.business_id !== business || (book && result.book_id !== book))
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this ledger safely.",
    );
  return result;
}
export function fetchLedger(business: string, after?: string, book?: string) {
  const query = new URLSearchParams();
  if (after) query.set("after", after);
  if (book) query.set("book_id", book);
  return read(
    business,
    ledgerOverviewSchema,
    base(business) + (query.size ? `?${query}` : ""),
  );
}
export function fetchBook(business: string, book: string) {
  return read(business, bookSchema, `${base(business)}/books/${book}`, book);
}
export function fetchAccounts(business: string, book: string, after?: string) {
  return read(
    business,
    accountListSchema,
    `${base(business)}/books/${book}/accounts?limit=100${after ? `&after=${encodeURIComponent(after)}` : ""}`,
    book,
  );
}
export function fetchEntries(business: string, book: string, after?: string) {
  return read(
    business,
    entryListSchema,
    `${base(business)}/books/${book}/entries?schema_version=2${after ? `&after=${after}` : ""}`,
    book,
  );
}
export async function fetchEntry(business: string, book: string, id: string) {
  const result = await read(
    business,
    entrySchema,
    `${base(business)}/books/${book}/entries/${id}?schema_version=2`,
    book,
  );
  if (result.entry_id !== id)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected journal entry.",
    );
  return result;
}
export async function fetchPeriod(
  business: string,
  book: string,
  period: string,
) {
  const result = await read(
    business,
    periodSchema,
    `${base(business)}/books/${book}/periods/${period}`,
    book,
  );
  if (result.period !== period)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected ledger month.",
    );
  return result;
}
export async function fetchTrialBalance(
  business: string,
  book: string,
  from: string,
  to: string,
  currency: string,
) {
  const query = new URLSearchParams({
    period_from: from,
    period_to: to,
    currency,
  });
  const result = await read(
    business,
    trialBalanceSchema,
    `${base(business)}/books/${book}/trial-balance?${query}`,
    book,
  );
  if (
    result.currency !== currency ||
    result.period_from !== from ||
    result.period_to !== to
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected report currency or period.",
    );
  return result;
}
export async function executeLedgerCommand(
  business: string,
  command: LedgerCommand,
) {
  const path = `${base(business)}/books/${command.book}`;
  const init = {
    body: JSON.stringify(command.body),
    headers: { "Idempotency-Key": command.key },
  };
  if (command.type === "book")
    return read(business, bookSchema, path, command.book, {
      ...init,
      method: "PUT",
    });
  if (command.type === "account") {
    const result = await read(
      business,
      accountSchema,
      `${path}/accounts/${command.id}`,
      command.book,
      { ...init, method: "PUT" },
    );
    if (result.account_id !== command.id)
      throw new ManagementApiError("INVALID_RESPONSE", "Unexpected account.");
    return result;
  }
  if (command.type === "entry" || command.type === "reverse") {
    const result = await read(
      business,
      entrySchema,
      `${path}/entries/${command.id}${command.type === "reverse" ? "/reverse" : ""}`,
      command.book,
      { ...init, method: command.type === "entry" ? "PUT" : "POST" },
    );
    const expected =
      command.type === "entry" ? command.id : command.body.reversal_entry_id;
    if (result.entry_id !== expected)
      throw new ManagementApiError(
        "INVALID_RESPONSE",
        "Unexpected posted entry.",
      );
    return result;
  }
  const result = await read(
    business,
    periodSchema,
    `${path}/periods/${command.period}/${command.type}`,
    command.book,
    { ...init, method: "POST" },
  );
  if (result.period !== command.period)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected ledger month.",
    );
  return result;
}
