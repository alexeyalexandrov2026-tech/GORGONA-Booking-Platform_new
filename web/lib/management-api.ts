import { accessToken } from "./auth";
import {
  managementResponseSchema,
  type Readiness,
} from "./management-contracts";
import { availabilitySchema, Availability } from "./contracts";
import {
  legalEntityListSchema,
  legalEntitySchema,
  type LegalEntity,
  type LegalEntityInput,
  type LegalEntityPage,
} from "./legal-entity-contracts";
import {
  departmentListSchema,
  departmentSchema,
  type Department,
  type DepartmentInput,
  type DepartmentPage,
} from "./department-contracts";
import {
  delegationListSchema,
  delegationSchema,
  type DelegatedBusiness,
  type Delegation,
  type DelegationDecision,
  type DelegationIssue,
  type DelegationPage,
} from "./delegation-contracts";
import {
  businessGroupListSchema,
  businessGroupSchema,
  type BusinessGroup,
  type BusinessGroupPage,
} from "./group-contracts";
import {
  configurationPreviewSchema,
  configurationSchema,
  configurationVersionListSchema,
  configurationVersionSchema,
  moduleCatalogSchema,
  type Configuration,
  type ConfigurationPreview,
  type ConfigurationVersion,
  type ConfigurationVersionPage,
  type ModuleCatalog,
} from "./configuration-contracts";
import type {
  Business,
  BusinessProfile,
  IndustryCatalog,
  ProfileInput,
} from "./business-contracts";
/**
 * GORGONA Management API Client.
 * Communicates with /v1 authenticated staff routes with real PostgreSQL persistence.
 */

export interface OverviewStats {
  today_bookings_count: number;
  confirmed_bookings_count: number;
  cancelled_bookings_count: number;
  today_revenue_cents: number;
  today_booked_value: { currency: string; amount_cents: number }[];
  active_staff_count: number;
  total_services_count: number;
}

export interface BookingSummary {
  booking_id: string;
  status: string;
  location_id: string;
  location_timezone: string;
  resource_id: string;
  resource_name: string;
  variant_id: string;
  service_name: string;
  variant_name: string;
  starts_at: string;
  ends_at: string;
  total_cents: number;
  currency: string;
  customer_name: string | null;
  customer_email: string | null;
  customer_phone: string | null;
  created_at: string;
  created_by: string;
}

export interface ActivityItem {
  id: string;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown>;
  occurred_at: string;
}

export interface SalonOverview {
  salon_id: string;
  salon_name: string;
  status: string;
  booking_state: string;
  stats: OverviewStats;
  today_bookings: BookingSummary[];
  recent_activity: ActivityItem[];
}

export interface ServiceView {
  id: string;
  service_id: string;
  code: string;
  name: string;
  status: string;
  price_cents: number;
  currency: string;
  booking_duration_minutes: number | null;
  is_bookable: boolean;
  revision: number;
}

export interface StaffView {
  id: string;
  location_id: string;
  kind: string;
  display_name: string;
  is_active: boolean;
}

export interface ResourceHours {
  id: string;
  weekday: number;
  opens_minute: number;
  closes_minute: number;
}

export interface StaffSchedule {
  resource_id: string;
  display_name: string;
  is_active: boolean;
  location_id: string;
  hours: ResourceHours[];
  service_ids: string[];
}

export interface ClientItem {
  customer_name: string;
  email: string;
  phone: string;
  total_bookings: number;
  confirmed_bookings: number;
  last_booking_at: string | null;
}

export interface LocationItem {
  id: string;
  name: string;
  timezone: string;
}

export interface BusinessHoursItem {
  id: string;
  location_id: string;
  weekday: number;
  opens_minute: number;
  closes_minute: number;
}

export interface SalonFactItem {
  fact_key: string;
  status: string;
  source_note: string | null;
  recorded_by: string;
  recorded_at: string;
}

export interface SalonEmbedOriginItem {
  id: string;
  origin: string;
  status: string;
  updated_at: string;
}

export interface SalonSettings {
  salon_id: string;
  slug: string;
  display_name: string;
  status: string;
  booking_state: string;
  locations: LocationItem[];
  business_hours: BusinessHoursItem[];
  policies: {
    cancellation_policy?: Record<string, unknown>;
    deposit_policy?: Record<string, unknown>;
    booking_rules?: Record<string, unknown>;
  };
  fact_confirmations: SalonFactItem[];
  embed_origins: SalonEmbedOriginItem[];
}

export interface MembershipView {
  salon_id: string;
  salon_name: string | null;
  role: string;
  status: string;
  location_id: string | null;
  /** Present only for a business served under another company's active grant. */
  delegation?: DelegatedBusiness;
}

export interface MemberView {
  membership_id: string;
  user_id: string;
  display_name: string | null;
  role: string;
  status: string;
  location_id: string | null;
}

export interface Workspace {
  salon_id: string;
  location_id: string | null;
  locations: LocationItem[];
  business_hours: BusinessHoursItem[];
  /** False once a published configuration turns booking off (ADR-0019). */
  booking_enabled: boolean;
}

export function fetchWorkspace(salonId: string): Promise<Workspace> {
  return managementFetch<Workspace>(`/v1/salons/${salonId}/workspace`);
}

export async function fetchLegalEntities(
  businessId: string,
  after?: string,
): Promise<LegalEntityPage> {
  const query = after ? `?after=${encodeURIComponent(after)}` : "";
  const result = legalEntityListSchema.parse(
    await managementFetch(
      `/v1/businesses/${businessId}/legal-entities${query}`,
    ),
  );
  if (result.business_id !== businessId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load these records safely.",
    );
  return result;
}

export async function fetchLegalEntity(
  businessId: string,
  entityId: string,
  revision?: number,
): Promise<LegalEntity> {
  const query = revision === undefined ? "" : `?revision=${revision}`;
  const result = checkedLegalEntity(
    await managementFetch(
      `/v1/businesses/${businessId}/legal-entities/${entityId}${query}`,
    ),
    businessId,
    entityId,
  );
  if (revision !== undefined && result.revision !== revision)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this saved version safely.",
    );
  return result;
}

export async function saveLegalEntity(
  businessId: string,
  entityId: string,
  body: LegalEntityInput,
  key: string,
): Promise<LegalEntity> {
  return checkedLegalEntity(
    await managementFetch(
      `/v1/businesses/${businessId}/legal-entities/${entityId}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
        headers: { "Idempotency-Key": key },
      },
    ),
    businessId,
    entityId,
  );
}

function checkedLegalEntity(
  value: unknown,
  businessId: string,
  entityId: string,
): LegalEntity {
  const result = legalEntitySchema.parse(value);
  if (result.business_id !== businessId || result.legal_entity_id !== entityId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

export async function fetchDepartments(
  businessId: string,
  after?: string,
): Promise<DepartmentPage> {
  const query = after ? `?after=${encodeURIComponent(after)}` : "";
  const result = departmentListSchema.parse(
    await managementFetch(`/v1/businesses/${businessId}/departments${query}`),
  );
  if (result.business_id !== businessId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load these records safely.",
    );
  return result;
}

export async function fetchDepartment(
  businessId: string,
  departmentId: string,
  revision?: number,
): Promise<Department> {
  const query = revision === undefined ? "" : `?revision=${revision}`;
  const result = checkedDepartment(
    await managementFetch(
      `/v1/businesses/${businessId}/departments/${departmentId}${query}`,
    ),
    businessId,
    departmentId,
  );
  if (revision !== undefined && result.revision !== revision)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this saved version safely.",
    );
  return result;
}

export async function saveDepartment(
  businessId: string,
  departmentId: string,
  body: DepartmentInput,
  key: string,
): Promise<Department> {
  return checkedDepartment(
    await managementFetch(
      `/v1/businesses/${businessId}/departments/${departmentId}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
        headers: { "Idempotency-Key": key },
      },
    ),
    businessId,
    departmentId,
  );
}

function checkedDepartment(
  value: unknown,
  businessId: string,
  departmentId: string,
): Department {
  const result = departmentSchema.parse(value);
  if (
    result.business_id !== businessId ||
    result.department_id !== departmentId
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

export async function fetchDelegations(
  businessId: string,
  after?: string,
): Promise<DelegationPage> {
  const query = after ? `?after=${encodeURIComponent(after)}` : "";
  const result = delegationListSchema.parse(
    await managementFetch(`/v1/businesses/${businessId}/delegations${query}`),
  );
  if (result.business_id !== businessId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load these records safely.",
    );
  return result;
}

export async function issueDelegation(
  businessId: string,
  grantId: string,
  body: DelegationIssue,
  key: string,
): Promise<Delegation> {
  const result = checkedDelegation(
    await managementFetch(
      `/v1/businesses/${businessId}/delegations/${grantId}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
        headers: { "Idempotency-Key": key },
      },
    ),
    businessId,
    grantId,
  );
  if (result.owner_business_id !== businessId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

export async function decideDelegation(
  businessId: string,
  grantId: string,
  action: "accept" | "decline" | "revoke" | "delegates",
  body: DelegationDecision,
  key: string,
): Promise<Delegation> {
  const path = `/v1/businesses/${businessId}/delegations/${grantId}/${action}`;
  return checkedDelegation(
    await managementFetch(path, {
      method: action === "delegates" ? "PUT" : "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": key },
    }),
    businessId,
    grantId,
  );
}

function checkedDelegation(
  value: unknown,
  businessId: string,
  grantId: string,
): Delegation {
  const result = delegationSchema.parse(value);
  if (
    result.grant_id !== grantId ||
    (result.owner_business_id !== businessId &&
      result.servicer_business_id !== businessId)
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

export async function fetchGroups(
  businessId: string,
  after?: string,
): Promise<BusinessGroupPage> {
  const query = after ? `?after=${encodeURIComponent(after)}` : "";
  const result = businessGroupListSchema.parse(
    await managementFetch(`/v1/businesses/${businessId}/groups${query}`),
  );
  if (result.business_id !== businessId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load these records safely.",
    );
  return result;
}

export type GroupCommand =
  | { kind: "create"; code: string; name: string }
  | { kind: "invite"; member: string }
  | { kind: "remove"; member: string; revision: number }
  | { kind: "accept" | "decline" | "leave"; revision: number };

export async function changeGroup(
  businessId: string,
  groupId: string,
  command: GroupCommand,
  key: string,
): Promise<BusinessGroup> {
  const base = `/v1/businesses/${businessId}/groups/${groupId}`;
  const [path, method, body] =
    command.kind === "create"
      ? [base, "PUT", { code: command.code, name: command.name }]
      : command.kind === "invite"
        ? [`${base}/members/${command.member}`, "PUT", {}]
        : command.kind === "remove"
          ? [
              `${base}/members/${command.member}/remove`,
              "POST",
              { expected_revision: command.revision },
            ]
          : [
              `${base}/${command.kind}`,
              "POST",
              { expected_revision: command.revision },
            ];
  const result = businessGroupSchema.parse(
    await managementFetch(path, {
      method,
      body: JSON.stringify({ schema_version: 1, ...body }),
      headers: { "Idempotency-Key": key },
    }),
  );
  if (result.group_id !== groupId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

function sameBusiness<T extends { business_id: string }>(
  result: T,
  businessId: string,
): T {
  if (result.business_id !== businessId)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

export async function fetchModuleCatalog(
  businessId: string,
): Promise<ModuleCatalog> {
  return moduleCatalogSchema.parse(
    await managementFetch(`/v1/businesses/${businessId}/module-catalog`),
  );
}

export async function fetchConfiguration(
  businessId: string,
): Promise<Configuration> {
  return sameBusiness(
    configurationSchema.parse(
      await managementFetch(`/v1/businesses/${businessId}/configuration`),
    ),
    businessId,
  );
}

export async function fetchConfigurationVersions(
  businessId: string,
  before?: number,
): Promise<ConfigurationVersionPage> {
  const query = before ? `?before=${before}` : "";
  return sameBusiness(
    configurationVersionListSchema.parse(
      await managementFetch(
        `/v1/businesses/${businessId}/configuration/versions${query}`,
      ),
    ),
    businessId,
  );
}

export async function fetchConfigurationPreview(
  businessId: string,
  version: number,
): Promise<ConfigurationPreview> {
  return sameBusiness(
    configurationPreviewSchema.parse(
      await managementFetch(
        `/v1/businesses/${businessId}/configuration/versions/${version}/preview`,
      ),
    ),
    businessId,
  );
}

export type ConfigurationCommand =
  | {
      kind: "draft";
      expectedVersion: number;
      profileRevision: number;
      moduleIds: string[];
    }
  | { kind: "validate" | "publish"; version: number; revision: number };

export async function changeConfiguration(
  businessId: string,
  command: ConfigurationCommand,
  key: string,
): Promise<ConfigurationVersion> {
  const base = `/v1/businesses/${businessId}/configuration`;
  const [path, method, body] =
    command.kind === "draft"
      ? [
          `${base}/draft`,
          "PUT",
          {
            expected_version: command.expectedVersion,
            profile_revision: command.profileRevision,
            module_ids: command.moduleIds,
          },
        ]
      : [
          `${base}/versions/${command.version}/${command.kind}`,
          "POST",
          { expected_revision: command.revision },
        ];
  const result = sameBusiness(
    configurationVersionSchema.parse(
      await managementFetch(path, {
        method,
        body: JSON.stringify({ schema_version: 1, ...body }),
        headers: { "Idempotency-Key": key },
      }),
    ),
    businessId,
  );
  if (command.kind !== "draft" && result.version !== command.version)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unable to load this record safely.",
    );
  return result;
}

export async function fetchMembers(salonId: string): Promise<MemberView[]> {
  return managementFetch<MemberView[]>(`/v1/salons/${salonId}/members`);
}

export interface MeView {
  user_id: string;
  display_name: string;
  platform_roles: string[];
  memberships: MembershipView[];
  delegations: DelegatedBusiness[];
}

export class ManagementApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ManagementApiError";
  }
}

const ACTIVE_SALON_KEY = "gorgona_active_salon";

export function getActiveSalonId(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(ACTIVE_SALON_KEY);
}

export function setActiveSalonId(salonId: string | null): void {
  if (typeof window === "undefined") return;
  if (salonId) {
    sessionStorage.setItem(ACTIVE_SALON_KEY, salonId);
  } else {
    sessionStorage.removeItem(ACTIVE_SALON_KEY);
  }
}

/**
 * An authorized management request: allowlisted path, bearer token, timeout and
 * the API error envelope. Returns only successful responses; the body is unread.
 */
export async function authorizedResponse(
  path: string,
  options?: RequestInit,
  timeoutMs = 15000,
): Promise<Response> {
  if (
    !/^\/v1\/(me$|(?:salons|businesses)\/[0-9a-f-]{36}(?:\/|\?|$))/i.test(path)
  )
    throw new ManagementApiError(
      "INVALID_REQUEST",
      "Invalid management request.",
    );
  const token = await accessToken();
  if (!token)
    throw new ManagementApiError(
      "AUTHENTICATION_REQUIRED",
      "Your session expired. Please sign in again.",
    );
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string>),
    Authorization: `Bearer ${token}`,
  };

  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      headers,
      cache: "no-store",
      credentials: "omit",
      signal: options?.signal
        ? AbortSignal.any([options.signal, AbortSignal.timeout(timeoutMs)])
        : AbortSignal.timeout(timeoutMs),
    });
  } catch {
    throw new ManagementApiError(
      "NETWORK_ERROR",
      "We couldn’t reach the studio. Retry safely to check whether the request arrived.",
    );
  }
  if (response.ok) return response;

  let data: unknown;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (typeof data === "object" && data !== null && "error" in data) {
    const err = (data as { error: { code: string; message: string } }).error;
    throw new ManagementApiError(err.code, err.message, response.status);
  }
  if (response.status === 401) {
    throw new ManagementApiError(
      "AUTHENTICATION_REQUIRED",
      "Staff authentication required. Please sign in with your access token.",
      response.status,
    );
  }
  if (response.status === 403) {
    throw new ManagementApiError(
      "PERMISSION_DENIED",
      "You do not have permission for this salon action.",
      response.status,
    );
  }
  if (response.status === 503) {
    throw new ManagementApiError(
      "SERVICE_UNAVAILABLE",
      "Authentication or database service is temporarily unavailable.",
      response.status,
    );
  }
  throw new ManagementApiError(
    "UNKNOWN_ERROR",
    "The studio service is temporarily unavailable. Please try again.",
    response.status,
  );
}

/** A JSON management request whose response must match its route's contract. */
export async function managementFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await authorizedResponse(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers as Record<string, string>),
    },
  });
  let data: unknown;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch (error) {
    if (error instanceof SyntaxError) data = null;
    else
      throw new ManagementApiError(
        "NETWORK_ERROR",
        "We couldn’t reach the studio. Retry safely to check whether the request arrived.",
      );
  }

  const parsed = managementResponseSchema(
    path,
    options?.method ?? "GET",
  ).safeParse(data);
  if (!parsed.success)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "The studio service returned incomplete information. Please retry.",
    );
  return parsed.data as T;
}

const pendingMutations = new Map<string, string>();
async function bookingMutation<T>(path: string, payload: unknown): Promise<T> {
  const body = JSON.stringify(payload);
  const signature = `${path}:${body}`;
  let key = pendingMutations.get(signature);
  if (!key) {
    key = crypto.randomUUID();
    pendingMutations.set(signature, key);
  }
  // Keep the key after timeout/response loss. A safe retry must replay the same operation.
  const result = await managementFetch<T>(path, {
    method: "POST",
    body,
    headers: { "Idempotency-Key": key },
  });
  pendingMutations.delete(signature);
  return result;
}

// --- Specific API Calls ---

export async function fetchMe(): Promise<MeView> {
  return managementFetch<MeView>("/v1/me");
}

export async function fetchBusiness(businessId: string): Promise<Business> {
  return managementFetch<Business>(`/v1/businesses/${businessId}`);
}

export async function fetchIndustryCatalog(
  businessId: string,
): Promise<IndustryCatalog> {
  return managementFetch<IndustryCatalog>(
    `/v1/businesses/${businessId}/industry-catalog`,
  );
}

export async function saveBusinessProfile(
  businessId: string,
  body: ProfileInput,
  key: string,
): Promise<BusinessProfile> {
  return managementFetch<BusinessProfile>(
    `/v1/businesses/${businessId}/profile`,
    {
      method: "PUT",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": key },
    },
  );
}

export async function fetchOverview(salonId: string): Promise<SalonOverview> {
  return managementFetch<SalonOverview>(`/v1/salons/${salonId}/overview`);
}

export async function fetchBookings(
  salonId: string,
  params?: {
    startDate?: string;
    endDate?: string;
    resourceId?: string;
    status?: string;
    localDay?: string;
    localStartDay?: string;
    localEndDay?: string;
    locationId?: string;
  },
): Promise<BookingSummary[]> {
  const query = new URLSearchParams();
  if (params?.startDate) query.set("start_date", params.startDate);
  if (params?.endDate) query.set("end_date", params.endDate);
  if (params?.resourceId) query.set("resource_id", params.resourceId);
  if (params?.status) query.set("status", params.status);
  if (params?.localDay) query.set("local_day", params.localDay);
  if (params?.localStartDay) query.set("local_start_day", params.localStartDay);
  if (params?.localEndDay) query.set("local_end_day", params.localEndDay);
  if (params?.locationId) query.set("location_id", params.locationId);
  const qStr = query.toString();
  return managementFetch<BookingSummary[]>(
    `/v1/salons/${salonId}/bookings${qStr ? `?${qStr}` : ""}`,
  );
}

export async function createStaffBooking(
  salonId: string,
  data: {
    location_id: string;
    resource_id: string;
    variant_id: string;
    starts_at: string;
    customer_name: string;
    customer_email: string;
    customer_phone: string;
    add_on_ids?: string[];
  },
): Promise<BookingSummary> {
  return bookingMutation<BookingSummary>(
    `/v1/salons/${salonId}/bookings`,
    data,
  );
}

export async function rescheduleBooking(
  salonId: string,
  bookingId: string,
  data: {
    new_starts_at: string;
    new_resource_id?: string;
  },
): Promise<BookingSummary> {
  return bookingMutation<BookingSummary>(
    `/v1/salons/${salonId}/bookings/${bookingId}/reschedule`,
    data,
  );
}

export async function cancelBooking(
  salonId: string,
  bookingId: string,
  reason: string = "Cancelled by staff",
): Promise<BookingSummary> {
  return bookingMutation<BookingSummary>(
    `/v1/salons/${salonId}/bookings/${bookingId}/cancel`,
    { reason },
  );
}

export async function fetchClients(
  salonId: string,
  search?: string,
): Promise<ClientItem[]> {
  const q = search?.trim() ? `?q=${encodeURIComponent(search.trim())}` : "";
  return managementFetch<ClientItem[]>(`/v1/salons/${salonId}/clients${q}`);
}

export async function fetchClientHistory(
  salonId: string,
  params: { email?: string; phone?: string },
): Promise<BookingSummary[]> {
  const query = new URLSearchParams();
  if (params.email) query.set("email", params.email);
  if (params.phone) query.set("phone", params.phone);
  return managementFetch<BookingSummary[]>(
    `/v1/salons/${salonId}/clients/history?${query.toString()}`,
  );
}

export async function fetchServices(salonId: string): Promise<ServiceView[]> {
  return managementFetch<ServiceView[]>(`/v1/salons/${salonId}/services`);
}

export async function createService(
  salonId: string,
  data: {
    service_code: string;
    service_name: string;
    code: string;
    name: string;
    price_cents: number;
    currency: string;
    booking_duration_minutes?: number;
    display_duration_min_minutes?: number;
    display_duration_max_minutes?: number;
  },
): Promise<ServiceView> {
  return managementFetch<ServiceView>(`/v1/salons/${salonId}/services`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateService(
  salonId: string,
  variantId: string,
  data: {
    name?: string;
    price_cents?: number;
    booking_duration_minutes?: number;
    is_bookable?: boolean;
  },
): Promise<ServiceView> {
  return managementFetch<ServiceView>(
    `/v1/salons/${salonId}/services/${variantId}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
  );
}

export async function publishService(
  salonId: string,
  variantId: string,
): Promise<ServiceView> {
  return managementFetch<ServiceView>(
    `/v1/salons/${salonId}/services/${variantId}/publish`,
    {
      method: "POST",
    },
  );
}

export async function unpublishService(
  salonId: string,
  variantId: string,
): Promise<ServiceView> {
  return managementFetch<ServiceView>(
    `/v1/salons/${salonId}/services/${variantId}/unpublish`,
    {
      method: "POST",
    },
  );
}

export async function fetchStaff(salonId: string): Promise<StaffView[]> {
  return managementFetch<StaffView[]>(`/v1/salons/${salonId}/staff`);
}

export async function createStaff(
  salonId: string,
  data: {
    display_name: string;
    location_id: string;
    kind: "artist" | "chair" | "room";
  },
): Promise<StaffView> {
  return managementFetch<StaffView>(`/v1/salons/${salonId}/staff`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateStaff(
  salonId: string,
  resourceId: string,
  data: {
    display_name?: string;
    is_active?: boolean;
  },
): Promise<StaffView> {
  return managementFetch<StaffView>(
    `/v1/salons/${salonId}/staff/${resourceId}`,
    {
      method: "PATCH",
      body: JSON.stringify(data),
    },
  );
}

export async function fetchStaffSchedule(
  salonId: string,
  resourceId: string,
): Promise<StaffSchedule> {
  return managementFetch<StaffSchedule>(
    `/v1/salons/${salonId}/staff/${resourceId}/schedule`,
  );
}

export async function updateStaffSchedule(
  salonId: string,
  resourceId: string,
  hours: { weekday: number; opens_minute: number; closes_minute: number }[],
): Promise<StaffSchedule> {
  return managementFetch<StaffSchedule>(
    `/v1/salons/${salonId}/staff/${resourceId}/schedule`,
    {
      method: "PUT",
      body: JSON.stringify({ hours }),
    },
  );
}

export async function updateStaffServices(
  salonId: string,
  resourceId: string,
  serviceIds: string[],
): Promise<StaffSchedule> {
  return managementFetch<StaffSchedule>(
    `/v1/salons/${salonId}/staff/${resourceId}/services`,
    {
      method: "PUT",
      body: JSON.stringify({ service_ids: serviceIds }),
    },
  );
}

export async function fetchActivity(salonId: string): Promise<ActivityItem[]> {
  return managementFetch<ActivityItem[]>(`/v1/salons/${salonId}/activity`);
}

export async function fetchSettings(salonId: string): Promise<SalonSettings> {
  return managementFetch<SalonSettings>(`/v1/salons/${salonId}/settings`);
}

export async function fetchManagementAvailability(
  salonId: string,
  data: {
    location_id: string;
    variant_id: string;
    resource_id: string | null;
    add_on_ids: string[];
    day: string;
    booking_id?: string;
  },
  signal?: AbortSignal,
): Promise<Availability> {
  const result = await managementFetch<Availability>(
    `/v1/salons/${salonId}/availability`,
    { method: "POST", body: JSON.stringify(data), signal },
  );
  return availabilitySchema.parse(result);
}

export async function savePolicies(
  salonId: string,
  payload: {
    booking_rules: {
      version: 1;
      slot_interval_minutes: number;
      advance_notice_minutes: number;
      max_days_ahead: number;
    };
    deposit_policy: { version: 1; required: boolean };
    cancellation_policy: { version: 1; summary: string };
  },
): Promise<Readiness> {
  return managementFetch<Readiness>(`/v1/salons/${salonId}/policies`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}
export async function saveBusinessHours(
  salonId: string,
  locationId: string,
  hours: { weekday: number; opens: string; closes: string }[],
): Promise<Readiness> {
  return managementFetch<Readiness>(`/v1/salons/${salonId}/business-hours`, {
    method: "PUT",
    body: JSON.stringify({ location_id: locationId, hours }),
  });
}
export async function saveFact(
  salonId: string,
  key: string,
  status: "confirmed" | "unconfirmed",
  sourceNote: string,
): Promise<Readiness> {
  return managementFetch<Readiness>(
    `/v1/salons/${salonId}/facts/${encodeURIComponent(key)}`,
    {
      method: "PUT",
      body: JSON.stringify({ status, source_note: sourceNote }),
    },
  );
}

export function formatPrice(cents: number, currency: string = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(cents / 100);
}

export function formatTime(
  isoString: string,
  timezone: string = "UTC",
): string {
  const d = new Date(isoString);
  return d.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    timeZone: timezone,
    timeZoneName: "short",
  });
}

export function formatDate(
  isoString: string,
  timezone: string = "UTC",
): string {
  const d = new Date(isoString);
  return d.toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: timezone,
  });
}
