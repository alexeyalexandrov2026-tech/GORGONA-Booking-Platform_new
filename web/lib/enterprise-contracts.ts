// ENTERPRISE-01 Slice 3 (ADR-0041): strict Zod contracts for /enterprise/ UI.
import { z } from "zod";

export type MembershipSummary = {
  role: string;
  delegated?: boolean;
  delegation?: unknown;
};

const uuid = z.string().uuid();
const isoDateTime = z.string().min(1);
const currency = z.string().regex(/^[A-Z]{3}$/);

export const SsoProtocolSchema = z.enum(["oidc", "saml"]);
export type SsoProtocol = z.infer<typeof SsoProtocolSchema>;

export const SsoProviderStatusSchema = z.enum(["active", "disabled"]);
export type SsoProviderStatus = z.infer<typeof SsoProviderStatusSchema>;

export const DirectoryLinkStatusSchema = z.enum(["active", "deprovisioned"]);
export type DirectoryLinkStatus = z.infer<typeof DirectoryLinkStatusSchema>;

export const LifecycleEventKindSchema = z.enum([
  "provisioned",
  "deprovisioned",
]);
export type LifecycleEventKind = z.infer<typeof LifecycleEventKindSchema>;

export const ReportSetSchema = z.enum([
  "ledger_summary",
  "revenue_by_currency",
  "order_volume",
  "headcount",
]);
export type ReportSet = z.infer<typeof ReportSetSchema>;

export const ALL_REPORT_SETS: readonly ReportSet[] = [
  "ledger_summary",
  "revenue_by_currency",
  "order_volume",
  "headcount",
] as const;

export const GrantStatusSchema = z.enum(["active", "revoked"]);
export type GrantStatus = z.infer<typeof GrantStatusSchema>;

export const SsoProviderViewSchema = z
  .object({
    schema_version: z.literal(1),
    provider_id: uuid,
    location_id: uuid.nullable(),
    code: z.string(),
    display_name: z.string(),
    protocol: SsoProtocolSchema,
    issuer_url: z.string(),
    email_domain: z.string(),
    status: SsoProviderStatusSchema,
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type SsoProviderView = z.infer<typeof SsoProviderViewSchema>;

export const SsoProviderListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(SsoProviderViewSchema),
  })
  .strict();

export const DirectoryLinkViewSchema = z
  .object({
    schema_version: z.literal(1),
    link_id: uuid,
    location_id: uuid.nullable(),
    provider_id: uuid,
    user_id: uuid,
    external_subject: z.string(),
    employee_code: z.string(),
    status: DirectoryLinkStatusSchema,
    deprovisioned_at: isoDateTime.nullable(),
    deprovision_reason: z.string().nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type DirectoryLinkView = z.infer<typeof DirectoryLinkViewSchema>;

export const DirectoryLinkListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(DirectoryLinkViewSchema),
  })
  .strict();

export const LifecycleEventViewSchema = z
  .object({
    schema_version: z.literal(1),
    event_id: uuid,
    location_id: uuid.nullable(),
    directory_link_id: uuid,
    user_id: uuid,
    event_kind: LifecycleEventKindSchema,
    reason: z.string().nullable(),
    memberships_suspended: z.number().int(),
    delegations_removed: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type LifecycleEventView = z.infer<typeof LifecycleEventViewSchema>;

export const LifecycleEventListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(LifecycleEventViewSchema),
  })
  .strict();

export const DeprovisionResultViewSchema = z
  .object({
    schema_version: z.literal(1),
    link: DirectoryLinkViewSchema,
    event: LifecycleEventViewSchema,
  })
  .strict();
export type DeprovisionResultView = z.infer<typeof DeprovisionResultViewSchema>;

export const GroupReportGrantViewSchema = z
  .object({
    schema_version: z.literal(1),
    grant_id: uuid,
    owner_business_id: uuid,
    organizer_business_id: uuid,
    group_id: uuid,
    allowed_report_sets: z.array(ReportSetSchema),
    status: GrantStatusSchema,
    revoked_at: isoDateTime.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type GroupReportGrantView = z.infer<typeof GroupReportGrantViewSchema>;

export const GroupReportGrantListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(GroupReportGrantViewSchema),
  })
  .strict();

export const GroupReportSnapshotViewSchema = z
  .object({
    schema_version: z.literal(1),
    snapshot_id: uuid,
    owner_business_id: uuid,
    organizer_business_id: uuid,
    group_id: uuid,
    legal_entity_id: uuid,
    period_key: z.string(),
    currency,
    report_set: ReportSetSchema,
    metric_count: z.number().int(),
    metric_amount_minor: z.number().int(),
    notes: z.string().nullable(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type GroupReportSnapshotView = z.infer<
  typeof GroupReportSnapshotViewSchema
>;

export const CurrencyTotalSchema = z
  .object({
    currency,
    report_set: ReportSetSchema,
    total_count: z.number().int(),
    total_amount_minor: z.number().int(),
    contributing_businesses: z.number().int(),
  })
  .strict();

export const ConsolidatedGroupReportViewSchema = z
  .object({
    schema_version: z.literal(1),
    group_id: uuid,
    organizer_business_id: uuid,
    period_key: z.string().nullable(),
    entries: z.array(GroupReportSnapshotViewSchema),
    totals_by_currency: z.array(CurrencyTotalSchema),
  })
  .strict();
export type ConsolidatedGroupReportView = z.infer<
  typeof ConsolidatedGroupReportViewSchema
>;

export function enterpriseResponseSchema(
  subpath: string,
  method: string,
): z.ZodType | null {
  const path = subpath.split("?")[0] ?? "";
  if (!path.startsWith("/enterprise/")) return null;
  const rest = path.slice("/enterprise/".length);
  const m = method.toUpperCase();
  if (rest === "sso-providers" && m === "GET") return SsoProviderListSchema;
  if (/^sso-providers\/[^/]+$/.test(rest) && m === "PUT") {
    return SsoProviderViewSchema;
  }
  if (rest === "directory-links" && m === "GET") return DirectoryLinkListSchema;
  if (/^directory-links\/[^/]+$/.test(rest) && m === "PUT") {
    return DirectoryLinkViewSchema;
  }
  if (/^directory-links\/[^/]+\/deprovision$/.test(rest) && m === "POST") {
    return DeprovisionResultViewSchema;
  }
  if (rest === "lifecycle-events" && m === "GET") {
    return LifecycleEventListSchema;
  }
  if (rest === "group-report-grants" && m === "GET") {
    return GroupReportGrantListSchema;
  }
  if (/^group-report-grants\/[^/]+$/.test(rest) && m === "PUT") {
    return GroupReportGrantViewSchema;
  }
  if (/^group-report-snapshots\/[^/]+$/.test(rest) && m === "PUT") {
    return GroupReportSnapshotViewSchema;
  }
  if (/^groups\/[^/]+\/consolidated-report$/.test(rest) && m === "GET") {
    return ConsolidatedGroupReportViewSchema;
  }
  return null;
}

export function formatEnterpriseMinor(minor: number, curr = "USD"): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100);
  const cents = String(abs % 100).padStart(2, "0");
  return `${sign}${whole}.${cents} ${curr}`;
}

export function canReadEnterprise(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation)) {
    return false;
  }
  return ["owner", "manager", "front_desk", "artist"].includes(member.role);
}

export function canManageEnterprise(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation)) {
    return false;
  }
  return member.role === "owner" || member.role === "manager";
}
