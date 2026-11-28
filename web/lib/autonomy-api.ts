import { z } from "zod";
import { aiEngineSchema } from "./growth-api";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const autonomyLevelSchema = z.enum([
  "observe_only",
  "safe_autopilot",
  "strict_approval",
]);
export type AutonomyLevel = z.infer<typeof autonomyLevelSchema>;

export const briefWeekdaySchema = z.enum([
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
]);
export type BriefWeekday = z.infer<typeof briefWeekdaySchema>;

export const autonomyPolicySchema = z.object({
  autonomy_level: autonomyLevelSchema,
  auto_confirm_open_bookings: z.boolean(),
  auto_send_invoice_reminders: z.boolean(),
  auto_offer_waitlist_slots: z.boolean(),
  auto_send_weekly_brief: z.boolean(),
  weekly_brief_day: briefWeekdaySchema,
  weekly_brief_email: z.string().nullable().optional(),
  require_human_approval_over_cents: z.number().int(),
  updated_at: z.string().nullable().optional(),
});
export type AutonomyPolicy = z.infer<typeof autonomyPolicySchema>;

export const autonomyExecutionSchema = z.object({
  id: z.string(),
  action_kind: z.enum([
    "send_invoice_reminder",
    "offer_waitlist_slot",
    "confirm_open_booking",
    "dispatch_weekly_brief",
    "financial_proposal_blocked",
  ]),
  execution_mode: z.enum([
    "autonomous_safe",
    "human_approved",
    "queued_for_approval",
    "blocked_by_policy",
  ]),
  target_reference: z.string(),
  summary: z.string(),
  details: z.record(z.string(), z.unknown()),
  status: z.enum([
    "completed",
    "pending_approval",
    "rejected",
    "rolled_back",
    "failed",
  ]),
  created_at: z.string(),
  resolved_at: z.string().nullable().optional(),
});
export type AutonomyExecution = z.infer<typeof autonomyExecutionSchema>;

export const predictiveSignalSchema = z.object({
  severity: z.enum(["critical", "high", "medium", "positive"]),
  category: z.string(),
  title: z.string(),
  metric_label: z.string(),
  recommendation: z.string(),
  action_path: z.string(),
});
export type PredictiveSignal = z.infer<typeof predictiveSignalSchema>;

export const predictiveReportSchema = z.object({
  id: z.string(),
  period_days: z.number().int(),
  engine: aiEngineSchema,
  headline: z.string(),
  executive_summary: z.string(),
  health_score: z.number().int(),
  signals: z.array(predictiveSignalSchema),
  metrics_snapshot: z.record(z.string(), z.unknown()),
  emailed_to_masked: z.string().nullable().optional(),
  created_at: z.string(),
});
export type PredictiveReport = z.infer<typeof predictiveReportSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/ai-autonomy`;
}

async function readJson<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  let data: unknown;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "AMARKAL AI Autonomy returned incomplete data. Please retry.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchAutonomyPolicy(
  businessId: string,
): Promise<AutonomyPolicy> {
  const res = await authorizedResponse(`${base(businessId)}/policy`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, autonomyPolicySchema);
}

export async function saveAutonomyPolicy(
  businessId: string,
  input: {
    autonomy_level: AutonomyLevel;
    auto_confirm_open_bookings: boolean;
    auto_send_invoice_reminders: boolean;
    auto_offer_waitlist_slots: boolean;
    auto_send_weekly_brief: boolean;
    weekly_brief_day: BriefWeekday;
    weekly_brief_email?: string | null;
  },
): Promise<AutonomyPolicy> {
  const res = await authorizedResponse(`${base(businessId)}/policy`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, autonomyPolicySchema);
}

export async function fetchAutonomyExecutions(
  businessId: string,
): Promise<AutonomyExecution[]> {
  const res = await authorizedResponse(`${base(businessId)}/executions`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(autonomyExecutionSchema));
}

export async function runSafeAutonomyCycle(
  businessId: string,
): Promise<AutonomyExecution[]> {
  const res = await authorizedResponse(`${base(businessId)}/run-cycle`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(autonomyExecutionSchema));
}

export async function decideAutonomyExecution(
  businessId: string,
  executionId: string,
  decision: "approve" | "reject" | "rollback",
): Promise<AutonomyExecution> {
  const res = await authorizedResponse(
    `${base(businessId)}/executions/${encodeURIComponent(executionId)}/decision`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ decision }),
    },
  );
  return readJson(res, autonomyExecutionSchema);
}

export async function fetchPredictiveReports(
  businessId: string,
): Promise<PredictiveReport[]> {
  const res = await authorizedResponse(
    `${base(businessId)}/predictive-reports`,
    {
      headers: { Accept: "application/json" },
    },
  );
  return readJson(res, z.array(predictiveReportSchema));
}

export async function generatePredictiveReport(
  businessId: string,
  input: {
    period_days?: number;
    send_email?: boolean;
    recipient_email?: string;
    webhook_url?: string;
    broadcast_to_webhooks?: boolean;
  } = {},
): Promise<PredictiveReport> {
  const res = await authorizedResponse(
    `${base(businessId)}/predictive-reports/generate`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        period_days: input.period_days ?? 30,
        send_email: input.send_email ?? false,
        recipient_email: input.recipient_email || undefined,
        webhook_url: input.webhook_url || undefined,
        broadcast_to_webhooks: input.broadcast_to_webhooks ?? false,
      }),
    },
  );
  return readJson(res, predictiveReportSchema);
}
