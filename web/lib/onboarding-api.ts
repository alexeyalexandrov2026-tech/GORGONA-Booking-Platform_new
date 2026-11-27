import { z } from "zod";
import { accessToken } from "./auth";

export const industryPresetSchema = z.object({
  id: z.number().int().min(1).max(39),
  code: z.string(),
  name: z.string(),
  examples: z.string(),
  naics_sectors: z.array(z.string()),
  workflow_readiness: z.string(),
  enableable_module_ids: z.array(z.string()),
  pending_module_ids: z.array(z.string()),
});
export type IndustryPreset = z.infer<typeof industryPresetSchema>;

const presetsResponseSchema = z.object({
  industries: z.array(industryPresetSchema),
});

export const onboardingStatusSchema = z.object({
  linked: z.boolean(),
  user_id: z.string().nullable(),
  display_name: z.string(),
  email: z.string().nullable(),
  can_create_business: z.boolean(),
  businesses: z.array(
    z.object({
      business_id: z.string(),
      business_name: z.string(),
      role: z.string(),
      status: z.string(),
    }),
  ),
});
export type OnboardingStatus = z.infer<typeof onboardingStatusSchema>;

export const registerBusinessResultSchema = z.object({
  schema_version: z.literal(1),
  business_id: z.string(),
  slug: z.string(),
  business_name: z.string(),
  location_id: z.string(),
  location_name: z.string(),
  timezone: z.string(),
  user_id: z.string(),
  membership_id: z.string(),
  role: z.literal("owner"),
  profile_revision: z.number().int(),
  configuration_version: z.number().int(),
  industry_ids: z.array(z.number().int()),
  effective_module_ids: z.array(z.string()),
  pending_module_ids: z.array(z.string()),
  created_services_count: z.number().int().optional().default(0),
  created_resources_count: z.number().int().optional().default(0),
  created_hours_count: z.number().int().optional().default(0),
});
export type RegisterBusinessResult = z.infer<
  typeof registerBusinessResultSchema
>;

export interface RegisterBusinessInput {
  business_name: string;
  slug: string;
  location_name: string;
  timezone: string;
  industry_ids: number[];
  business_formats: string[];
  custom_activity_name?: string | null;
  /** Human-approved AI Business Architect starter data (optional). */
  starter_services?: StarterService[];
  starter_resources?: StarterResource[];
  starter_hours?: StarterHours[];
  cancellation_summary?: string | null;
}

export const RESOURCE_KINDS = ["artist", "chair", "room", "equipment"] as const;
export type ResourceKind = (typeof RESOURCE_KINDS)[number];

export interface StarterService {
  code: string;
  name: string;
  duration_minutes: number;
  price_cents: number;
  currency: "USD";
}
export interface StarterResource {
  display_name: string;
  kind: ResourceKind;
}
export interface StarterHours {
  weekday: number;
  opens_minute: number;
  closes_minute: number;
}

/** Limits enforced by POST /v1/onboarding/ai-blueprint and /v1/onboarding/businesses. */
export const BLUEPRINT_LIMITS = {
  descriptionMin: 8,
  descriptionMax: 2000,
  imageDataUrlMax: 5_500_000,
  imageBytesMax: 4_000_000,
  servicesMax: 12,
  resourcesMax: 8,
  serviceNameMin: 2,
  serviceNameMax: 160,
  resourceNameMin: 2,
  resourceNameMax: 120,
  durationMin: 10,
  durationMax: 480,
  priceCentsMax: 5_000_000,
  cancellationMax: 300,
} as const;

export const aiBlueprintSchema = z.object({
  schema_version: z.literal(1),
  engine: z.string(),
  model: z.string(),
  business_name: z.string(),
  slug: z.string(),
  location_name: z.string(),
  timezone: z.string(),
  industry_ids: z.array(z.number().int()),
  business_formats: z.array(z.string()),
  enableable_module_ids: z.array(z.string()),
  pending_module_ids: z.array(z.string()),
  services: z.array(
    z.object({
      code: z.string(),
      name: z.string(),
      duration_minutes: z.number().int(),
      price_cents: z.number().int(),
      currency: z.string(),
    }),
  ),
  resources: z.array(z.object({ display_name: z.string(), kind: z.string() })),
  business_hours: z.array(
    z.object({
      weekday: z.number().int(),
      opens_minute: z.number().int(),
      closes_minute: z.number().int(),
    }),
  ),
  cancellation_summary: z.string(),
  recommended_connectors: z.array(z.string()),
  rationale: z.string(),
});
export type AiBlueprint = z.infer<typeof aiBlueprintSchema>;

async function authHeaders(): Promise<HeadersInit> {
  const token = await accessToken();
  if (!token) throw new Error("Please sign in before continuing.");
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
  };
}

async function optionalAuthHeaders(): Promise<HeadersInit> {
  const token = await accessToken();
  return token
    ? {
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      }
    : { Accept: "application/json" };
}

export async function fetchOnboardingPresets(): Promise<IndustryPreset[]> {
  const res = await fetch("/v1/onboarding/presets", {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Unable to load the 39-industry catalog.");
  return presetsResponseSchema.parse(await res.json()).industries;
}

export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  const res = await fetch("/v1/onboarding/status", {
    headers: await authHeaders(),
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Unable to verify your onboarding status.");
  return onboardingStatusSchema.parse(await res.json());
}

async function errorText(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as {
      error?: {
        message?: string;
        details?: { loc?: unknown[]; msg?: string }[];
      };
      detail?: string;
    };
    const first = body.error?.details?.[0];
    if (body.error?.message && first?.msg)
      return `${body.error.message}: ${first.msg}`;
    if (body.error?.message) return body.error.message;
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* ignore non-JSON error body */
  }
  return fallback;
}

/** Draft a business blueprint for human review. Nothing is created by this call. */
export async function requestAiBlueprint(
  input: { description: string; price_list_image_data_url?: string | null },
  signal?: AbortSignal,
): Promise<AiBlueprint> {
  let res: Response;
  try {
    res = await fetch("/v1/onboarding/ai-blueprint", {
      method: "POST",
      headers: {
        ...(await optionalAuthHeaders()),
        "Content-Type": "application/json",
      },
      cache: "no-store",
      body: JSON.stringify({
        description: input.description,
        price_list_image_data_url: input.price_list_image_data_url ?? null,
      }),
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(60000)])
        : AbortSignal.timeout(60000),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new Error(
      "We couldn’t reach the AI Business Architect. Check your connection and try again.",
    );
  }
  if (!res.ok)
    throw new Error(
      await errorText(
        res,
        "The AI Business Architect could not draft a blueprint.",
      ),
    );
  const parsed = aiBlueprintSchema.safeParse(
    await res.json().catch(() => null),
  );
  if (!parsed.success)
    throw new Error(
      "The AI Business Architect returned an incomplete blueprint. Please try again.",
    );
  return parsed.data;
}

export async function registerSelfServiceBusiness(
  input: RegisterBusinessInput,
  idempotencyKey: string,
): Promise<RegisterBusinessResult> {
  const headers = await authHeaders();
  const res = await fetch("/v1/onboarding/businesses", {
    method: "POST",
    headers: {
      ...headers,
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(input),
  });
  if (!res.ok)
    throw new Error(
      await errorText(res, "Could not create your business workspace."),
    );
  return registerBusinessResultSchema.parse(await res.json());
}
