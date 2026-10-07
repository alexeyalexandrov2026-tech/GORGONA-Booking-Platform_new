import { z } from "zod";

const id = z.uuid();
const revision = z.number().int().positive();
const instant = z.iso.datetime({ offset: true });
const day = z.iso.date();
const month = z.string().regex(/^[1-9]\d{3}-(0[1-9]|1[0-2])$/);
const code = z.string().regex(/^[A-Z]{3}$/);
const scale = z.union([z.literal(0), z.literal(2), z.literal(3)]);
const amount = z
  .string()
  .max(64)
  .regex(/^(0|[1-9]\d*)(\.\d{1,3})?$/);
const type = z.enum(["asset", "liability", "equity", "revenue", "expense"]);
const envelope = { schema_version: z.literal(1), business_id: id };
const unique = <T>(items: T[], key: (item: T) => string) =>
  new Set(items.map(key)).size === items.length;

/** Exact money, including totals above Number.MAX_SAFE_INTEGER. No float conversion. */
export function minorUnits(value: string, places: number): bigint | null {
  if (![0, 2, 3].includes(places) || !/^(0|[1-9]\d*)(\.\d{1,3})?$/.test(value))
    return null;
  const [whole, fraction = ""] = value.split(".");
  if (fraction.length > places) return null;
  return (
    BigInt(whole!) * 10n ** BigInt(places) +
    BigInt(fraction.padEnd(places, "0") || "0")
  );
}
export const bookSchema = z.strictObject({
  ...envelope,
  book_id: id,
  legal_entity_id: id,
  revision,
  base_currency: code,
  minor_units: scale,
  fiscal_year_start_month: z.number().int().min(1).max(12),
  accounting_start: day,
  has_entries: z.boolean(),
  created_at: instant,
});
export const ledgerOverviewSchema = z
  .strictObject({
    ...envelope,
    items: z
      .array(
        z.strictObject({
          legal_entity_id: id,
          code: z.string(),
          legal_name: z.string(),
          book: bookSchema.nullable(),
        }),
      )
      .max(100),
    next_cursor: z.string().nullable(),
    currencies: z.array(z.strictObject({ code, minor_units: scale })),
  })
  .refine(
    (v) =>
      unique(v.items, (x) => x.legal_entity_id) &&
      unique(v.currencies, (x) => x.code) &&
      v.items.every(
        (x) =>
          !x.book ||
          (x.book.business_id === v.business_id &&
            x.book.legal_entity_id === x.legal_entity_id),
      ),
  );
const account = z.strictObject({
  account_id: id,
  code: z.string().regex(/^[0-9A-Za-z][0-9A-Za-z.-]{0,31}$/),
  type,
  name: z.string().min(1).max(400),
  archived: z.boolean(),
  revision,
  has_lines: z.boolean(),
  updated_at: instant,
});
export const accountSchema = account.extend({ ...envelope, book_id: id });
export const accountListSchema = z
  .strictObject({
    ...envelope,
    book_id: id,
    items: z.array(account).max(100),
    next_cursor: z.string().nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.account_id));
const summary = z.strictObject({
  entry_id: id,
  entry_date: day,
  period: month,
  currency: code,
  source_kind: z.enum(["manual", "opening", "reversal"]),
  source_id: z.string().min(1),
  memo: z.string().nullable(),
  total: amount,
  reverses_entry_id: id.nullable(),
  reversed_by_entry_id: id.nullable(),
  created_at: instant,
});
const entryRecord = summary.extend({
  ...envelope,
  book_id: id,
  minor_units: scale,
  lines: z
    .array(
      z.strictObject({
        line_no: z.number().int().min(1).max(200),
        account_id: id,
        account_code: z.string(),
        account_name: z.string(),
        side: z.enum(["debit", "credit"]),
        amount,
      }),
    )
    .min(2)
    .max(200),
});
// Finite v2 origins: G kinds plus journals owned by a financial document.
const sourceKindV2 = z.enum([
  "manual",
  "opening",
  "reversal",
  "invoice",
  "accrual",
]);
const entryRecordV2 = entryRecord.extend({
  schema_version: z.literal(2),
  source_kind: sourceKindV2,
});
const validEntry = (
  v: z.infer<typeof entryRecord> | z.infer<typeof entryRecordV2>,
) => {
  let debit = 0n,
    credit = 0n;
  for (const line of v.lines) {
    const value = minorUnits(line.amount, v.minor_units);
    if (value === null || value <= 0n) return false;
    if (line.side === "debit") debit += value;
    else credit += value;
  }
  return (
    unique(v.lines, (x) => String(x.line_no)) &&
    debit === credit &&
    debit === minorUnits(v.total, v.minor_units) &&
    v.period === v.entry_date.slice(0, 7) &&
    (v.source_kind === "reversal") === (v.reverses_entry_id !== null)
  );
};
export const entrySchema = z.discriminatedUnion("schema_version", [
  entryRecord.refine(validEntry),
  entryRecordV2.refine(validEntry),
]);
const entryListRecord = z.strictObject({
  ...envelope,
  book_id: id,
  items: z.array(summary).max(100),
  next_cursor: id.nullable(),
});
const summaryV2 = summary.extend({ source_kind: sourceKindV2 });
const entryListRecordV2 = entryListRecord.extend({
  schema_version: z.literal(2),
  items: z.array(summaryV2).max(100),
});
const validEntryList = (
  v: z.infer<typeof entryListRecord> | z.infer<typeof entryListRecordV2>,
) =>
  unique(v.items, (x) => x.entry_id) &&
  v.items.every(
    (x) =>
      x.period === x.entry_date.slice(0, 7) &&
      (x.source_kind === "reversal") === (x.reverses_entry_id !== null),
  );
export const entryListSchema = z.discriminatedUnion("schema_version", [
  entryListRecord.refine(validEntryList),
  entryListRecordV2.refine(validEntryList),
]);
const event = z.strictObject({
  sequence: revision,
  action: z.enum(["closed", "reopened"]),
  reason: z.string().nullable(),
  decided_at: instant,
});
const period = z.strictObject({
  period: month,
  state: z.enum(["open", "closed"]),
  sequence: z.number().int().nonnegative(),
  last_event: event.nullable(),
});
const consistentPeriod = (v: z.infer<typeof period>) =>
  v.last_event
    ? v.sequence === v.last_event.sequence &&
      (v.state === "closed") === (v.last_event.action === "closed")
    : v.sequence === 0 && v.state === "open";
export const periodSchema = period
  .extend({ ...envelope, book_id: id, events: z.array(event) })
  .refine(
    (v) =>
      consistentPeriod(v) &&
      v.events.length === v.sequence &&
      v.events.every(
        (x, i) =>
          x.sequence === v.sequence - i &&
          x.action === (x.sequence % 2 ? "closed" : "reopened"),
      ),
  );
export const periodListSchema = z
  .strictObject({
    ...envelope,
    book_id: id,
    items: z.array(period).max(100),
    next_cursor: month.nullable(),
  })
  .refine(
    (v) => unique(v.items, (x) => x.period) && v.items.every(consistentPeriod),
  );
const balances = {
  opening_debit: amount,
  opening_credit: amount,
  debit: amount,
  credit: amount,
  closing_debit: amount,
  closing_credit: amount,
};
export const trialBalanceSchema = z
  .strictObject({
    ...envelope,
    book_id: id,
    currency: code,
    minor_units: scale,
    period_from: month,
    period_to: month,
    currencies: z.array(code),
    rows: z.array(
      z.strictObject({
        account_id: id,
        code: z.string(),
        name: z.string(),
        type,
        archived: z.boolean(),
        ...balances,
      }),
    ),
    totals: z.strictObject(balances),
  })
  .refine((v) => {
    if (v.period_from > v.period_to || !unique(v.rows, (x) => x.account_id))
      return false;
    for (const row of v.rows) {
      const openingDebit = minorUnits(row.opening_debit, v.minor_units);
      const openingCredit = minorUnits(row.opening_credit, v.minor_units);
      const debit = minorUnits(row.debit, v.minor_units);
      const credit = minorUnits(row.credit, v.minor_units);
      const closingDebit = minorUnits(row.closing_debit, v.minor_units);
      const closingCredit = minorUnits(row.closing_credit, v.minor_units);
      if (
        openingDebit === null ||
        openingCredit === null ||
        debit === null ||
        credit === null ||
        closingDebit === null ||
        closingCredit === null
      )
        return false;
      if (
        (openingDebit > 0n && openingCredit > 0n) ||
        (closingDebit > 0n && closingCredit > 0n) ||
        openingDebit - openingCredit + debit - credit !==
          closingDebit - closingCredit
      )
        return false;
    }
    const keys = Object.keys(balances) as (keyof typeof balances)[];
    for (const key of keys) {
      const values = v.rows.map((x) => minorUnits(x[key], v.minor_units));
      if (
        values.some((x) => x === null) ||
        values.reduce<bigint>((sum, x) => sum + (x ?? 0n), 0n) !==
          minorUnits(v.totals[key], v.minor_units)
      )
        return false;
    }
    return (
      v.totals.debit === v.totals.credit &&
      v.totals.opening_debit === v.totals.opening_credit &&
      v.totals.closing_debit === v.totals.closing_credit
    );
  });
export type LedgerOverview = z.infer<typeof ledgerOverviewSchema>;
export type LedgerBook = z.infer<typeof bookSchema>;
export type LedgerAccount = z.infer<typeof account>;
export type LedgerEntry = z.infer<typeof entrySchema>;
export type LedgerEntries = z.infer<typeof entryListSchema>;
export type LedgerPeriod = z.infer<typeof periodSchema>;
export type TrialBalance = z.infer<typeof trialBalanceSchema>;
export interface BookInput {
  schema_version: 1;
  expected_revision: number;
  legal_entity_id: string;
  base_currency: string;
  fiscal_year_start_month: number;
  accounting_start: string;
  chart?: "starter" | "empty";
}
export interface AccountInput {
  schema_version: 1;
  expected_revision: number;
  code: string;
  type: z.infer<typeof type>;
  name: string;
  archived: boolean;
}
export interface EntryInput {
  schema_version: 1;
  entry_date: string;
  currency: string;
  source_kind: "manual" | "opening";
  source_id: string | null;
  memo: string | null;
  lines: { account_id: string; side: "debit" | "credit"; amount: string }[];
}
export type LedgerCommand = { book: string; key: string } & (
  | { type: "book"; body: BookInput }
  | { type: "account"; id: string; body: AccountInput }
  | { type: "entry"; id: string; body: EntryInput }
  | {
      type: "reverse";
      id: string;
      body: {
        schema_version: 1;
        reversal_entry_id: string;
        entry_date: string;
        memo: string | null;
      };
    }
  | {
      type: "close";
      period: string;
      body: {
        schema_version: 1;
        expected_sequence: number;
        reason: string | null;
      };
    }
  | {
      type: "reopen";
      period: string;
      body: { schema_version: 1; expected_sequence: number; reason: string };
    }
);
export function ledgerResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  if (
    /^\/ledger\/commands\/[A-Za-z0-9._:-]{8,255}\/(resolve|cancel)$/.test(
      suffix,
    ) &&
    method === "POST"
  )
    return commandStatusSchema;
  if (suffix === "/ledger" && method === "GET") return ledgerOverviewSchema;
  const match = /^\/ledger\/books\/[0-9a-f-]{36}(.*)$/i.exec(suffix);
  if (!match) return null;
  const tail = match[1] ?? "";
  if (tail === "" && ["GET", "PUT"].includes(method)) return bookSchema;
  if (tail === "/accounts" && method === "GET") return accountListSchema;
  if (
    /^\/accounts\/[0-9a-f-]{36}$/i.test(tail) &&
    ["GET", "PUT"].includes(method)
  )
    return accountSchema;
  if (tail === "/entries" && method === "GET") return entryListSchema;
  if (
    /^\/entries\/[0-9a-f-]{36}$/i.test(tail) &&
    ["GET", "PUT"].includes(method)
  )
    return entrySchema;
  if (/^\/entries\/[0-9a-f-]{36}\/reverse$/i.test(tail) && method === "POST")
    return entrySchema;
  if (tail === "/periods" && method === "GET") return periodListSchema;
  if (/^\/periods\/[1-9]\d{3}-(0[1-9]|1[0-2])$/.test(tail) && method === "GET")
    return periodSchema;
  if (
    /^\/periods\/[1-9]\d{3}-(0[1-9]|1[0-2])\/(close|reopen)$/.test(tail) &&
    method === "POST"
  )
    return periodSchema;
  if (tail === "/trial-balance" && method === "GET") return trialBalanceSchema;
  return null;
}

export const commandKindSchema = z.enum([
  "book",
  "account",
  "entry",
  "reverse",
  "close",
  "reopen",
]);
export const commandReferenceSchema = z
  .strictObject({
    schema_version: z.literal(1),
    operation: commandKindSchema,
    book_id: id,
    subject_id: id.nullable(),
    revision: revision.max(2147483647).nullable(),
    period: month.nullable(),
    sequence: revision.max(2147483647).nullable(),
  })
  .refine((v) => {
    const wanted = {
      book: [false, true, false, false],
      account: [true, true, false, false],
      entry: [true, false, false, false],
      reverse: [true, false, false, false],
      close: [false, false, true, true],
      reopen: [false, false, true, true],
    }[v.operation];
    return [
      v.subject_id !== null,
      v.revision !== null,
      v.period !== null,
      v.sequence !== null,
    ].every((x, i) => x === wanted[i]);
  });
export const commandStatusSchema = z.strictObject({
  ...envelope,
  key: z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/),
  operation: commandKindSchema,
  state: z.enum(["committed", "cancelled", "unresolved"]),
});
export type CommandReference = z.infer<typeof commandReferenceSchema>;
export type CommandStatus = z.infer<typeof commandStatusSchema>;
