// SPECIAL-05: typed API client for /specialized/ workspace (SPECIAL-01..04).
import { ManagementApiError, managementFetch } from "./management-api";
import {
  AssetIncidentListSchema,
  AssetIncidentViewSchema,
  CareConsentListSchema,
  CareConsentViewSchema,
  CareEncounterListSchema,
  CareEncounterViewSchema,
  CareSubjectListSchema,
  CareSubjectViewSchema,
  CivicAllocationListSchema,
  CivicAllocationViewSchema,
  CivicCaseListSchema,
  CivicCaseViewSchema,
  CivicProgramListSchema,
  CivicProgramViewSchema,
  ManagedAssetListSchema,
  ManagedAssetViewSchema,
  SpecialEnrollmentViewSchema,
  SpecialProgramListSchema,
  SpecialProgramViewSchema,
  type AssetIncidentView,
  type CareConsentView,
  type CareEncounterView,
  type CareSubjectView,
  type CivicAllocationView,
  type CivicCaseView,
  type CivicProgramView,
  type ManagedAssetView,
  type SpecialEnrollmentView,
  type SpecialProgramView,
} from "./specialized-contracts";

export function specializedError(error: unknown): string {
  if (error instanceof ManagementApiError) {
    return `${error.code}: ${error.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

const base = (business: string) => `/v1/businesses/${business}`;

// --- SPECIAL-01 ---
export async function fetchSpecialPrograms(
  business: string,
): Promise<SpecialProgramView[]> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/special-venues/programs`,
  );
  return SpecialProgramListSchema.parse(raw).items;
}

export async function saveSpecialProgram(
  business: string,
  programId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    title: string;
    program_kind: "education_cohort" | "fitness_membership" | "club_pass";
    capacity: number;
    included_sessions: number;
    price_minor: number;
    currency: string;
  },
): Promise<SpecialProgramView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/special-venues/programs/${programId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return SpecialProgramViewSchema.parse(raw);
}

export async function createSpecialEnrollment(
  business: string,
  enrollmentId: string,
  key: string,
  body: {
    location_id: string;
    program_id: string;
    participant_counterparty_id: string;
  },
): Promise<SpecialEnrollmentView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/special-venues/enrollments/${enrollmentId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return SpecialEnrollmentViewSchema.parse(raw);
}

// --- SPECIAL-02 ---
export async function fetchCareSubjects(
  business: string,
): Promise<CareSubjectView[]> {
  const raw = await managementFetch<unknown>(`${base(business)}/care/subjects`);
  return CareSubjectListSchema.parse(raw).items;
}

export async function saveCareSubject(
  business: string,
  subjectId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    guardian_counterparty_id: string;
    subject_kind: "human_patient" | "animal_patient" | "social_care_recipient";
    code: string;
    display_name: string;
    allergies_summary?: string | null;
  },
): Promise<CareSubjectView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/care/subjects/${subjectId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CareSubjectViewSchema.parse(raw);
}

export async function fetchCareConsents(
  business: string,
): Promise<CareConsentView[]> {
  const raw = await managementFetch<unknown>(`${base(business)}/care/consents`);
  return CareConsentListSchema.parse(raw).items;
}

export async function saveCareConsent(
  business: string,
  consentId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    subject_id: string;
    scope: "care_records" | "procedures" | "medication" | "sharing";
    status: "active" | "revoked";
    granted_by_name: string;
  },
): Promise<CareConsentView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/care/consents/${consentId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CareConsentViewSchema.parse(raw);
}

export async function fetchCareEncounters(
  business: string,
): Promise<CareEncounterView[]> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/care/encounters`,
  );
  return CareEncounterListSchema.parse(raw).items;
}

export async function recordCareEncounter(
  business: string,
  encounterId: string,
  key: string,
  body: {
    location_id: string;
    subject_id: string;
    consent_id: string;
    encounter_date: string;
    summary: string;
    clinical_notes: string;
  },
): Promise<CareEncounterView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/care/encounters/${encounterId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CareEncounterViewSchema.parse(raw);
}

// --- SPECIAL-03 ---
export async function fetchManagedAssets(
  business: string,
): Promise<ManagedAssetView[]> {
  const raw = await managementFetch<unknown>(`${base(business)}/assets/items`);
  return ManagedAssetListSchema.parse(raw).items;
}

export async function saveManagedAsset(
  business: string,
  assetId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    asset_domain:
      | "agriculture_plot"
      | "utility_infrastructure"
      | "mining_equipment"
      | "security_post"
      | "facility_system"
      | "environmental_site";
    code: string;
    name: string;
    status: "active" | "maintenance" | "out_of_service" | "decommissioned";
  },
): Promise<ManagedAssetView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/assets/items/${assetId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return ManagedAssetViewSchema.parse(raw);
}

export async function fetchAssetIncidents(
  business: string,
): Promise<AssetIncidentView[]> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/assets/incidents`,
  );
  return AssetIncidentListSchema.parse(raw).items;
}

export async function saveAssetIncident(
  business: string,
  incidentId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    asset_id: string;
    incident_kind:
      | "safety_hazard"
      | "environmental_spill"
      | "security_breach"
      | "utility_outage"
      | "equipment_failure";
    severity: "low" | "medium" | "high" | "critical";
    status: "open" | "contained" | "resolved";
    description: string;
    resolution_summary?: string;
  },
): Promise<AssetIncidentView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/assets/incidents/${incidentId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return AssetIncidentViewSchema.parse(raw);
}

// --- SPECIAL-04 ---
export async function fetchCivicPrograms(
  business: string,
): Promise<CivicProgramView[]> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/civic/programs`,
  );
  return CivicProgramListSchema.parse(raw).items;
}

export async function saveCivicProgram(
  business: string,
  programId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    program_domain:
      | "advisory_engagement"
      | "staffing_requisition"
      | "membership_program"
      | "public_service_program";
    code: string;
    title: string;
    status: "active" | "paused" | "closed";
    requires_dual_review: boolean;
  },
): Promise<CivicProgramView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/civic/programs/${programId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CivicProgramViewSchema.parse(raw);
}

export async function fetchCivicCases(
  business: string,
): Promise<CivicCaseView[]> {
  const raw = await managementFetch<unknown>(`${base(business)}/civic/cases`);
  return CivicCaseListSchema.parse(raw).items;
}

export async function saveCivicCase(
  business: string,
  caseId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    program_id: string;
    subject_counterparty_id: string;
    case_number: string;
    status: "submitted" | "in_review" | "approved" | "rejected" | "closed";
    summary: string;
    decision_notes?: string;
  },
): Promise<CivicCaseView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/civic/cases/${caseId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CivicCaseViewSchema.parse(raw);
}

export async function fetchCivicAllocations(
  business: string,
): Promise<CivicAllocationView[]> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/civic/allocations`,
  );
  return CivicAllocationListSchema.parse(raw).items;
}

export async function saveCivicAllocation(
  business: string,
  allocationId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    case_id: string;
    allocation_kind:
      | "staffing_placement"
      | "advisory_mandate"
      | "membership_award"
      | "grant_award"
      | "public_permit";
    reference_code: string;
    status: "active" | "suspended" | "revoked" | "expired";
    effective_from: string;
    effective_until?: string | null;
  },
): Promise<CivicAllocationView> {
  const raw = await managementFetch<unknown>(
    `${base(business)}/civic/allocations/${allocationId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CivicAllocationViewSchema.parse(raw);
}
