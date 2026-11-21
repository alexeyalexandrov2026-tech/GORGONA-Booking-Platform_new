import { z } from "zod";

export const ServiceStyleSchema = z.enum(["dining", "bar", "patio", "private"]);
export type ServiceStyle = z.infer<typeof ServiceStyleSchema>;

export const ReservationStatusSchema = z.enum([
  "booked",
  "seated",
  "completed",
  "cancelled",
  "no_show",
]);
export type ReservationStatus = z.infer<typeof ReservationStatusSchema>;

export const ReservationActionSchema = z.enum([
  "seat",
  "complete",
  "cancel",
  "no_show",
]);
export type ReservationAction = z.infer<typeof ReservationActionSchema>;

export const KitchenStationSchema = z.enum(["hot", "cold", "bar", "pastry"]);
export type KitchenStation = z.infer<typeof KitchenStationSchema>;

export const ServiceModeSchema = z.enum([
  "dine_in",
  "takeout",
  "bar",
  "delivery",
]);
export type ServiceMode = z.infer<typeof ServiceModeSchema>;

export const CheckStatusSchema = z.enum(["open", "closed", "voided"]);
export type CheckStatus = z.infer<typeof CheckStatusSchema>;

export const CheckLineStatusSchema = z.enum([
  "draft",
  "fired",
  "served",
  "voided",
]);
export type CheckLineStatus = z.infer<typeof CheckLineStatusSchema>;

export const KitchenTicketStatusSchema = z.enum([
  "queued",
  "preparing",
  "ready",
  "served",
  "voided",
]);
export type KitchenTicketStatus = z.infer<typeof KitchenTicketStatusSchema>;

export const KitchenTicketActionSchema = z.enum([
  "start",
  "mark_ready",
  "serve",
  "void",
]);
export type KitchenTicketAction = z.infer<typeof KitchenTicketActionSchema>;

export const AreaViewSchema = z
  .object({
    schema_version: z.literal(1),
    area_id: z.string().uuid(),
    location_id: z.string().uuid(),
    name: z.string(),
    service_style: ServiceStyleSchema,
    revision: z.number().int(),
    is_active: z.boolean(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type AreaView = z.infer<typeof AreaViewSchema>;

export const AreaListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(AreaViewSchema),
    next_after: z.string().uuid().nullable(),
  })
  .strict();
export type AreaList = z.infer<typeof AreaListSchema>;

export const TableViewSchema = z
  .object({
    schema_version: z.literal(1),
    table_id: z.string().uuid(),
    location_id: z.string().uuid(),
    area_id: z.string().uuid(),
    resource_id: z.string().uuid(),
    code: z.string(),
    min_covers: z.number().int(),
    max_covers: z.number().int(),
    revision: z.number().int(),
    is_active: z.boolean(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type TableView = z.infer<typeof TableViewSchema>;

export const TableListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(TableViewSchema),
    next_after: z.string().uuid().nullable(),
  })
  .strict();
export type TableList = z.infer<typeof TableListSchema>;

export const ReservationViewSchema = z
  .object({
    schema_version: z.literal(1),
    reservation_id: z.string().uuid(),
    location_id: z.string().uuid(),
    table_id: z.string().uuid(),
    table_resource_id: z.string().uuid(),
    guest_counterparty_id: z.string().uuid().nullable(),
    guest_name: z.string(),
    party_size: z.number().int(),
    starts_at: z.string(),
    ends_at: z.string(),
    note: z.string().nullable(),
    status: ReservationStatusSchema,
    revision: z.number().int(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type ReservationView = z.infer<typeof ReservationViewSchema>;

export const ReservationListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(ReservationViewSchema),
    next_after: z.string().uuid().nullable(),
  })
  .strict();
export type ReservationList = z.infer<typeof ReservationListSchema>;

export const MenuItemViewSchema = z
  .object({
    schema_version: z.literal(1),
    menu_item_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    name: z.string(),
    category: z.string(),
    kitchen_station: KitchenStationSchema,
    price_minor: z.number().int(),
    currency: z.string(),
    description: z.string().nullable(),
    revision: z.number().int(),
    is_active: z.boolean(),
    modifier_group_ids: z.array(z.string().uuid()),
    latest_recipe_revision: z.number().int().nullable(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type MenuItemView = z.infer<typeof MenuItemViewSchema>;

export const MenuItemListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(MenuItemViewSchema),
    next_after: z.string().uuid().nullable(),
  })
  .strict();
export type MenuItemList = z.infer<typeof MenuItemListSchema>;

export const ModifierOptionViewSchema = z
  .object({
    schema_version: z.literal(1),
    option_id: z.string().uuid(),
    group_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    name: z.string(),
    price_delta_minor: z.number().int(),
    sort_order: z.number().int(),
    stock_item_id: z.string().uuid().nullable(),
    stock_quantity: z.number().int().nullable(),
    stock_item_code: z.string().nullable(),
    stock_item_unit: z.string().nullable(),
    stock_item_quantity_scale: z.number().int().nullable(),
    revision: z.number().int(),
    is_active: z.boolean(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type ModifierOptionView = z.infer<typeof ModifierOptionViewSchema>;

export const ModifierGroupViewSchema = z
  .object({
    schema_version: z.literal(1),
    group_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    name: z.string(),
    min_select: z.number().int(),
    max_select: z.number().int(),
    currency: z.string(),
    revision: z.number().int(),
    is_active: z.boolean(),
    options: z.array(ModifierOptionViewSchema),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type ModifierGroupView = z.infer<typeof ModifierGroupViewSchema>;

export const ModifierGroupListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(ModifierGroupViewSchema),
    next_after: z.string().uuid().nullable(),
  })
  .strict();
export type ModifierGroupList = z.infer<typeof ModifierGroupListSchema>;

export const RecipeLineViewSchema = z
  .object({
    line_no: z.number().int(),
    stock_item_id: z.string().uuid(),
    stock_item_code: z.string(),
    stock_item_unit: z.string(),
    stock_item_quantity_scale: z.number().int(),
    quantity: z.number().int(),
    note: z.string().nullable(),
  })
  .strict();
export type RecipeLineView = z.infer<typeof RecipeLineViewSchema>;

export const RecipeViewSchema = z
  .object({
    schema_version: z.literal(1),
    menu_item_id: z.string().uuid(),
    location_id: z.string().uuid(),
    revision: z.number().int(),
    note: z.string().nullable(),
    lines: z.array(RecipeLineViewSchema),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type RecipeView = z.infer<typeof RecipeViewSchema>;

export const CheckLineModifierViewSchema = z
  .object({
    modifier_no: z.number().int(),
    group_id: z.string().uuid(),
    option_id: z.string().uuid(),
    group_name: z.string(),
    option_code: z.string(),
    option_name: z.string(),
    price_delta_minor: z.number().int(),
    stock_item_id: z.string().uuid().nullable(),
    stock_quantity: z.number().int().nullable(),
  })
  .strict();

export const CheckLineViewSchema = z
  .object({
    line_id: z.string().uuid(),
    check_id: z.string().uuid(),
    line_no: z.number().int(),
    menu_item_id: z.string().uuid(),
    menu_item_revision: z.number().int(),
    recipe_revision: z.number().int().nullable(),
    item_code: z.string(),
    item_name: z.string(),
    kitchen_station: KitchenStationSchema,
    quantity: z.number().int(),
    base_price_minor: z.number().int(),
    modifiers_delta_minor: z.number().int(),
    unit_price_minor: z.number().int(),
    line_total_minor: z.number().int(),
    status: CheckLineStatusSchema,
    kitchen_ticket_id: z.string().uuid().nullable(),
    note: z.string().nullable(),
    void_reason: z.string().nullable(),
    modifiers: z.array(CheckLineModifierViewSchema),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type CheckLineView = z.infer<typeof CheckLineViewSchema>;

export const CheckViewSchema = z
  .object({
    schema_version: z.literal(1),
    check_id: z.string().uuid(),
    location_id: z.string().uuid(),
    service_mode: ServiceModeSchema,
    table_id: z.string().uuid().nullable(),
    reservation_id: z.string().uuid().nullable(),
    guest_counterparty_id: z.string().uuid().nullable(),
    guest_name: z.string().nullable(),
    currency: z.string(),
    status: CheckStatusSchema,
    subtotal_minor: z.number().int(),
    note: z.string().nullable(),
    revision: z.number().int(),
    opened_by: z.string().uuid(),
    opened_at: z.string(),
    closed_by: z.string().uuid().nullable(),
    closed_at: z.string().nullable(),
    consumption_posted: z.boolean(),
    stock_document_id: z.string().uuid().nullable(),
    lines: z.array(CheckLineViewSchema),
  })
  .strict();
export type CheckView = z.infer<typeof CheckViewSchema>;

export const CheckListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(CheckViewSchema),
    next_after: z.string().uuid().nullable(),
  })
  .strict();
export type CheckList = z.infer<typeof CheckListSchema>;

export const KitchenTicketEventViewSchema = z
  .object({
    revision: z.number().int(),
    action: KitchenTicketActionSchema,
    note: z.string().nullable(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();

export const KitchenTicketViewSchema = z
  .object({
    schema_version: z.literal(1),
    ticket_id: z.string().uuid(),
    check_id: z.string().uuid(),
    location_id: z.string().uuid(),
    ticket_no: z.number().int(),
    kitchen_station: KitchenStationSchema,
    status: KitchenTicketStatusSchema,
    revision: z.number().int(),
    fired_by: z.string().uuid(),
    fired_at: z.string(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
    lines: z.array(CheckLineViewSchema),
    events: z.array(KitchenTicketEventViewSchema),
  })
  .strict();
export type KitchenTicketView = z.infer<typeof KitchenTicketViewSchema>;

export const KitchenTicketListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(KitchenTicketViewSchema),
    next_after: z.string().uuid().nullable(),
  })
  .strict();
export type KitchenTicketList = z.infer<typeof KitchenTicketListSchema>;

export const FireResultViewSchema = z
  .object({
    schema_version: z.literal(1),
    check_id: z.string().uuid(),
    tickets: z.array(KitchenTicketViewSchema),
  })
  .strict();
export type FireResultView = z.infer<typeof FireResultViewSchema>;

export const ConsumptionLineViewSchema = z
  .object({
    stock_item_id: z.string().uuid(),
    stock_item_code: z.string(),
    stock_item_unit: z.string(),
    stock_item_quantity_scale: z.number().int(),
    quantity: z.number().int(),
  })
  .strict();

export const CheckConsumptionViewSchema = z
  .object({
    schema_version: z.literal(1),
    check_id: z.string().uuid(),
    location_id: z.string().uuid(),
    posted: z.boolean(),
    legal_entity_id: z.string().uuid().nullable(),
    place_id: z.string().uuid().nullable(),
    document_date: z.string().nullable(),
    stock_document_id: z.string().uuid().nullable(),
    posted_by: z.string().uuid().nullable(),
    posted_at: z.string().nullable(),
    lines: z.array(ConsumptionLineViewSchema),
  })
  .strict();
export type CheckConsumptionView = z.infer<typeof CheckConsumptionViewSchema>;

export const SplitShareViewSchema = z
  .object({
    share_no: z.number().int(),
    label: z.string(),
    counterparty_id: z.string().uuid().nullable(),
    amount_minor: z.number().int(),
    line_ids: z.array(z.string().uuid()),
    billed: z.boolean(),
    book_id: z.string().uuid().nullable(),
    invoice_document_id: z.string().uuid().nullable(),
    billed_counterparty_id: z.string().uuid().nullable(),
    billed_at: z.string().nullable(),
  })
  .strict();

export const CheckSplitViewSchema = z
  .object({
    schema_version: z.literal(1),
    check_id: z.string().uuid(),
    location_id: z.string().uuid(),
    split_mode: z.enum(["by_items", "by_amounts"]),
    share_count: z.number().int(),
    total_minor: z.number().int(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
    shares: z.array(SplitShareViewSchema),
  })
  .strict();
export type CheckSplitView = z.infer<typeof CheckSplitViewSchema>;

export const CheckReconciliationViewSchema = z
  .object({
    schema_version: z.literal(1),
    check_id: z.string().uuid(),
    location_id: z.string().uuid(),
    currency: z.string(),
    status: z.string(),
    consumption_posted: z.boolean(),
    stock_document_id: z.string().uuid().nullable(),
    split_mode: z.enum(["by_items", "by_amounts"]).nullable(),
    shares: z.array(
      z
        .object({
          share_no: z.number().int(),
          label: z.string(),
          amount_minor: z.number().int(),
          line_ids: z.array(z.string().uuid()),
          book_id: z.string().uuid().nullable(),
          invoice_document_id: z.string().uuid().nullable(),
          invoice_state: z.enum(["unbilled", "draft", "issued"]),
          principal_minor: z.number().int(),
          paid_minor: z.number().int(),
          credited_minor: z.number().int(),
          open_minor: z.number().int(),
        })
        .strict(),
    ),
    refunds: z.array(
      z
        .object({
          number: z.number().int(),
          share_no: z.number().int(),
          returned_line_id: z.string().uuid().nullable(),
          method: z.enum(["credit", "external"]),
          amount_minor: z.number().int(),
          state: z.enum(["recorded", "draft", "issued", "voided"]),
          credit_document_id: z.string().uuid().nullable(),
          refund_obligation_minor: z.number().int().nullable(),
          refund_paid_minor: z.number().int().nullable(),
        })
        .strict(),
    ),
    totals: z
      .object({
        check_subtotal_minor: z.number().int(),
        split_total_minor: z.number().int(),
        billed_total_minor: z.number().int(),
        invoiced_issued_minor: z.number().int(),
        paid_minor: z.number().int(),
        credited_minor: z.number().int(),
        open_minor: z.number().int(),
        refunded_external_minor: z.number().int(),
        refund_owed_minor: z.number().int(),
        balanced: z.boolean(),
      })
      .strict(),
  })
  .strict();
export type CheckReconciliationView = z.infer<
  typeof CheckReconciliationViewSchema
>;

export type MemberLike = {
  role: string;
  status: string;
  location_id?: string | null;
  delegation?: unknown;
};

export function canReadRestaurant(member: MemberLike | undefined): boolean {
  if (!member || member.status !== "active" || member.delegation) return false;
  return ["owner", "manager", "front_desk", "artist"].includes(member.role);
}

export function canOperateKitchen(member: MemberLike | undefined): boolean {
  return canReadRestaurant(member);
}

export function canRunService(member: MemberLike | undefined): boolean {
  if (!member || member.status !== "active" || member.delegation) return false;
  return ["owner", "manager", "front_desk"].includes(member.role);
}

export function canManageRestaurant(member: MemberLike | undefined): boolean {
  if (!member || member.status !== "active" || member.delegation) return false;
  return ["owner", "manager"].includes(member.role);
}

export function canRunCompanyFinance(member: MemberLike | undefined): boolean {
  return canManageRestaurant(member) && !member?.location_id;
}

export function formatMinor(minor: number, currency: string): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const major = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${sign}${major}.${frac} ${currency}`;
}

export function parseMajorToMinor(raw: string): number | null {
  const cleaned = raw.trim();
  if (!/^-?\d+(?:\.\d{1,2})?$/.test(cleaned)) return null;
  const negative = cleaned.startsWith("-");
  const body = negative ? cleaned.slice(1) : cleaned;
  const [whole, frac = ""] = body.split(".");
  const minor = Number(whole) * 100 + Number(frac.padEnd(2, "0"));
  if (!Number.isSafeInteger(minor)) return null;
  return negative ? -minor : minor;
}

const UUID_RE = "[0-9a-f-]{36}";

export const MenuItemModifierGroupsViewSchema = z
  .object({
    schema_version: z.literal(1),
    menu_item_id: z.string().uuid(),
    location_id: z.string().uuid(),
    modifier_group_ids: z.array(z.string().uuid()),
  })
  .strict();

export function restaurantResponseSchema(
  subpath: string,
  method: string,
): z.ZodType | null {
  const path = subpath.split("?")[0] ?? "";
  if (!path.startsWith("/restaurant/")) return null;
  const rest = path.slice("/restaurant".length);
  if (rest === "/areas" && method === "GET") return AreaListSchema;
  if (
    new RegExp(`^/areas/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return AreaViewSchema;
  if (rest === "/tables" && method === "GET") return TableListSchema;
  if (
    new RegExp(`^/tables/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return TableViewSchema;
  if (rest === "/reservations" && method === "GET")
    return ReservationListSchema;
  if (
    new RegExp(`^/reservations/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return ReservationViewSchema;
  if (
    new RegExp(`^/reservations/${UUID_RE}/events$`, "i").test(rest) &&
    method === "POST"
  )
    return ReservationViewSchema;
  if (rest === "/menu-items" && method === "GET") return MenuItemListSchema;
  if (
    new RegExp(`^/menu-items/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return MenuItemViewSchema;
  if (
    new RegExp(`^/menu-items/${UUID_RE}/modifier-groups$`, "i").test(rest) &&
    method === "PUT"
  )
    return MenuItemModifierGroupsViewSchema;
  if (
    new RegExp(`^/menu-items/${UUID_RE}/recipes$`, "i").test(rest) &&
    method === "POST"
  )
    return RecipeViewSchema;
  if (rest === "/modifier-groups" && method === "GET")
    return ModifierGroupListSchema;
  if (
    new RegExp(`^/modifier-groups/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return ModifierGroupViewSchema;
  if (
    new RegExp(`^/modifier-groups/${UUID_RE}/options/${UUID_RE}$`, "i").test(
      rest,
    ) &&
    method === "PUT"
  )
    return ModifierOptionViewSchema;
  if (rest === "/checks" && method === "GET") return CheckListSchema;
  if (rest === "/checks" && method === "POST") return CheckViewSchema;
  if (new RegExp(`^/checks/${UUID_RE}$`, "i").test(rest) && method === "GET")
    return CheckViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/lines$`, "i").test(rest) &&
    method === "POST"
  )
    return CheckViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/lines/${UUID_RE}/void$`, "i").test(rest) &&
    method === "POST"
  )
    return CheckViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/fire$`, "i").test(rest) &&
    method === "POST"
  )
    return FireResultViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/close$`, "i").test(rest) &&
    method === "POST"
  )
    return CheckViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/consumption$`, "i").test(rest) &&
    method === "GET"
  )
    return CheckConsumptionViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/post-consumption$`, "i").test(rest) &&
    method === "POST"
  )
    return CheckConsumptionViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/split$`, "i").test(rest) &&
    (method === "GET" || method === "POST")
  )
    return CheckSplitViewSchema;
  if (
    new RegExp(`^/checks/${UUID_RE}/reconciliation$`, "i").test(rest) &&
    method === "GET"
  )
    return CheckReconciliationViewSchema;
  if (rest === "/kitchen/tickets" && method === "GET")
    return KitchenTicketListSchema;
  if (
    new RegExp(`^/kitchen/tickets/${UUID_RE}$`, "i").test(rest) &&
    method === "GET"
  )
    return KitchenTicketViewSchema;
  if (
    new RegExp(`^/kitchen/tickets/${UUID_RE}/events$`, "i").test(rest) &&
    method === "POST"
  )
    return KitchenTicketViewSchema;
  return null;
}
