import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const sourcePlatformSchema = z.enum([
  "quickbooks",
  "zoho",
  "odoo",
  "shopify",
  "square",
  "excel_csv",
]);
export type SourcePlatform = z.infer<typeof sourcePlatformSchema>;

export const migrationEntitySchema = z.enum([
  "counterparties",
  "mrp_materials",
  "eam_assets",
  "payroll_profiles",
]);
export type MigrationEntityKind = z.infer<typeof migrationEntitySchema>;

export const migrationRowErrorSchema = z.object({
  row_number: z.number().int(),
  message: z.string(),
});

export const migrationImportResponseSchema = z.object({
  source_platform: sourcePlatformSchema,
  entity_kind: migrationEntitySchema,
  dry_run: z.boolean(),
  parsed_count: z.number().int(),
  imported_count: z.number().int(),
  skipped_count: z.number().int(),
  errors: z.array(migrationRowErrorSchema),
  preview_rows: z.array(z.record(z.string(), z.unknown())),
});
export type MigrationImportResponse = z.infer<
  typeof migrationImportResponseSchema
>;

export const sampleSandboxResponseSchema = z.object({
  action: z.enum(["seeded", "cleared"]),
  summary: z.record(z.string(), z.number().int()),
  message: z.string(),
});
export type SampleSandboxResponse = z.infer<typeof sampleSandboxResponseSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/migration`;
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
  if (!parsed.success) {
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Migration API returned unexpected data. Please retry.",
      response.status,
    );
  }
  return parsed.data;
}

export async function importMigrationCsv(
  businessId: string,
  input: {
    source_platform: SourcePlatform;
    entity_kind: MigrationEntityKind;
    csv_text: string;
    dry_run: boolean;
  },
): Promise<MigrationImportResponse> {
  const res = await authorizedResponse(`${base(businessId)}/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, migrationImportResponseSchema);
}

export async function seedSampleSandbox(
  businessId: string,
): Promise<SampleSandboxResponse> {
  const res = await authorizedResponse(`${base(businessId)}/sample-sandbox`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  return readJson(res, sampleSandboxResponseSchema);
}

export async function clearSampleSandbox(
  businessId: string,
): Promise<SampleSandboxResponse> {
  const res = await authorizedResponse(`${base(businessId)}/sample-sandbox`, {
    method: "DELETE",
    headers: { Accept: "application/json" },
  });
  return readJson(res, sampleSandboxResponseSchema);
}
