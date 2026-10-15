import { z } from "zod";
import { ManagementApiError, managementFetch } from "./management-api";
import {
  balanceListSchema,
  commandStatusSchema,
  costListSchema,
  documentListSchema,
  documentSchema,
  itemListSchema,
  itemSchema,
  placeListSchema,
  placeSchema,
  postingRulesSchema,
  type CommandReference,
  type InventoryCommand,
} from "./inventory-contracts";

const base = (business: string) => `/v1/businesses/${business}/inventory`;

/** Every object that names its business must name this one. */
function own<T>(business: string, value: T): T {
  const named = (value as { business_id?: string }).business_id;
  const items = (value as { items?: { business_id?: string }[] }).items ?? [];
  if (
    (named !== undefined && named !== business) ||
    items.some((x) => x.business_id !== undefined && x.business_id !== business)
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load materials safely.",
    );
  return value;
}
async function read<T>(
  business: string,
  schema: z.ZodType<T>,
  path: string,
  init?: RequestInit,
): Promise<T> {
  return own(business, schema.parse(await managementFetch(path, init)));
}
const query = (values: Record<string, string | undefined>) => {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(values))
    if (value) search.set(name, value);
  return search.size ? `?${search}` : "";
};

export const fetchItems = (business: string, after?: string) =>
  read(business, itemListSchema, `${base(business)}/items${query({ after })}`);
export const fetchPlaces = (business: string, after?: string) =>
  read(
    business,
    placeListSchema,
    `${base(business)}/places${query({ after })}`,
  );
export const fetchBalances = (
  business: string,
  place?: string,
  after?: string,
) =>
  read(
    business,
    balanceListSchema,
    `${base(business)}/balances${query({ place_id: place, after })}`,
  );
export const fetchCosts = (business: string, after?: string) =>
  read(business, costListSchema, `${base(business)}/costs${query({ after })}`);

/** Validate each page at the API boundary; publish the catalogue only when complete. */
async function allPages<T>(
  fetchPage: (
    after?: string,
  ) => Promise<{ items: T[]; next_cursor: string | null }>,
) {
  const items: T[] = [];
  const seen = new Set<string>();
  let after: string | undefined;
  for (;;) {
    const page = await fetchPage(after);
    items.push(...page.items);
    if (page.next_cursor === null) return { items, next_cursor: null };
    if (seen.has(page.next_cursor))
      throw new ManagementApiError(
        "INVALID_RESPONSE",
        "Unable to load the complete materials list safely.",
      );
    seen.add(page.next_cursor);
    after = page.next_cursor;
  }
}
export const fetchAllItems = (business: string) =>
  allPages((after) => fetchItems(business, after));
export const fetchAllPlaces = (business: string) =>
  allPages((after) => fetchPlaces(business, after));
export const fetchAllBalances = (business: string, place?: string) =>
  allPages((after) => fetchBalances(business, place, after));
export const fetchAllCosts = (business: string) =>
  allPages((after) => fetchCosts(business, after));

/** The accounts of materials of a book, or null when none are chosen yet. */
export async function fetchPostingRules(business: string, book: string) {
  try {
    return await read(
      business,
      postingRulesSchema,
      `${base(business)}/posting-rules/${book}`,
    );
  } catch (error) {
    if (error instanceof ManagementApiError && error.code === "NOT_FOUND")
      return null;
    throw error;
  }
}

export const fetchDocuments = (
  business: string,
  place?: string,
  after?: string,
) =>
  read(
    business,
    documentListSchema,
    `${base(business)}/documents${query({ place_id: place, after })}`,
  );
export const fetchDocument = (business: string, document: string) =>
  read(business, documentSchema, `${base(business)}/documents/${document}`);

export async function executeInventoryCommand(
  business: string,
  command: InventoryCommand,
) {
  const init = {
    method: "PUT",
    body: JSON.stringify(command.body),
    headers: { "Idempotency-Key": command.key },
  };
  if (command.type === "document")
    return subject(
      command.id,
      "document_id",
      await read(
        business,
        documentSchema,
        `${base(business)}/documents/${command.id}`,
        init,
      ),
    );
  if (command.type === "item")
    return subject(
      command.id,
      "item_id",
      await read(
        business,
        itemSchema,
        `${base(business)}/items/${command.id}`,
        init,
      ),
    );
  if (command.type === "place")
    return subject(
      command.id,
      "place_id",
      await read(
        business,
        placeSchema,
        `${base(business)}/places/${command.id}`,
        init,
      ),
    );
  return subject(
    command.book,
    "book_id",
    await read(
      business,
      postingRulesSchema,
      `${base(business)}/posting-rules/${command.book}`,
      init,
    ),
  );
}

function subject<T, K extends keyof T>(
  expected: string,
  field: K,
  value: T,
): T {
  if (value[field] !== expected)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected inventory command subject.",
    );
  return value;
}

/** What became of a command whose answer was lost; `cancel` refuses its late copy. */
export async function settleInventoryCommand(
  business: string,
  key: string,
  reference: CommandReference,
  cancel = false,
) {
  const result = await read(
    business,
    commandStatusSchema,
    `${base(business)}/commands/${encodeURIComponent(key)}/${cancel ? "cancel" : "resolve"}`,
    { method: "POST", body: JSON.stringify(reference) },
  );
  if (result.key !== key || result.operation !== reference.operation)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected recovered inventory command.",
    );
  return result;
}
