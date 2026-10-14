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

/** The reference a command will resolve to once it has taken effect. */
export function commandReference(command: MaterialsCommand): CommandReference {
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
  return null;
}
