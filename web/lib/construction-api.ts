// O7a (package O): the construction routes the list and the project page use. The project list is read
// to its end through the server's cursor; a command keeps its Idempotency-Key until it succeeds, so a
// retry after a lost answer is the same request (as on the transport screens, ADR-0030).
import { ManagementApiError, managementFetch } from "./management-api";
import type {
  ChangeOrder,
  ChangeOrderList,
  Contract,
  Estimate,
  EstimateList,
  LineKind,
  Project,
  ProjectList,
} from "./construction-contracts";

/** The server's refusal, or what went wrong on the way, in words the screen can show. */
export function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

const base = (business: string) => `/v1/businesses/${business}/construction`;
const projectPath = (business: string, project: string) =>
  `${base(business)}/projects/${project}`;

export async function fetchAllProjects(business: string): Promise<Project[]> {
  const items: Project[] = [];
  let after = "";
  for (;;) {
    const page = await managementFetch<ProjectList>(
      `${base(business)}/projects${after ? `?after=${encodeURIComponent(after)}` : ""}`,
    );
    items.push(...page.items);
    if (!page.next_cursor) return items;
    after = page.next_cursor;
  }
}
export const fetchProject = (business: string, project: string) =>
  managementFetch<Project>(projectPath(business, project));
export const fetchEstimates = (business: string, project: string) =>
  managementFetch<EstimateList>(`${projectPath(business, project)}/estimates`);
export const fetchEstimate = (
  business: string,
  project: string,
  version: number,
) =>
  managementFetch<Estimate>(
    `${projectPath(business, project)}/estimates/${version}`,
  );
export const fetchChangeOrders = (business: string, project: string) =>
  managementFetch<ChangeOrderList>(
    `${projectPath(business, project)}/change-orders`,
  );
export const fetchChangeOrder = (
  business: string,
  project: string,
  number: number,
) =>
  managementFetch<ChangeOrder>(
    `${projectPath(business, project)}/change-orders/${number}`,
  );

/** The project's contract, or null while the customer has not accepted a proposal. */
export async function fetchContract(
  business: string,
  project: string,
): Promise<Contract | null> {
  try {
    return await managementFetch<Contract>(
      `${projectPath(business, project)}/contract`,
    );
  } catch (error) {
    if (error instanceof ManagementApiError && error.code === "NOT_FOUND")
      return null;
    throw error;
  }
}

const pending = new Map<string, string>();
async function command<T>(
  path: string,
  method: string,
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

export type ProjectBody = {
  schema_version: 1;
  expected_revision: number;
  number: string;
  name: string;
  customer_id: string;
  location_id: string;
  site_address: string;
  time_zone: string;
  currency: string;
};
export const saveProject = (
  business: string,
  project: string,
  body: ProjectBody,
) => command<Project>(projectPath(business, project), "PUT", body);

export type LineBody = {
  kind: LineKind;
  description: string;
  phase: string;
  quantity: string;
  unit: string;
  unit_cost_minor: number;
  unit_price_minor: number;
  material_id: string | null;
};
export type EstimateBody = {
  schema_version: 1;
  based_on: number;
  note: string | null;
  lines: LineBody[];
};
export const saveEstimate = (
  business: string,
  project: string,
  body: EstimateBody,
) =>
  command<Estimate>(
    `${projectPath(business, project)}/estimates`,
    "POST",
    body,
  );
export const propose = (business: string, project: string, version: number) =>
  command<Estimate>(
    `${projectPath(business, project)}/estimates/${version}/proposal`,
    "POST",
    { schema_version: 1 },
  );

export type Source = "paper" | "email";
export type ContractBody = {
  schema_version: 1;
  version: number;
  signatory: string;
  source: Source;
  note: string | null;
};
export const acceptProposal = (
  business: string,
  project: string,
  body: ContractBody,
) =>
  command<Contract>(`${projectPath(business, project)}/contract`, "POST", body);

export type ChangeLineBody =
  | (LineBody & { action: "add" })
  | { action: "remove"; contract_position: number; quantity: string };
export type ChangeOrderBody = {
  schema_version: 1;
  title: string;
  reason: string | null;
  days_delta: number;
  lines: ChangeLineBody[];
};
export const proposeChange = (
  business: string,
  project: string,
  body: ChangeOrderBody,
) =>
  command<ChangeOrder>(
    `${projectPath(business, project)}/change-orders`,
    "POST",
    body,
  );
export type DecisionBody = {
  schema_version: 1;
  decision: "approved" | "rejected" | "withdrawn";
  source: Source | null;
  note: string | null;
};
export const decide = (
  business: string,
  project: string,
  number: number,
  body: DecisionBody,
) =>
  command<ChangeOrder>(
    `${projectPath(business, project)}/change-orders/${number}/decision`,
    "POST",
    body,
  );
