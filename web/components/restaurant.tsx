"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  fetchWorkspace,
  managementFetch,
  type LocationItem,
} from "../lib/management-api";
import {
  addCheckLine,
  attachModifierGroups,
  closeCheck,
  createRecipe,
  createReservation,
  fetchAreas,
  fetchCheckSplit,
  fetchChecks,
  fetchConsumption,
  fetchKitchenTickets,
  fetchMenuItems,
  fetchModifierGroups,
  fetchReconciliation,
  fetchReservations,
  fetchTables,
  fireCheck,
  openCheck,
  postConsumption,
  postKitchenEvent,
  postReservationEvent,
  restaurantError,
  saveArea,
  saveMenuItem,
  saveModifierGroup,
  saveModifierOption,
  saveTable,
  splitCheckByAmounts,
} from "../lib/restaurant-api";
import {
  formatMinor,
  parseMajorToMinor,
  type AreaView,
  type CheckConsumptionView,
  type CheckReconciliationView,
  type CheckSplitView,
  type CheckView,
  type KitchenStation,
  type KitchenTicketAction,
  type KitchenTicketView,
  type MenuItemView,
  type ModifierGroupView,
  type ReservationAction,
  type ReservationView,
  type ServiceMode,
  type ServiceStyle,
  type TableView,
} from "../lib/restaurant-contracts";

type TabId = "floor" | "menu" | "checks" | "kitchen";
const TABS: { id: TabId; label: string }[] = [
  { id: "floor", label: "Floor & Reservations" },
  { id: "menu", label: "Menu & Recipes" },
  { id: "checks", label: "Checks & Split Billing" },
  { id: "kitchen", label: "Kitchen Station Board" },
];

type StockItemRef = {
  item_id: string;
  code: string;
  name: string;
  unit: string;
};
type StockPlaceRef = {
  place_id: string;
  location_id: string;
  code: string;
  name: string;
};
type LegalEntityRef = {
  legal_entity_id: string;
  code: string;
  legal_name: string;
};

interface RestaurantScreenProps {
  businessId: string;
  assignedLocationId: string | null;
  canManage: boolean;
  canService: boolean;
  canKitchen: boolean;
  canCompanyFinance: boolean;
}

function nextId(): string {
  return crypto.randomUUID();
}

export function RestaurantScreen({
  businessId,
  assignedLocationId,
  canManage,
  canService,
  canKitchen,
  canCompanyFinance,
}: RestaurantScreenProps) {
  const [tab, setTab] = useState<TabId>(canService ? "floor" : "kitchen");
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [areas, setAreas] = useState<AreaView[]>([]);
  const [tables, setTables] = useState<TableView[]>([]);
  const [reservations, setReservations] = useState<ReservationView[]>([]);
  const [menuItems, setMenuItems] = useState<MenuItemView[]>([]);
  const [modifierGroups, setModifierGroups] = useState<ModifierGroupView[]>([]);
  const [checks, setChecks] = useState<CheckView[]>([]);
  const [tickets, setTickets] = useState<KitchenTicketView[]>([]);
  const [stockItems, setStockItems] = useState<StockItemRef[]>([]);
  const [stockPlaces, setStockPlaces] = useState<StockPlaceRef[]>([]);
  const [legalEntities, setLegalEntities] = useState<LegalEntityRef[]>([]);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Retry-safe pending idempotency keys per action
  const keysRef = useRef<Record<string, string>>({});
  const keyFor = (slot: string) => {
    if (!keysRef.current[slot]) keysRef.current[slot] = `rest-ui-${nextId()}`;
    return keysRef.current[slot];
  };
  const clearKey = (slot: string) => {
    delete keysRef.current[slot];
  };

  // Floor form states
  const [areaLoc, setAreaLoc] = useState(assignedLocationId ?? "");
  const [areaName, setAreaName] = useState("");
  const [areaStyle, setAreaStyle] = useState<ServiceStyle>("dining");

  const [tableAreaId, setTableAreaId] = useState("");
  const [tableCode, setTableCode] = useState("");
  const [tableMin, setTableMin] = useState("1");
  const [tableMax, setTableMax] = useState("4");

  const [resTableId, setResTableId] = useState("");
  const [resGuest, setResGuest] = useState("");
  const [resParty, setResParty] = useState("2");
  const [resStart, setResStart] = useState("2026-11-22T18:00");
  const [resEnd, setResEnd] = useState("2026-11-22T20:00");

  // Menu form states
  const [miCode, setMiCode] = useState("");
  const [miName, setMiName] = useState("");
  const [miCategory, setMiCategory] = useState("Mains");
  const [miStation, setMiStation] = useState<KitchenStation>("hot");
  const [miPrice, setMiPrice] = useState("15.00");
  const [miCurrency, setMiCurrency] = useState("USD");

  const [mgCode, setMgCode] = useState("");
  const [mgName, setMgName] = useState("");
  const [mgMin, setMgMin] = useState("0");
  const [mgMax, setMgMax] = useState("2");

  const [optGroupId, setOptGroupId] = useState("");
  const [optCode, setOptCode] = useState("");
  const [optName, setOptName] = useState("");
  const [optDelta, setOptDelta] = useState("2.00");

  const [attachItemId, setAttachItemId] = useState("");
  const [attachGroupId, setAttachGroupId] = useState("");

  const [recItemId, setRecItemId] = useState("");
  const [recStockId, setRecStockId] = useState("");
  const [recQty, setRecQty] = useState("180");

  // Checks & split billing states
  const [chkMode, setChkMode] = useState<ServiceMode>("takeout");
  const [chkTableId, setChkTableId] = useState("");
  const [chkGuest, setChkGuest] = useState("");
  const [chkCurrency, setChkCurrency] = useState("USD");

  const [selectedCheckId, setSelectedCheckId] = useState("");
  const [lineItemId, setLineItemId] = useState("");
  const [lineQty, setLineQty] = useState("1");
  const [lineOptId, setLineOptId] = useState("");

  const [splitLabel1, setSplitLabel1] = useState("Guest 1");
  const [splitAmt1, setSplitAmt1] = useState("");
  const [splitLabel2, setSplitLabel2] = useState("Guest 2");
  const [splitAmt2, setSplitAmt2] = useState("");

  const [consEntityId, setConsEntityId] = useState("");
  const [consPlaceId, setConsPlaceId] = useState("");
  const [consDate, setConsDate] = useState("2026-10-01");

  const [selectedSplit, setSelectedSplit] = useState<CheckSplitView | null>(
    null,
  );
  const [selectedCons, setSelectedCons] = useState<CheckConsumptionView | null>(
    null,
  );
  const [selectedRecon, setSelectedRecon] =
    useState<CheckReconciliationView | null>(null);

  // Kitchen station filter
  const [stationFilter, setStationFilter] = useState<KitchenStation | "all">(
    "all",
  );

  const defaultLocation = useMemo(
    () => assignedLocationId ?? locations[0]?.id ?? "",
    [assignedLocationId, locations],
  );

  const loadAll = useCallback(async () => {
    try {
      const [ws, a, t, r, m, mg, c, kt] = await Promise.all([
        fetchWorkspace(businessId),
        fetchAreas(businessId),
        fetchTables(businessId),
        fetchReservations(businessId),
        fetchMenuItems(businessId),
        fetchModifierGroups(businessId),
        fetchChecks(businessId),
        fetchKitchenTickets(businessId),
      ]);
      setLocations(ws.locations);
      setAreas(a);
      setTables(t);
      setReservations(r);
      setMenuItems(m);
      setModifierGroups(mg);
      setChecks(c);
      setTickets(kt);
      setError(null);

      if (canManage) {
        try {
          const inv = await managementFetch<{ items: StockItemRef[] }>(
            `/v1/businesses/${businessId}/inventory/items`,
          );
          setStockItems(inv.items ?? []);
        } catch {
          setStockItems([]);
        }
      }
      if (canCompanyFinance) {
        try {
          const [pl, le] = await Promise.all([
            managementFetch<{ items: StockPlaceRef[] }>(
              `/v1/businesses/${businessId}/inventory/places`,
            ),
            managementFetch<{ items: LegalEntityRef[] }>(
              `/v1/businesses/${businessId}/legal-entities`,
            ),
          ]);
          setStockPlaces(pl.items ?? []);
          setLegalEntities(le.items ?? []);
        } catch {
          setStockPlaces([]);
          setLegalEntities([]);
        }
      }
    } catch (err) {
      setError(restaurantError(err));
    } finally {
      setLoading(false);
    }
  }, [businessId, canManage, canCompanyFinance]);

  useEffect(() => {
    let alive = true;
    void Promise.resolve().then(() => {
      if (alive) return loadAll();
      return undefined;
    });
    return () => {
      alive = false;
    };
  }, [loadAll]);

  const effAreaLoc = areaLoc || defaultLocation;
  const effTableAreaId = tableAreaId || areas[0]?.area_id || "";
  const effResTableId = resTableId || tables[0]?.table_id || "";
  const effOptGroupId = optGroupId || modifierGroups[0]?.group_id || "";
  const effAttachItemId = attachItemId || menuItems[0]?.menu_item_id || "";
  const effAttachGroupId = attachGroupId || modifierGroups[0]?.group_id || "";
  const effRecItemId = recItemId || menuItems[0]?.menu_item_id || "";
  const effRecStockId = recStockId || stockItems[0]?.item_id || "";
  const effLineItemId = lineItemId || menuItems[0]?.menu_item_id || "";
  const effConsEntityId =
    consEntityId || legalEntities[0]?.legal_entity_id || "";
  const effConsPlaceId = consPlaceId || stockPlaces[0]?.place_id || "";
  const effSelectedCheckId = selectedCheckId || checks[0]?.check_id || "";

  const checkDetailSeq = useRef(0);

  const loadCheckDetails = useCallback(
    async (checkId: string) => {
      const seq = ++checkDetailSeq.current;
      if (!checkId) {
        setSelectedSplit(null);
        setSelectedCons(null);
        setSelectedRecon(null);
        return;
      }
      try {
        const [sp, cons] = await Promise.all([
          fetchCheckSplit(businessId, checkId),
          fetchConsumption(businessId, checkId),
        ]);
        if (checkDetailSeq.current !== seq) return;
        setSelectedSplit(sp);
        setSelectedCons(cons);
        if (canCompanyFinance) {
          const recon = await fetchReconciliation(businessId, checkId);
          if (checkDetailSeq.current !== seq) return;
          setSelectedRecon(recon);
        } else {
          setSelectedRecon(null);
        }
      } catch (err) {
        if (checkDetailSeq.current !== seq) return;
        setError(restaurantError(err));
      }
    },
    [businessId, canCompanyFinance],
  );

  useEffect(() => {
    let alive = true;
    void Promise.resolve().then(() => {
      if (alive) return loadCheckDetails(effSelectedCheckId);
      return undefined;
    });
    return () => {
      alive = false;
    };
  }, [effSelectedCheckId, loadCheckDetails]);

  const selectedCheck = useMemo(
    () => checks.find((c) => c.check_id === effSelectedCheckId) ?? null,
    [checks, effSelectedCheckId],
  );

  const selectedMenuItem = useMemo(
    () => menuItems.find((m) => m.menu_item_id === effLineItemId) ?? null,
    [menuItems, effLineItemId],
  );

  const availableOptions = useMemo(() => {
    if (!selectedMenuItem) return [];
    const allowed = new Set(selectedMenuItem.modifier_group_ids);
    return modifierGroups
      .filter((g) => allowed.has(g.group_id))
      .flatMap((g) => g.options.filter((o) => o.is_active));
  }, [selectedMenuItem, modifierGroups]);

  const visibleTickets = useMemo(
    () =>
      stationFilter === "all"
        ? tickets
        : tickets.filter((t) => t.kitchen_station === stationFilter),
    [tickets, stationFilter],
  );

  const onTabKeyDown = (e: KeyboardEvent<HTMLButtonElement>, idx: number) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = TABS[(idx + 1) % TABS.length];
      if (next) setTab(next.id);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = TABS[(idx - 1 + TABS.length) % TABS.length];
      if (prev) setTab(prev.id);
    }
  };

  async function runAction(
    slot: string,
    fn: () => Promise<string | { message: string; nextCheckId?: string }>,
  ) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await fn();
      const msg = typeof result === "string" ? result : result.message;
      const targetCheckId =
        typeof result === "string"
          ? effSelectedCheckId
          : (result.nextCheckId ?? effSelectedCheckId);
      clearKey(slot);
      setNotice(msg);
      await loadAll();
      if (targetCheckId) await loadCheckDetails(targetCheckId);
    } catch (err) {
      setError(restaurantError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateArea(e: FormEvent) {
    e.preventDefault();
    const loc = effAreaLoc;
    await runAction("create-area", async () => {
      const created = await saveArea(
        businessId,
        nextId(),
        keyFor("create-area"),
        {
          expected_revision: 0,
          location_id: loc,
          name: areaName,
          service_style: areaStyle,
        },
      );
      setAreaName("");
      setTableAreaId(created.area_id);
      return `Dining area ${created.name} saved.`;
    });
  }

  async function handleCreateTable(e: FormEvent) {
    e.preventDefault();
    const area = areas.find((a) => a.area_id === effTableAreaId);
    if (!area) {
      setError("Select a dining area first.");
      return;
    }
    await runAction("create-table", async () => {
      const created = await saveTable(
        businessId,
        nextId(),
        keyFor("create-table"),
        {
          expected_revision: 0,
          location_id: area.location_id,
          area_id: area.area_id,
          code: tableCode,
          min_covers: Number(tableMin),
          max_covers: Number(tableMax),
        },
      );
      setTableCode("");
      setResTableId(created.table_id);
      return `Table ${created.code} saved.`;
    });
  }

  async function handleCreateReservation(e: FormEvent) {
    e.preventDefault();
    await runAction("create-reservation", async () => {
      const created = await createReservation(
        businessId,
        nextId(),
        keyFor("create-reservation"),
        {
          table_id: effResTableId,
          guest_name: resGuest,
          party_size: Number(resParty),
          starts_at: new Date(resStart).toISOString(),
          ends_at: new Date(resEnd).toISOString(),
        },
      );
      setResGuest("");
      return `Reservation for ${created.guest_name} booked.`;
    });
  }

  async function handleReservationAction(
    res: ReservationView,
    action: ReservationAction,
  ) {
    const slot = `res-${res.reservation_id}-${res.revision}-${action}`;
    await runAction(slot, async () => {
      const updated = await postReservationEvent(
        businessId,
        res.reservation_id,
        keyFor(slot),
        { expected_revision: res.revision, action },
      );
      return `Reservation ${updated.guest_name} is now ${updated.status}.`;
    });
  }

  async function handleCreateMenuItem(e: FormEvent) {
    e.preventDefault();
    const minor = parseMajorToMinor(miPrice);
    if (minor === null || minor < 0) {
      setError("Enter a valid non-negative price.");
      return;
    }
    await runAction("create-menu-item", async () => {
      const created = await saveMenuItem(
        businessId,
        nextId(),
        keyFor("create-menu-item"),
        {
          expected_revision: 0,
          location_id: effAreaLoc,
          code: miCode,
          name: miName,
          category: miCategory,
          kitchen_station: miStation,
          price_minor: minor,
          currency: miCurrency,
        },
      );
      setMiCode("");
      setMiName("");
      setAttachItemId(created.menu_item_id);
      setRecItemId(created.menu_item_id);
      setLineItemId(created.menu_item_id);
      return `Menu item ${created.name} saved (rev ${created.revision}).`;
    });
  }

  async function handleCreateModifierGroup(e: FormEvent) {
    e.preventDefault();
    await runAction("create-mod-group", async () => {
      const created = await saveModifierGroup(
        businessId,
        nextId(),
        keyFor("create-mod-group"),
        {
          expected_revision: 0,
          location_id: effAreaLoc,
          code: mgCode,
          name: mgName,
          min_select: Number(mgMin),
          max_select: Number(mgMax),
          currency: miCurrency,
        },
      );
      setMgCode("");
      setMgName("");
      setOptGroupId(created.group_id);
      setAttachGroupId(created.group_id);
      return `Modifier group ${created.name} saved.`;
    });
  }

  async function handleCreateModifierOption(e: FormEvent) {
    e.preventDefault();
    const delta = parseMajorToMinor(optDelta);
    if (delta === null) {
      setError("Enter a valid price delta.");
      return;
    }
    await runAction("create-mod-opt", async () => {
      const created = await saveModifierOption(
        businessId,
        effOptGroupId,
        nextId(),
        keyFor("create-mod-opt"),
        {
          expected_revision: 0,
          code: optCode,
          name: optName,
          price_delta_minor: delta,
        },
      );
      setOptCode("");
      setOptName("");
      return `Modifier option ${created.name} saved.`;
    });
  }

  async function handleAttachGroup(e: FormEvent) {
    e.preventDefault();
    const item = menuItems.find((m) => m.menu_item_id === effAttachItemId);
    if (!item || !effAttachGroupId) return;
    const nextGroups = Array.from(
      new Set([...item.modifier_group_ids, effAttachGroupId]),
    );
    await runAction("attach-group", async () => {
      await attachModifierGroups(
        businessId,
        item.menu_item_id,
        keyFor("attach-group"),
        nextGroups,
      );
      return `Modifier group attached to ${item.name}.`;
    });
  }

  async function handleCreateRecipe(e: FormEvent) {
    e.preventDefault();
    const item = menuItems.find((m) => m.menu_item_id === effRecItemId);
    if (!item || !effRecStockId) return;
    await runAction("create-recipe", async () => {
      const rec = await createRecipe(
        businessId,
        item.menu_item_id,
        keyFor("create-recipe"),
        {
          expected_revision: item.latest_recipe_revision ?? 0,
          lines: [{ stock_item_id: effRecStockId, quantity: Number(recQty) }],
        },
      );
      return `Recipe rev ${rec.revision} saved for ${item.name}.`;
    });
  }

  async function handleOpenCheck(e: FormEvent) {
    e.preventDefault();
    await runAction("open-check", async () => {
      const created = await openCheck(businessId, keyFor("open-check"), {
        location_id: effAreaLoc,
        service_mode: chkMode,
        currency: chkCurrency,
        table_id: chkTableId || null,
        guest_name: chkGuest.trim() || null,
      });
      setChkGuest("");
      setSelectedSplit(null);
      setSelectedCons(null);
      setSelectedRecon(null);
      setSelectedCheckId(created.check_id);
      return {
        message: `Check opened (${created.service_mode}).`,
        nextCheckId: created.check_id,
      };
    });
  }

  async function handleAddLine(e: FormEvent) {
    e.preventDefault();
    if (!selectedCheck) return;
    await runAction("add-line", async () => {
      await addCheckLine(
        businessId,
        selectedCheck.check_id,
        keyFor("add-line"),
        {
          menu_item_id: effLineItemId,
          quantity: Number(lineQty),
          modifier_option_ids: lineOptId ? [lineOptId] : [],
        },
      );
      return "Order line added to check.";
    });
  }

  async function handleFireCheck() {
    if (!selectedCheck) return;
    await runAction(`fire-${selectedCheck.check_id}`, async () => {
      const res = await fireCheck(
        businessId,
        selectedCheck.check_id,
        keyFor(`fire-${selectedCheck.check_id}`),
      );
      return `Fired ${res.tickets.length} kitchen ticket(s).`;
    });
  }

  async function handleSplitCheck(e: FormEvent) {
    e.preventDefault();
    if (!selectedCheck) return;
    const a1 = parseMajorToMinor(splitAmt1);
    const a2 = parseMajorToMinor(splitAmt2);
    if (a1 === null || a1 <= 0 || a2 === null || a2 <= 0) {
      setError("Enter positive amounts for both shares.");
      return;
    }
    await runAction(`split-${selectedCheck.check_id}`, async () => {
      await splitCheckByAmounts(
        businessId,
        selectedCheck.check_id,
        keyFor(`split-${selectedCheck.check_id}`),
        [
          { label: splitLabel1, amount_minor: a1 },
          { label: splitLabel2, amount_minor: a2 },
        ],
      );
      return "Check split conserved and saved.";
    });
  }

  async function handleCloseCheck() {
    if (!selectedCheck) return;
    const slot = `close-${selectedCheck.check_id}-${selectedCheck.revision}`;
    await runAction(slot, async () => {
      await closeCheck(
        businessId,
        selectedCheck.check_id,
        keyFor(slot),
        selectedCheck.revision,
      );
      return "Check closed.";
    });
  }

  async function handlePostConsumption(e: FormEvent) {
    e.preventDefault();
    if (!selectedCheck) return;
    await runAction(`cons-${selectedCheck.check_id}`, async () => {
      const res = await postConsumption(
        businessId,
        selectedCheck.check_id,
        keyFor(`cons-${selectedCheck.check_id}`),
        {
          legal_entity_id: effConsEntityId,
          place_id: effConsPlaceId,
          document_date: consDate,
        },
      );
      return res.stock_document_id
        ? `STOCK-01 write-off posted (${res.lines.length} materials).`
        : "Zero-ingredient consumption recorded.";
    });
  }

  async function handleTicketAction(
    ticket: KitchenTicketView,
    action: KitchenTicketAction,
  ) {
    const slot = `kt-${ticket.ticket_id}-${ticket.revision}-${action}`;
    await runAction(slot, async () => {
      const updated = await postKitchenEvent(
        businessId,
        ticket.ticket_id,
        keyFor(slot),
        { expected_revision: ticket.revision, action },
      );
      return `Ticket #${updated.ticket_no} (${updated.kitchen_station}) is now ${updated.status}.`;
    });
  }

  return (
    <div className="restaurant-screen">
      <h1>Restaurant</h1>
      <p>
        Manage dining floor tables, versioned menu &amp; STOCK-01 recipes,
        independent guest checks, split billing, and kitchen station tickets.
      </p>

      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}

      <div
        className="restaurant-tabs"
        role="tablist"
        aria-label="Restaurant sections"
      >
        {TABS.map((t, idx) => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            type="button"
            role="tab"
            className="restaurant-tab"
            aria-selected={tab === t.id}
            aria-controls={
              !loading && tab === t.id ? `panel-${t.id}` : undefined
            }
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKeyDown(e, idx)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p>Loading restaurant workspace...</p>
      ) : (
        <>
          {tab === "floor" && (
            <div
              id="panel-floor"
              role="tabpanel"
              aria-labelledby="tab-floor"
              className="restaurant-panel"
            >
              <section className="restaurant-card">
                <h2>Dining Areas &amp; Tables</h2>
                {canManage && (
                  <form onSubmit={handleCreateArea}>
                    <h3>New Dining Area</h3>
                    <div className="restaurant-form-grid">
                      <label>
                        Branch
                        <select
                          value={effAreaLoc}
                          onChange={(e) => setAreaLoc(e.target.value)}
                          disabled={Boolean(assignedLocationId)}
                        >
                          {locations.map((l) => (
                            <option key={l.id} value={l.id}>
                              {l.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Area name
                        <input
                          value={areaName}
                          onChange={(e) => setAreaName(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Service style
                        <select
                          value={areaStyle}
                          onChange={(e) =>
                            setAreaStyle(e.target.value as ServiceStyle)
                          }
                        >
                          <option value="dining">Dining</option>
                          <option value="bar">Bar</option>
                          <option value="patio">Patio</option>
                          <option value="private">Private</option>
                        </select>
                      </label>
                    </div>
                    <div className="restaurant-actions">
                      <button type="submit" disabled={busy}>
                        Save area
                      </button>
                    </div>
                  </form>
                )}

                {canManage && areas.length > 0 && (
                  <form onSubmit={handleCreateTable}>
                    <h3>New Table</h3>
                    <div className="restaurant-form-grid">
                      <label>
                        Dining area
                        <select
                          value={effTableAreaId}
                          onChange={(e) => setTableAreaId(e.target.value)}
                        >
                          {areas.map((a) => (
                            <option key={a.area_id} value={a.area_id}>
                              {a.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Table code
                        <input
                          value={tableCode}
                          onChange={(e) => setTableCode(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Min covers
                        <input
                          type="number"
                          min={1}
                          max={100}
                          value={tableMin}
                          onChange={(e) => setTableMin(e.target.value)}
                        />
                      </label>
                      <label>
                        Max covers
                        <input
                          type="number"
                          min={1}
                          max={100}
                          value={tableMax}
                          onChange={(e) => setTableMax(e.target.value)}
                        />
                      </label>
                    </div>
                    <div className="restaurant-actions">
                      <button type="submit" disabled={busy}>
                        Save table
                      </button>
                    </div>
                  </form>
                )}

                <div
                  className="restaurant-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Floor areas table"
                >
                  <table
                    className="restaurant-table"
                    aria-label="Restaurant tables"
                  >
                    <thead>
                      <tr>
                        <th>Code</th>
                        <th>Area</th>
                        <th>Covers</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tables.map((t) => (
                        <tr key={t.table_id}>
                          <td>{t.code}</td>
                          <td>
                            {areas.find((a) => a.area_id === t.area_id)?.name ??
                              t.area_id}
                          </td>
                          <td>
                            {t.min_covers}–{t.max_covers}
                          </td>
                          <td>{t.is_active ? "Active" : "Inactive"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="restaurant-card">
                <h2>Table Reservations</h2>
                {canService && tables.length > 0 && (
                  <form onSubmit={handleCreateReservation}>
                    <h3>Book Table</h3>
                    <div className="restaurant-form-grid">
                      <label>
                        Table
                        <select
                          value={effResTableId}
                          onChange={(e) => setResTableId(e.target.value)}
                        >
                          {tables.map((t) => (
                            <option key={t.table_id} value={t.table_id}>
                              {t.code} ({t.min_covers}–{t.max_covers})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Guest name
                        <input
                          value={resGuest}
                          onChange={(e) => setResGuest(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Party size
                        <input
                          type="number"
                          min={1}
                          max={100}
                          value={resParty}
                          onChange={(e) => setResParty(e.target.value)}
                        />
                      </label>
                      <label>
                        Starts at
                        <input
                          type="datetime-local"
                          value={resStart}
                          onChange={(e) => setResStart(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Ends at
                        <input
                          type="datetime-local"
                          value={resEnd}
                          onChange={(e) => setResEnd(e.target.value)}
                          required
                        />
                      </label>
                    </div>
                    <div className="restaurant-actions">
                      <button type="submit" disabled={busy}>
                        Book table
                      </button>
                    </div>
                  </form>
                )}

                <div
                  className="restaurant-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Dining tables list"
                >
                  <table
                    className="restaurant-table"
                    aria-label="Table reservations"
                  >
                    <thead>
                      <tr>
                        <th>Guest</th>
                        <th>Party</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reservations.map((r) => (
                        <tr key={r.reservation_id}>
                          <td>{r.guest_name}</td>
                          <td>{r.party_size}</td>
                          <td>{r.status}</td>
                          <td>
                            {canService && r.status === "booked" && (
                              <div className="restaurant-actions">
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() =>
                                    void handleReservationAction(r, "seat")
                                  }
                                >
                                  Seat
                                </button>
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() =>
                                    void handleReservationAction(r, "cancel")
                                  }
                                >
                                  Cancel
                                </button>
                              </div>
                            )}
                            {canService && r.status === "seated" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void handleReservationAction(r, "complete")
                                }
                              >
                                Complete
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          )}

          {tab === "menu" && (
            <div
              id="panel-menu"
              role="tabpanel"
              aria-labelledby="tab-menu"
              className="restaurant-panel"
            >
              <section className="restaurant-card">
                <h2>Menu Items</h2>
                {canManage && (
                  <form onSubmit={handleCreateMenuItem}>
                    <h3>New Menu Item</h3>
                    <div className="restaurant-form-grid">
                      <label>
                        Item code
                        <input
                          value={miCode}
                          onChange={(e) => setMiCode(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Item name
                        <input
                          value={miName}
                          onChange={(e) => setMiName(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Category
                        <input
                          value={miCategory}
                          onChange={(e) => setMiCategory(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Kitchen station
                        <select
                          value={miStation}
                          onChange={(e) =>
                            setMiStation(e.target.value as KitchenStation)
                          }
                        >
                          <option value="hot">Hot</option>
                          <option value="cold">Cold</option>
                          <option value="bar">Bar</option>
                          <option value="pastry">Pastry</option>
                        </select>
                      </label>
                      <label>
                        Price
                        <input
                          value={miPrice}
                          onChange={(e) => setMiPrice(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Currency
                        <input
                          value={miCurrency}
                          onChange={(e) => setMiCurrency(e.target.value)}
                          required
                        />
                      </label>
                    </div>
                    <div className="restaurant-actions">
                      <button type="submit" disabled={busy}>
                        Save menu item
                      </button>
                    </div>
                  </form>
                )}

                <div
                  className="restaurant-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Reservations table"
                >
                  <table className="restaurant-table" aria-label="Menu items">
                    <thead>
                      <tr>
                        <th>Code</th>
                        <th>Name</th>
                        <th>Station</th>
                        <th>Price</th>
                        <th>Recipe rev</th>
                      </tr>
                    </thead>
                    <tbody>
                      {menuItems.map((m) => (
                        <tr key={m.menu_item_id}>
                          <td>{m.code}</td>
                          <td>{m.name}</td>
                          <td>{m.kitchen_station}</td>
                          <td>{formatMinor(m.price_minor, m.currency)}</td>
                          <td>{m.latest_recipe_revision ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              {canManage && (
                <section className="restaurant-card">
                  <h2>Modifiers &amp; STOCK-01 Recipe BOMs</h2>
                  <form onSubmit={handleCreateModifierGroup}>
                    <h3>New Modifier Group</h3>
                    <div className="restaurant-form-grid">
                      <label>
                        Group code
                        <input
                          value={mgCode}
                          onChange={(e) => setMgCode(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Group name
                        <input
                          value={mgName}
                          onChange={(e) => setMgName(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Min select
                        <input
                          type="number"
                          min={0}
                          max={50}
                          value={mgMin}
                          onChange={(e) => setMgMin(e.target.value)}
                        />
                      </label>
                      <label>
                        Max select
                        <input
                          type="number"
                          min={1}
                          max={50}
                          value={mgMax}
                          onChange={(e) => setMgMax(e.target.value)}
                        />
                      </label>
                    </div>
                    <div className="restaurant-actions">
                      <button type="submit" disabled={busy}>
                        Save modifier group
                      </button>
                    </div>
                  </form>

                  {modifierGroups.length > 0 && (
                    <form onSubmit={handleCreateModifierOption}>
                      <h3>New Modifier Option</h3>
                      <div className="restaurant-form-grid">
                        <label>
                          Modifier group
                          <select
                            value={effOptGroupId}
                            onChange={(e) => setOptGroupId(e.target.value)}
                          >
                            {modifierGroups.map((g) => (
                              <option key={g.group_id} value={g.group_id}>
                                {g.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Option code
                          <input
                            value={optCode}
                            onChange={(e) => setOptCode(e.target.value)}
                            required
                          />
                        </label>
                        <label>
                          Option name
                          <input
                            value={optName}
                            onChange={(e) => setOptName(e.target.value)}
                            required
                          />
                        </label>
                        <label>
                          Price delta
                          <input
                            value={optDelta}
                            onChange={(e) => setOptDelta(e.target.value)}
                            required
                          />
                        </label>
                      </div>
                      <div className="restaurant-actions">
                        <button type="submit" disabled={busy}>
                          Save modifier option
                        </button>
                      </div>
                    </form>
                  )}

                  {menuItems.length > 0 && modifierGroups.length > 0 && (
                    <form onSubmit={handleAttachGroup}>
                      <h3>Attach Modifier Group to Menu Item</h3>
                      <div className="restaurant-form-grid">
                        <label>
                          Menu item
                          <select
                            value={effAttachItemId}
                            onChange={(e) => setAttachItemId(e.target.value)}
                          >
                            {menuItems.map((m) => (
                              <option
                                key={m.menu_item_id}
                                value={m.menu_item_id}
                              >
                                {m.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Modifier group to attach
                          <select
                            value={effAttachGroupId}
                            onChange={(e) => setAttachGroupId(e.target.value)}
                          >
                            {modifierGroups.map((g) => (
                              <option key={g.group_id} value={g.group_id}>
                                {g.name}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                      <div className="restaurant-actions">
                        <button type="submit" disabled={busy}>
                          Attach group
                        </button>
                      </div>
                    </form>
                  )}

                  {menuItems.length > 0 && stockItems.length > 0 && (
                    <form onSubmit={handleCreateRecipe}>
                      <h3>Save STOCK-01 Recipe BOM</h3>
                      <div className="restaurant-form-grid">
                        <label>
                          Recipe menu item
                          <select
                            value={effRecItemId}
                            onChange={(e) => setRecItemId(e.target.value)}
                          >
                            {menuItems.map((m) => (
                              <option
                                key={m.menu_item_id}
                                value={m.menu_item_id}
                              >
                                {m.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Inventory material
                          <select
                            value={effRecStockId}
                            onChange={(e) => setRecStockId(e.target.value)}
                          >
                            {stockItems.map((s) => (
                              <option key={s.item_id} value={s.item_id}>
                                {s.code} — {s.name} ({s.unit})
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Scaled quantity
                          <input
                            type="number"
                            min={1}
                            value={recQty}
                            onChange={(e) => setRecQty(e.target.value)}
                            required
                          />
                        </label>
                      </div>
                      <div className="restaurant-actions">
                        <button type="submit" disabled={busy}>
                          Save recipe revision
                        </button>
                      </div>
                    </form>
                  )}
                </section>
              )}
            </div>
          )}

          {tab === "checks" && (
            <div
              id="panel-checks"
              role="tabpanel"
              aria-labelledby="tab-checks"
              className="restaurant-panel"
            >
              {canService && (
                <section className="restaurant-card">
                  <h2>Open Independent Check</h2>
                  <form onSubmit={handleOpenCheck}>
                    <div className="restaurant-form-grid">
                      <label>
                        Service mode
                        <select
                          value={chkMode}
                          onChange={(e) =>
                            setChkMode(e.target.value as ServiceMode)
                          }
                        >
                          <option value="takeout">Takeout</option>
                          <option value="dine_in">Dine-in</option>
                          <option value="bar">Bar</option>
                          <option value="delivery">Delivery</option>
                        </select>
                      </label>
                      <label>
                        Optional table
                        <select
                          value={chkTableId}
                          onChange={(e) => setChkTableId(e.target.value)}
                        >
                          <option value="">No table (independent)</option>
                          {tables.map((t) => (
                            <option key={t.table_id} value={t.table_id}>
                              {t.code}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Guest label
                        <input
                          value={chkGuest}
                          onChange={(e) => setChkGuest(e.target.value)}
                        />
                      </label>
                      <label>
                        Check currency
                        <input
                          value={chkCurrency}
                          onChange={(e) => setChkCurrency(e.target.value)}
                          required
                        />
                      </label>
                    </div>
                    <div className="restaurant-actions">
                      <button type="submit" disabled={busy}>
                        Open check
                      </button>
                    </div>
                  </form>
                </section>
              )}

              <section className="restaurant-card">
                <h2>Active &amp; Closed Checks</h2>
                <div
                  className="restaurant-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Menu items table"
                >
                  <table
                    className="restaurant-table"
                    aria-label="Restaurant checks"
                  >
                    <thead>
                      <tr>
                        <th>Guest / Mode</th>
                        <th>Status</th>
                        <th>Subtotal</th>
                        <th>Write-off</th>
                        <th>Select</th>
                      </tr>
                    </thead>
                    <tbody>
                      {checks.map((c) => (
                        <tr key={c.check_id}>
                          <td>
                            {c.guest_name ?? "Walk-in"} ({c.service_mode})
                          </td>
                          <td>{c.status}</td>
                          <td>{formatMinor(c.subtotal_minor, c.currency)}</td>
                          <td>{c.consumption_posted ? "Posted" : "Pending"}</td>
                          <td>
                            <button
                              type="button"
                              onClick={() => {
                                if (c.check_id !== effSelectedCheckId) {
                                  setSelectedSplit(null);
                                  setSelectedCons(null);
                                  setSelectedRecon(null);
                                }
                                setSelectedCheckId(c.check_id);
                              }}
                            >
                              {effSelectedCheckId === c.check_id
                                ? "Selected"
                                : "Inspect"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {selectedCheck && (
                  <div style={{ marginTop: "20px" }}>
                    <h3>
                      Selected Check ({selectedCheck.status} —{" "}
                      {formatMinor(
                        selectedCheck.subtotal_minor,
                        selectedCheck.currency,
                      )}
                      )
                    </h3>

                    {canService &&
                      selectedCheck.status === "open" &&
                      !selectedSplit &&
                      menuItems.length > 0 && (
                        <form onSubmit={handleAddLine}>
                          <div className="restaurant-form-grid">
                            <label>
                              Order menu item
                              <select
                                value={effLineItemId}
                                onChange={(e) => {
                                  setLineItemId(e.target.value);
                                  setLineOptId("");
                                }}
                              >
                                {menuItems.map((m) => (
                                  <option
                                    key={m.menu_item_id}
                                    value={m.menu_item_id}
                                  >
                                    {m.name} (
                                    {formatMinor(m.price_minor, m.currency)})
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              Quantity
                              <input
                                type="number"
                                min={1}
                                max={100}
                                value={lineQty}
                                onChange={(e) => setLineQty(e.target.value)}
                              />
                            </label>
                            <label>
                              Optional modifier
                              <select
                                value={lineOptId}
                                onChange={(e) => setLineOptId(e.target.value)}
                              >
                                <option value="">None</option>
                                {availableOptions.map((o) => (
                                  <option key={o.option_id} value={o.option_id}>
                                    {o.name} (
                                    {formatMinor(
                                      o.price_delta_minor,
                                      selectedCheck.currency,
                                    )}
                                    )
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>
                          <div className="restaurant-actions">
                            <button type="submit" disabled={busy}>
                              Add line
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void handleFireCheck()}
                            >
                              Fire to kitchen
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void handleCloseCheck()}
                            >
                              Close check
                            </button>
                          </div>
                        </form>
                      )}

                    <div
                      className="restaurant-table-wrap"
                      tabIndex={0}
                      role="region"
                      aria-label="Checks table"
                    >
                      <table
                        className="restaurant-table"
                        aria-label="Check lines"
                      >
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Item</th>
                            <th>Station</th>
                            <th>Qty</th>
                            <th>Total</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedCheck.lines.map((l) => (
                            <tr key={l.line_id}>
                              <td>{l.line_no}</td>
                              <td>
                                {l.item_name}
                                {l.modifiers.length > 0 &&
                                  ` (+ ${l.modifiers.map((m) => m.option_name).join(", ")})`}
                              </td>
                              <td>{l.kitchen_station}</td>
                              <td>{l.quantity}</td>
                              <td>
                                {formatMinor(
                                  l.line_total_minor,
                                  selectedCheck.currency,
                                )}
                              </td>
                              <td>{l.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {canService &&
                      !selectedSplit &&
                      selectedCheck.subtotal_minor > 0 && (
                        <form onSubmit={handleSplitCheck}>
                          <h4>Split Check (Exact Amounts)</h4>
                          <div className="restaurant-form-grid">
                            <label>
                              Share 1 label
                              <input
                                value={splitLabel1}
                                onChange={(e) => setSplitLabel1(e.target.value)}
                                required
                              />
                            </label>
                            <label>
                              Share 1 amount
                              <input
                                value={splitAmt1}
                                onChange={(e) => setSplitAmt1(e.target.value)}
                                placeholder="e.g. 10.00"
                                required
                              />
                            </label>
                            <label>
                              Share 2 label
                              <input
                                value={splitLabel2}
                                onChange={(e) => setSplitLabel2(e.target.value)}
                                required
                              />
                            </label>
                            <label>
                              Share 2 amount
                              <input
                                value={splitAmt2}
                                onChange={(e) => setSplitAmt2(e.target.value)}
                                placeholder="e.g. 7.00"
                                required
                              />
                            </label>
                          </div>
                          <div className="restaurant-actions">
                            <button type="submit" disabled={busy}>
                              Save split
                            </button>
                          </div>
                        </form>
                      )}

                    {selectedSplit && (
                      <div style={{ marginTop: "12px" }}>
                        <h4>
                          Split Shares ({selectedSplit.split_mode},{" "}
                          {formatMinor(
                            selectedSplit.total_minor,
                            selectedCheck.currency,
                          )}
                          )
                        </h4>
                        <ul>
                          {selectedSplit.shares.map((s) => (
                            <li key={s.share_no}>
                              Share #{s.share_no} ({s.label}):{" "}
                              {formatMinor(
                                s.amount_minor,
                                selectedCheck.currency,
                              )}{" "}
                              — {s.billed ? "Billed" : "Unbilled"}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {selectedCons && (
                      <div style={{ marginTop: "12px" }}>
                        <h4>
                          STOCK-01 Ingredient Write-Off (
                          {selectedCons.posted ? "Posted" : "Planned"})
                        </h4>
                        {selectedCons.lines.length === 0 ? (
                          <p>No recipe ingredients linked yet.</p>
                        ) : (
                          <ul>
                            {selectedCons.lines.map((cl) => (
                              <li key={cl.stock_item_id}>
                                {cl.stock_item_code}: {cl.quantity} (
                                {cl.stock_item_unit})
                              </li>
                            ))}
                          </ul>
                        )}
                        {canCompanyFinance &&
                          !selectedCons.posted &&
                          legalEntities.length > 0 &&
                          stockPlaces.length > 0 && (
                            <form onSubmit={handlePostConsumption}>
                              <div className="restaurant-form-grid">
                                <label>
                                  Legal entity
                                  <select
                                    value={effConsEntityId}
                                    onChange={(e) =>
                                      setConsEntityId(e.target.value)
                                    }
                                  >
                                    {legalEntities.map((le) => (
                                      <option
                                        key={le.legal_entity_id}
                                        value={le.legal_entity_id}
                                      >
                                        {le.legal_name}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                                <label>
                                  Storage place
                                  <select
                                    value={effConsPlaceId}
                                    onChange={(e) =>
                                      setConsPlaceId(e.target.value)
                                    }
                                  >
                                    {stockPlaces.map((pl) => (
                                      <option
                                        key={pl.place_id}
                                        value={pl.place_id}
                                      >
                                        {pl.name} ({pl.code})
                                      </option>
                                    ))}
                                  </select>
                                </label>
                                <label>
                                  Write-off date
                                  <input
                                    type="date"
                                    value={consDate}
                                    onChange={(e) =>
                                      setConsDate(e.target.value)
                                    }
                                    required
                                  />
                                </label>
                              </div>
                              <div className="restaurant-actions">
                                <button type="submit" disabled={busy}>
                                  Post STOCK-01 write-off
                                </button>
                              </div>
                            </form>
                          )}
                      </div>
                    )}

                    {selectedRecon && (
                      <dl className="restaurant-facts">
                        <div>
                          <dt>Balanced</dt>
                          <dd>
                            {selectedRecon.totals.balanced ? "Yes" : "No"}
                          </dd>
                        </div>
                        <div>
                          <dt>Split total</dt>
                          <dd>
                            {formatMinor(
                              selectedRecon.totals.split_total_minor,
                              selectedRecon.currency,
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>Billed</dt>
                          <dd>
                            {formatMinor(
                              selectedRecon.totals.billed_total_minor,
                              selectedRecon.currency,
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>Credited</dt>
                          <dd>
                            {formatMinor(
                              selectedRecon.totals.credited_minor,
                              selectedRecon.currency,
                            )}
                          </dd>
                        </div>
                      </dl>
                    )}
                  </div>
                )}
              </section>
            </div>
          )}

          {tab === "kitchen" && (
            <div
              id="panel-kitchen"
              role="tabpanel"
              aria-labelledby="tab-kitchen"
              className="restaurant-panel"
            >
              <section className="restaurant-card">
                <h2>Kitchen Station Board</h2>
                <div
                  className="restaurant-station-bar"
                  role="group"
                  aria-label="Station filter"
                >
                  {(["all", "hot", "cold", "bar", "pastry"] as const).map(
                    (st) => (
                      <button
                        key={st}
                        type="button"
                        aria-pressed={stationFilter === st}
                        onClick={() => setStationFilter(st)}
                      >
                        {st === "all" ? "All stations" : st}
                      </button>
                    ),
                  )}
                </div>

                {visibleTickets.length === 0 ? (
                  <p style={{ marginTop: "12px" }}>
                    No kitchen tickets in this station view.
                  </p>
                ) : (
                  <div className="restaurant-ticket-grid">
                    {visibleTickets.map((t) => (
                      <article key={t.ticket_id} className="restaurant-card">
                        <h3>
                          Ticket #{t.ticket_no} — {t.kitchen_station} (
                          {t.status})
                        </h3>
                        <ul>
                          {t.lines.map((l) => (
                            <li key={l.line_id}>
                              {l.quantity} × {l.item_name}
                              {l.modifiers.length > 0 &&
                                ` [${l.modifiers.map((m) => m.option_name).join(", ")}]`}
                            </li>
                          ))}
                        </ul>
                        {canKitchen && (
                          <div className="restaurant-actions">
                            {t.status === "queued" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void handleTicketAction(t, "start")
                                }
                              >
                                Start prep
                              </button>
                            )}
                            {t.status === "preparing" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void handleTicketAction(t, "mark_ready")
                                }
                              >
                                Mark ready
                              </button>
                            )}
                            {t.status === "ready" && (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void handleTicketAction(t, "serve")
                                }
                              >
                                Mark served
                              </button>
                            )}
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </>
      )}
    </div>
  );
}
