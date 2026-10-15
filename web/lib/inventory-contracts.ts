import { z } from "zod";

const id = z.uuid();
const revision = z.number().int().positive();
const version = { schema_version: z.literal(1) };
const envelope = { ...version, business_id: id };
// Exact decimal text as the server sends it; never converted to a float.
const quantity = z.string().regex(/^(0|[1-9]\d{0,14})(\.\d{1,3})?$/);
const money = z.string().regex(/^-?(0|[1-9]\d*)(\.\d{1,3})?$/);
const code = z.string().regex(/^[A-Z0-9][A-Z0-9_-]{0,63}$/);
const label = z.string().min(1).max(200);
const unique = <T>(items: T[], key: (item: T) => string) =>
  new Set(items.map(key)).size === items.length;

export const itemSchema = z.strictObject({
  ...envelope,
  item_id: id,
  code,
  unit: z.string().min(1).max(16),
  quantity_scale: z.number().int().min(0).max(3),
  revision,
  name: label,
  archived: z.boolean(),
});
export type Item = z.infer<typeof itemSchema>;
export const itemListSchema = z
  .strictObject({
    ...version,
    items: z.array(itemSchema).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.item_id), "Duplicate materials.");

export const placeSchema = z.strictObject({
  ...envelope,
  place_id: id,
  location_id: id,
  code,
  revision,
  name: label,
  archived: z.boolean(),
});
export type Place = z.infer<typeof placeSchema>;
export const placeListSchema = z
  .strictObject({
    ...version,
    items: z.array(placeSchema).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.place_id), "Duplicate places.");

export const balanceSchema = z.strictObject({
  item_id: id,
  place_id: id,
  location_id: id,
  legal_entity_id: id,
  quantity,
});
export type Balance = z.infer<typeof balanceSchema>;
export const balanceListSchema = z.strictObject({
  ...version,
  items: z.array(balanceSchema).max(100),
  next_cursor: z.string().nullable(),
});

export const costSchema = z.strictObject({
  legal_entity_id: id,
  item_id: id,
  quantity,
  value: money,
  currency: z.string().regex(/^[A-Z]{3}$/),
});
export type Cost = z.infer<typeof costSchema>;
export const costListSchema = z.strictObject({
  ...version,
  items: z.array(costSchema).max(100),
  next_cursor: z.string().nullable(),
});

/** The seven accounts of materials of one book, in the order the server names them. */
export const RULE_ACCOUNTS = [
  ["inventory_account_id", "Inventory"],
  ["receipt_account_id", "Receipts"],
  ["opening_account_id", "Opening balances"],
  ["surplus_account_id", "Surplus"],
  ["consumption_account_id", "Material consumption"],
  ["loss_account_id", "Losses"],
  ["difference_account_id", "Price differences"],
] as const;
export type RuleAccount = (typeof RULE_ACCOUNTS)[number][0];
export const postingRulesSchema = z.strictObject({
  ...envelope,
  book_id: id,
  revision,
  inventory_account_id: id,
  receipt_account_id: id,
  opening_account_id: id,
  surplus_account_id: id,
  consumption_account_id: id,
  loss_account_id: id,
  difference_account_id: id,
});
export type PostingRules = z.infer<typeof postingRulesSchema>;

export const commandOperationSchema = z.enum([
  "item",
  "place",
  "posting_rules",
  "document",
]);
export const commandKeySchema = z.string().regex(/^[A-Za-z0-9._:-]{8,255}$/);
/** What a command was expected to produce. Identifiers only, never names or amounts. */
export const commandReferenceSchema = z
  .strictObject({
    ...version,
    operation: commandOperationSchema,
    subject_id: id,
    revision: z.number().int().min(0).max(2147483647),
  })
  .refine(
    (v) => (v.operation === "document") === (v.revision === 0),
    "A document names no revision; everything else names its revision.",
  );
export type CommandReference = z.infer<typeof commandReferenceSchema>;
export const commandStatusSchema = z.strictObject({
  ...envelope,
  key: commandKeySchema,
  operation: commandOperationSchema,
  state: z.enum(["committed", "cancelled", "unresolved"]),
});
export type CommandStatus = z.infer<typeof commandStatusSchema>;

export type ItemBody = {
  schema_version: 1;
  expected_revision: number;
  code: string;
  name: string;
  unit: string;
  quantity_scale: number;
  archived: boolean;
};
export type PlaceBody = {
  schema_version: 1;
  expected_revision: number;
  location_id: string;
  code: string;
  name: string;
  archived: boolean;
};
export type RulesBody = {
  schema_version: 1;
  expected_revision: number;
} & Record<RuleAccount, string>;
export type MaterialsCommand =
  | { type: "item"; id: string; key: string; body: ItemBody }
  | { type: "place"; id: string; key: string; body: PlaceBody }
  | { type: "posting_rules"; book: string; key: string; body: RulesBody };

export const DOCUMENT_KINDS = [
  ["receipt", "Receipt"],
  ["write_off", "Write-off"],
  ["transfer", "Transfer"],
  ["return", "Return"],
] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number][0];
/** The reasons of each kind, in the order the server names them. */
export const DOCUMENT_REASONS = {
  receipt: [
    ["purchase", "Purchase"],
    ["opening_balance", "Opening balance"],
    ["surplus", "Surplus"],
  ],
  write_off: [
    ["used", "Used"],
    ["damaged", "Damaged"],
    ["lost", "Lost"],
    ["expired", "Expired"],
    ["other", "Other"],
  ],
  transfer: [["relocation", "Relocation"]],
  return: [
    ["supplier_return", "Return to supplier"],
    ["unused", "Unused, back to stock"],
    ["entry_error", "Entry error"],
  ],
} as const;
type LineBody = { item_id: string; quantity: string };
type Dated = {
  schema_version: 1;
  legal_entity_id: string;
  place_id: string;
  document_date: string;
};
export type DocumentBody =
  | (Dated & {
      kind: "receipt";
      reason: string;
      supplier_id: string | null;
      supplier_document: string | null;
      lines: (LineBody & { amount: string })[];
    })
  | (Dated & { kind: "write_off"; reason: string; lines: LineBody[] })
  | (Dated & { kind: "transfer"; to_place_id: string; lines: LineBody[] })
  | (Dated & {
      kind: "return";
      reason: string;
      source_document_id: string;
      supplier_id: string | null;
      supplier_document: string | null;
      lines: { source_line_no: number; quantity: string }[];
    });
/** Every command whose answer can be settled by its key. */
export type InventoryCommand =
  | MaterialsCommand
  | { type: "document"; id: string; key: string; body: DocumentBody };

const day = z.iso.date();
const instant = z.iso.datetime({ offset: true });
const amount = z.string().regex(/^(0|[1-9]\d{0,14})(\.\d{1,3})?$/);
// A document total has its own 18-minor-digit bound, larger than a line's limit.
const documentTotal = z
  .string()
  .regex(/^(0|[1-9]\d{0,17})(\.\d{1,3})?$/)
  .pipe(
    z
      .string()
      .refine(
        (value) => BigInt(value.replace(".", "")) <= 999_999_999_999_999_999n,
      ),
  );
const documentKind = z.enum(["receipt", "write_off", "transfer", "return"]);
type Placed = {
  kind: DocumentKind;
  reason: string;
  to_place_id: string | null;
  to_location_id: string | null;
  source_document_id: string | null;
};
/** A transfer names where it arrives, a return what it returns, and nothing else does. */
const placed = (v: Placed) =>
  (DOCUMENT_REASONS[v.kind] as readonly (readonly string[])[]).some(
    ([reason]) => reason === v.reason,
  ) &&
  (v.kind === "transfer") === (v.to_place_id !== null) &&
  (v.to_place_id === null) === (v.to_location_id === null) &&
  (v.kind === "return") === (v.source_document_id !== null);
const documentSummarySchema = z
  .strictObject({
    document_id: id,
    kind: documentKind,
    reason: z.string(),
    legal_entity_id: id,
    place_id: id,
    location_id: id,
    to_place_id: id.nullable(),
    to_location_id: id.nullable(),
    source_document_id: id.nullable(),
    document_date: day,
    line_count: z.number().int().min(1).max(100),
    created_at: instant,
  })
  .refine(placed, "Inconsistent document.");
export type DocumentSummary = z.infer<typeof documentSummarySchema>;
export const documentListSchema = z
  .strictObject({
    ...version,
    items: z.array(documentSummarySchema).max(100),
    next_cursor: id.nullable(),
  })
  .refine((v) => unique(v.items, (x) => x.document_id), "Duplicate documents.");
const documentLineSchema = z.strictObject({
  line_no: z.number().int().min(1).max(100),
  item_id: id,
  quantity,
  amount: amount.nullable(),
  source_line_no: z.number().int().min(1).max(100).nullable(),
  source_amount: amount.nullable(),
});
export const documentSchema = z
  .strictObject({
    ...envelope,
    document_id: id,
    kind: documentKind,
    reason: z.string(),
    legal_entity_id: id,
    place_id: id,
    location_id: id,
    to_place_id: id.nullable(),
    to_location_id: id.nullable(),
    source_document_id: id.nullable(),
    document_date: day,
    supplier_id: id.nullable(),
    supplier_document: z.string().min(1).max(64).nullable(),
    created_at: instant,
    lines: z.array(documentLineSchema).min(1).max(100),
    money: z
      .strictObject({
        book_id: id,
        rule_revision: revision,
        currency: z.string().regex(/^[A-Z]{3}$/),
        total: documentTotal,
        entry_id: id.nullable(),
      })
      .nullable(),
  })
  .refine(placed, "Inconsistent document.")
  .refine(
    (v) => unique(v.lines, (x) => String(x.line_no)),
    "Duplicate document lines.",
  )
  // Amounts come with the money of the document or not at all; a transfer has none.
  .refine(
    (v) =>
      (v.kind !== "transfer" || v.money === null) &&
      v.lines.every(
        (line) =>
          (line.amount === null) === (v.money === null) &&
          (line.source_line_no === null) === (v.kind !== "return") &&
          (line.source_amount === null ||
            (v.kind === "return" && v.money !== null)),
      ),
    "Amounts and money disagree.",
  );
export type StockDocument = z.infer<typeof documentSchema>;

function count(text: string, scale: number): bigint | null {
  const match = /^(0|[1-9]\d{0,14})(?:\.(\d{1,3}))?$/.exec(text);
  if (!match || (match[2]?.length ?? 0) > scale) return null;
  return (
    BigInt(match[1]!) * 10n ** BigInt(scale) +
    BigInt((match[2] ?? "").padEnd(scale, "0") || "0")
  );
}
/** A positive quantity within the decimal places of its material and the server's limit. */
export function quantityFits(text: string, scale: number) {
  const value = count(text, scale);
  return value !== null && value >= 1n && value <= 999_999_999_999n;
}
/** An amount within the minor units of the book's currency and the server's limit. */
export function amountFits(text: string, scale: number) {
  const value = count(text, scale);
  return value !== null && value <= 999_999_999_999_999n;
}

/** The reference a command will resolve to once it has taken effect. */
export function commandReference(command: InventoryCommand): CommandReference {
  // A document is posted once and has no versions.
  if (command.type === "document")
    return {
      schema_version: 1,
      operation: "document",
      subject_id: command.id,
      revision: 0,
    };
  const revision = command.body.expected_revision + 1;
  if (command.type === "posting_rules")
    return {
      schema_version: 1,
      operation: "posting_rules",
      subject_id: command.book,
      revision,
    };
  return {
    schema_version: 1,
    operation: command.type,
    subject_id: command.id,
    revision,
  };
}

export function inventoryResponseSchema(
  suffix: string,
  method: string,
): z.ZodType | null {
  if (
    /^\/inventory\/commands\/[A-Za-z0-9._:-]{8,255}\/(resolve|cancel)$/.test(
      suffix,
    ) &&
    method === "POST"
  )
    return commandStatusSchema;
  if (suffix === "/inventory/items" && method === "GET") return itemListSchema;
  if (
    /^\/inventory\/items\/[0-9a-f-]{36}$/i.test(suffix) &&
    ["GET", "PUT"].includes(method)
  )
    return itemSchema;
  if (suffix === "/inventory/places" && method === "GET")
    return placeListSchema;
  if (
    /^\/inventory\/places\/[0-9a-f-]{36}$/i.test(suffix) &&
    ["GET", "PUT"].includes(method)
  )
    return placeSchema;
  if (suffix === "/inventory/balances" && method === "GET")
    return balanceListSchema;
  if (suffix === "/inventory/costs" && method === "GET") return costListSchema;
  if (
    /^\/inventory\/posting-rules\/[0-9a-f-]{36}$/i.test(suffix) &&
    ["GET", "PUT"].includes(method)
  )
    return postingRulesSchema;
  if (suffix === "/inventory/documents" && method === "GET")
    return documentListSchema;
  if (
    /^\/inventory\/documents\/[0-9a-f-]{36}$/i.test(suffix) &&
    ["GET", "PUT"].includes(method)
  )
    return documentSchema;
  return null;
}
