// SUPPLY-01 Slice 4: typed API client for /supply/ with Idempotency-Key mutations.
import { ManagementApiError, managementFetch } from "./management-api";
import {
  BomListSchema,
  BomViewSchema,
  GoodsOwnerListSchema,
  GoodsOwnerViewSchema,
  LotBalanceListSchema,
  LotListSchema,
  LotViewSchema,
  OrderReturnListSchema,
  OrderReturnViewSchema,
  OrderShipmentListSchema,
  OrderShipmentViewSchema,
  PriceListCollectionSchema,
  PriceListViewSchema,
  SerialUnitListSchema,
  TradeOrderListSchema,
  TradeOrderViewSchema,
  WarehouseBinListSchema,
  WarehouseBinViewSchema,
  WmsMovementListSchema,
  WmsMovementViewSchema,
  WorkOrderIssueListSchema,
  WorkOrderIssueViewSchema,
  WorkOrderListSchema,
  WorkOrderOutputViewSchema,
  WorkOrderQcViewSchema,
  WorkOrderReturnListSchema,
  WorkOrderReturnViewSchema,
  WorkOrderViewSchema,
  type BinKind,
  type BomView,
  type GoodsOwnerKind,
  type GoodsOwnerView,
  type LotBalanceView,
  type LotView,
  type OrderReturnView,
  type OrderShipmentView,
  type PriceChannel,
  type PriceListView,
  type SerialUnitView,
  type TradeOrderKind,
  type TradeOrderView,
  type WarehouseBinView,
  type WmsMovementView,
  type WorkOrderIssueView,
  type WorkOrderOutputView,
  type WorkOrderQcView,
  type WorkOrderReturnView,
  type WorkOrderView,
} from "./supply-contracts";

const root = (business: string) => `/v1/businesses/${business}/supply`;

export function supplyError(error: unknown): string {
  if (error instanceof ManagementApiError) {
    return `${error.code}: ${error.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

export async function fetchGoodsOwners(
  business: string,
): Promise<GoodsOwnerView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/owners`);
  return GoodsOwnerListSchema.parse(raw).items;
}

export async function saveGoodsOwner(
  business: string,
  ownerId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    display_name: string;
    owner_kind: GoodsOwnerKind;
    legal_entity_id?: string | null;
    counterparty_id?: string | null;
    is_active?: boolean;
  },
): Promise<GoodsOwnerView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/owners/${ownerId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return GoodsOwnerViewSchema.parse(raw);
}

export async function fetchWarehouseBins(
  business: string,
): Promise<WarehouseBinView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/bins`);
  return WarehouseBinListSchema.parse(raw).items;
}

export async function saveWarehouseBin(
  business: string,
  binId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    place_id: string;
    zone_code: string;
    bin_code: string;
    bin_kind: BinKind;
    dedicated_owner_id?: string | null;
  },
): Promise<WarehouseBinView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/bins/${binId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return WarehouseBinViewSchema.parse(raw);
}

export async function fetchLots(business: string): Promise<LotView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/lots`);
  return LotListSchema.parse(raw).items;
}

export async function saveLot(
  business: string,
  lotId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    goods_owner_id: string;
    item_id: string;
    lot_code: string;
    unit_cost_minor: number;
    expires_on?: string | null;
  },
): Promise<LotView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/lots/${lotId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return LotViewSchema.parse(raw);
}

export async function fetchSerialUnits(
  business: string,
): Promise<SerialUnitView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/serials`);
  return SerialUnitListSchema.parse(raw).items;
}

export async function fetchLotBalances(
  business: string,
): Promise<LotBalanceView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/lot-balances`);
  return LotBalanceListSchema.parse(raw).items;
}

export async function fetchWmsMovements(
  business: string,
): Promise<WmsMovementView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/movements`);
  return WmsMovementListSchema.parse(raw).items;
}

export async function postInboundPutaway(
  business: string,
  key: string,
  body: {
    location_id: string;
    bin_id: string;
    goods_owner_id: string;
    item_id: string;
    lot_id: string;
    quantity: number;
    serial_codes?: string[];
    auto_stock_receipt_date?: string | null;
    auto_stock_receipt_reason?: "purchase" | "opening_balance" | "surplus";
    auto_stock_receipt_amount?: string | null;
  },
): Promise<WmsMovementView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/movements/inbound`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return WmsMovementViewSchema.parse(raw);
}

export async function fetchBoms(business: string): Promise<BomView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/boms`);
  return BomListSchema.parse(raw).items;
}

export async function saveBom(
  business: string,
  bomId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    title: string;
    output_item_id: string;
    batch_output_quantity: number;
    standard_labor_minor: number;
    standard_overhead_minor: number;
    components: {
      component_item_id: string;
      quantity_per_batch: number;
      scrap_bps?: number;
    }[];
  },
): Promise<BomView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/boms/${bomId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return BomViewSchema.parse(raw);
}

export async function fetchWorkOrders(
  business: string,
): Promise<WorkOrderView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/work-orders`);
  return WorkOrderListSchema.parse(raw).items;
}

export async function saveWorkOrder(
  business: string,
  workOrderId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    goods_owner_id: string;
    bom_id: string;
    place_id: string;
    planned_quantity: number;
    labor_cost_minor?: number;
    overhead_cost_minor?: number;
  },
): Promise<WorkOrderView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/work-orders/${workOrderId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return WorkOrderViewSchema.parse(raw);
}

export async function fetchWorkOrderIssues(
  business: string,
  workOrderId: string,
): Promise<WorkOrderIssueView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/work-orders/${workOrderId}/issues`,
  );
  return WorkOrderIssueListSchema.parse(raw).items;
}

export async function postWorkOrderIssue(
  business: string,
  workOrderId: string,
  key: string,
  body: {
    bin_id: string;
    component_item_id: string;
    lot_id: string;
    quantity: number;
    document_date: string;
  },
): Promise<WorkOrderIssueView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/work-orders/${workOrderId}/issues`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return WorkOrderIssueViewSchema.parse(raw);
}

export async function fetchWorkOrderReturns(
  business: string,
  workOrderId: string,
): Promise<WorkOrderReturnView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/work-orders/${workOrderId}/returns`,
  );
  return WorkOrderReturnListSchema.parse(raw).items;
}

export async function postWorkOrderReturn(
  business: string,
  workOrderId: string,
  key: string,
  body: {
    issue_id: string;
    bin_id: string;
    quantity: number;
    document_date: string;
  },
): Promise<WorkOrderReturnView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/work-orders/${workOrderId}/returns`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return WorkOrderReturnViewSchema.parse(raw);
}

export async function postWorkOrderQc(
  business: string,
  workOrderId: string,
  key: string,
  body: {
    passed_quantity: number;
    scrap_quantity: number;
    notes?: string | null;
  },
): Promise<WorkOrderQcView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/work-orders/${workOrderId}/qc`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return WorkOrderQcViewSchema.parse(raw);
}

export async function postWorkOrderOutput(
  business: string,
  workOrderId: string,
  key: string,
  body: {
    bin_id: string;
    output_lot_code: string;
    manufactured_on: string;
    expires_on?: string | null;
  },
): Promise<WorkOrderOutputView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/work-orders/${workOrderId}/output`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return WorkOrderOutputViewSchema.parse(raw);
}

export async function fetchPriceLists(
  business: string,
): Promise<PriceListView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/price-lists`);
  return PriceListCollectionSchema.parse(raw).items;
}

export async function savePriceList(
  business: string,
  priceListId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    title: string;
    channel: PriceChannel;
    currency: string;
    items: {
      item_id: string;
      min_quantity: number;
      unit_price_minor: number;
    }[];
  },
): Promise<PriceListView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/price-lists/${priceListId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return PriceListViewSchema.parse(raw);
}

export async function fetchTradeOrders(
  business: string,
): Promise<TradeOrderView[]> {
  const raw = await managementFetch<unknown>(`${root(business)}/orders`);
  return TradeOrderListSchema.parse(raw).items;
}

export async function saveTradeOrder(
  business: string,
  orderId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    order_kind: TradeOrderKind;
    goods_owner_id: string;
    customer_counterparty_id: string;
    price_list_id?: string | null;
    currency: string;
    book_id?: string | null;
    control_account_id?: string | null;
    revenue_account_id?: string | null;
    lines: {
      item_id: string;
      ordered_quantity: number;
      unit_price_minor?: number | null;
    }[];
  },
): Promise<TradeOrderView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/orders/${orderId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return TradeOrderViewSchema.parse(raw);
}

export async function fetchOrderShipments(
  business: string,
  orderId: string,
): Promise<OrderShipmentView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/orders/${orderId}/shipments`,
  );
  return OrderShipmentListSchema.parse(raw).items;
}

export async function postOrderShipment(
  business: string,
  orderId: string,
  key: string,
  body: {
    order_line_id: string;
    bin_id: string;
    lot_id: string;
    quantity: number;
    serial_codes?: string[];
    document_date: string;
    invoice_number?: string | null;
  },
): Promise<OrderShipmentView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/orders/${orderId}/shipments`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return OrderShipmentViewSchema.parse(raw);
}

export async function fetchOrderReturns(
  business: string,
  orderId: string,
): Promise<OrderReturnView[]> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/orders/${orderId}/returns`,
  );
  return OrderReturnListSchema.parse(raw).items;
}

export async function postOrderReturn(
  business: string,
  orderId: string,
  key: string,
  body: {
    shipment_id: string;
    bin_id: string;
    quantity: number;
    serial_codes?: string[];
    document_date: string;
    reason: string;
    credit_note_number?: string | null;
  },
): Promise<OrderReturnView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/orders/${orderId}/returns`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return OrderReturnViewSchema.parse(raw);
}
