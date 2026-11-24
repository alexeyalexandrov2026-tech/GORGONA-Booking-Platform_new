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
}

async function authHeaders(): Promise<HeadersInit> {
  const token = await accessToken();
  if (!token) throw new Error("Please sign in before continuing.");
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
  };
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
  if (!res.ok) {
    let message = "Could not create your business workspace.";
    try {
      const body = (await res.json()) as {
        error?: { message?: string };
        detail?: string;
      };
      if (body.error?.message) message = body.error.message;
      else if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* ignore non-JSON error body */
    }
    throw new Error(message);
  }
  return registerBusinessResultSchema.parse(await res.json());
}
