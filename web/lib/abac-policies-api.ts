import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const baseRoleSchema = z.enum([
  "artist",
  "front_desk",
  "manager",
  "owner",
]);
export type BaseRole = z.infer<typeof baseRoleSchema>;

export const abacPolicyViewSchema = z.object({
  id: z.string(),
  policy_code: z.string(),
  display_name: z.string(),
  description: z.string(),
  base_role: baseRoleSchema,
  is_active: z.boolean(),
  denied_permissions: z.array(z.string()),
  allowed_regions: z.array(z.string()),
  masked_fields: z.array(z.string()),
  write_window_enabled: z.boolean(),
  write_window_timezone: z.string(),
  write_window_start_minute: z.number().int(),
  write_window_end_minute: z.number().int(),
  write_window_days: z.array(z.number().int()),
  write_window_permissions: z.array(z.string()),
  write_window_summary: z.string(),
  max_financial_amount_cents: z.number().int().nullable(),
  assigned_member_count: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type AbacPolicyView = z.infer<typeof abacPolicyViewSchema>;

export const abacAssignmentViewSchema = z.object({
  id: z.string(),
  policy_id: z.string(),
  policy_code: z.string(),
  policy_name: z.string(),
  user_id: z.string(),
  member_name: z.string(),
  member_email_masked: z.string().nullable(),
  member_role: z.string(),
  assigned_regions_override: z.array(z.string()),
  is_active: z.boolean(),
  assigned_at: z.string(),
});
export type AbacAssignmentView = z.infer<typeof abacAssignmentViewSchema>;

export const abacMemberSummarySchema = z.object({
  user_id: z.string(),
  display_name: z.string(),
  email_masked: z.string().nullable(),
  role: z.string(),
  location_id: z.string().nullable(),
});
export type AbacMemberSummary = z.infer<typeof abacMemberSummarySchema>;

export const abacPresetTemplateSchema = z.object({
  policy_code: z.string(),
  display_name: z.string(),
  description: z.string(),
  base_role: baseRoleSchema,
  denied_permissions: z.array(z.string()),
  allowed_regions: z.array(z.string()),
  masked_fields: z.array(z.string()),
  write_window_enabled: z.boolean(),
  write_window_timezone: z.string(),
  write_window_start_minute: z.number().int(),
  write_window_end_minute: z.number().int(),
  write_window_days: z.array(z.number().int()),
  write_window_permissions: z.array(z.string()),
  max_financial_amount_cents: z.number().int().nullable(),
  installed: z.boolean(),
});
export type AbacPresetTemplate = z.infer<typeof abacPresetTemplateSchema>;

export const abacRoleCeilingSchema = z.object({
  role: baseRoleSchema,
  permission_count: z.number().int(),
  sample_permissions: z.array(z.string()),
});
export type AbacRoleCeiling = z.infer<typeof abacRoleCeilingSchema>;

export const abacOverviewResponseSchema = z.object({
  policies: z.array(abacPolicyViewSchema),
  assignments: z.array(abacAssignmentViewSchema),
  members: z.array(abacMemberSummarySchema),
  presets: z.array(abacPresetTemplateSchema),
  role_ceilings: z.array(abacRoleCeilingSchema),
  available_permissions: z.array(z.string()),
  available_masked_fields: z.array(z.string()),
});
export type AbacOverviewResponse = z.infer<typeof abacOverviewResponseSchema>;

export const simulateAbacResponseSchema = z.object({
  policy_code: z.string(),
  base_role: baseRoleSchema,
  base_role_allows: z.boolean(),
  allowed: z.boolean(),
  blocked_by: z.string().nullable(),
  reason: z.string(),
  evaluated_local_time: z.string(),
  masked_fields: z.array(z.string()),
  effective_regions: z.array(z.string()),
  max_financial_amount_cents: z.number().int().nullable(),
  raw_preview: z.record(z.string(), z.unknown()),
  masked_preview: z.record(z.string(), z.unknown()),
});
export type SimulateAbacResponse = z.infer<typeof simulateAbacResponseSchema>;

async function parseOrThrow<T>(
  res: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = (await res.json()) as {
        detail?: unknown;
        message?: unknown;
      };
      if (typeof data.detail === "string") detail = data.detail;
      else if (typeof data.message === "string") detail = data.message;
    } catch {
      // Ignore non-JSON error body
    }
    throw new ManagementApiError("REQUEST_FAILED", detail, res.status);
  }
  const raw: unknown = await res.json();
  return schema.parse(raw);
}

export async function fetchAbacOverview(
  businessId: string,
): Promise<AbacOverviewResponse> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/overview`,
    { method: "GET" },
  );
  return parseOrThrow(res, abacOverviewResponseSchema);
}

export interface CreateAbacPolicyInput {
  policy_code: string;
  display_name: string;
  description: string;
  base_role: BaseRole;
  is_active: boolean;
  denied_permissions: string[];
  allowed_regions: string[];
  masked_fields: string[];
  write_window_enabled: boolean;
  write_window_timezone: string;
  write_window_start_minute: number;
  write_window_end_minute: number;
  write_window_days: number[];
  write_window_permissions: string[];
  max_financial_amount_cents: number | null;
}

export async function createAbacPolicy(
  businessId: string,
  payload: CreateAbacPolicyInput,
): Promise<AbacPolicyView> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/policies`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseOrThrow(res, abacPolicyViewSchema);
}

export async function installAbacPreset(
  businessId: string,
  presetCode: string,
): Promise<AbacPolicyView> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/presets/${encodeURIComponent(presetCode)}`,
    { method: "POST" },
  );
  return parseOrThrow(res, abacPolicyViewSchema);
}

export async function toggleAbacPolicyActive(
  businessId: string,
  policyId: string,
  isActive: boolean,
): Promise<AbacPolicyView> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/policies/${encodeURIComponent(policyId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: isActive }),
    },
  );
  return parseOrThrow(res, abacPolicyViewSchema);
}

export async function deleteAbacPolicy(
  businessId: string,
  policyId: string,
): Promise<void> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/policies/${encodeURIComponent(policyId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    throw new ManagementApiError(
      "REQUEST_FAILED",
      `Failed to delete policy (${res.status})`,
      res.status,
    );
  }
}

export async function assignAbacPolicy(
  businessId: string,
  payload: {
    policy_id: string;
    user_id: string;
    assigned_regions_override: string[];
  },
): Promise<AbacAssignmentView> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/assignments`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseOrThrow(res, abacAssignmentViewSchema);
}

export async function revokeAbacAssignment(
  businessId: string,
  assignmentId: string,
): Promise<void> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/assignments/${encodeURIComponent(assignmentId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) {
    throw new ManagementApiError(
      "REQUEST_FAILED",
      `Failed to revoke assignment (${res.status})`,
      res.status,
    );
  }
}

export async function simulateAbacPolicy(
  businessId: string,
  payload: {
    policy_id: string;
    permission: string;
    simulated_at_utc?: string;
    record_region?: string | null;
    amount_cents?: number | null;
  },
): Promise<SimulateAbacResponse> {
  const res = await authorizedResponse(
    `/v1/businesses/${encodeURIComponent(businessId)}/access-control/simulate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseOrThrow(res, simulateAbacResponseSchema);
}

export function formatUsdCents(cents: number | null): string {
  if (cents === null) return "Unlimited";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}
