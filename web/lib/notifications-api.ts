import { z } from "zod";
import { accessToken } from "./auth";

export const channelReadinessSchema = z.object({
  mode: z.enum(["sandbox", "live"]),
  provider: z.string(),
  production_credentials_configured: z.boolean(),
  missing_production_env_vars: z.array(z.string()),
});

export const notificationReadinessSchema = z.object({
  salon_id: z.string(),
  templates: z.array(z.string()),
  channels: z.object({
    email: channelReadinessSchema,
    sms: channelReadinessSchema,
  }),
});
export type NotificationReadiness = z.infer<typeof notificationReadinessSchema>;

export const notificationOutboxItemSchema = z.object({
  id: z.string(),
  channel: z.enum(["email", "sms"]),
  template_code: z.string(),
  recipient_masked: z.string(),
  subject: z.string(),
  body_preview: z.string(),
  idempotency_key: z.string(),
  status: z.string(),
  attempt_count: z.number().int(),
  max_attempts: z.number().int(),
  provider_name: z.string(),
  provider_message_id: z.string().nullable(),
  last_error: z.string().nullable(),
  created_at: z.string(),
  sent_at: z.string().nullable(),
});
export type NotificationOutboxItem = z.infer<
  typeof notificationOutboxItemSchema
>;

export interface SendTestNotificationInput {
  channel: "email" | "sms";
  template_code: string;
  recipient: string;
  variables: Record<string, string>;
  idempotency_key: string;
}

async function authHeaders(): Promise<HeadersInit> {
  const token = await accessToken();
  if (!token) throw new Error("Sign in required.");
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/json",
  };
}

export async function fetchNotificationReadiness(
  salonId: string,
): Promise<NotificationReadiness> {
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/notifications/readiness`,
    { headers: await authHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new Error("Unable to load notification readiness.");
  return notificationReadinessSchema.parse(await res.json());
}

export async function fetchNotificationOutbox(
  salonId: string,
  limit = 10,
): Promise<NotificationOutboxItem[]> {
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/notifications/outbox?limit=${limit}`,
    { headers: await authHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new Error("Unable to load notification outbox.");
  return z.array(notificationOutboxItemSchema).parse(await res.json());
}

export async function sendTestNotification(
  salonId: string,
  input: SendTestNotificationInput,
): Promise<NotificationOutboxItem> {
  const headers = await authHeaders();
  const res = await fetch(
    `/v1/businesses/${encodeURIComponent(salonId)}/notifications/enqueue`,
    {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ ...input, dispatch_now: true }),
    },
  );
  if (!res.ok) {
    let msg = "Failed to send notification.";
    try {
      const data = (await res.json()) as { detail?: string };
      if (typeof data.detail === "string") msg = data.detail;
    } catch {
      /* ignore non-JSON body */
    }
    throw new Error(msg);
  }
  return notificationOutboxItemSchema.parse(await res.json());
}
