// O7a (package O): the construction routes the list and the project page use. The project list is read
// to its end through the server's cursor; a command keeps its Idempotency-Key until it succeeds, so a
// retry after a lost answer is the same request (as on the transport screens, ADR-0030).
import { ManagementApiError, managementFetch } from "./management-api";
import type {
  Budget,
  ChangeOrder,
  ChangeOrderList,
  Commitment,
  CommitmentSummary,
  Contract,
  DailyReport,
  DailyReportList,
  Measurement,
  Progress,
  Schedule,
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

// O7b: the budget, commitments, schedule, daily reports and completed quantities.
export const fetchBudget = (business: string, project: string) =>
  managementFetch<Budget>(`${projectPath(business, project)}/budget`);
export const fetchCommitments = (business: string, project: string) =>
  managementFetch<{ items: CommitmentSummary[] }>(
    `${projectPath(business, project)}/commitments`,
  ).then((list) => list.items);
export const fetchCommitment = (
  business: string,
  project: string,
  number: number,
) =>
  managementFetch<Commitment>(
    `${projectPath(business, project)}/commitments/${number}`,
  );
export type CommitmentLineBody = {
  change_order: number | null;
  position: number;
  amount_minor: number;
};
export type CommitmentBody = {
  schema_version: 1;
  kind: "subcontract" | "purchase_order";
  counterparty_id: string;
  title: string;
  reference: string | null;
  note: string | null;
  lines: CommitmentLineBody[];
};
export const createCommitment = (
  business: string,
  project: string,
  body: CommitmentBody,
) =>
  command<Commitment>(
    `${projectPath(business, project)}/commitments`,
    "POST",
    body,
  );
export type RevisionBody = {
  schema_version: 1;
  expected_revision: number;
  state: "open" | "cancelled";
  title: string;
  reference: string | null;
  note: string | null;
  lines: CommitmentLineBody[];
};
export const reviseCommitment = (
  business: string,
  project: string,
  number: number,
  body: RevisionBody,
) =>
  command<Commitment>(
    `${projectPath(business, project)}/commitments/${number}`,
    "PUT",
    body,
  );

export const fetchSchedule = (business: string, project: string) =>
  managementFetch<Schedule>(`${projectPath(business, project)}/schedule`);
export type ScheduleBody = {
  schema_version: 1;
  expected_revision: number;
  note: string | null;
  phases: {
    phase: string;
    planned_start: string;
    planned_finish: string;
    depends_on: string[];
  }[];
};
export const saveSchedule = (
  business: string,
  project: string,
  body: ScheduleBody,
) =>
  command<Schedule>(`${projectPath(business, project)}/schedule`, "PUT", body);

export const fetchDailyReports = (business: string, project: string) =>
  managementFetch<DailyReportList>(
    `${projectPath(business, project)}/daily-reports`,
  ).then((list) => list.items);
/** The report of a site date, or null while there is none. */
export async function fetchDailyReport(
  business: string,
  project: string,
  date: string,
): Promise<DailyReport | null> {
  try {
    return await managementFetch<DailyReport>(
      `${projectPath(business, project)}/daily-reports/${date}`,
    );
  } catch (error) {
    if (error instanceof ManagementApiError && error.code === "NOT_FOUND")
      return null;
    throw error;
  }
}
export type DailyReportBody = {
  schema_version: 1;
  expected_revision: number;
  weather: string | null;
  notes: string | null;
  crew: { label: string; headcount: number; counterparty_id: null }[];
  photos: { document_id: string; revision: number }[];
};
export const saveDailyReport = (
  business: string,
  project: string,
  date: string,
  body: DailyReportBody,
) =>
  command<DailyReport>(
    `${projectPath(business, project)}/daily-reports/${date}`,
    "PUT",
    body,
  );

export const fetchProgress = (business: string, project: string) =>
  managementFetch<Progress>(`${projectPath(business, project)}/progress`);
export const fetchMeasurements = (business: string, project: string) =>
  managementFetch<{ items: Measurement[] }>(
    `${projectPath(business, project)}/progress/measurements`,
  ).then((list) => list.items);
export type MeasurementBody = {
  schema_version: 1;
  change_order: number | null;
  position: number;
  measured_on: string;
  quantity_to_date: string;
  note: string | null;
};
export const recordMeasurement = (
  business: string,
  project: string,
  body: MeasurementBody,
) =>
  command<Measurement>(
    `${projectPath(business, project)}/progress`,
    "POST",
    body,
  );
