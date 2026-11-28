import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const materialKindSchema = z.enum(["raw", "subassembly", "finished"]);
export type MaterialKind = z.infer<typeof materialKindSchema>;

export const materialUnitSchema = z.enum([
  "ton",
  "kg",
  "lb",
  "liter",
  "gallon",
  "meter",
  "unit",
  "box",
]);
export type MaterialUnit = z.infer<typeof materialUnitSchema>;

export const mrpMaterialSchema = z.object({
  id: z.string(),
  sku: z.string(),
  name: z.string(),
  material_kind: materialKindSchema,
  unit: materialUnitSchema,
  on_hand_milli: z.number().int(),
  reserved_milli: z.number().int(),
  available_milli: z.number().int(),
  reorder_point_milli: z.number().int(),
  unit_cost_cents: z.number().int(),
  preferred_vendor_name: z.string(),
  preferred_vendor_email: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type MrpMaterial = z.infer<typeof mrpMaterialSchema>;

export const mrpRecipeLineSchema = z.object({
  id: z.string(),
  recipe_id: z.string(),
  component_material_id: z.string(),
  component_sku: z.string(),
  component_name: z.string(),
  component_unit: materialUnitSchema,
  qty_per_batch_milli: z.number().int(),
  scrap_bps: z.number().int(),
  notes: z.string(),
});
export type MrpRecipeLine = z.infer<typeof mrpRecipeLineSchema>;

export const mrpRecipeSchema = z.object({
  id: z.string(),
  code: z.string(),
  name: z.string(),
  output_material_id: z.string(),
  output_sku: z.string(),
  output_name: z.string(),
  output_unit: materialUnitSchema,
  output_qty_milli: z.number().int(),
  lead_time_days: z.number().int(),
  notes: z.string(),
  is_active: z.boolean(),
  lines: z.array(mrpRecipeLineSchema),
  created_at: z.string(),
  updated_at: z.string(),
});
export type MrpRecipe = z.infer<typeof mrpRecipeSchema>;

export const mrpExplosionLineSchema = z.object({
  material_id: z.string(),
  sku: z.string(),
  name: z.string(),
  unit: materialUnitSchema,
  required_milli: z.number().int(),
  on_hand_milli: z.number().int(),
  already_reserved_milli: z.number().int(),
  available_milli: z.number().int(),
  reservable_milli: z.number().int(),
  shortage_milli: z.number().int(),
  unit_cost_cents: z.number().int(),
  estimated_cost_cents: z.number().int(),
  preferred_vendor_name: z.string(),
  preferred_vendor_email: z.string().nullable().optional(),
});
export type MrpExplosionLine = z.infer<typeof mrpExplosionLineSchema>;

export const mrpExplosionSchema = z.object({
  recipe_id: z.string(),
  recipe_code: z.string(),
  recipe_name: z.string(),
  output_material_id: z.string(),
  output_sku: z.string(),
  output_unit: materialUnitSchema,
  target_qty_milli: z.number().int(),
  requirements: z.array(mrpExplosionLineSchema),
  total_material_cost_cents: z.number().int(),
  shortage_count: z.number().int(),
  can_fully_reserve: z.boolean(),
});
export type MrpExplosion = z.infer<typeof mrpExplosionSchema>;

export const mrpReservationSchema = z.object({
  id: z.string(),
  run_id: z.string(),
  material_id: z.string(),
  material_sku: z.string(),
  material_name: z.string(),
  material_unit: materialUnitSchema,
  required_milli: z.number().int(),
  reserved_milli: z.number().int(),
  shortage_milli: z.number().int(),
  unit_cost_cents: z.number().int(),
  status: z.enum(["active", "consumed", "released"]),
});
export type MrpReservation = z.infer<typeof mrpReservationSchema>;

export const mrpProductionRunSchema = z.object({
  id: z.string(),
  run_number: z.string(),
  recipe_id: z.string(),
  recipe_code: z.string(),
  recipe_name: z.string(),
  output_sku: z.string(),
  output_unit: materialUnitSchema,
  target_qty_milli: z.number().int(),
  status: z.enum([
    "planned",
    "reserved",
    "in_progress",
    "completed",
    "cancelled",
  ]),
  scheduled_date: z.string().nullable().optional(),
  estimated_material_cost_cents: z.number().int(),
  shortage_count: z.number().int(),
  draft_po_id: z.string().nullable().optional(),
  notes: z.string(),
  reservations: z.array(mrpReservationSchema),
  completed_at: z.string().nullable().optional(),
  created_at: z.string(),
});
export type MrpProductionRun = z.infer<typeof mrpProductionRunSchema>;

export const assetCategorySchema = z.enum([
  "fleet_vehicle",
  "heavy_machinery",
  "cnc_industrial",
  "hvac_facility",
  "power_generator",
  "iot_sensor_node",
]);
export type AssetCategory = z.infer<typeof assetCategorySchema>;

export const metricKeySchema = z.enum([
  "engine_hours",
  "odometer_miles",
  "temperature_c",
  "vibration_mm_s",
  "oil_pressure_psi",
  "battery_voltage",
  "fuel_mpg",
]);
export type MetricKey = z.infer<typeof metricKeySchema>;

export const ruleOperatorSchema = z.enum(["gte", "lte", "interval_every"]);
export type RuleOperator = z.infer<typeof ruleOperatorSchema>;

export const woPrioritySchema = z.enum(["low", "normal", "high", "critical"]);
export type WoPriority = z.infer<typeof woPrioritySchema>;

export const woStatusSchema = z.enum([
  "open",
  "scheduled",
  "in_progress",
  "completed",
  "cancelled",
]);
export type WoStatus = z.infer<typeof woStatusSchema>;

export const eamAssetSchema = z.object({
  id: z.string(),
  asset_tag: z.string(),
  name: z.string(),
  category: assetCategorySchema,
  serial_number: z.string(),
  location_label: z.string(),
  status: z.enum([
    "operational",
    "warning",
    "maintenance_due",
    "out_of_service",
  ]),
  engine_hours_milli: z.number().int(),
  odometer_miles_milli: z.number().int(),
  health_score: z.number().int(),
  iot_token_prefix: z.string().nullable().optional(),
  last_telemetry_at: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type EamAsset = z.infer<typeof eamAssetSchema>;

export const eamAssetCreatedSchema = z.object({
  asset: eamAssetSchema,
  iot_ingest_token: z.string(),
});
export type EamAssetCreated = z.infer<typeof eamAssetCreatedSchema>;

export const eamRuleSchema = z.object({
  id: z.string(),
  asset_id: z.string(),
  rule_name: z.string(),
  metric_key: metricKeySchema,
  operator: ruleOperatorSchema,
  threshold_milli: z.number().int(),
  warning_lead_pct: z.number().int(),
  priority: woPrioritySchema,
  wo_title_template: z.string(),
  wo_checklist: z.string(),
  auto_create_wo: z.boolean(),
  last_triggered_milli: z.number().int(),
  is_active: z.boolean(),
  created_at: z.string(),
});
export type EamRule = z.infer<typeof eamRuleSchema>;

export const eamTelemetrySchema = z.object({
  id: z.string(),
  asset_id: z.string(),
  metric_key: metricKeySchema,
  value_milli: z.number().int(),
  unit: z.string(),
  source: z.enum(["iot_webhook", "manual", "telematics"]),
  anomaly_flagged: z.boolean(),
  notes: z.string(),
  recorded_at: z.string(),
});
export type EamTelemetry = z.infer<typeof eamTelemetrySchema>;

export const eamWorkOrderSchema = z.object({
  id: z.string(),
  wo_number: z.string(),
  asset_id: z.string(),
  asset_tag: z.string(),
  asset_name: z.string(),
  rule_id: z.string().nullable().optional(),
  trigger_reading_id: z.string().nullable().optional(),
  trigger_kind: z.enum(["predictive_iot", "preventive_interval", "manual"]),
  priority: woPrioritySchema,
  status: woStatusSchema,
  title: z.string(),
  diagnostic_summary: z.string(),
  estimated_cost_cents: z.number().int(),
  due_at: z.string().nullable().optional(),
  completed_at: z.string().nullable().optional(),
  completion_notes: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type EamWorkOrder = z.infer<typeof eamWorkOrderSchema>;

export const telemetryIngestResultSchema = z.object({
  reading: eamTelemetrySchema,
  asset: eamAssetSchema,
  auto_created_work_orders: z.array(eamWorkOrderSchema),
});
export type TelemetryIngestResult = z.infer<typeof telemetryIngestResultSchema>;

export const draftPoResultSchema = z.object({
  purchase_order_id: z.string(),
  po_number: z.string(),
  total_cents: z.number().int(),
});
export type DraftPoResult = z.infer<typeof draftPoResultSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/industrial`;
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
      "Industrial MRP II / EAM API returned unexpected data.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchMrpMaterials(
  businessId: string,
): Promise<MrpMaterial[]> {
  const res = await authorizedResponse(`${base(businessId)}/mrp/materials`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(mrpMaterialSchema));
}

export async function createMrpMaterial(
  businessId: string,
  input: {
    sku: string;
    name: string;
    material_kind: MaterialKind;
    unit: MaterialUnit;
    on_hand_milli: number;
    reorder_point_milli: number;
    unit_cost_cents: number;
    preferred_vendor_name: string;
    preferred_vendor_email?: string | null;
  },
): Promise<MrpMaterial> {
  const res = await authorizedResponse(`${base(businessId)}/mrp/materials`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, mrpMaterialSchema);
}

export async function adjustMrpMaterialStock(
  businessId: string,
  materialId: string,
  deltaMilli: number,
): Promise<MrpMaterial> {
  const res = await authorizedResponse(
    `${base(businessId)}/mrp/materials/${encodeURIComponent(materialId)}/adjust`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ delta_milli: deltaMilli }),
    },
  );
  return readJson(res, mrpMaterialSchema);
}

export async function fetchMrpRecipes(
  businessId: string,
): Promise<MrpRecipe[]> {
  const res = await authorizedResponse(`${base(businessId)}/mrp/recipes`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(mrpRecipeSchema));
}

export async function createMrpRecipe(
  businessId: string,
  input: {
    code: string;
    name: string;
    output_material_id: string;
    output_qty_milli: number;
    lead_time_days: number;
    notes: string;
    lines: {
      component_material_id: string;
      qty_per_batch_milli: number;
      scrap_bps: number;
      notes: string;
    }[];
  },
): Promise<MrpRecipe> {
  const res = await authorizedResponse(`${base(businessId)}/mrp/recipes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, mrpRecipeSchema);
}

export async function explodeMrpBom(
  businessId: string,
  recipeId: string,
  targetQtyMilli: number,
): Promise<MrpExplosion> {
  const res = await authorizedResponse(`${base(businessId)}/mrp/explode`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      recipe_id: recipeId,
      target_qty_milli: targetQtyMilli,
    }),
  });
  return readJson(res, mrpExplosionSchema);
}

export async function fetchMrpRuns(
  businessId: string,
): Promise<MrpProductionRun[]> {
  const res = await authorizedResponse(`${base(businessId)}/mrp/runs`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(mrpProductionRunSchema));
}

export async function createMrpRun(
  businessId: string,
  input: {
    recipe_id: string;
    target_qty_milli: number;
    scheduled_date?: string | null;
    notes: string;
    reserve_available: boolean;
  },
): Promise<MrpProductionRun> {
  const res = await authorizedResponse(`${base(businessId)}/mrp/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, mrpProductionRunSchema);
}

export async function transitionMrpRun(
  businessId: string,
  runId: string,
  action: "start" | "complete" | "cancel",
): Promise<MrpProductionRun> {
  const res = await authorizedResponse(
    `${base(businessId)}/mrp/runs/${encodeURIComponent(runId)}/transition`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ action }),
    },
  );
  return readJson(res, mrpProductionRunSchema);
}

export async function generateDraftPoForRun(
  businessId: string,
  runId: string,
): Promise<DraftPoResult> {
  const res = await authorizedResponse(
    `${base(businessId)}/mrp/runs/${encodeURIComponent(runId)}/draft-po`,
    {
      method: "POST",
      headers: { Accept: "application/json" },
    },
  );
  return readJson(res, draftPoResultSchema);
}

export async function fetchEamAssets(businessId: string): Promise<EamAsset[]> {
  const res = await authorizedResponse(`${base(businessId)}/eam/assets`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(eamAssetSchema));
}

export async function createEamAsset(
  businessId: string,
  input: {
    asset_tag: string;
    name: string;
    category: AssetCategory;
    serial_number: string;
    location_label: string;
    engine_hours_milli: number;
    odometer_miles_milli: number;
  },
): Promise<EamAssetCreated> {
  const res = await authorizedResponse(`${base(businessId)}/eam/assets`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, eamAssetCreatedSchema);
}

export async function rotateEamToken(
  businessId: string,
  assetId: string,
): Promise<EamAssetCreated> {
  const res = await authorizedResponse(
    `${base(businessId)}/eam/assets/${encodeURIComponent(assetId)}/rotate-token`,
    { method: "POST", headers: { Accept: "application/json" } },
  );
  return readJson(res, eamAssetCreatedSchema);
}

export async function fetchEamRules(businessId: string): Promise<EamRule[]> {
  const res = await authorizedResponse(`${base(businessId)}/eam/rules`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(eamRuleSchema));
}

export async function createEamRule(
  businessId: string,
  input: {
    asset_id: string;
    rule_name: string;
    metric_key: MetricKey;
    operator: RuleOperator;
    threshold_milli: number;
    warning_lead_pct: number;
    priority: WoPriority;
    wo_title_template: string;
    wo_checklist: string;
    auto_create_wo: boolean;
  },
): Promise<EamRule> {
  const res = await authorizedResponse(`${base(businessId)}/eam/rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, eamRuleSchema);
}

export async function deleteEamRule(
  businessId: string,
  ruleId: string,
): Promise<void> {
  await authorizedResponse(
    `${base(businessId)}/eam/rules/${encodeURIComponent(ruleId)}`,
    { method: "DELETE" },
  );
}

export async function fetchEamTelemetry(
  businessId: string,
): Promise<EamTelemetry[]> {
  const res = await authorizedResponse(`${base(businessId)}/eam/telemetry`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(eamTelemetrySchema));
}

export async function ingestEamTelemetry(
  businessId: string,
  input: {
    asset_id: string;
    metric_key: MetricKey;
    value_milli: number;
    source: "iot_webhook" | "manual" | "telematics";
    notes: string;
  },
): Promise<TelemetryIngestResult> {
  const res = await authorizedResponse(`${base(businessId)}/eam/telemetry`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, telemetryIngestResultSchema);
}

export async function fetchEamWorkOrders(
  businessId: string,
): Promise<EamWorkOrder[]> {
  const res = await authorizedResponse(`${base(businessId)}/eam/work-orders`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(eamWorkOrderSchema));
}

export async function updateEamWorkOrder(
  businessId: string,
  woId: string,
  input: {
    status: WoStatus;
    completion_notes?: string;
    estimated_cost_cents?: number | null;
  },
): Promise<EamWorkOrder> {
  const res = await authorizedResponse(
    `${base(businessId)}/eam/work-orders/${encodeURIComponent(woId)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        status: input.status,
        completion_notes: input.completion_notes ?? "",
        estimated_cost_cents: input.estimated_cost_cents ?? null,
      }),
    },
  );
  return readJson(res, eamWorkOrderSchema);
}
