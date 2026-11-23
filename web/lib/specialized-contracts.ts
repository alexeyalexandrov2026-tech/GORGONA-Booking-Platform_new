// SPECIAL-05: strict Zod contracts for /specialized/ UI (SPECIAL-01..04).
import { z } from "zod";
import { type MembershipSummary } from "./enterprise-contracts";

const uuid = z.string().uuid();
const isoDateTime = z.string().min(1);
const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
const currency = z.string().regex(/^[A-Z]{3}$/);

// --- SPECIAL-01 (hospitality_events) ---
export const SpecialProgramViewSchema = z
  .object({
    schema_version: z.literal(1),
    program_id: uuid,
    location_id: uuid,
    code: z.string(),
    title: z.string(),
    program_kind: z.enum([
      "education_cohort",
      "fitness_membership",
      "club_pass",
    ]),
    capacity: z.number().int(),
    enrolled_count: z.number().int(),
    included_sessions: z.number().int(),
    price_minor: z.number().int(),
    currency,
    is_active: z.boolean(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type SpecialProgramView = z.infer<typeof SpecialProgramViewSchema>;

export const SpecialProgramListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(SpecialProgramViewSchema),
  })
  .strict();

export const SpecialEnrollmentViewSchema = z
  .object({
    schema_version: z.literal(1),
    enrollment_id: uuid,
    location_id: uuid,
    program_id: uuid,
    participant_counterparty_id: uuid,
    status: z.enum(["active", "completed", "cancelled"]),
    sessions_used: z.number().int(),
    sessions_total: z.number().int(),
    result_grade: z.string().nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type SpecialEnrollmentView = z.infer<typeof SpecialEnrollmentViewSchema>;

// --- SPECIAL-02 (clinical_care) ---
export const CareSubjectViewSchema = z
  .object({
    schema_version: z.literal(1),
    subject_id: uuid,
    location_id: uuid,
    guardian_counterparty_id: uuid,
    subject_kind: z.enum([
      "human_patient",
      "animal_patient",
      "social_care_recipient",
    ]),
    code: z.string(),
    display_name: z.string(),
    species_or_profile: z.string().nullable(),
    allergies_summary: z.string().nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type CareSubjectView = z.infer<typeof CareSubjectViewSchema>;

export const CareSubjectListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(CareSubjectViewSchema),
  })
  .strict();

export const CareConsentViewSchema = z
  .object({
    schema_version: z.literal(1),
    consent_id: uuid,
    location_id: uuid,
    subject_id: uuid,
    scope: z.enum(["care_records", "procedures", "medication", "sharing"]),
    status: z.enum(["active", "revoked"]),
    granted_by_name: z.string(),
    revoked_at: isoDateTime.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type CareConsentView = z.infer<typeof CareConsentViewSchema>;

export const CareConsentListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(CareConsentViewSchema),
  })
  .strict();

export const CareEncounterViewSchema = z
  .object({
    schema_version: z.literal(1),
    encounter_id: uuid,
    location_id: uuid,
    subject_id: uuid,
    consent_id: uuid,
    plan_id: uuid.nullable(),
    encounter_date: isoDate,
    summary: z.string(),
    clinical_notes: z.string().nullable(),
    consent_active: z.boolean(),
    recorded_by: uuid,
    recorded_at: isoDateTime,
  })
  .strict();
export type CareEncounterView = z.infer<typeof CareEncounterViewSchema>;

export const CareEncounterListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(CareEncounterViewSchema),
  })
  .strict();

// --- SPECIAL-03 (assets) ---
export const ManagedAssetViewSchema = z
  .object({
    schema_version: z.literal(1),
    asset_id: uuid,
    location_id: uuid,
    owner_counterparty_id: uuid.nullable(),
    asset_domain: z.enum([
      "agriculture_plot",
      "utility_infrastructure",
      "mining_equipment",
      "security_post",
      "facility_system",
      "environmental_site",
    ]),
    code: z.string(),
    name: z.string(),
    status: z.enum([
      "active",
      "maintenance",
      "out_of_service",
      "decommissioned",
    ]),
    serial_or_parcel: z.string(),
    next_inspection_due: isoDate.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    updated_at: isoDateTime,
  })
  .strict();
export type ManagedAssetView = z.infer<typeof ManagedAssetViewSchema>;

export const ManagedAssetListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(ManagedAssetViewSchema),
  })
  .strict();

export const AssetIncidentViewSchema = z
  .object({
    schema_version: z.literal(1),
    incident_id: uuid,
    location_id: uuid,
    asset_id: uuid,
    incident_kind: z.enum([
      "safety_hazard",
      "environmental_spill",
      "security_breach",
      "utility_outage",
      "equipment_failure",
    ]),
    severity: z.enum(["low", "medium", "high", "critical"]),
    status: z.enum(["open", "contained", "resolved"]),
    description: z.string(),
    resolution_summary: z.string(),
    occurred_at: isoDateTime,
    resolved_at: isoDateTime.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    updated_at: isoDateTime,
  })
  .strict();
export type AssetIncidentView = z.infer<typeof AssetIncidentViewSchema>;

export const AssetIncidentListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(AssetIncidentViewSchema),
  })
  .strict();

// --- SPECIAL-04 (public_civic) ---
export const CivicProgramViewSchema = z
  .object({
    schema_version: z.literal(1),
    program_id: uuid,
    location_id: uuid,
    program_domain: z.enum([
      "advisory_engagement",
      "staffing_requisition",
      "membership_program",
      "public_service_program",
    ]),
    code: z.string(),
    title: z.string(),
    status: z.enum(["active", "paused", "closed"]),
    requires_dual_review: z.boolean(),
    revision: z.number().int(),
    recorded_by: uuid,
    updated_at: isoDateTime,
  })
  .strict();
export type CivicProgramView = z.infer<typeof CivicProgramViewSchema>;

export const CivicProgramListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(CivicProgramViewSchema),
  })
  .strict();

export const CivicCaseViewSchema = z
  .object({
    schema_version: z.literal(1),
    case_id: uuid,
    location_id: uuid,
    program_id: uuid,
    subject_counterparty_id: uuid,
    case_number: z.string(),
    status: z.enum([
      "submitted",
      "in_review",
      "approved",
      "rejected",
      "closed",
    ]),
    summary: z.string(),
    decision_notes: z.string(),
    submitted_by: uuid,
    decided_by: uuid.nullable(),
    decided_at: isoDateTime.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    updated_at: isoDateTime,
  })
  .strict();
export type CivicCaseView = z.infer<typeof CivicCaseViewSchema>;

export const CivicCaseListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(CivicCaseViewSchema),
  })
  .strict();

export const CivicAllocationViewSchema = z
  .object({
    schema_version: z.literal(1),
    allocation_id: uuid,
    location_id: uuid,
    case_id: uuid,
    allocation_kind: z.enum([
      "staffing_placement",
      "advisory_mandate",
      "membership_award",
      "grant_award",
      "public_permit",
    ]),
    reference_code: z.string(),
    status: z.enum(["active", "suspended", "revoked", "expired"]),
    effective_from: isoDate,
    effective_until: isoDate.nullable(),
    revision: z.number().int(),
    recorded_by: uuid,
    updated_at: isoDateTime,
  })
  .strict();
export type CivicAllocationView = z.infer<typeof CivicAllocationViewSchema>;

export const CivicAllocationListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(CivicAllocationViewSchema),
  })
  .strict();

export function specializedResponseSchema(
  subpath: string,
  method: string,
): z.ZodTypeAny | null {
  const path = subpath.split("?")[0] ?? subpath;
  const upper = method.toUpperCase();
  if (path === "/special-venues/programs" && upper === "GET") {
    return SpecialProgramListSchema;
  }
  if (/^\/special-venues\/programs\/[^/]+$/.test(path) && upper === "PUT") {
    return SpecialProgramViewSchema;
  }
  if (/^\/special-venues\/enrollments\/[^/]+$/.test(path) && upper === "PUT") {
    return SpecialEnrollmentViewSchema;
  }
  if (path === "/care/subjects" && upper === "GET") {
    return CareSubjectListSchema;
  }
  if (/^\/care\/subjects\/[^/]+$/.test(path) && upper === "PUT") {
    return CareSubjectViewSchema;
  }
  if (path === "/care/consents" && upper === "GET") {
    return CareConsentListSchema;
  }
  if (/^\/care\/consents\/[^/]+$/.test(path) && upper === "PUT") {
    return CareConsentViewSchema;
  }
  if (path === "/care/encounters" && upper === "GET") {
    return CareEncounterListSchema;
  }
  if (/^\/care\/encounters\/[^/]+$/.test(path) && upper === "PUT") {
    return CareEncounterViewSchema;
  }
  if (path === "/assets/items" && upper === "GET") {
    return ManagedAssetListSchema;
  }
  if (/^\/assets\/items\/[^/]+$/.test(path) && upper === "PUT") {
    return ManagedAssetViewSchema;
  }
  if (path === "/assets/incidents" && upper === "GET") {
    return AssetIncidentListSchema;
  }
  if (/^\/assets\/incidents\/[^/]+$/.test(path) && upper === "PUT") {
    return AssetIncidentViewSchema;
  }
  if (path === "/civic/programs" && upper === "GET") {
    return CivicProgramListSchema;
  }
  if (/^\/civic\/programs\/[^/]+$/.test(path) && upper === "PUT") {
    return CivicProgramViewSchema;
  }
  if (path === "/civic/cases" && upper === "GET") {
    return CivicCaseListSchema;
  }
  if (/^\/civic\/cases\/[^/]+$/.test(path) && upper === "PUT") {
    return CivicCaseViewSchema;
  }
  if (path === "/civic/allocations" && upper === "GET") {
    return CivicAllocationListSchema;
  }
  if (/^\/civic\/allocations\/[^/]+$/.test(path) && upper === "PUT") {
    return CivicAllocationViewSchema;
  }
  return null;
}

export function canReadSpecialized(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation)) {
    return false;
  }
  return ["owner", "manager", "front_desk", "artist"].includes(member.role);
}

export function canManageSpecialized(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation)) {
    return false;
  }
  return member.role === "owner" || member.role === "manager";
}
