import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const triggerEntitySchema = z.enum([
  "contract",
  "purchase_order",
  "quote",
  "invoice",
  "payroll_run",
  "intercompany_trade",
  "work_order",
]);
export type TriggerEntity = z.infer<typeof triggerEntitySchema>;

export const bpmnNodeTypeSchema = z.enum([
  "start_trigger",
  "exclusive_gateway",
  "human_approval",
  "ai_compliance_check",
  "notify_or_webhook",
  "end_approved",
  "end_rejected",
]);
export type BpmnNodeType = z.infer<typeof bpmnNodeTypeSchema>;

export const edgeBranchSchema = z.enum(["default", "yes", "no"]);
export type EdgeBranch = z.infer<typeof edgeBranchSchema>;

export const bpmnNodeSchema = z.object({
  id: z.string(),
  node_type: bpmnNodeTypeSchema,
  label: z.string(),
  x: z.number().int(),
  y: z.number().int(),
  config: z.record(z.string(), z.unknown()),
});
export type BpmnNode = z.infer<typeof bpmnNodeSchema>;

export const bpmnEdgeSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  target_id: z.string(),
  label: z.string(),
  branch: edgeBranchSchema,
});
export type BpmnEdge = z.infer<typeof bpmnEdgeSchema>;

export const bpmnWorkflowViewSchema = z.object({
  id: z.string(),
  workflow_code: z.string(),
  display_name: z.string(),
  description: z.string(),
  trigger_entity: triggerEntitySchema,
  version: z.number().int(),
  status: z.enum(["draft", "active", "paused", "archived"]),
  nodes: z.array(bpmnNodeSchema),
  edges: z.array(bpmnEdgeSchema),
  warnings: z.array(z.string()),
  active_instance_count: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type BpmnWorkflowView = z.infer<typeof bpmnWorkflowViewSchema>;

export const bpmnTraceStepSchema = z.object({
  node_id: z.string(),
  node_type: z.string(),
  label: z.string(),
  outcome: z.string(),
  detail: z.string(),
  at: z.string(),
});
export type BpmnTraceStep = z.infer<typeof bpmnTraceStepSchema>;

export const bpmnInstanceViewSchema = z.object({
  id: z.string(),
  workflow_id: z.string(),
  workflow_code: z.string(),
  workflow_name: z.string(),
  reference_code: z.string(),
  entity_title: z.string(),
  amount_cents: z.number().int(),
  context: z.record(z.string(), z.unknown()),
  current_node_id: z.string(),
  current_node_label: z.string(),
  status: z.enum([
    "running",
    "awaiting_approval",
    "approved",
    "rejected",
    "cancelled",
  ]),
  trace: z.array(bpmnTraceStepSchema),
  started_at: z.string(),
  completed_at: z.string().nullable(),
});
export type BpmnInstanceView = z.infer<typeof bpmnInstanceViewSchema>;

export const bpmnPresetViewSchema = z.object({
  workflow_code: z.string(),
  display_name: z.string(),
  description: z.string(),
  trigger_entity: triggerEntitySchema,
  node_count: z.number().int(),
  installed: z.boolean(),
});
export type BpmnPresetView = z.infer<typeof bpmnPresetViewSchema>;

export const workflowsOverviewResponseSchema = z.object({
  workflows: z.array(bpmnWorkflowViewSchema),
  instances: z.array(bpmnInstanceViewSchema),
  presets: z.array(bpmnPresetViewSchema),
  pending_approvals_count: z.number().int(),
});
export type WorkflowsOverviewResponse = z.infer<
  typeof workflowsOverviewResponseSchema
>;

export const generatedDraftResponseSchema = z.object({
  workflow_code: z.string(),
  display_name: z.string(),
  description: z.string(),
  trigger_entity: triggerEntitySchema,
  nodes: z.array(bpmnNodeSchema),
  edges: z.array(bpmnEdgeSchema),
  warnings: z.array(z.string()),
});
export type GeneratedDraftResponse = z.infer<
  typeof generatedDraftResponseSchema
>;

export const dryRunResponseSchema = z.object({
  workflow_code: z.string(),
  simulated_status: z.string(),
  visited_node_ids: z.array(z.string()),
  trace: z.array(bpmnTraceStepSchema),
});
export type DryRunResponse = z.infer<typeof dryRunResponseSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/workflows`;
}

async function parseJson<T>(res: Response, schema: z.ZodType<T>): Promise<T> {
  const text = await res.text();
  let raw: unknown = null;
  if (text) {
    try {
      raw = JSON.parse(text);
    } catch {
      raw = null;
    }
  }
  if (!res.ok) {
    const detail =
      raw &&
      typeof raw === "object" &&
      "detail" in raw &&
      typeof raw.detail === "string"
        ? raw.detail
        : `Request failed (HTTP ${res.status}).`;
    throw new ManagementApiError("REQUEST_FAILED", detail, res.status);
  }
  return schema.parse(raw);
}

export async function fetchWorkflowsOverview(
  businessId: string,
): Promise<WorkflowsOverviewResponse> {
  const res = await authorizedResponse(`${base(businessId)}/overview`, {
    method: "GET",
  });
  return parseJson(res, workflowsOverviewResponseSchema);
}

export async function installWorkflowPreset(
  businessId: string,
  presetCode: string,
): Promise<BpmnWorkflowView> {
  const res = await authorizedResponse(
    `${base(businessId)}/presets/${encodeURIComponent(presetCode)}`,
    { method: "POST" },
  );
  return parseJson(res, bpmnWorkflowViewSchema);
}

export async function generateWorkflowFromPrompt(
  businessId: string,
  prompt: string,
): Promise<GeneratedDraftResponse> {
  const res = await authorizedResponse(
    `${base(businessId)}/generate-from-prompt`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    },
  );
  return parseJson(res, generatedDraftResponseSchema);
}

export async function createWorkflow(
  businessId: string,
  payload: {
    workflow_code: string;
    display_name: string;
    description: string;
    trigger_entity: TriggerEntity;
    status: "draft" | "active" | "paused" | "archived";
    nodes: BpmnNode[];
    edges: BpmnEdge[];
  },
): Promise<BpmnWorkflowView> {
  const res = await authorizedResponse(base(businessId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseJson(res, bpmnWorkflowViewSchema);
}

export async function updateWorkflowGraph(
  businessId: string,
  workflowId: string,
  payload: {
    display_name?: string;
    status?: "draft" | "active" | "paused" | "archived";
    nodes: BpmnNode[];
    edges: BpmnEdge[];
  },
): Promise<BpmnWorkflowView> {
  const res = await authorizedResponse(
    `${base(businessId)}/${encodeURIComponent(workflowId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseJson(res, bpmnWorkflowViewSchema);
}

export async function dryRunWorkflow(
  businessId: string,
  workflowId: string,
  payload: { amount_cents: number; context: Record<string, unknown> },
): Promise<DryRunResponse> {
  const res = await authorizedResponse(
    `${base(businessId)}/${encodeURIComponent(workflowId)}/dry-run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseJson(res, dryRunResponseSchema);
}

export async function startWorkflowInstance(
  businessId: string,
  workflowId: string,
  payload: {
    reference_code: string;
    entity_title: string;
    amount_cents: number;
    context: Record<string, unknown>;
  },
): Promise<BpmnInstanceView> {
  const res = await authorizedResponse(
    `${base(businessId)}/${encodeURIComponent(workflowId)}/instances`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseJson(res, bpmnInstanceViewSchema);
}

export async function decideWorkflowInstance(
  businessId: string,
  instanceId: string,
  payload: { decision: "approve" | "reject"; comment: string },
): Promise<BpmnInstanceView> {
  const res = await authorizedResponse(
    `${base(businessId)}/instances/${encodeURIComponent(instanceId)}/decide`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return parseJson(res, bpmnInstanceViewSchema);
}

export async function fetchWorkflowBpmnXml(
  businessId: string,
  workflowId: string,
): Promise<string> {
  const res = await authorizedResponse(
    `${base(businessId)}/${encodeURIComponent(workflowId)}/bpmn-xml`,
    { method: "GET" },
  );
  if (!res.ok) {
    throw new ManagementApiError(
      "REQUEST_FAILED",
      `Failed to export BPMN 2.0 XML (HTTP ${res.status}).`,
      res.status,
    );
  }
  return res.text();
}
