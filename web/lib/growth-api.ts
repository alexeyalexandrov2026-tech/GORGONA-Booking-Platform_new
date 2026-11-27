import { z } from "zod";
import { accessToken } from "./auth";

export const recommendedSlotSchema = z.object({
  location_id: z.string(),
  location_name: z.string(),
  variant_id: z.string(),
  service_name: z.string(),
  variant_name: z.string(),
  resource_id: z.string(),
  resource_name: z.string(),
  day: z.string(),
  start_at: z.string(),
  end_at: z.string(),
  timezone: z.string(),
  price_cents: z.number().int(),
  currency: z.string(),
  duration_minutes: z.number().int(),
});
export type RecommendedSlot = z.infer<typeof recommendedSlotSchema>;

export const customerAssistantSchema = z.object({
  version: z.literal(1),
  engine: z.enum(["cloudflare", "gemini", "grounded"]),
  business_name: z.string(),
  reply: z.string(),
  recommended_slots: z.array(recommendedSlotSchema),
  waitlist_suggested: z.boolean(),
  cancellation_summary: z.string(),
});
export type CustomerAssistantResponse = z.infer<typeof customerAssistantSchema>;

export const waitlistEntrySchema = z.object({
  id: z.string(),
  location_id: z.string(),
  location_name: z.string(),
  variant_id: z.string(),
  variant_name: z.string(),
  service_name: z.string(),
  price_cents: z.number().int(),
  currency: z.string(),
  preferred_resource_id: z.string().nullable(),
  preferred_day: z.string(),
  preferred_window: z.string(),
  customer_name: z.string(),
  contact_channel: z.string(),
  contact_masked: z.string(),
  notes: z.string(),
  status: z.string(),
  offered_at: z.string().nullable(),
  offer_notification_id: z.string().nullable(),
  created_at: z.string(),
});
export type WaitlistEntry = z.infer<typeof waitlistEntrySchema>;

export const growthSettingsSchema = z.object({
  tenant_id: z.string(),
  google_review_url: z.string().nullable(),
  reminder_hours_before: z.number().int(),
  review_delay_hours: z.number().int(),
  rebooking_days_after: z.number().int(),
  waitlist_auto_offer: z.boolean(),
  ai_assistant_enabled: z.boolean(),
  ai_assistant_tone: z.string(),
  updated_at: z.string().nullable(),
});
export type GrowthSettings = z.infer<typeof growthSettingsSchema>;

export const copilotInsightSchema = z.object({
  priority: z.enum(["high", "medium", "low"]),
  category: z.string(),
  title: z.string(),
  detail: z.string(),
  action_path: z.string(),
});

export const ownerCopilotSchema = z.object({
  version: z.literal(1),
  engine: z.enum(["cloudflare", "gemini", "grounded"]),
  business_name: z.string(),
  reply: z.string(),
  metrics: z.record(z.string(), z.unknown()),
  insights: z.array(copilotInsightSchema),
});
export type OwnerCopilotResponse = z.infer<typeof ownerCopilotSchema>;

async function authHeaders(): Promise<HeadersInit> {
  const token = await accessToken();
  if (!token) throw new Error("Sign in required.");
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
  };
}

export async function askCustomerAssistant(input: {
  message: string;
  location_id?: string;
  preferred_day?: string;
}): Promise<CustomerAssistantResponse> {
  const res = await fetch("/v1/customer/assistant", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    let msg = "AI Assistant is unavailable right now.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === "string") msg = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return customerAssistantSchema.parse(await res.json());
}

export async function joinCustomerWaitlist(input: {
  location_id: string;
  variant_id: string;
  preferred_resource_id: string | null;
  preferred_day: string;
  preferred_window: "any" | "morning" | "afternoon" | "evening";
  customer_name: string;
  contact_channel: "email" | "sms";
  contact_value: string;
  notes?: string;
}): Promise<WaitlistEntry> {
  const res = await fetch("/v1/customer/waitlist", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    let msg = "Unable to join waitlist. Please check your contact details.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === "string") msg = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return waitlistEntrySchema.parse(await res.json());
}

export async function fetchGrowthSettings(
  salonId: string,
): Promise<GrowthSettings> {
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/growth/settings`,
    { headers: await authHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new Error("Unable to load growth settings.");
  return growthSettingsSchema.parse(await res.json());
}

export async function saveGrowthSettings(
  salonId: string,
  input: {
    google_review_url: string | null;
    reminder_hours_before: number;
    review_delay_hours: number;
    rebooking_days_after: number;
    waitlist_auto_offer: boolean;
    ai_assistant_enabled: boolean;
    ai_assistant_tone:
      "warm_professional" | "concise_direct" | "executive_hospitality";
  },
): Promise<GrowthSettings> {
  const headers = await authHeaders();
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/growth/settings`,
    {
      method: "PUT",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!res.ok) {
    let msg = "Failed to save growth settings.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === "string") msg = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return growthSettingsSchema.parse(await res.json());
}

export async function fetchWaitlist(salonId: string): Promise<WaitlistEntry[]> {
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/growth/waitlist`,
    { headers: await authHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new Error("Unable to load waitlist.");
  return z.array(waitlistEntrySchema).parse(await res.json());
}

export async function updateWaitlistEntryStatus(
  salonId: string,
  entryId: string,
  status: "waiting" | "offered" | "booked" | "expired" | "cancelled",
): Promise<WaitlistEntry> {
  const headers = await authHeaders();
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/growth/waitlist/${encodeURIComponent(entryId)}/status`,
    {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    },
  );
  if (!res.ok) throw new Error("Failed to update waitlist status.");
  return waitlistEntrySchema.parse(await res.json());
}

export async function askOwnerCopilot(
  salonId: string,
  question?: string,
): Promise<OwnerCopilotResponse> {
  const headers = await authHeaders();
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/copilot`,
    {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ question: question || null }),
    },
  );
  if (!res.ok) throw new Error("Unable to load AI Business Copilot.");
  return ownerCopilotSchema.parse(await res.json());
}

export const readinessStepSchema = z.object({
  key: z.string(),
  title: z.string(),
  detail: z.string(),
  completed: z.boolean(),
  action_path: z.string(),
  action_label: z.string(),
});

export const launchReadinessSchema = z.object({
  business_name: z.string(),
  slug: z.string(),
  booking_state: z.string(),
  score_percent: z.number().int(),
  completed_steps: z.number().int(),
  total_steps: z.number().int(),
  stripe_live_ready: z.boolean(),
  trailing_30d_volume_cents: z.number().int(),
  commission_saved_vs_5pct_cents: z.number().int(),
  steps: z.array(readinessStepSchema),
});
export type LaunchReadiness = z.infer<typeof launchReadinessSchema>;

export async function fetchLaunchReadiness(
  salonId: string,
): Promise<LaunchReadiness> {
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/readiness`,
    { headers: await authHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new Error("Unable to load launch readiness.");
  return launchReadinessSchema.parse(await res.json());
}

export async function downloadBusinessSnapshot(
  salonId: string,
  slug: string,
): Promise<void> {
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/export/snapshot`,
    { headers: await authHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new Error("Unable to export business snapshot.");
  const payload = await res.json();
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  const safeSlug = (slug || "amarkal-business").replace(/[^a-z0-9-_]/gi, "-");
  anchor.download = `${safeSlug}-portable-export.json`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
