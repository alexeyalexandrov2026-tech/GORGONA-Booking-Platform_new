import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const pluginProtocolSchema = z.enum([
  "https_api",
  "mcp_remote",
  "webhook_bridge",
  "oauth2_custom",
]);
export type PluginProtocol = z.infer<typeof pluginProtocolSchema>;

export const installStatusSchema = z.enum([
  "installed",
  "paused",
  "uninstalled",
]);
export type InstallStatus = z.infer<typeof installStatusSchema>;

export const submissionStatusSchema = z.enum([
  "draft",
  "validated",
  "submitted_for_review",
  "published_private",
]);

export const marketplacePluginCardSchema = z.object({
  slug: z.string(),
  version: z.string(),
  display_name: z.string(),
  publisher_name: z.string(),
  verified: z.boolean(),
  source_tier: z.enum(["official_curated", "tenant_private_sdk"]),
  category: z.string(),
  protocol: pluginProtocolSchema,
  summary: z.string(),
  naics_tags: z.array(z.string()),
  default_endpoint_url: z.string(),
  requested_scopes: z.array(z.string()),
  subscribed_events: z.array(z.string()),
  install_status: installStatusSchema.nullable(),
  installed_at: z.string().nullable(),
});
export type MarketplacePluginCard = z.infer<typeof marketplacePluginCardSchema>;

export const marketplaceInstallationViewSchema = z.object({
  id: z.string(),
  plugin_slug: z.string(),
  plugin_version: z.string(),
  display_name: z.string(),
  publisher_name: z.string(),
  category: z.string(),
  protocol: pluginProtocolSchema,
  endpoint_url: z.string(),
  granted_scopes: z.array(z.string()),
  subscribed_events: z.array(z.string()),
  status: installStatusSchema,
  installed_at: z.string(),
  updated_at: z.string(),
});
export type MarketplaceInstallationView = z.infer<
  typeof marketplaceInstallationViewSchema
>;

export const developerSubmissionViewSchema = z.object({
  id: z.string(),
  plugin_slug: z.string(),
  version: z.string(),
  display_name: z.string(),
  publisher_name: z.string(),
  category: z.string(),
  protocol: pluginProtocolSchema,
  naics_codes: z.array(z.string()),
  manifest_json: z.record(z.string(), z.unknown()),
  validation_status: submissionStatusSchema,
  validation_warnings: z.array(z.string()),
  created_at: z.string(),
});
export type DeveloperSubmissionView = z.infer<
  typeof developerSubmissionViewSchema
>;

export const marketplaceCatalogResponseSchema = z.object({
  catalog: z.array(marketplacePluginCardSchema),
  installations: z.array(marketplaceInstallationViewSchema),
  submissions: z.array(developerSubmissionViewSchema),
  allowed_scopes: z.array(z.string()),
  allowed_events: z.array(z.string()),
  sdk_manifest_template: z.record(z.string(), z.unknown()),
});
export type MarketplaceCatalogResponse = z.infer<
  typeof marketplaceCatalogResponseSchema
>;

export const validateManifestResponseSchema = z.object({
  valid: z.boolean(),
  errors: z.array(z.string()),
  warnings: z.array(z.string()),
  normalized_manifest: z.record(z.string(), z.unknown()).nullable(),
});
export type ValidateManifestResponse = z.infer<
  typeof validateManifestResponseSchema
>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/app-marketplace`;
}

async function readJson<T>(
  response: Response,
  schema: z.ZodType<T>,
): Promise<T> {
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
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
      "Plugin Marketplace API returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchMarketplaceCatalog(
  businessId: string,
): Promise<MarketplaceCatalogResponse> {
  const res = await authorizedResponse(`${base(businessId)}/catalog`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, marketplaceCatalogResponseSchema);
}

export async function installMarketplacePlugin(
  businessId: string,
  input: {
    plugin_slug: string;
    endpoint_url?: string | null;
    granted_scopes?: string[] | null;
  },
): Promise<MarketplaceInstallationView> {
  const res = await authorizedResponse(`${base(businessId)}/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, marketplaceInstallationViewSchema);
}

export async function updateInstallationStatus(
  businessId: string,
  pluginSlug: string,
  status: InstallStatus,
): Promise<MarketplaceInstallationView> {
  const res = await authorizedResponse(
    `${base(businessId)}/installations/${encodeURIComponent(pluginSlug)}/status`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ status }),
    },
  );
  return readJson(res, marketplaceInstallationViewSchema);
}

export async function validateDeveloperManifest(
  businessId: string,
  manifest: Record<string, unknown>,
): Promise<ValidateManifestResponse> {
  const res = await authorizedResponse(`${base(businessId)}/sdk/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ manifest }),
  });
  return readJson(res, validateManifestResponseSchema);
}

export async function submitDeveloperManifest(
  businessId: string,
  manifest: Record<string, unknown>,
  publishMode: "published_private" | "submitted_for_review",
): Promise<DeveloperSubmissionView> {
  const res = await authorizedResponse(`${base(businessId)}/sdk/submissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ manifest, publish_mode: publishMode }),
  });
  return readJson(res, developerSubmissionViewSchema);
}
