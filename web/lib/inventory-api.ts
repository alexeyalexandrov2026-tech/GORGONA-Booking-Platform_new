import { z } from "zod";
import { ManagementApiError, managementFetch } from "./management-api";
import {
  balanceListSchema,
  commandStatusSchema,
  costListSchema,
  itemListSchema,
  itemSchema,
  placeListSchema,
  placeSchema,
  postingRulesSchema,
  type CommandReference,
  type MaterialsCommand,
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

export async function executeMaterialsCommand(
  business: string,
  command: MaterialsCommand,
) {
  const init = {
    method: "PUT",
    body: JSON.stringify(command.body),
    headers: { "Idempotency-Key": command.key },
  };
  if (command.type === "item")
    return read(
      business,
      itemSchema,
      `${base(business)}/items/${command.id}`,
      init,
    );
  if (command.type === "place")
    return read(
      business,
      placeSchema,
      `${base(business)}/places/${command.id}`,
      init,
    );
  return read(
    business,
    postingRulesSchema,
    `${base(business)}/posting-rules/${command.book}`,
    init,
  );
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
