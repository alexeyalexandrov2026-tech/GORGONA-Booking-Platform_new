import { z } from "zod";
import { authorizedResponse, ManagementApiError } from "./management-api";

export const entityKindSchema = z.enum([
  "counterparty",
  "commercial_quote",
  "purchase_order",
  "booking",
  "asset",
  "project_matter",
]);
export type EntityKind = z.infer<typeof entityKindSchema>;

export const boardEntityKindSchema = z.enum([
  "general",
  "counterparty",
  "commercial_quote",
  "purchase_order",
  "booking",
  "asset",
  "project_matter",
]);
export type BoardEntityKind = z.infer<typeof boardEntityKindSchema>;

export const customFieldTypeSchema = z.enum([
  "text",
  "number",
  "currency_usd",
  "date",
  "select",
  "boolean",
]);
export type CustomFieldType = z.infer<typeof customFieldTypeSchema>;

export const cardPrioritySchema = z.enum(["low", "medium", "high", "urgent"]);
export type CardPriority = z.infer<typeof cardPrioritySchema>;

export const surfacePresetSchema = z.enum([
  "monolith_light",
  "warm_stone",
  "slate_enterprise",
]);
export type SurfacePreset = z.infer<typeof surfacePresetSchema>;

export const customFieldDefinitionSchema = z.object({
  id: z.string(),
  entity_kind: entityKindSchema,
  field_key: z.string(),
  label: z.string(),
  field_type: customFieldTypeSchema,
  options: z.array(z.string()),
  is_required: z.boolean(),
  display_order: z.number().int(),
  created_at: z.string(),
});
export type CustomFieldDefinition = z.infer<typeof customFieldDefinitionSchema>;

export const kanbanLaneSchema = z.object({
  id: z.string(),
  title: z.string(),
  color_hex: z.string(),
});
export type KanbanLane = z.infer<typeof kanbanLaneSchema>;

export const workspaceBoardSchema = z.object({
  id: z.string(),
  slug: z.string(),
  title: z.string(),
  entity_kind: boardEntityKindSchema,
  lanes: z.array(kanbanLaneSchema),
  created_at: z.string(),
  updated_at: z.string(),
});
export type WorkspaceBoard = z.infer<typeof workspaceBoardSchema>;

export const workspaceBoardCardSchema = z.object({
  id: z.string(),
  board_id: z.string(),
  lane_id: z.string(),
  title: z.string(),
  description: z.string(),
  priority: cardPrioritySchema,
  amount_cents: z.number().int().nullable().optional(),
  due_date: z.string().nullable().optional(),
  position: z.number().int(),
  custom_fields: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string(),
  updated_at: z.string(),
});
export type WorkspaceBoardCard = z.infer<typeof workspaceBoardCardSchema>;

export const brandThemeSchema = z.object({
  brand_display_name: z.string().nullable().optional(),
  logo_url: z.string().nullable().optional(),
  accent_hex: z.string(),
  accent_contrast_on_white: z.number(),
  surface_preset: surfacePresetSchema,
  dashboard_widgets: z.array(z.string()),
  updated_at: z.string().nullable().optional(),
});
export type BrandTheme = z.infer<typeof brandThemeSchema>;

function base(businessId: string): string {
  return `/v1/businesses/${encodeURIComponent(businessId)}/workspace-studio`;
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
      "AMARKAL Workspace Studio returned incomplete data. Please retry.",
      response.status,
    );
  }
  return parsed.data;
}

export async function fetchCustomFields(
  businessId: string,
): Promise<CustomFieldDefinition[]> {
  const res = await authorizedResponse(`${base(businessId)}/custom-fields`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(customFieldDefinitionSchema));
}

export async function createCustomField(
  businessId: string,
  input: {
    entity_kind: EntityKind;
    field_key: string;
    label: string;
    field_type: CustomFieldType;
    options: string[];
    is_required: boolean;
  },
): Promise<CustomFieldDefinition> {
  const res = await authorizedResponse(`${base(businessId)}/custom-fields`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, customFieldDefinitionSchema);
}

export async function deleteCustomField(
  businessId: string,
  definitionId: string,
): Promise<void> {
  await authorizedResponse(
    `${base(businessId)}/custom-fields/${encodeURIComponent(definitionId)}`,
    { method: "DELETE" },
  );
}

export async function fetchWorkspaceBoards(
  businessId: string,
): Promise<WorkspaceBoard[]> {
  const res = await authorizedResponse(`${base(businessId)}/boards`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, z.array(workspaceBoardSchema));
}

export async function createWorkspaceBoard(
  businessId: string,
  input: {
    slug: string;
    title: string;
    entity_kind: BoardEntityKind;
  },
): Promise<WorkspaceBoard> {
  const res = await authorizedResponse(`${base(businessId)}/boards`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, workspaceBoardSchema);
}

export async function deleteWorkspaceBoard(
  businessId: string,
  boardId: string,
): Promise<void> {
  await authorizedResponse(
    `${base(businessId)}/boards/${encodeURIComponent(boardId)}`,
    { method: "DELETE" },
  );
}

export async function fetchBoardCards(
  businessId: string,
  boardId: string,
): Promise<WorkspaceBoardCard[]> {
  const res = await authorizedResponse(
    `${base(businessId)}/boards/${encodeURIComponent(boardId)}/cards`,
    { headers: { Accept: "application/json" } },
  );
  return readJson(res, z.array(workspaceBoardCardSchema));
}

export async function createBoardCard(
  businessId: string,
  boardId: string,
  input: {
    lane_id: string;
    title: string;
    description: string;
    priority: CardPriority;
    amount_cents?: number | null;
    due_date?: string | null;
  },
): Promise<WorkspaceBoardCard> {
  const res = await authorizedResponse(
    `${base(businessId)}/boards/${encodeURIComponent(boardId)}/cards`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(input),
    },
  );
  return readJson(res, workspaceBoardCardSchema);
}

export async function moveBoardCard(
  businessId: string,
  boardId: string,
  cardId: string,
  targetLaneId: string,
  targetPosition = 0,
): Promise<WorkspaceBoardCard> {
  const res = await authorizedResponse(
    `${base(businessId)}/boards/${encodeURIComponent(boardId)}/cards/${encodeURIComponent(cardId)}/move`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        target_lane_id: targetLaneId,
        target_position: targetPosition,
      }),
    },
  );
  return readJson(res, workspaceBoardCardSchema);
}

export async function deleteBoardCard(
  businessId: string,
  boardId: string,
  cardId: string,
): Promise<void> {
  await authorizedResponse(
    `${base(businessId)}/boards/${encodeURIComponent(boardId)}/cards/${encodeURIComponent(cardId)}`,
    { method: "DELETE" },
  );
}

export async function fetchBrandTheme(businessId: string): Promise<BrandTheme> {
  const res = await authorizedResponse(`${base(businessId)}/brand-theme`, {
    headers: { Accept: "application/json" },
  });
  return readJson(res, brandThemeSchema);
}

export async function saveBrandTheme(
  businessId: string,
  input: {
    brand_display_name?: string | null;
    logo_url?: string | null;
    accent_hex: string;
    surface_preset: SurfacePreset;
    dashboard_widgets: string[];
  },
): Promise<BrandTheme> {
  const res = await authorizedResponse(`${base(businessId)}/brand-theme`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  return readJson(res, brandThemeSchema);
}
