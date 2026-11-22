// ENTERPRISE-01 Slice 3: typed API client for /enterprise/ with Idempotency-Key mutations.
import { ManagementApiError, managementFetch } from "./management-api";
import {
  ConsolidatedGroupReportViewSchema,
  DeprovisionResultViewSchema,
  DirectoryLinkListSchema,
  DirectoryLinkViewSchema,
  GroupReportGrantListSchema,
  GroupReportGrantViewSchema,
  GroupReportSnapshotViewSchema,
  LifecycleEventListSchema,
  SsoProviderListSchema,
  SsoProviderViewSchema,
  type ConsolidatedGroupReportView,
  type DeprovisionResultView,
  type DirectoryLinkView,
  type GrantStatus,
  type GroupReportGrantView,
  type GroupReportSnapshotView,
  type LifecycleEventView,
  type ReportSet,
  type SsoProtocol,
  type SsoProviderStatus,
  type SsoProviderView,
} from "./enterprise-contracts";

const root = (business: string) => `/v1/businesses/${business}/enterprise`;

export function enterpriseError(error: unknown): string {
  if (error instanceof ManagementApiError) {
    return `${error.code}: ${error.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

export async function fetchSsoProviders(
  business: string,
): Promise<SsoProviderView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/sso-providers`);
  return SsoProviderListSchema.parse(raw).items;
}

export async function saveSsoProvider(
  business: string,
  providerId: string,
  key: string,
  body: {
    expected_revision: number;
    code: string;
    display_name: string;
    protocol: SsoProtocol;
    issuer_url: string;
    email_domain: string;
    status?: SsoProviderStatus;
  },
): Promise<SsoProviderView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/sso-providers/${providerId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return SsoProviderViewSchema.parse(raw);
}

export async function fetchDirectoryLinks(
  business: string,
): Promise<DirectoryLinkView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/directory-links`,
  );
  return DirectoryLinkListSchema.parse(raw).items;
}

export async function saveDirectoryLink(
  business: string,
  linkId: string,
  key: string,
  body: {
    expected_revision: number;
    provider_id: string;
    user_id: string;
    external_subject: string;
    employee_code: string;
  },
): Promise<DirectoryLinkView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/directory-links/${linkId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return DirectoryLinkViewSchema.parse(raw);
}

export async function postDeprovisionLink(
  business: string,
  linkId: string,
  key: string,
  body: { reason: string },
): Promise<DeprovisionResultView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/directory-links/${linkId}/deprovision`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return DeprovisionResultViewSchema.parse(raw);
}

export async function fetchLifecycleEvents(
  business: string,
): Promise<LifecycleEventView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/lifecycle-events`,
  );
  return LifecycleEventListSchema.parse(raw).items;
}

export async function fetchGroupReportGrants(
  business: string,
): Promise<GroupReportGrantView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/group-report-grants`,
  );
  return GroupReportGrantListSchema.parse(raw).items;
}

export async function saveGroupReportGrant(
  business: string,
  grantId: string,
  key: string,
  body: {
    expected_revision: number;
    organizer_business_id: string;
    group_id: string;
    allowed_report_sets: ReportSet[];
    status: GrantStatus;
  },
): Promise<GroupReportGrantView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/group-report-grants/${grantId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return GroupReportGrantViewSchema.parse(raw);
}

export async function publishGroupReportSnapshot(
  business: string,
  snapshotId: string,
  key: string,
  body: {
    organizer_business_id: string;
    group_id: string;
    legal_entity_id: string;
    period_key: string;
    currency: string;
    report_set: ReportSet;
    metric_count: number;
    metric_amount_minor: number;
    notes?: string | null;
  },
): Promise<GroupReportSnapshotView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/group-report-snapshots/${snapshotId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return GroupReportSnapshotViewSchema.parse(raw);
}

export async function fetchConsolidatedGroupReport(
  business: string,
  groupId: string,
  periodKey?: string,
): Promise<ConsolidatedGroupReportView> {
  const query = periodKey ? `?period_key=${encodeURIComponent(periodKey)}` : "";
  const raw = await managementFetch<unknown>(
    `${root(business)}/groups/${groupId}/consolidated-report${query}`,
  );
  return ConsolidatedGroupReportViewSchema.parse(raw);
}
