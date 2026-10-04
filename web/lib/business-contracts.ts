import { z } from "zod";

const formats = z.enum(["b2b", "b2c", "marketplace", "franchise", "holding"]);
const unique = <T>(values: T[]) => new Set(values).size === values.length;
const industries = z
  .array(z.number().int().min(1).max(39))
  .min(1)
  .max(39)
  .refine(unique);
export const businessProfileSchema = z.object({
  schema_version: z.literal(1),
  business_id: z.uuid(),
  revision: z.number().int().positive(),
  catalog_version: z.literal(1),
  state: z.literal("draft"),
  industry_ids: industries,
  business_formats: z.array(formats).max(5).refine(unique),
  custom_activity_name: z.string().min(1).max(200).nullable(),
  created_at: z.iso.datetime({ offset: true }),
});
export const businessSchema = z.object({
  schema_version: z.literal(1),
  business_id: z.uuid(),
  display_name: z.string(),
  locations: z.array(
    z.object({ id: z.uuid(), name: z.string(), timezone: z.string() }),
  ),
  profile: businessProfileSchema.nullable(),
});
export const industryCatalogSchema = z.object({
  schema_version: z.literal(1),
  catalog_version: z.literal(1),
  classification: z.literal("NAICS-2022-sector-mapping"),
  industries: z
    .array(
      z.object({
        id: z.number().int().min(1).max(39),
        code: z.string().min(1),
        name: z.string().min(1),
        examples: z.string(),
        naics_sectors: z.array(z.string()),
        workflow_readiness: z.enum([
          "planned",
          "implemented",
          "technically_verified",
          "pilot_accepted",
          "production_approved",
        ]),
      }),
    )
    .length(39)
    .refine(
      (items) =>
        unique(items.map((item) => item.id)) &&
        unique(items.map((item) => item.code)),
    ),
  business_formats: z.array(formats).refine(unique),
});
export type Business = z.infer<typeof businessSchema>;
export type BusinessProfile = z.infer<typeof businessProfileSchema>;
export type IndustryCatalog = z.infer<typeof industryCatalogSchema>;
export type BusinessFormat = z.infer<typeof formats>;
export interface ProfileInput {
  schema_version: 1;
  catalog_version: 1;
  expected_revision: number;
  industry_ids: number[];
  business_formats: BusinessFormat[];
  custom_activity_name: string | null;
}
