import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

/**
 * GORGONA App Hub client: the connector catalog, Scoped API Keys, signed webhooks
 * and the native MCP endpoint. Every request goes through `authorizedResponse`
 * (allowlisted /v1/businesses/{uuid}/ path, bearer token, timeout, error envelope).
 *
 * One-time secrets (`secret_token`, `signing_secret`) are returned to the caller
 * only; this module never stores or logs them.
 */

export const connectorAuthModeSchema = z.string();

export const connectorSchema = z.object({
  id: z.string(),
  name: z.string(),
  category: z.string(),
  summary: z.string(),
  auth_mode: connectorAuthModeSchema,
  fields: z.array(z.string()),
  us_highlight: z.string(),
  installed: z.boolean(),
  status: z.string().nullable().optional(),
  config_masked: z.record(z.string(), z.unknown()).optional().default({}),
  updated_at: z.string().nullable().optional(),
});
export type Connector = z.infer<typeof connectorSchema>;

export const connectorInstallationSchema = z.object({
  connector_id: z.string(),
  display_name: z.string(),
  category: z.string(),
  status: z.string(),
  config_masked: z.record(z.string(), z.unknown()),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ConnectorInstallation = z.infer<typeof connectorInstallationSchema>;

export const apiKeySchema = z.object({
  id: z.string(),
  name: z.string(),
  key_prefix: z.string(),
  scopes: z.array(z.string()),
  status: z.string(),
  last_used_at: z.string().nullable(),
  created_at: z.string(),
  revoked_at: z.string().nullable(),
});
export type ApiKey = z.infer<typeof apiKeySchema>;

const apiKeyCreatedSchema = z.object({
  key: apiKeySchema,
  secret_token: z.string().startsWith("gorg_live_"),
});
export type ApiKeyCreated = z.infer<typeof apiKeyCreatedSchema>;

export const webhookEndpointSchema = z.object({
  id: z.string(),
  url: z.string(),
  description: z.string(),
  events: z.array(z.string()),
  signing_secret_prefix: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type WebhookEndpoint = z.infer<typeof webhookEndpointSchema>;

const webhookCreatedSchema = z.object({
  endpoint: webhookEndpointSchema,
  signing_secret: z.string().optional(),
});
export type WebhookCreated = z.infer<typeof webhookCreatedSchema>;

export const webhookDeliverySchema = z.object({
  id: z.string(),
  endpoint_id: z.string(),
  event_type: z.string(),
  signature_header: z.string(),
  status: z.string(),
  http_status: z.number().int().nullable(),
  attempts: z.number().int(),
  last_error: z.string().nullable().optional(),
  created_at: z.string(),
  delivered_at: z.string().nullable(),
});
export type WebhookDelivery = z.infer<typeof webhookDeliverySchema>;

export const appHubMetaSchema = z.object({
  allowed_scopes: z.array(z.string()),
  allowed_webhook_events: z.array(z.string()),
  mcp_endpoint: z.string(),
});
export type AppHubMeta = z.infer<typeof appHubMetaSchema>;

/** Used only when the meta route is unavailable; mirrors the backend allow-lists. */
export const FALLBACK_SCOPES = [
  "bookings:read",
  "bookings:write",
  "catalog:read",
  "finance:read",
  "mcp:read",
  "webhooks:manage",
];
export const FALLBACK_WEBHOOK_EVENTS = [
  "booking.cancelled",
  "booking.created",
  "connector.test",
  "invoice.issued",
  "payment.recorded",
  "purchase_order.issued",
  "purchase_order.matched",
  "quote.accepted",
  "quote.created",
  "waitlist.joined",
];

export const oauthProviderStatusSchema = z.object({
  connector_id: z.string(),
  display_name: z.string(),
  configured: z.boolean(),
  scopes: z.array(z.string()),
  callback_url: z.string(),
});
export type OAuthProviderStatus = z.infer<typeof oauthProviderStatusSchema>;

export const oauthStartSchema = z.object({
  connector_id: z.string(),
  configured: z.boolean(),
  authorization_url: z.string().nullable().optional(),
  message: z.string(),
});
export type OAuthStartResult = z.infer<typeof oauthStartSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/connectors`;
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
  const parsed = schema.safeParse(data);
  if (!parsed.success)
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "AMARKAL App Hub returned incomplete information. Please retry.",
      response.status,
    );
  return parsed.data;
}

async function getJson<T>(path: string, schema: z.ZodType<T>): Promise<T> {
  const response = await authorizedResponse(path, {
    headers: { Accept: "application/json" },
  });
  return readJson(response, schema);
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PUT" | "PATCH",
  body: unknown,
  schema: z.ZodType<T>,
): Promise<T> {
  const response = await authorizedResponse(path, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return readJson(response, schema);
}

async function remove(path: string): Promise<void> {
  await authorizedResponse(path, { method: "DELETE" });
}

export function fetchConnectorCatalog(
  businessId: string,
): Promise<Connector[]> {
  return getJson(`${base(businessId)}/catalog`, z.array(connectorSchema));
}

export function fetchAppHubMeta(businessId: string): Promise<AppHubMeta> {
  return getJson(`${base(businessId)}/meta`, appHubMetaSchema);
}

/** Install, reconfigure, pause or resume a connector (PUT replaces its configuration). */
export function saveConnector(
  businessId: string,
  connectorId: string,
  status: "installed" | "paused",
  config: Record<string, string>,
): Promise<ConnectorInstallation> {
  return sendJson(
    `${base(businessId)}/${encodeURIComponent(connectorId)}`,
    "PUT",
    { status, config },
    connectorInstallationSchema,
  );
}

export function removeConnector(
  businessId: string,
  connectorId: string,
): Promise<void> {
  return remove(`${base(businessId)}/${encodeURIComponent(connectorId)}`);
}

export function fetchApiKeys(businessId: string): Promise<ApiKey[]> {
  return getJson(`${base(businessId)}/api-keys`, z.array(apiKeySchema));
}

export function createApiKey(
  businessId: string,
  name: string,
  scopes: string[],
): Promise<ApiKeyCreated> {
  return sendJson(
    `${base(businessId)}/api-keys`,
    "POST",
    { name, scopes },
    apiKeyCreatedSchema,
  );
}

export function revokeApiKey(businessId: string, keyId: string): Promise<void> {
  return remove(`${base(businessId)}/api-keys/${encodeURIComponent(keyId)}`);
}

export function fetchWebhooks(businessId: string): Promise<WebhookEndpoint[]> {
  return getJson(
    `${base(businessId)}/webhooks`,
    z.array(webhookEndpointSchema),
  );
}

export function createWebhook(
  businessId: string,
  input: { url: string; description: string; events: string[] },
): Promise<WebhookCreated> {
  return sendJson(
    `${base(businessId)}/webhooks`,
    "POST",
    input,
    webhookCreatedSchema,
  );
}

export function deleteWebhook(
  businessId: string,
  endpointId: string,
): Promise<void> {
  return remove(
    `${base(businessId)}/webhooks/${encodeURIComponent(endpointId)}`,
  );
}

export function testWebhook(
  businessId: string,
  endpointId: string,
): Promise<WebhookDelivery> {
  return sendJson(
    `${base(businessId)}/webhooks/${encodeURIComponent(endpointId)}/test`,
    "POST",
    undefined,
    webhookDeliverySchema,
  );
}

export function fetchWebhookDeliveries(
  businessId: string,
): Promise<WebhookDelivery[]> {
  return getJson(
    `${base(businessId)}/webhooks/deliveries`,
    z.array(webhookDeliverySchema),
  );
}

export function fetchOAuthProviders(
  businessId: string,
): Promise<OAuthProviderStatus[]> {
  return getJson(
    `${base(businessId)}/oauth/providers`,
    z.array(oauthProviderStatusSchema),
  );
}

export function startConnectorOAuth(
  businessId: string,
  connectorId: string,
): Promise<OAuthStartResult> {
  return sendJson(
    `${base(businessId)}/oauth/${encodeURIComponent(connectorId)}/start`,
    "POST",
    undefined,
    oauthStartSchema,
  );
}

export const byokProviderIdSchema = z.enum([
  "anthropic",
  "google_gemini",
  "openai",
]);
export type ByokProviderId = z.infer<typeof byokProviderIdSchema>;

export const byokProviderCatalogEntrySchema = z.object({
  id: byokProviderIdSchema,
  display_name: z.string(),
  default_model: z.string(),
  suggested_models: z.array(z.string()),
  key_prefix_hint: z.string(),
});
export type ByokProviderCatalogEntry = z.infer<
  typeof byokProviderCatalogEntrySchema
>;

export const byokAiConfigSchema = z.object({
  configured: z.boolean(),
  enabled: z.boolean(),
  provider: byokProviderIdSchema.nullable().optional(),
  model: z.string().nullable().optional(),
  key_hint: z.string().nullable().optional(),
  updated_at: z.string().nullable().optional(),
  supported_providers: z.array(byokProviderCatalogEntrySchema),
});
export type ByokAiConfig = z.infer<typeof byokAiConfigSchema>;

export const byokAiProbeSchema = z.object({
  ok: z.boolean(),
  provider: byokProviderIdSchema,
  model: z.string(),
  http_status: z.number().int().nullable().optional(),
  latency_ms: z.number().int(),
  message: z.string(),
});
export type ByokAiProbeResult = z.infer<typeof byokAiProbeSchema>;

export const customPluginProtocolSchema = z.enum([
  "https_api",
  "mcp_remote",
  "webhook_bridge",
  "oauth2_custom",
]);
export type CustomPluginProtocol = z.infer<typeof customPluginProtocolSchema>;

export const customPluginAuthSchemeSchema = z.enum([
  "Bearer",
  "ApiKey",
  "None",
]);
export type CustomPluginAuthScheme = z.infer<
  typeof customPluginAuthSchemeSchema
>;

export const customPluginSchema = z.object({
  id: z.string(),
  slug: z.string(),
  display_name: z.string(),
  category: z.string(),
  protocol: customPluginProtocolSchema,
  endpoint_url: z.string(),
  auth_header_name: z.string(),
  auth_scheme: customPluginAuthSchemeSchema,
  scopes: z.array(z.string()),
  subscribed_events: z.array(z.string()),
  description: z.string(),
  has_secret: z.boolean(),
  secret_hint: z.string().nullable().optional(),
  status: z.enum(["active", "paused"]),
  created_at: z.string(),
  updated_at: z.string(),
});
export type CustomPlugin = z.infer<typeof customPluginSchema>;

export const customPluginProbeSchema = z.object({
  ok: z.boolean(),
  status: z.enum(["reachable", "unreachable", "local_validated"]),
  http_status: z.number().int().nullable().optional(),
  latency_ms: z.number().int(),
  message: z.string(),
});
export type CustomPluginProbeResult = z.infer<typeof customPluginProbeSchema>;

export function fetchByokAiConfig(businessId: string): Promise<ByokAiConfig> {
  return getJson(`${base(businessId)}/ai-provider`, byokAiConfigSchema);
}

export function saveByokAiConfig(
  businessId: string,
  input: {
    provider: ByokProviderId;
    model?: string;
    api_key?: string;
    enabled: boolean;
  },
): Promise<ByokAiConfig> {
  return sendJson(
    `${base(businessId)}/ai-provider`,
    "PUT",
    input,
    byokAiConfigSchema,
  );
}

export function testByokAiConfig(
  businessId: string,
): Promise<ByokAiProbeResult> {
  return sendJson(
    `${base(businessId)}/ai-provider/test`,
    "POST",
    undefined,
    byokAiProbeSchema,
  );
}

export function deleteByokAiConfig(businessId: string): Promise<void> {
  return remove(`${base(businessId)}/ai-provider`);
}

export function fetchCustomPlugins(
  businessId: string,
): Promise<CustomPlugin[]> {
  return getJson(
    `${base(businessId)}/custom-plugins`,
    z.array(customPluginSchema),
  );
}

export function createCustomPlugin(
  businessId: string,
  input: {
    slug: string;
    display_name: string;
    category: string;
    protocol: CustomPluginProtocol;
    endpoint_url: string;
    auth_header_name: string;
    auth_scheme: CustomPluginAuthScheme;
    auth_credential?: string;
    scopes: string[];
    subscribed_events: string[];
    description: string;
  },
): Promise<CustomPlugin> {
  return sendJson(
    `${base(businessId)}/custom-plugins`,
    "POST",
    input,
    customPluginSchema,
  );
}

export function updateCustomPlugin(
  businessId: string,
  pluginId: string,
  input: {
    status?: "active" | "paused";
    endpoint_url?: string;
    description?: string;
    auth_credential?: string;
    clear_secret?: boolean;
  },
): Promise<CustomPlugin> {
  return sendJson(
    `${base(businessId)}/custom-plugins/${encodeURIComponent(pluginId)}`,
    "PATCH",
    input,
    customPluginSchema,
  );
}

export function deleteCustomPlugin(
  businessId: string,
  pluginId: string,
): Promise<void> {
  return remove(
    `${base(businessId)}/custom-plugins/${encodeURIComponent(pluginId)}`,
  );
}

export function probeCustomPlugin(
  businessId: string,
  pluginId: string,
): Promise<CustomPluginProbeResult> {
  return sendJson(
    `${base(businessId)}/custom-plugins/${encodeURIComponent(pluginId)}/probe`,
    "POST",
    undefined,
    customPluginProbeSchema,
  );
}

/** Config keys that look like credentials are never prefilled or re-sent from masked values. */
export function isSecretField(name: string): boolean {
  return /secret|token|key|password/i.test(name);
}
