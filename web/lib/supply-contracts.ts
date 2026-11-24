// SUPPLY-01 Slice 4 (ADR-0039): strict Zod contracts and role gates for /supply/.
import { z } from "zod";

export type MembershipSummary = {
  salon_id?: string;
  salon_slug?: string | null;
  salon_name?: string | null;
  role: string;
  status?: string;
  location_id?: string | null;
  delegation?: unknown;
  delegated?: boolean;
};

export const GoodsOwnerKindSchema = z.enum([
  "company_entity",
  "counterparty_3pl",
]);
export type GoodsOwnerKind = z.infer<typeof GoodsOwnerKindSchema>;

export const BinKindSchema = z.enum([
  "receiving",
  "storage",
  "picking",
  "production",
  "quarantine",
  "shipping",
]);
export type BinKind = z.infer<typeof BinKindSchema>;

export const LotStatusSchema = z.enum(["active", "quarantine", "expired"]);
export type LotStatus = z.infer<typeof LotStatusSchema>;

export const SerialStateSchema = z.enum([
  "in_stock",
  "reserved",
  "shipped",
  "consumed",
  "returned",
]);
export type SerialState = z.infer<typeof SerialStateSchema>;

export const WmsMovementKindSchema = z.enum([
  "inbound_putaway",
  "bin_relocation",
  "outbound_pick",
  "return_putaway",
  "production_issue",
  "production_output",
  "production_return",
]);
export type WmsMovementKind = z.infer<typeof WmsMovementKindSchema>;

export const WmsMovementDirectionSchema = z.enum(["in", "out", "relocate"]);
export type WmsMovementDirection = z.infer<typeof WmsMovementDirectionSchema>;

export const WorkOrderStatusSchema = z.enum([
  "draft",
  "released",
  "in_progress",
  "qc_passed",
  "completed",
  "cancelled",
]);
export type WorkOrderStatus = z.infer<typeof WorkOrderStatusSchema>;

export const PriceChannelSchema = z.enum([
  "retail",
  "wholesale",
  "contract_b2b",
]);
export type PriceChannel = z.infer<typeof PriceChannelSchema>;

export const TradeOrderKindSchema = z.enum([
  "retail_sale",
  "wholesale_sale",
  "3pl_fulfillment",
]);
export type TradeOrderKind = z.infer<typeof TradeOrderKindSchema>;

export const TradeOrderStatusSchema = z.enum([
  "draft",
  "confirmed",
  "partially_shipped",
  "shipped",
  "returned",
  "cancelled",
]);
export type TradeOrderStatus = z.infer<typeof TradeOrderStatusSchema>;

export const GoodsOwnerViewSchema = z
  .object({
    schema_version: z.literal(1),
    goods_owner_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    display_name: z.string(),
    owner_kind: GoodsOwnerKindSchema,
    legal_entity_id: z.string().uuid().nullable(),
    counterparty_id: z.string().uuid().nullable(),
    is_active: z.boolean(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type GoodsOwnerView = z.infer<typeof GoodsOwnerViewSchema>;

export const GoodsOwnerListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(GoodsOwnerViewSchema),
  })
  .strict();

export const WarehouseBinViewSchema = z
  .object({
    schema_version: z.literal(1),
    bin_id: z.string().uuid(),
    location_id: z.string().uuid(),
    place_id: z.string().uuid(),
    zone_code: z.string(),
    bin_code: z.string(),
    bin_kind: BinKindSchema,
    dedicated_owner_id: z.string().uuid().nullable(),
    is_active: z.boolean(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type WarehouseBinView = z.infer<typeof WarehouseBinViewSchema>;

export const WarehouseBinListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(WarehouseBinViewSchema),
  })
  .strict();

export const LotViewSchema = z
  .object({
    schema_version: z.literal(1),
    lot_id: z.string().uuid(),
    location_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    item_id: z.string().uuid(),
    lot_code: z.string(),
    manufactured_on: z.string().nullable(),
    expires_on: z.string().nullable(),
    status: LotStatusSchema,
    unit_cost_minor: z.number().int().min(0),
    notes: z.string().nullable(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type LotView = z.infer<typeof LotViewSchema>;

export const LotListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(LotViewSchema),
  })
  .strict();

export const SerialUnitViewSchema = z
  .object({
    schema_version: z.literal(1),
    serial_id: z.string().uuid(),
    location_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    item_id: z.string().uuid(),
    lot_id: z.string().uuid(),
    serial_code: z.string(),
    state: SerialStateSchema,
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type SerialUnitView = z.infer<typeof SerialUnitViewSchema>;

export const SerialUnitListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(SerialUnitViewSchema),
  })
  .strict();

export const LotBalanceViewSchema = z
  .object({
    schema_version: z.literal(1),
    balance_id: z.string().uuid(),
    location_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    item_id: z.string().uuid(),
    lot_id: z.string().uuid(),
    quantity: z.number().int().min(0),
    updated_at: z.string(),
  })
  .strict();
export type LotBalanceView = z.infer<typeof LotBalanceViewSchema>;

export const LotBalanceListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(LotBalanceViewSchema),
  })
  .strict();

export const WmsMovementViewSchema = z
  .object({
    schema_version: z.literal(1),
    movement_id: z.string().uuid(),
    location_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    to_place_id: z.string().uuid().nullable(),
    to_bin_id: z.string().uuid().nullable(),
    goods_owner_id: z.string().uuid(),
    item_id: z.string().uuid(),
    lot_id: z.string().uuid(),
    movement_kind: WmsMovementKindSchema,
    direction: WmsMovementDirectionSchema,
    quantity: z.number().int().min(1),
    stock_document_id: z.string().uuid().nullable(),
    stock_line_no: z.number().int().nullable(),
    reference_code: z.string().nullable(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type WmsMovementView = z.infer<typeof WmsMovementViewSchema>;

export const WmsMovementListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(WmsMovementViewSchema),
  })
  .strict();

export const BomComponentViewSchema = z
  .object({
    schema_version: z.literal(1),
    component_id: z.string().uuid(),
    bom_id: z.string().uuid(),
    line_no: z.number().int().min(1),
    component_item_id: z.string().uuid(),
    quantity_per_batch: z.number().int().min(1),
    scrap_bps: z.number().int().min(0),
  })
  .strict();

export const BomViewSchema = z
  .object({
    schema_version: z.literal(1),
    bom_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    title: z.string(),
    output_item_id: z.string().uuid(),
    batch_output_quantity: z.number().int().min(1),
    standard_labor_minor: z.number().int().min(0),
    standard_overhead_minor: z.number().int().min(0),
    is_active: z.boolean(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
    components: z.array(BomComponentViewSchema),
  })
  .strict();
export type BomView = z.infer<typeof BomViewSchema>;

export const BomListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(BomViewSchema),
  })
  .strict();

export const WorkOrderViewSchema = z
  .object({
    schema_version: z.literal(1),
    work_order_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    goods_owner_id: z.string().uuid(),
    bom_id: z.string().uuid(),
    output_item_id: z.string().uuid(),
    place_id: z.string().uuid(),
    planned_quantity: z.number().int().min(1),
    issued_material_cost_minor: z.number().int().min(0),
    returned_material_cost_minor: z.number().int().min(0),
    labor_cost_minor: z.number().int().min(0),
    overhead_cost_minor: z.number().int().min(0),
    completed_quantity: z.number().int().min(0),
    scrap_quantity: z.number().int().min(0),
    output_total_cost_minor: z.number().int().min(0),
    status: WorkOrderStatusSchema,
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type WorkOrderView = z.infer<typeof WorkOrderViewSchema>;

export const WorkOrderListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(WorkOrderViewSchema),
  })
  .strict();

export const WorkOrderIssueViewSchema = z
  .object({
    schema_version: z.literal(1),
    issue_id: z.string().uuid(),
    work_order_id: z.string().uuid(),
    location_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    component_item_id: z.string().uuid(),
    lot_id: z.string().uuid(),
    quantity: z.number().int().min(1),
    returned_quantity: z.number().int().min(0),
    stock_document_id: z.string().uuid(),
    stock_line_no: z.number().int(),
    cost_minor: z.number().int().min(0),
    returned_cost_minor: z.number().int().min(0),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type WorkOrderIssueView = z.infer<typeof WorkOrderIssueViewSchema>;

export const WorkOrderIssueListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(WorkOrderIssueViewSchema),
  })
  .strict();

export const WorkOrderReturnViewSchema = z
  .object({
    schema_version: z.literal(1),
    return_id: z.string().uuid(),
    work_order_id: z.string().uuid(),
    issue_id: z.string().uuid(),
    location_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    component_item_id: z.string().uuid(),
    lot_id: z.string().uuid(),
    quantity: z.number().int().min(1),
    stock_return_document_id: z.string().uuid(),
    stock_return_line_no: z.number().int(),
    cost_returned_minor: z.number().int().min(0),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type WorkOrderReturnView = z.infer<typeof WorkOrderReturnViewSchema>;

export const WorkOrderReturnListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(WorkOrderReturnViewSchema),
  })
  .strict();

export const WorkOrderQcViewSchema = z
  .object({
    schema_version: z.literal(1),
    qc_id: z.string().uuid(),
    work_order_id: z.string().uuid(),
    location_id: z.string().uuid(),
    passed_quantity: z.number().int().min(1),
    scrap_quantity: z.number().int().min(0),
    notes: z.string().nullable(),
    inspected_by: z.string().uuid(),
    inspected_at: z.string(),
  })
  .strict();
export type WorkOrderQcView = z.infer<typeof WorkOrderQcViewSchema>;

export const WorkOrderOutputViewSchema = z
  .object({
    schema_version: z.literal(1),
    output_id: z.string().uuid(),
    work_order_id: z.string().uuid(),
    location_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    output_item_id: z.string().uuid(),
    output_lot_id: z.string().uuid(),
    quantity: z.number().int().min(1),
    material_cost_minor: z.number().int().min(0),
    labor_cost_minor: z.number().int().min(0),
    overhead_cost_minor: z.number().int().min(0),
    total_cost_minor: z.number().int().min(0),
    unit_cost_minor: z.number().int().min(0),
    stock_receipt_document_id: z.string().uuid(),
    stock_receipt_line_no: z.number().int(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type WorkOrderOutputView = z.infer<typeof WorkOrderOutputViewSchema>;

export const PriceListItemViewSchema = z
  .object({
    schema_version: z.literal(1),
    price_list_item_id: z.string().uuid(),
    price_list_id: z.string().uuid(),
    item_id: z.string().uuid(),
    min_quantity: z.number().int().min(1),
    unit_price_minor: z.number().int().min(0),
  })
  .strict();

export const PriceListViewSchema = z
  .object({
    schema_version: z.literal(1),
    price_list_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    title: z.string(),
    channel: PriceChannelSchema,
    currency: z.string(),
    counterparty_id: z.string().uuid().nullable(),
    is_active: z.boolean(),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
    items: z.array(PriceListItemViewSchema),
  })
  .strict();
export type PriceListView = z.infer<typeof PriceListViewSchema>;

export const PriceListCollectionSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(PriceListViewSchema),
  })
  .strict();

export const TradeOrderLineViewSchema = z
  .object({
    schema_version: z.literal(1),
    order_line_id: z.string().uuid(),
    order_id: z.string().uuid(),
    line_no: z.number().int().min(1),
    item_id: z.string().uuid(),
    ordered_quantity: z.number().int().min(1),
    shipped_quantity: z.number().int().min(0),
    returned_quantity: z.number().int().min(0),
    unit_price_minor: z.number().int().min(0),
    line_total_minor: z.number().int().min(0),
  })
  .strict();
export type TradeOrderLineView = z.infer<typeof TradeOrderLineViewSchema>;

export const TradeOrderViewSchema = z
  .object({
    schema_version: z.literal(1),
    order_id: z.string().uuid(),
    location_id: z.string().uuid(),
    code: z.string(),
    order_kind: TradeOrderKindSchema,
    goods_owner_id: z.string().uuid(),
    customer_counterparty_id: z.string().uuid(),
    price_list_id: z.string().uuid().nullable(),
    currency: z.string(),
    book_id: z.string().uuid().nullable(),
    control_account_id: z.string().uuid().nullable(),
    revenue_account_id: z.string().uuid().nullable(),
    status: TradeOrderStatusSchema,
    total_ordered_minor: z.number().int().min(0),
    total_shipped_minor: z.number().int().min(0),
    total_returned_minor: z.number().int().min(0),
    revision: z.number().int().min(1),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
    lines: z.array(TradeOrderLineViewSchema),
  })
  .strict();
export type TradeOrderView = z.infer<typeof TradeOrderViewSchema>;

export const TradeOrderListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(TradeOrderViewSchema),
  })
  .strict();

export const OrderShipmentViewSchema = z
  .object({
    schema_version: z.literal(1),
    shipment_id: z.string().uuid(),
    order_id: z.string().uuid(),
    order_line_id: z.string().uuid(),
    location_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    item_id: z.string().uuid(),
    lot_id: z.string().uuid(),
    quantity: z.number().int().min(1),
    returned_quantity: z.number().int().min(0),
    unit_price_minor: z.number().int().min(0),
    revenue_minor: z.number().int().min(0),
    cogs_minor: z.number().int().min(0),
    returned_cogs_minor: z.number().int().min(0),
    wms_movement_id: z.string().uuid(),
    stock_document_id: z.string().uuid().nullable(),
    stock_line_no: z.number().int().nullable(),
    book_id: z.string().uuid().nullable(),
    invoice_document_id: z.string().uuid().nullable(),
    invoice_line_id: z.string().uuid().nullable(),
    obligation_id: z.string().uuid().nullable(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type OrderShipmentView = z.infer<typeof OrderShipmentViewSchema>;

export const OrderShipmentListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(OrderShipmentViewSchema),
  })
  .strict();

export const OrderReturnViewSchema = z
  .object({
    schema_version: z.literal(1),
    return_id: z.string().uuid(),
    order_id: z.string().uuid(),
    order_line_id: z.string().uuid(),
    shipment_id: z.string().uuid(),
    location_id: z.string().uuid(),
    goods_owner_id: z.string().uuid(),
    place_id: z.string().uuid(),
    bin_id: z.string().uuid(),
    item_id: z.string().uuid(),
    lot_id: z.string().uuid(),
    quantity: z.number().int().min(1),
    refund_minor: z.number().int().min(0),
    cogs_restored_minor: z.number().int().min(0),
    wms_movement_id: z.string().uuid(),
    stock_return_document_id: z.string().uuid().nullable(),
    stock_return_line_no: z.number().int().nullable(),
    book_id: z.string().uuid().nullable(),
    credit_note_document_id: z.string().uuid().nullable(),
    reason: z.string(),
    recorded_by: z.string().uuid(),
    recorded_at: z.string(),
  })
  .strict();
export type OrderReturnView = z.infer<typeof OrderReturnViewSchema>;

export const OrderReturnListSchema = z
  .object({
    schema_version: z.literal(1),
    items: z.array(OrderReturnViewSchema),
  })
  .strict();

export function canReadSupply(member: MembershipSummary | undefined): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation))
    return false;
  return ["owner", "manager", "front_desk", "artist"].includes(member.role);
}

export function canWorkSupply(member: MembershipSummary | undefined): boolean {
  return canReadSupply(member);
}

export function canManageSupply(
  member: MembershipSummary | undefined,
): boolean {
  if (!member || Boolean(member.delegated) || Boolean(member.delegation))
    return false;
  return member.role === "owner" || member.role === "manager";
}

export function formatSupplyMinor(minor: number, currency = "USD"): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${sign}${whole}.${frac} ${currency}`;
}

const UUID_RE = "[0-9a-f-]{36}";

export function supplyResponseSchema(
  subpath: string,
  method: string,
): z.ZodType | null {
  const path = subpath.split("?")[0] ?? "";
  if (!path.startsWith("/supply/")) return null;
  const rest = path.slice("/supply".length);

  if (rest === "/owners" && method === "GET") return GoodsOwnerListSchema;
  if (
    new RegExp(`^/owners/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return GoodsOwnerViewSchema;

  if (rest === "/bins" && method === "GET") return WarehouseBinListSchema;
  if (
    new RegExp(`^/bins/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return WarehouseBinViewSchema;

  if (rest === "/lots" && method === "GET") return LotListSchema;
  if (
    new RegExp(`^/lots/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return LotViewSchema;

  if (rest === "/serials" && method === "GET") return SerialUnitListSchema;
  if (rest === "/lot-balances" && method === "GET") return LotBalanceListSchema;
  if (rest === "/movements" && method === "GET") return WmsMovementListSchema;
  if (
    (rest === "/movements/inbound" ||
      rest === "/movements/relocate" ||
      rest === "/movements/outbound") &&
    method === "POST"
  )
    return WmsMovementViewSchema;

  if (rest === "/boms" && method === "GET") return BomListSchema;
  if (
    new RegExp(`^/boms/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return BomViewSchema;

  if (rest === "/work-orders" && method === "GET") return WorkOrderListSchema;
  if (
    new RegExp(`^/work-orders/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return WorkOrderViewSchema;
  if (
    new RegExp(`^/work-orders/${UUID_RE}/issues$`, "i").test(rest) &&
    method === "GET"
  )
    return WorkOrderIssueListSchema;
  if (
    new RegExp(`^/work-orders/${UUID_RE}/issues$`, "i").test(rest) &&
    method === "POST"
  )
    return WorkOrderIssueViewSchema;
  if (
    new RegExp(`^/work-orders/${UUID_RE}/returns$`, "i").test(rest) &&
    method === "GET"
  )
    return WorkOrderReturnListSchema;
  if (
    new RegExp(`^/work-orders/${UUID_RE}/returns$`, "i").test(rest) &&
    method === "POST"
  )
    return WorkOrderReturnViewSchema;
  if (
    new RegExp(`^/work-orders/${UUID_RE}/qc$`, "i").test(rest) &&
    method === "POST"
  )
    return WorkOrderQcViewSchema;
  if (
    new RegExp(`^/work-orders/${UUID_RE}/output$`, "i").test(rest) &&
    (method === "GET" || method === "POST")
  )
    return WorkOrderOutputViewSchema;

  if (rest === "/price-lists" && method === "GET")
    return PriceListCollectionSchema;
  if (
    new RegExp(`^/price-lists/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return PriceListViewSchema;

  if (rest === "/orders" && method === "GET") return TradeOrderListSchema;
  if (
    new RegExp(`^/orders/${UUID_RE}$`, "i").test(rest) &&
    (method === "GET" || method === "PUT")
  )
    return TradeOrderViewSchema;
  if (
    new RegExp(`^/orders/${UUID_RE}/shipments$`, "i").test(rest) &&
    method === "GET"
  )
    return OrderShipmentListSchema;
  if (
    new RegExp(`^/orders/${UUID_RE}/shipments$`, "i").test(rest) &&
    method === "POST"
  )
    return OrderShipmentViewSchema;
  if (
    new RegExp(`^/orders/${UUID_RE}/returns$`, "i").test(rest) &&
    method === "GET"
  )
    return OrderReturnListSchema;
  if (
    new RegExp(`^/orders/${UUID_RE}/returns$`, "i").test(rest) &&
    method === "POST"
  )
    return OrderReturnViewSchema;

  return null;
}
