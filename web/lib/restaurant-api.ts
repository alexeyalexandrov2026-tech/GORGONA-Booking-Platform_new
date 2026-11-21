// REST-01 Slice 5: typed restaurant client with cursor reads and retry-safe Idempotency-Key.
import { ManagementApiError, managementFetch } from "./management-api";
import {
  AreaListSchema,
  AreaViewSchema,
  CheckConsumptionViewSchema,
  CheckListSchema,
  CheckReconciliationViewSchema,
  CheckSplitViewSchema,
  CheckViewSchema,
  FireResultViewSchema,
  KitchenTicketListSchema,
  KitchenTicketViewSchema,
  MenuItemListSchema,
  MenuItemViewSchema,
  ModifierGroupListSchema,
  ModifierGroupViewSchema,
  ModifierOptionViewSchema,
  RecipeViewSchema,
  ReservationListSchema,
  ReservationViewSchema,
  TableListSchema,
  TableViewSchema,
  type AreaView,
  type CheckConsumptionView,
  type CheckReconciliationView,
  type CheckSplitView,
  type CheckView,
  type FireResultView,
  type KitchenStation,
  type KitchenTicketAction,
  type KitchenTicketView,
  type MenuItemView,
  type ModifierGroupView,
  type ModifierOptionView,
  type RecipeView,
  type ReservationAction,
  type ReservationView,
  type ServiceMode,
  type ServiceStyle,
  type TableView,
} from "./restaurant-contracts";

const root = (business: string) => `/v1/businesses/${business}/restaurant`;

export function restaurantError(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export async function fetchAreas(business: string): Promise<AreaView[]> {
  const all: AreaView[] = [];
  let after = "";
  for (;;) {
    const raw = await managementFetch<unknown>(
      after
        ? `${root(business)}/areas?after=${encodeURIComponent(after)}`
        : `${root(business)}/areas`,
    );
    const page = AreaListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function saveArea(
  business: string,
  areaId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    name: string;
    service_style: ServiceStyle;
    is_active?: boolean;
  },
): Promise<AreaView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/areas/${areaId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, is_active: true, ...body }),
    },
  );
  return AreaViewSchema.parse(raw);
}

export async function fetchTables(business: string): Promise<TableView[]> {
  const all: TableView[] = [];
  let after = "";
  for (;;) {
    const raw = await managementFetch<unknown>(
      after
        ? `${root(business)}/tables?after=${encodeURIComponent(after)}`
        : `${root(business)}/tables`,
    );
    const page = TableListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function saveTable(
  business: string,
  tableId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    area_id: string;
    code: string;
    min_covers: number;
    max_covers: number;
    is_active?: boolean;
  },
): Promise<TableView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/tables/${tableId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, is_active: true, ...body }),
    },
  );
  return TableViewSchema.parse(raw);
}

export async function fetchReservations(
  business: string,
): Promise<ReservationView[]> {
  const all: ReservationView[] = [];
  let after = "";
  for (;;) {
    const raw = await managementFetch<unknown>(
      after
        ? `${root(business)}/reservations?after=${encodeURIComponent(after)}`
        : `${root(business)}/reservations`,
    );
    const page = ReservationListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function createReservation(
  business: string,
  reservationId: string,
  key: string,
  body: {
    table_id: string;
    guest_name: string;
    party_size: number;
    starts_at: string;
    ends_at: string;
    note?: string | null;
  },
): Promise<ReservationView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/reservations/${reservationId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return ReservationViewSchema.parse(raw);
}

export async function postReservationEvent(
  business: string,
  reservationId: string,
  key: string,
  body: { expected_revision: number; action: ReservationAction; note?: string },
): Promise<ReservationView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/reservations/${reservationId}/events`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return ReservationViewSchema.parse(raw);
}

export async function fetchMenuItems(
  business: string,
): Promise<MenuItemView[]> {
  const all: MenuItemView[] = [];
  let after = "";
  for (;;) {
    const raw = await managementFetch<unknown>(
      after
        ? `${root(business)}/menu-items?after=${encodeURIComponent(after)}`
        : `${root(business)}/menu-items`,
    );
    const page = MenuItemListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function saveMenuItem(
  business: string,
  menuItemId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    name: string;
    category: string;
    kitchen_station: KitchenStation;
    price_minor: number;
    currency: string;
    description?: string | null;
    is_active?: boolean;
  },
): Promise<MenuItemView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/menu-items/${menuItemId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, is_active: true, ...body }),
    },
  );
  return MenuItemViewSchema.parse(raw);
}

export async function fetchModifierGroups(
  business: string,
): Promise<ModifierGroupView[]> {
  const all: ModifierGroupView[] = [];
  let after = "";
  for (;;) {
    const raw = await managementFetch<unknown>(
      after
        ? `${root(business)}/modifier-groups?after=${encodeURIComponent(after)}`
        : `${root(business)}/modifier-groups`,
    );
    const page = ModifierGroupListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function saveModifierGroup(
  business: string,
  groupId: string,
  key: string,
  body: {
    expected_revision: number;
    location_id: string;
    code: string;
    name: string;
    min_select: number;
    max_select: number;
    currency: string;
    is_active?: boolean;
  },
): Promise<ModifierGroupView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/modifier-groups/${groupId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, is_active: true, ...body }),
    },
  );
  return ModifierGroupViewSchema.parse(raw);
}

export async function saveModifierOption(
  business: string,
  groupId: string,
  optionId: string,
  key: string,
  body: {
    expected_revision: number;
    code: string;
    name: string;
    price_delta_minor: number;
    sort_order?: number;
    stock_item_id?: string | null;
    stock_quantity?: number | null;
    is_active?: boolean;
  },
): Promise<ModifierOptionView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/modifier-groups/${groupId}/options/${optionId}`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, is_active: true, ...body }),
    },
  );
  return ModifierOptionViewSchema.parse(raw);
}

export async function attachModifierGroups(
  business: string,
  menuItemId: string,
  key: string,
  modifierGroupIds: string[],
): Promise<void> {
  await managementFetch<unknown>(
    `${root(business)}/menu-items/${menuItemId}/modifier-groups`,
    {
      method: "PUT",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({
        schema_version: 1,
        modifier_group_ids: modifierGroupIds,
      }),
    },
  );
}

export async function createRecipe(
  business: string,
  menuItemId: string,
  key: string,
  body: {
    expected_revision: number;
    note?: string | null;
    lines: { stock_item_id: string; quantity: number; note?: string | null }[];
  },
): Promise<RecipeView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/menu-items/${menuItemId}/recipes`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return RecipeViewSchema.parse(raw);
}

export async function fetchChecks(business: string): Promise<CheckView[]> {
  const all: CheckView[] = [];
  let after = "";
  for (;;) {
    const raw = await managementFetch<unknown>(
      after
        ? `${root(business)}/checks?after=${encodeURIComponent(after)}`
        : `${root(business)}/checks`,
    );
    const page = CheckListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function openCheck(
  business: string,
  key: string,
  body: {
    location_id: string;
    service_mode: ServiceMode;
    currency: string;
    table_id?: string | null;
    guest_name?: string | null;
  },
): Promise<CheckView> {
  const raw = await managementFetch<unknown>(`${root(business)}/checks`, {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({ schema_version: 1, ...body }),
  });
  return CheckViewSchema.parse(raw);
}

export async function addCheckLine(
  business: string,
  checkId: string,
  key: string,
  body: {
    menu_item_id: string;
    quantity: number;
    modifier_option_ids?: string[];
    note?: string | null;
  },
): Promise<CheckView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/checks/${checkId}/lines`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CheckViewSchema.parse(raw);
}

export async function fireCheck(
  business: string,
  checkId: string,
  key: string,
): Promise<FireResultView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/checks/${checkId}/fire`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1 }),
    },
  );
  return FireResultViewSchema.parse(raw);
}

export async function closeCheck(
  business: string,
  checkId: string,
  key: string,
  expectedRevision: number,
): Promise<CheckView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/checks/${checkId}/close`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({
        schema_version: 1,
        expected_revision: expectedRevision,
        void_check: false,
      }),
    },
  );
  return CheckViewSchema.parse(raw);
}

export async function fetchKitchenTickets(
  business: string,
  station?: KitchenStation,
): Promise<KitchenTicketView[]> {
  const all: KitchenTicketView[] = [];
  let after = "";
  for (;;) {
    const qs = new URLSearchParams();
    if (station) qs.set("kitchen_station", station);
    if (after) qs.set("after", after);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    const raw = await managementFetch<unknown>(
      `${root(business)}/kitchen/tickets${suffix}`,
    );
    const page = KitchenTicketListSchema.parse(raw);
    all.push(...page.items);
    if (!page.next_after) return all;
    after = page.next_after;
  }
}

export async function postKitchenEvent(
  business: string,
  ticketId: string,
  key: string,
  body: {
    expected_revision: number;
    action: KitchenTicketAction;
    note?: string;
  },
): Promise<KitchenTicketView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/kitchen/tickets/${ticketId}/events`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return KitchenTicketViewSchema.parse(raw);
}

export async function fetchConsumption(
  business: string,
  checkId: string,
): Promise<CheckConsumptionView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/checks/${checkId}/consumption`,
  );
  return CheckConsumptionViewSchema.parse(raw);
}

export async function postConsumption(
  business: string,
  checkId: string,
  key: string,
  body: { legal_entity_id: string; place_id: string; document_date: string },
): Promise<CheckConsumptionView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/checks/${checkId}/post-consumption`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({ schema_version: 1, ...body }),
    },
  );
  return CheckConsumptionViewSchema.parse(raw);
}

export async function fetchCheckSplit(
  business: string,
  checkId: string,
): Promise<CheckSplitView | null> {
  try {
    const raw = await managementFetch<unknown>(
      `${root(business)}/checks/${checkId}/split`,
    );
    return CheckSplitViewSchema.parse(raw);
  } catch (err) {
    if (err instanceof ManagementApiError && err.status === 404) return null;
    throw err;
  }
}

export async function splitCheckByAmounts(
  business: string,
  checkId: string,
  key: string,
  shares: { label: string; amount_minor: number }[],
): Promise<CheckSplitView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/checks/${checkId}/split`,
    {
      method: "POST",
      headers: { "Idempotency-Key": key },
      body: JSON.stringify({
        schema_version: 1,
        split_mode: "by_amounts",
        shares,
      }),
    },
  );
  return CheckSplitViewSchema.parse(raw);
}

export async function fetchReconciliation(
  business: string,
  checkId: string,
): Promise<CheckReconciliationView> {
  const raw = await managementFetch<unknown>(
    `${root(business)}/checks/${checkId}/reconciliation`,
  );
  return CheckReconciliationViewSchema.parse(raw);
}
