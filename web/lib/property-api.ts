// PROPERTY-01 (catalog screen): the internal catalog routes. Lists are read to their end through
// the server's cursor; a save keeps its Idempotency-Key until it succeeds, so a retry after a lost
// answer is the same request (ADR-0030).
import { ManagementApiError, managementFetch } from "./management-api";
import type {
  LeaseList,
  LeaseRegistration,
  LeaseTerm,
  LeaseTermCommand,
  LeaseTermHistory,
  LeaseView,
  ListingBody,
  ListingRevision,
  ListingView,
  ContractorCompanyBody,
  ContractorCompanyView,
  ContractorUpdateBody,
  ContractorUpdateList,
  ContractorUpdateView,
  ContractorWorkLink,
  ContractorWorkOrderView,
  MaintenanceEventBody,
  MaintenanceEventHistory,
  MaintenanceEventView,
  MaintenanceObligationBody,
  MaintenanceObligationList,
  MaintenanceObligationView,
  MaintenanceRequestBody,
  MaintenanceRequestList,
  MaintenanceRequestView,
  MoveInCommand,
  MoveInView,
  MoveOutCommand,
  MoveOutView,
  ShowingBody,
  ShowingList,
  ShowingView,
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
async function mutate<T>(
  path: string,
  method: "PUT" | "POST",
  body: unknown,
): Promise<T> {
  const payload = JSON.stringify(body);
  const signature = `${method} ${path} ${payload}`;
  let key = pending.get(signature);
  if (!key) {
    key = crypto.randomUUID();
    pending.set(signature, key);
  }
  const result = await managementFetch<T>(path, {
    method,
    body: payload,
    headers: { "Idempotency-Key": key },
  });
  pending.delete(signature);
  return result;
}

export const saveProperty = (
  business: string,
  id: string,
  body: PropertyBody,
) => mutate<PropertyRevision>(`${base(business)}/${id}`, "PUT", body);

const operations = (business: string) => `/v1/businesses/${business}/property`;

export async function fetchListing(
  business: string,
  objectId: string,
): Promise<ListingView | null> {
  try {
    return await managementFetch<ListingView>(
      `${operations(business)}/listings/${objectId}`,
    );
  } catch (error) {
    if (error instanceof ManagementApiError && error.status === 404)
      return null;
    throw error;
  }
}

export const saveListing = (
  business: string,
  objectId: string,
  body: ListingBody,
) =>
  mutate<ListingRevision>(
    `${operations(business)}/listings/${objectId}`,
    "PUT",
    body,
  );

export async function fetchShowings(
  business: string,
  objectId: string,
): Promise<ShowingView[]> {
  const path = `${operations(business)}/showings`;
  const items: ShowingView[] = [];
  let after: string | null = null;
  do {
    const page: ShowingList = await managementFetch(
      after ? `${path}?after=${encodeURIComponent(after)}` : path,
    );
    items.push(
      ...page.items.filter((showing) => showing.object_id === objectId),
    );
    after = page.next_cursor;
  } while (after !== null);
  return items;
}

export const createShowing = (
  business: string,
  id: string,
  body: ShowingBody,
) => mutate<ShowingView>(`${operations(business)}/showings/${id}`, "PUT", body);

export const cancelShowing = (business: string, id: string) =>
  mutate<ShowingView>(`${operations(business)}/showings/${id}/cancel`, "POST", {
    schema_version: 1,
  });

const leaseBase = (business: string) =>
  `/v1/businesses/${business}/property/leases`;

/** Leases of one unit. Omitting the unit on the server still returns the company list. */
export async function fetchLeases(
  business: string,
  objectId: string,
): Promise<LeaseView[]> {
  const all: LeaseView[] = [];
  let after = "";
  for (;;) {
    const query = new URLSearchParams({ object_id: objectId });
    if (after) query.set("after", after);
    const page = await managementFetch<LeaseList>(
      `${leaseBase(business)}?${query}`,
    );
    all.push(...page.items);
    if (!page.next_cursor) return all;
    after = page.next_cursor;
  }
}

export const registerLease = (
  business: string,
  leaseId: string,
  body: LeaseRegistration,
) => mutate<LeaseView>(`${leaseBase(business)}/${leaseId}`, "PUT", body);

export async function fetchTermHistory(
  business: string,
  leaseId: string,
): Promise<LeaseTerm[]> {
  const all: LeaseTerm[] = [];
  let before = 0;
  for (;;) {
    const page = await managementFetch<LeaseTermHistory>(
      `${leaseBase(business)}/${leaseId}/terms${before ? `?before=${before}` : ""}`,
    );
    all.push(...page.items);
    if (page.next_before === null) return all;
    before = page.next_before;
  }
}

export const recordTerm = (
  business: string,
  leaseId: string,
  body: LeaseTermCommand,
) => mutate<LeaseTerm>(`${leaseBase(business)}/${leaseId}/terms`, "POST", body);

export async function fetchMoveIn(
  business: string,
  leaseId: string,
): Promise<MoveInView | null> {
  try {
    return await managementFetch<MoveInView>(
      `${leaseBase(business)}/${leaseId}/move-in`,
    );
  } catch (error) {
    if (error instanceof ManagementApiError && error.status === 404)
      return null;
    throw error;
  }
}

export const recordMoveIn = (
  business: string,
  leaseId: string,
  body: MoveInCommand,
) =>
  mutate<MoveInView>(`${leaseBase(business)}/${leaseId}/move-in`, "PUT", body);

/** A stale term is reloaded. The failed command is not repeated with a new revision. */
export function termConflict(error: unknown): boolean {
  return (
    error instanceof ManagementApiError &&
    (error.code === "PROPERTY_LEASE_REVISION_CONFLICT" ||
      error.code === "PROPERTY_LEASE_MOVE_IN_CONFLICT")
  );
}

export async function fetchMoveOut(
  business: string,
  leaseId: string,
): Promise<MoveOutView | null> {
  try {
    return await managementFetch<MoveOutView>(
      `${leaseBase(business)}/${leaseId}/move-out`,
    );
  } catch (error) {
    if (error instanceof ManagementApiError && error.status === 404)
      return null;
    throw error;
  }
}

export const recordMoveOut = (
  business: string,
  leaseId: string,
  body: MoveOutCommand,
) =>
  mutate<MoveOutView>(
    `${leaseBase(business)}/${leaseId}/move-out`,
    "PUT",
    body,
  );

const maintenanceBase = (business: string) =>
  `/v1/businesses/${business}/property/maintenance`;

export async function fetchMaintenanceRequests(
  business: string,
  objectId: string,
): Promise<MaintenanceRequestView[]> {
  const all: MaintenanceRequestView[] = [];
  let after = "";
  for (;;) {
    const query = new URLSearchParams({ object_id: objectId });
    if (after) query.set("after", after);
    const page = await managementFetch<MaintenanceRequestList>(
      `${maintenanceBase(business)}?${query}`,
    );
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export const createMaintenanceRequest = (
  business: string,
  requestId: string,
  body: MaintenanceRequestBody,
) =>
  mutate<MaintenanceRequestView>(
    `${maintenanceBase(business)}/${requestId}`,
    "PUT",
    body,
  );

export async function fetchMaintenanceEvents(
  business: string,
  requestId: string,
): Promise<MaintenanceEventView[]> {
  const all: MaintenanceEventView[] = [];
  let before = 0;
  for (;;) {
    const page = await managementFetch<MaintenanceEventHistory>(
      `${maintenanceBase(business)}/${requestId}/events${before ? `?before=${before}` : ""}`,
    );
    all.push(...page.items);
    if (page.next_before === null) return all;
    before = page.next_before;
  }
}

export const recordMaintenanceEvent = (
  business: string,
  requestId: string,
  body: MaintenanceEventBody,
) =>
  mutate<MaintenanceRequestView>(
    `${maintenanceBase(business)}/${requestId}/events`,
    "POST",
    body,
  );

export async function fetchMaintenanceObligations(
  business: string,
  requestId: string,
): Promise<MaintenanceObligationView[]> {
  const page = await managementFetch<MaintenanceObligationList>(
    `${maintenanceBase(business)}/${requestId}/obligations`,
  );
  return page.items;
}

export const recordMaintenanceObligation = (
  business: string,
  requestId: string,
  body: MaintenanceObligationBody,
) =>
  mutate<MaintenanceObligationView>(
    `${maintenanceBase(business)}/${requestId}/obligations`,
    "POST",
    body,
  );

export const fetchContractorCompany = (business: string, requestId: string) =>
  managementFetch<ContractorCompanyView>(
    `${maintenanceBase(business)}/${requestId}/contractor-company`,
  );

export const saveContractorCompany = (
  business: string,
  requestId: string,
  body: ContractorCompanyBody,
) =>
  mutate<ContractorCompanyView>(
    `${maintenanceBase(business)}/${requestId}/contractor-company`,
    "PUT",
    body,
  );

export async function fetchContractorUpdates(
  business: string,
  requestId: string,
): Promise<ContractorUpdateView[]> {
  const page = await managementFetch<ContractorUpdateList>(
    `${maintenanceBase(business)}/${requestId}/contractor-updates`,
  );
  return page.items;
}

export const fetchContractorWork = (
  link: ContractorWorkLink,
  signal?: AbortSignal,
) =>
  managementFetch<ContractorWorkOrderView>(
    `${maintenanceBase(link.business)}/${link.request}/contractor-work/${link.grant}`,
    signal ? { signal } : undefined,
  );

export const postContractorUpdate = (
  link: ContractorWorkLink,
  body: ContractorUpdateBody,
) =>
  mutate<ContractorUpdateView>(
    `${maintenanceBase(link.business)}/${link.request}/contractor-work/${link.grant}/updates`,
    "POST",
    body,
  );

export function contractorWorkHref(link: ContractorWorkLink): string {
  return `/property/contractor/?${new URLSearchParams(link).toString()}`;
}

export function maintenanceConflict(error: unknown): boolean {
  return (
    error instanceof ManagementApiError &&
    error.code === "PROPERTY_MAINTENANCE_REVISION_CONFLICT"
  );
}
