// PROPERTY-01 (catalog screen): the internal catalog routes. Lists are read to their end through
// the server's cursor; a save keeps its Idempotency-Key until it succeeds, so a retry after a lost
// answer is the same request (ADR-0030).
import { ManagementApiError, managementFetch } from "./management-api";
import type {
  PropertyBody,
  PropertyHistory,
  PropertyList,
  PropertyRevision,
  PropertyView,
} from "./property-contracts";

const base = (business: string) =>
  `/v1/businesses/${business}/property/objects`;

/** The server's refusal, or what went wrong on the way, in words the screen can show. */
export function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

/** A stale save: the revision the server now holds, when it says so. */
export function staleRevision(error: unknown): number | null | undefined {
  if (
    !(error instanceof ManagementApiError) ||
    error.code !== "PROPERTY_REVISION_CONFLICT"
  )
    return undefined;
  const current = error.details?.revision;
  return typeof current === "number" ? current : null;
}

export async function fetchProperties(
  business: string,
): Promise<PropertyView[]> {
  const all: PropertyView[] = [];
  let after = "";
  for (;;) {
    const page = await managementFetch<PropertyList>(
      after
        ? `${base(business)}?after=${encodeURIComponent(after)}`
        : base(business),
    );
    all.push(...page.items);
    if (!page.next_cursor) return all;
    after = page.next_cursor;
  }
}

export const fetchProperty = (business: string, id: string) =>
  managementFetch<PropertyView>(`${base(business)}/${id}`);

export async function fetchHistory(
  business: string,
  id: string,
): Promise<PropertyRevision[]> {
  const all: PropertyRevision[] = [];
  let after = 0;
  for (;;) {
    const page = await managementFetch<PropertyHistory>(
      `${base(business)}/${id}/history${after ? `?after=${after}` : ""}`,
    );
    all.push(...page.items);
    if (page.next_cursor === null) return all;
    after = page.next_cursor;
  }
}

const pending = new Map<string, string>();
export async function saveProperty(
  business: string,
  id: string,
  body: PropertyBody,
): Promise<PropertyRevision> {
  const path = `${base(business)}/${id}`;
  const payload = JSON.stringify(body);
  const signature = `${path} ${payload}`;
  let key = pending.get(signature);
  if (!key) {
    key = crypto.randomUUID();
    pending.set(signature, key);
  }
  const result = await managementFetch<PropertyRevision>(path, {
    method: "PUT",
    body: payload,
    headers: { "Idempotency-Key": key },
  });
  pending.delete(signature);
  return result;
}
