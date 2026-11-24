// PRO-01 Slice 5 (ADR-0038): strict Zod contracts and role gates for /projects/.
import { z } from "zod";
export type MembershipSummary = {
  salon_id?: string;
  salon_slug?: string | null;
  salon_name?: string | null;
  role: string;
  status?: string;
  location_id?: string | null;
  delegation?: unknown;
  delegated?: boolean;
};

export const MatterKindSchema = z.enum([
  "legal_case",
  "project",
  "recurring_engagement",
]);
export type MatterKind = z.infer<typeof MatterKindSchema>;

export const MatterStatusSchema = z.enum([
  "intake",
  "conflict_check",
  "active",
  "on_hold",
  "closed",
  "cancelled",
]);
export type MatterStatus = z.infer<typeof MatterStatusSchema>;

export const MatterAccessModeSchema = z.enum(["branch", "restricted"]);
export type MatterAccessMode = z.infer<typeof MatterAccessModeSchema>;

export const MatterRoleSchema = z.enum([
  "lead",
  "contributor",
  "viewer",
  "billing",
]);
export type MatterRole = z.infer<typeof MatterRoleSchema>;

export const ConflictDecisionSchema = z.enum(["clear", "waived", "blocked"]);
export type ConflictDecision = z.infer<typeof ConflictDecisionSchema>;

export const StageStatusSchema = z.enum([
  "open",
  "submitted",
  "accepted",
  "rejected",
]);
export type StageStatus = z.infer<typeof StageStatusSchema>;

export const TaskPrioritySchema = z.enum(["low", "normal", "high", "urgent"]);
export type TaskPriority = z.infer<typeof TaskPrioritySchema>;

export const TaskStatusSchema = z.enum([
  "todo",
  "in_progress",
  "blocked",
  "done",
  "cancelled",
]);
export type TaskStatus = z.infer<typeof TaskStatusSchema>;

export const FileCategorySchema = z.enum([
  "pleading",
  "contract",
  "evidence",
  "deliverable",
  "correspondence",
  "other",
]);
export type FileCategory = z.infer<typeof FileCategorySchema>;

export const TimeEntryStatusSchema = z.enum([
  "draft",
  "submitted",
  "approved",
  "billed",
  "rejected",
]);
export type TimeEntryStatus = z.infer<typeof TimeEntryStatusSchema>;

export const RecurringCadenceSchema = z.enum([
  "weekly",
  "biweekly",
  "monthly",
  "quarterly",
]);
export type RecurringCadence = z.infer<typeof RecurringCadenceSchema>;

export const RecurringStatusSchema = z.enum(["active", "paused", "ended"]);
export type RecurringStatus = z.infer<typeof RecurringStatusSchema>;

export const MatterViewSchema = z
  .object({
    schema_version: z.literal(1),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    title: z.string(),
    description: z.string().nullable(),
    kind: MatterKindSchema,
    status: MatterStatusSchema,
    access_mode: MatterAccessModeSchema,
    client_counterparty_id: z.string().uuid(),
    currency: z.string().regex(/^[A-Z]{3}$/),
    budget_minor: z.number().int().nullable(),
    opened_on: z.string(),
    due_on: z.string().nullable(),
    closed_at: z.string().nullable(),
    revision: z.number().int().min(1),
    created_by: z.string().uuid(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type MatterView = z.infer<typeof MatterViewSchema>;

export const MatterListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(MatterViewSchema),
    next_after: z.string().uuid().nullable().optional(),
  })
  .strict();

export const ConflictCheckViewSchema = z
  .object({
    schema_version: z.literal(1),
    conflict_check_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    checked_parties: z.string(),
    decision: ConflictDecisionSchema,
    rationale: z.string(),
    decided_by: z.string().uuid(),
    decided_at: z.string(),
  })
  .strict();
export type ConflictCheckView = z.infer<typeof ConflictCheckViewSchema>;

export const ConflictCheckListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(ConflictCheckViewSchema),
  })
  .strict();

export const MatterMemberViewSchema = z
  .object({
    schema_version: z.literal(1),
    member_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    user_id: z.string().uuid(),
    matter_role: MatterRoleSchema,
    granted_by: z.string().uuid(),
    granted_at: z.string(),
    revoked_by: z.string().uuid().nullable(),
    revoked_at: z.string().nullable(),
  })
  .strict();
export type MatterMemberView = z.infer<typeof MatterMemberViewSchema>;

export const MatterMemberListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(MatterMemberViewSchema),
  })
  .strict();

export const StageViewSchema = z
  .object({
    schema_version: z.literal(1),
    stage_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    stage_no: z.number().int().min(1),
    title: z.string(),
    description: z.string().nullable(),
    due_on: z.string().nullable(),
    fixed_fee_minor: z.number().int().nullable(),
    deliverable_summary: z.string().nullable(),
    deliverable_revision: z.number().int().min(0),
    status: StageStatusSchema,
    decided_by: z.string().uuid().nullable(),
    decided_at: z.string().nullable(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type StageView = z.infer<typeof StageViewSchema>;

export const StageListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(StageViewSchema),
  })
  .strict();

export const TaskViewSchema = z
  .object({
    schema_version: z.literal(1),
    task_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    stage_id: z.string().uuid().nullable(),
    title: z.string(),
    description: z.string().nullable(),
    assignee_user_id: z.string().uuid().nullable(),
    priority: TaskPrioritySchema,
    status: TaskStatusSchema,
    due_on: z.string().nullable(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type TaskView = z.infer<typeof TaskViewSchema>;

export const TaskListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(TaskViewSchema),
    next_after: z.string().uuid().nullable().optional(),
  })
  .strict();

export const TaskDependencyViewSchema = z
  .object({
    schema_version: z.literal(1),
    matter_id: z.string().uuid(),
    task_id: z.string().uuid(),
    depends_on_task_id: z.string().uuid(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type TaskDependencyView = z.infer<typeof TaskDependencyViewSchema>;

export const TaskDependencyListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(TaskDependencyViewSchema),
  })
  .strict();

export const MatterFileViewSchema = z
  .object({
    schema_version: z.literal(1),
    file_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    stage_id: z.string().uuid().nullable(),
    task_id: z.string().uuid().nullable(),
    linked_document_id: z.string().uuid().nullable(),
    category: FileCategorySchema,
    title: z.string(),
    file_name: z.string(),
    media_type: z.enum(["application/pdf", "image/png", "image/jpeg"]),
    byte_size: z.number().int().min(1),
    sha256: z.string(),
    uploaded_by: z.string().uuid(),
    uploaded_at: z.string(),
  })
  .strict();
export type MatterFileView = z.infer<typeof MatterFileViewSchema>;

export const MatterFileListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(MatterFileViewSchema),
  })
  .strict();

export const SearchHitSchema = z
  .object({
    entity_type: z.enum(["matter", "stage", "task", "file"]),
    entity_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    title: z.string(),
    subtitle: z.string().nullable().optional(),
  })
  .strict();
export type SearchHit = z.infer<typeof SearchHitSchema>;

export const ProjectSearchResultSchema = z
  .object({
    schema_version: z.literal(1),
    query: z.string(),
    matters: z.array(SearchHitSchema),
    stages: z.array(SearchHitSchema),
    tasks: z.array(SearchHitSchema),
    files: z.array(SearchHitSchema),
  })
  .strict();
export type ProjectSearchResult = z.infer<typeof ProjectSearchResultSchema>;

export const TimeEntryViewSchema = z
  .object({
    schema_version: z.literal(1),
    time_entry_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    stage_id: z.string().uuid().nullable(),
    task_id: z.string().uuid().nullable(),
    staff_user_id: z.string().uuid(),
    work_date: z.string(),
    duration_minutes: z.number().int().min(1),
    hourly_rate_minor: z.number().int().min(0),
    currency: z.string(),
    billable: z.boolean(),
    amount_minor: z.number().int().min(0),
    description: z.string(),
    status: TimeEntryStatusSchema,
    decided_by: z.string().uuid().nullable(),
    decided_at: z.string().nullable(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type TimeEntryView = z.infer<typeof TimeEntryViewSchema>;

export const TimeEntryListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(TimeEntryViewSchema),
    next_after: z.string().uuid().nullable().optional(),
  })
  .strict();

export const RecurringScheduleViewSchema = z
  .object({
    schema_version: z.literal(1),
    schedule_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    title: z.string(),
    task_template_title: z.string(),
    task_template_description: z.string().nullable(),
    default_assignee_user_id: z.string().uuid().nullable(),
    cadence: RecurringCadenceSchema,
    next_run_date: z.string(),
    fixed_fee_minor: z.number().int().min(0),
    currency: z.string(),
    status: RecurringStatusSchema,
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type RecurringScheduleView = z.infer<typeof RecurringScheduleViewSchema>;

export const RecurringScheduleListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(RecurringScheduleViewSchema),
  })
  .strict();

export const RecurringRunViewSchema = z
  .object({
    schema_version: z.literal(1),
    run_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    schedule_id: z.string().uuid(),
    period_start: z.string(),
    period_end: z.string(),
    task_id: z.string().uuid(),
    fee_minor: z.number().int().min(0),
    currency: z.string(),
    billing_status: z.enum(["unbilled", "billed"]),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type RecurringRunView = z.infer<typeof RecurringRunViewSchema>;

export const RecurringRunListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(RecurringRunViewSchema),
  })
  .strict();

export const MatterInvoiceItemViewSchema = z
  .object({
    schema_version: z.literal(1),
    item_id: z.string().uuid(),
    matter_invoice_id: z.string().uuid(),
    item_kind: z.enum(["time_entry", "stage_fee", "recurring_run"]),
    time_entry_id: z.string().uuid().nullable(),
    stage_id: z.string().uuid().nullable(),
    recurring_run_id: z.string().uuid().nullable(),
    description: z.string(),
    amount_minor: z.number().int().min(1),
    currency: z.string(),
  })
  .strict();

export const MatterInvoiceViewSchema = z
  .object({
    schema_version: z.literal(1),
    matter_invoice_id: z.string().uuid(),
    matter_id: z.string().uuid(),
    location_id: z.string().uuid(),
    book_id: z.string().uuid(),
    invoice_document_id: z.string().uuid(),
    counterparty_id: z.string().uuid(),
    total_minor: z.number().int().min(1),
    currency: z.string(),
    title: z.string(),
    number: z.string().nullable(),
    invoice_date: z.string(),
    due_date: z.string(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
    items: z.array(MatterInvoiceItemViewSchema),
  })
  .strict();
export type MatterInvoiceView = z.infer<typeof MatterInvoiceViewSchema>;

export const MatterInvoiceListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(MatterInvoiceViewSchema),
  })
  .strict();

export const ProjectExportRecordSchema = z
  .object({
    schema_version: z.literal(1),
    export_id: z.string().uuid(),
    location_id: z.string().uuid(),
    scope: z.enum(["matter", "portfolio"]),
    matter_id: z.string().uuid().nullable(),
    requested_by: z.string().uuid(),
    matter_count: z.number().int().min(0),
    stage_count: z.number().int().min(0),
    task_count: z.number().int().min(0),
    file_count: z.number().int().min(0),
    time_entry_count: z.number().int().min(0),
    recurring_run_count: z.number().int().min(0),
    invoice_count: z.number().int().min(0),
    recorded_at: z.string(),
  })
  .strict();
export type ProjectExportRecord = z.infer<typeof ProjectExportRecordSchema>;

export const ProjectExportListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(ProjectExportRecordSchema),
  })
  .strict();

export const MatterExportBundleSchema = z
  .object({
    matter: MatterViewSchema,
    conflict_checks: z.array(ConflictCheckViewSchema),
    stages: z.array(StageViewSchema),
    tasks: z.array(TaskViewSchema),
    files: z.array(MatterFileViewSchema),
    time_entries: z.array(TimeEntryViewSchema),
    recurring_schedules: z.array(RecurringScheduleViewSchema),
    recurring_runs: z.array(RecurringRunViewSchema),
    invoices: z.array(MatterInvoiceViewSchema),
  })
  .strict();

export const MatterExportPayloadSchema = z
  .object({
    schema_version: z.literal(1),
    export: ProjectExportRecordSchema,
    bundle: MatterExportBundleSchema,
  })
  .strict();
export type MatterExportPayload = z.infer<typeof MatterExportPayloadSchema>;

export const PortfolioExportPayloadSchema = z
  .object({
    schema_version: z.literal(1),
    export: ProjectExportRecordSchema,
    matters: z.array(MatterExportBundleSchema),
  })
  .strict();
export type PortfolioExportPayload = z.infer<
  typeof PortfolioExportPayloadSchema
>;

export function canReadProjects(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation))
    return false;
  return ["owner", "manager", "front_desk", "artist"].includes(member.role);
}

export function canWorkProjects(
  member: MembershipSummary | undefined,
): boolean {
  return canReadProjects(member);
}

export function canManageProjects(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation))
    return false;
  return member.role === "owner" || member.role === "manager";
}

export function canBillProjects(
  member: MembershipSummary | undefined,
): boolean {
  return canManageProjects(member) && member?.location_id === null;
}

export function formatMinor(minor: number, currency: string): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${sign}${whole}.${frac} ${currency}`;
}

export function parseMajorToMinor(input: string): number | null {
  const trimmed = input.trim();
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  const [whole, frac = ""] = trimmed.split(".");
  return Number(whole) * 100 + Number(frac.padEnd(2, "0"));
}

const UUID_RE = "[0-9a-f-]{36}";

export function projectsResponseSchema(
  subpath: string,
  method: string,
): z.ZodType | null {
  const path = subpath.split("?")[0] ?? "";
  if (!path.startsWith("/projects/")) return null;
  const rest = path.slice("/projects".length);

  if (rest === "/search" && method === "GET") return ProjectSearchResultSchema;
  if (rest === "/matters" && method === "GET") return MatterListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return MatterViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/conflict-checks$`, "i").test(rest) &&
    method === "GET"
  )
    return ConflictCheckListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/conflict-checks$`, "i").test(rest) &&
    method === "POST"
  )
    return ConflictCheckViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/members$`, "i").test(rest) &&
    method === "GET"
  )
    return MatterMemberListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/members$`, "i").test(rest) &&
    method === "POST"
  )
    return MatterMemberViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/members/${UUID_RE}/revoke$`, "i").test(
      rest,
    ) &&
    method === "POST"
  )
    return MatterMemberViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/stages$`, "i").test(rest) &&
    method === "GET"
  )
    return StageListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/stages/${UUID_RE}$`, "i").test(rest) &&
    method === "PUT"
  )
    return StageViewSchema;
  if (
    new RegExp(
      `^/matters/${UUID_RE}/stages/${UUID_RE}/(submit|decision)$`,
      "i",
    ).test(rest) &&
    method === "POST"
  )
    return StageViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/tasks$`, "i").test(rest) &&
    method === "GET"
  )
    return TaskListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/tasks/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return TaskViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/tasks/${UUID_RE}/dependencies$`, "i").test(
      rest,
    ) &&
    method === "GET"
  )
    return TaskDependencyListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/tasks/${UUID_RE}/dependencies$`, "i").test(
      rest,
    ) &&
    method === "POST"
  )
    return TaskDependencyViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/files$`, "i").test(rest) &&
    method === "GET"
  )
    return MatterFileListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/time-entries$`, "i").test(rest) &&
    method === "GET"
  )
    return TimeEntryListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/time-entries/${UUID_RE}$`, "i").test(
      rest,
    ) &&
    method === "PUT"
  )
    return TimeEntryViewSchema;
  if (
    new RegExp(
      `^/matters/${UUID_RE}/time-entries/${UUID_RE}/decision$`,
      "i",
    ).test(rest) &&
    method === "POST"
  )
    return TimeEntryViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/recurring-schedules$`, "i").test(rest) &&
    method === "GET"
  )
    return RecurringScheduleListSchema;
  if (
    new RegExp(
      `^/matters/${UUID_RE}/recurring-schedules/${UUID_RE}$`,
      "i",
    ).test(rest) &&
    method === "PUT"
  )
    return RecurringScheduleViewSchema;
  if (
    new RegExp(
      `^/matters/${UUID_RE}/recurring-schedules/${UUID_RE}/run$`,
      "i",
    ).test(rest) &&
    method === "POST"
  )
    return RecurringRunViewSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/recurring-runs$`, "i").test(rest) &&
    method === "GET"
  )
    return RecurringRunListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/invoices$`, "i").test(rest) &&
    method === "GET"
  )
    return MatterInvoiceListSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/invoices$`, "i").test(rest) &&
    method === "POST"
  )
    return MatterInvoiceViewSchema;
  if (rest === "/exports" && method === "GET") return ProjectExportListSchema;
  if (rest === "/exports" && method === "POST")
    return PortfolioExportPayloadSchema;
  if (
    new RegExp(`^/matters/${UUID_RE}/exports$`, "i").test(rest) &&
    method === "POST"
  )
    return MatterExportPayloadSchema;
  return null;
}
