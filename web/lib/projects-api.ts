// PRO-01 Slice 5: typed client for /projects/ with Idempotency-Key commands and file uploads.
import {
  ManagementApiError,
  authorizedResponse,
  managementFetch,
} from "./management-api";
import {
  ConflictCheckListSchema,
  ConflictCheckViewSchema,
  MatterExportPayloadSchema,
  MatterFileListSchema,
  MatterFileViewSchema,
  MatterInvoiceListSchema,
  MatterInvoiceViewSchema,
  MatterListSchema,
  MatterMemberListSchema,
  MatterMemberViewSchema,
  MatterViewSchema,
  PortfolioExportPayloadSchema,
  ProjectExportListSchema,
  ProjectSearchResultSchema,
  RecurringRunListSchema,
  RecurringRunViewSchema,
  RecurringScheduleListSchema,
  RecurringScheduleViewSchema,
  StageListSchema,
  StageViewSchema,
  TaskListSchema,
  TaskViewSchema,
  TimeEntryListSchema,
  TimeEntryViewSchema,
  type ConflictCheckView,
  type ConflictDecision,
  type FileCategory,
  type MatterAccessMode,
  type MatterExportPayload,
  type MatterFileView,
  type MatterInvoiceView,
  type MatterKind,
  type MatterMemberView,
  type MatterRole,
  type MatterStatus,
  type MatterView,
  type PortfolioExportPayload,
  type ProjectExportRecord,
  type ProjectSearchResult,
  type RecurringCadence,
  type RecurringRunView,
  type RecurringScheduleView,
  type RecurringStatus,
  type StageView,
  type TaskPriority,
  type TaskStatus,
  type TaskView,
  type TimeEntryView,
} from "./projects-contracts";

const root = (business: string) => `/v1/businesses/${business}/projects`;

export function projectsError(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export async function fetchMatters(business: string): Promise<MatterView[]> {
  const all: MatterView[] = [];
  let after = "";
  for (;;) {
    const raw = await managementFetch<unknown>(
      after
        ? `${root(business)}/matters?after=${encodeURIComponent(after)}`
        : `${root(business)}/matters`,
    );
    const page = MatterListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function saveMatter(
  business: string,
  matterId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    title: string;
    description?: string | null;
    kind: MatterKind;
    status: MatterStatus;
    access_mode: MatterAccessMode;
    client_counterparty_id: string;
    currency: string;
    budget_minor?: number | null;
    opened_on: string;
    due_on?: string | null;
  },
): Promise<MatterView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return MatterViewSchema.parse(raw);
}

export async function fetchConflictChecks(
  business: string,
  matterId: string,
): Promise<ConflictCheckView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/conflict-checks`,
  );
  return ConflictCheckListSchema.parse(raw).items;
}

export async function recordConflictCheck(
  business: string,
  matterId: string,
  key: string,
  body: {
    checked_parties: string;
    decision: ConflictDecision;
    rationale: string;
  },
): Promise<ConflictCheckView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/conflict-checks`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return ConflictCheckViewSchema.parse(raw);
}

export async function fetchMatterMembers(
  business: string,
  matterId: string,
): Promise<MatterMemberView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/members`,
  );
  return MatterMemberListSchema.parse(raw).items;
}

export async function grantMatterMember(
  business: string,
  matterId: string,
  key: string,
  body: { user_id: string; matter_role: MatterRole },
): Promise<MatterMemberView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/members`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return MatterMemberViewSchema.parse(raw);
}

export async function revokeMatterMember(
  business: string,
  matterId: string,
  memberId: string,
  key: string,
): Promise<MatterMemberView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/members/${memberId}/revoke`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
    },
  );
  return MatterMemberViewSchema.parse(raw);
}

export async function searchProjects(
  business: string,
  query: string,
): Promise<ProjectSearchResult> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/search?q=${encodeURIComponent(query)}`,
  );
  return ProjectSearchResultSchema.parse(raw);
}

export async function fetchStages(
  business: string,
  matterId: string,
): Promise<StageView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/stages`,
  );
  return StageListSchema.parse(raw).items;
}

export async function saveStage(
  business: string,
  matterId: string,
  stageId: string,
  key: string,
  body: {
    expected_revision: number;
    stage_no: number;
    title: string;
    fixed_fee_minor?: number | null;
  },
): Promise<StageView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/stages/${stageId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return StageViewSchema.parse(raw);
}

export async function submitStage(
  business: string,
  matterId: string,
  stageId: string,
  key: string,
  body: { expected_revision: number; deliverable_summary: string },
): Promise<StageView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/stages/${stageId}/submit`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return StageViewSchema.parse(raw);
}

export async function decideStage(
  business: string,
  matterId: string,
  stageId: string,
  key: string,
  body: { expected_revision: number; decision: "accept" | "reject" },
): Promise<StageView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/stages/${stageId}/decision`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return StageViewSchema.parse(raw);
}

export async function fetchTasks(
  business: string,
  matterId: string,
): Promise<TaskView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/tasks?limit=100`,
  );
  return TaskListSchema.parse(raw).items;
}

export async function saveTask(
  business: string,
  matterId: string,
  taskId: string,
  key: string,
  body: {
    expected_revision: number;
    stage_id?: string | null;
    title: string;
    priority: TaskPriority;
    status: TaskStatus;
  },
): Promise<TaskView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/tasks/${taskId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return TaskViewSchema.parse(raw);
}

export async function fetchMatterFiles(
  business: string,
  matterId: string,
): Promise<MatterFileView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/files`,
  );
  return MatterFileListSchema.parse(raw).items;
}

export async function uploadMatterFile(
  business: string,
  matterId: string,
  fileId: string,
  key: string,
  params: {
    title: string;
    category: FileCategory;
    fileName: string;
    mediaType: "application/pdf" | "image/png" | "image/jpeg";
    bytes: Uint8Array;
  },
): Promise<MatterFileView> {
  const qs = new URLSearchParams({
    title: params.title,
    category: params.category,
  });
  const response = await authorizedResponse(
    `${root(business)}/matters/${matterId}/files/${fileId}?${qs.toString()}`,
    {
      method: "PUT",
      body: new Blob([new Uint8Array(params.bytes)], {
        type: params.mediaType,
      }),
      headers: {
        "Content-Type": params.mediaType,
        "X-File-Name": encodeURIComponent(params.fileName),
        "Idempotency-Key": key,
      },
    },
    60000,
  );
  const raw: unknown = await response.json();
  return MatterFileViewSchema.parse(raw);
}

export async function fetchTimeEntries(
  business: string,
  matterId: string,
): Promise<TimeEntryView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/time-entries?limit=100`,
  );
  return TimeEntryListSchema.parse(raw).items;
}

export async function saveTimeEntry(
  business: string,
  matterId: string,
  timeEntryId: string,
  key: string,
  body: {
    expected_revision: number;
    work_date: string;
    duration_minutes: number;
    hourly_rate_minor: number;
    billable: boolean;
    description: string;
    submit: boolean;
  },
): Promise<TimeEntryView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/time-entries/${timeEntryId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return TimeEntryViewSchema.parse(raw);
}

export async function decideTimeEntry(
  business: string,
  matterId: string,
  timeEntryId: string,
  key: string,
  body: { expected_revision: number; decision: "approve" | "reject" },
): Promise<TimeEntryView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/time-entries/${timeEntryId}/decision`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return TimeEntryViewSchema.parse(raw);
}

export async function fetchRecurringSchedules(
  business: string,
  matterId: string,
): Promise<RecurringScheduleView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/recurring-schedules`,
  );
  return RecurringScheduleListSchema.parse(raw).items;
}

export async function saveRecurringSchedule(
  business: string,
  matterId: string,
  scheduleId: string,
  key: string,
  body: {
    expected_revision: number;
    title: string;
    task_template_title: string;
    cadence: RecurringCadence;
    next_run_date: string;
    fixed_fee_minor: number;
    status: RecurringStatus;
  },
): Promise<RecurringScheduleView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/recurring-schedules/${scheduleId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return RecurringScheduleViewSchema.parse(raw);
}

export async function fetchRecurringRuns(
  business: string,
  matterId: string,
): Promise<RecurringRunView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/recurring-runs`,
  );
  return RecurringRunListSchema.parse(raw).items;
}

export async function triggerRecurringRun(
  business: string,
  matterId: string,
  scheduleId: string,
  key: string,
  expectedRevision: number,
): Promise<RecurringRunView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/recurring-schedules/${scheduleId}/run`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({
        schema_version: 1,
        expected_revision: expectedRevision,
      }),
    },
  );
  return RecurringRunViewSchema.parse(raw);
}

export async function fetchMatterInvoices(
  business: string,
  matterId: string,
): Promise<MatterInvoiceView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/invoices`,
  );
  return MatterInvoiceListSchema.parse(raw).items;
}

export async function createMatterInvoice(
  business: string,
  matterId: string,
  key: string,
  body: {
    book_id: string;
    receivable_account_id: string;
    revenue_account_id: string;
    invoice_date: string;
    due_date: string;
    title: string;
    number?: string | null;
    time_entry_ids: string[];
    stage_ids: string[];
    recurring_run_ids: string[];
  },
): Promise<MatterInvoiceView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/invoices`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return MatterInvoiceViewSchema.parse(raw);
}

export async function fetchExports(
  business: string,
): Promise<ProjectExportRecord[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/exports`);
  return ProjectExportListSchema.parse(raw).items;
}

export async function runMatterExport(
  business: string,
  matterId: string,
  key: string,
): Promise<MatterExportPayload> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/matters/${matterId}/exports`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
    },
  );
  return MatterExportPayloadSchema.parse(raw);
}

export async function runPortfolioExport(
  business: string,
  locationId: string,
  key: string,
): Promise<PortfolioExportPayload> {
  const raw = await managementFetch<unknown>(`${root(business)}/exports`, {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({ schema_version: 1, location_id: locationId }),
  });
  return PortfolioExportPayloadSchema.parse(raw);
}
