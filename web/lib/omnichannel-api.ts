import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const channelTypeSchema = z.enum([
  "email",
  "voice_pbx",
  "sms",
  "whatsapp",
  "web_chat",
]);
export type ChannelType = z.infer<typeof channelTypeSchema>;

export const messageChannelTypeSchema = z.enum([
  "email",
  "voice_pbx",
  "sms",
  "whatsapp",
  "web_chat",
  "internal_note",
]);
export type MessageChannelType = z.infer<typeof messageChannelTypeSchema>;

export const threadStatusSchema = z.enum([
  "open",
  "pending",
  "snoozed",
  "resolved",
]);
export type ThreadStatus = z.infer<typeof threadStatusSchema>;

export const threadPrioritySchema = z.enum(["low", "normal", "high", "urgent"]);
export type ThreadPriority = z.infer<typeof threadPrioritySchema>;

export const callDirectionSchema = z.enum(["inbound", "outbound", "missed"]);
export type CallDirection = z.infer<typeof callDirectionSchema>;

export const callStatusSchema = z.enum([
  "ringing",
  "completed",
  "missed",
  "voicemail",
  "failed",
]);
export type CallStatus = z.infer<typeof callStatusSchema>;

export const callDispositionSchema = z.enum([
  "resolved",
  "follow_up",
  "quote_requested",
  "support_ticket",
  "voicemail_left",
]);
export type CallDisposition = z.infer<typeof callDispositionSchema>;

export const inboxChannelSchema = z.object({
  id: z.string(),
  channel_type: channelTypeSchema,
  display_name: z.string(),
  address_or_number: z.string(),
  mode: z.enum(["built_in", "optional_byok"]),
  provider_label: z.string(),
  is_enabled: z.boolean(),
  auto_greeting: z.string(),
  webhook_token_prefix: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type InboxChannel = z.infer<typeof inboxChannelSchema>;

export const inboxChannelUpsertSchema = z.object({
  channel: inboxChannelSchema,
  webhook_token: z.string().nullable().optional(),
});
export type InboxChannelUpsert = z.infer<typeof inboxChannelUpsertSchema>;

export const inboxThreadSchema = z.object({
  id: z.string(),
  contact_name: z.string(),
  contact_email: z.string().nullable().optional(),
  contact_phone: z.string().nullable().optional(),
  counterparty_id: z.string().nullable().optional(),
  linked_entity_kind: z
    .enum(["quote", "purchase_order", "booking", "work_order"])
    .nullable()
    .optional(),
  linked_entity_ref: z.string().nullable().optional(),
  primary_channel: channelTypeSchema,
  subject: z.string(),
  status: threadStatusSchema,
  priority: threadPrioritySchema,
  unread_count: z.number().int(),
  last_message_preview: z.string(),
  last_message_at: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type InboxThread = z.infer<typeof inboxThreadSchema>;

export const inboxMessageSchema = z.object({
  id: z.string(),
  thread_id: z.string(),
  channel_type: messageChannelTypeSchema,
  direction: z.enum(["inbound", "outbound", "internal"]),
  sender_name: z.string(),
  sender_address: z.string(),
  recipient_address: z.string(),
  subject: z.string(),
  body: z.string(),
  delivery_status: z.enum([
    "received",
    "queued",
    "sent",
    "delivered",
    "failed",
    "logged",
  ]),
  provider_message_id: z.string().nullable().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string(),
});
export type InboxMessage = z.infer<typeof inboxMessageSchema>;

export const inboxCallLogSchema = z.object({
  id: z.string(),
  thread_id: z.string().nullable().optional(),
  direction: callDirectionSchema,
  caller_number: z.string(),
  callee_number: z.string(),
  contact_name: z.string(),
  call_status: callStatusSchema,
  duration_seconds: z.number().int(),
  extension_or_queue: z.string(),
  recording_url: z.string().nullable().optional(),
  transcript_summary: z.string(),
  disposition: callDispositionSchema,
  started_at: z.string(),
  created_at: z.string(),
});
export type InboxCallLog = z.infer<typeof inboxCallLogSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/inbox`;
}

async function readJson<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  let data: unknown;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const detail =
      data &&
      typeof data === "object" &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (HTTP ${response.status}).`;
    throw new ManagementApiError("REQUEST_FAILED", detail, response.status);
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Omnichannel Inbox API returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchInboxChannels(
  businessId: string,
): Promise<InboxChannel[]> {
  const res = await authorizedResponse(`${base(businessId)}/channels`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(inboxChannelSchema));
}

export async function upsertInboxChannel(
  businessId: string,
  input: {
    channel_type: ChannelType;
    display_name: string;
    address_or_number: string;
    mode: "built_in" | "optional_byok";
    provider_label: string;
    is_enabled: boolean;
    auto_greeting: string;
  },
): Promise<InboxChannelUpsert> {
  const res = await authorizedResponse(`${base(businessId)}/channels`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, inboxChannelUpsertSchema);
}

export async function rotateInboxChannelToken(
  businessId: string,
  channelType: ChannelType,
): Promise<InboxChannelUpsert> {
  const res = await authorizedResponse(
    `${base(businessId)}/channels/${encodeURIComponent(channelType)}/rotate-token`,
    { method: "POST", headers: { Accept: "application/json" } },
  );
  return readJson(res, inboxChannelUpsertSchema);
}

export async function fetchInboxThreads(
  businessId: string,
): Promise<InboxThread[]> {
  const res = await authorizedResponse(`${base(businessId)}/threads`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(inboxThreadSchema));
}

export async function createInboxThread(
  businessId: string,
  input: {
    contact_name: string;
    contact_email?: string | null;
    contact_phone?: string | null;
    primary_channel: ChannelType;
    subject: string;
    priority: ThreadPriority;
    linked_entity_ref?: string | null;
    initial_body?: string | null;
  },
): Promise<{ thread: InboxThread; initial_message: InboxMessage | null }> {
  const res = await authorizedResponse(`${base(businessId)}/threads`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(
    res,
    z.object({
      thread: inboxThreadSchema,
      initial_message: inboxMessageSchema
        .nullable()
        .optional()
        .transform((v) => v ?? null),
    }),
  );
}

export async function fetchThreadMessages(
  businessId: string,
  threadId: string,
): Promise<InboxMessage[]> {
  const res = await authorizedResponse(
    `${base(businessId)}/threads/${encodeURIComponent(threadId)}/messages`,
    { headers: { Accept: "application/json" } },
  );
  return readJson(res, z.array(inboxMessageSchema));
}

export async function sendThreadMessage(
  businessId: string,
  threadId: string,
  input: {
    channel_type: MessageChannelType;
    direction: "outbound" | "internal";
    subject?: string;
    body: string;
  },
): Promise<{ message: InboxMessage; thread: InboxThread }> {
  const res = await authorizedResponse(
    `${base(businessId)}/threads/${encodeURIComponent(threadId)}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        channel_type: input.channel_type,
        direction: input.direction,
        subject: input.subject ?? "",
        body: input.body,
      }),
    },
  );
  return readJson(
    res,
    z.object({ message: inboxMessageSchema, thread: inboxThreadSchema }),
  );
}

export async function patchInboxThread(
  businessId: string,
  threadId: string,
  input: { status?: ThreadStatus; priority?: ThreadPriority },
): Promise<InboxThread> {
  const res = await authorizedResponse(
    `${base(businessId)}/threads/${encodeURIComponent(threadId)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return readJson(res, inboxThreadSchema);
}

export async function fetchInboxCalls(
  businessId: string,
): Promise<InboxCallLog[]> {
  const res = await authorizedResponse(`${base(businessId)}/calls`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(inboxCallLogSchema));
}

export async function recordInboxCall(
  businessId: string,
  input: {
    direction: CallDirection;
    caller_number: string;
    callee_number: string;
    contact_name: string;
    call_status: CallStatus;
    duration_seconds: number;
    extension_or_queue: string;
    transcript_summary: string;
    disposition: CallDisposition;
  },
): Promise<InboxCallLog> {
  const res = await authorizedResponse(`${base(businessId)}/calls`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, inboxCallLogSchema);
}
