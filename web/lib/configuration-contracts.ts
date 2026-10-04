import { z } from "zod";

const instant = z.iso.datetime({ offset: true });
const moduleId = z.string().regex(/^[a-z][a-z_]{1,62}$/);
const readiness = z.enum([
  "planned",
  "implemented",
  "technically_verified",
  "pilot_accepted",
  "production_approved",
]);

export const platformModuleSchema = z.strictObject({
  id: moduleId,
  name: z.string().min(1),
  kind: z.enum(["core", "optional"]),
  depends_on: z.array(moduleId),
  readiness,
  enableable: z.boolean(),
  limits: z.string(),
  stops: z.string(),
});
export const moduleCatalogSchema = z
  .strictObject({
    schema_version: z.literal(1),
    registry_version: z.number().int().positive(),
    minimum_readiness: readiness,
    modules: z.array(platformModuleSchema).min(1),
  })
  .refine(
    (catalog) =>
      new Set(catalog.modules.map((item) => item.id)).size ===
        catalog.modules.length &&
      catalog.modules.every(
        (item) => !(item.kind === "core" && item.enableable),
      ),
  );

const scenario = z.strictObject({
  id: z.string().regex(/^[A-Z]+-\d{2}$/),
  status: readiness,
  scope: z.string(),
  implementation_owner: z.string().nullable(),
  industry_acceptance_owner: z.string().nullable(),
  code_version: z.string().nullable(),
  schema_version: z.number().int().positive().nullable(),
  settings_version: z.number().int().positive().nullable(),
  evidence: z.array(z.string()),
  verified_on: z.iso.date().nullable(),
});
export const readinessRegistrySchema = z.strictObject({
  schema_version: z.literal(1),
  registry_version: z.number().int().positive(),
  statuses: z.array(readiness).length(5),
  scenarios: z.array(scenario).length(28),
  profiles: z
    .array(
      z.strictObject({
        industry_id: z.number().int().min(1).max(39),
        status: readiness,
        limitations: z.string(),
      }),
    )
    .length(39),
});

const problem = z.strictObject({
  code: z.enum([
    "MODULE_NOT_READY",
    "DEPENDENCY_MISSING",
    "REGISTRY_CHANGED",
    "PROFILE_OUTDATED",
  ]),
  module_id: moduleId.nullable(),
  message: z.string(),
});
const state = z.enum(["draft", "validated", "published", "superseded"]);
export const configurationVersionSchema = z.strictObject({
  schema_version: z.literal(1),
  business_id: z.uuid(),
  version: z.number().int().positive(),
  state,
  revision: z.number().int().positive(),
  profile_revision: z.number().int().positive(),
  registry_version: z.number().int().positive(),
  module_ids: z.array(moduleId),
  created_at: instant,
  validation: z
    .strictObject({
      registry_version: z.number().int().positive(),
      problems: z.array(problem),
      warnings: z.array(problem),
    })
    .nullable(),
  validated_at: instant.nullable(),
  published_at: instant.nullable(),
  superseded_at: instant.nullable(),
  superseded_by_version: z.number().int().positive().nullable(),
});
export const configurationSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    registry_version: z.number().int().positive(),
    baseline: z.boolean(),
    published: configurationVersionSchema.nullable(),
    latest: configurationVersionSchema.nullable(),
    effective_module_ids: z.array(moduleId),
  })
  .refine(
    (view) =>
      view.baseline === (view.published === null) &&
      (view.published === null || view.published.state === "published") &&
      [view.published, view.latest].every(
        (item) => item === null || item.business_id === view.business_id,
      ),
  );
export const configurationVersionListSchema = z
  .strictObject({
    schema_version: z.literal(1),
    business_id: z.uuid(),
    items: z.array(configurationVersionSchema).max(100),
    next_cursor: z.number().int().positive().nullable(),
  })
  .refine((page) =>
    page.items.every((item) => item.business_id === page.business_id),
  );
export const configurationPreviewSchema = z.strictObject({
  schema_version: z.literal(1),
  business_id: z.uuid(),
  version: z.number().int().positive(),
  compared_to_version: z.number().int().positive().nullable(),
  enabling: z.array(moduleId),
  disabling: z.array(moduleId),
  stopping: z.array(z.strictObject({ module_id: moduleId, stops: z.string() })),
  industries_added: z.array(z.number().int().min(1).max(39)),
  industries_removed: z.array(z.number().int().min(1).max(39)),
  profile_revision: z.number().int().positive(),
  latest_profile_revision: z.number().int().positive().nullable(),
  problems: z.array(problem),
  warnings: z.array(problem),
});

export type PlatformModule = z.infer<typeof platformModuleSchema>;
export type ModuleCatalog = z.infer<typeof moduleCatalogSchema>;
export type ReadinessRegistry = z.infer<typeof readinessRegistrySchema>;
export type ConfigurationProblem = z.infer<typeof problem>;
export type ConfigurationVersion = z.infer<typeof configurationVersionSchema>;
export type Configuration = z.infer<typeof configurationSchema>;
export type ConfigurationVersionPage = z.infer<
  typeof configurationVersionListSchema
>;
export type ConfigurationPreview = z.infer<typeof configurationPreviewSchema>;
