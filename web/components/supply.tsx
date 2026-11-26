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
  fetchBoms,
  fetchGoodsOwners,
  fetchLotBalances,
  fetchLots,
  fetchOrderReturns,
  fetchOrderShipments,
  fetchPriceLists,
  fetchSerialUnits,
  fetchTradeOrders,
  fetchWarehouseBins,
  fetchWmsMovements,
  fetchWorkOrderIssues,
  fetchWorkOrderReturns,
  fetchWorkOrders,
  postInboundPutaway,
  postOrderReturn,
  postOrderShipment,
  postWorkOrderIssue,
  postWorkOrderOutput,
  postWorkOrderQc,
  postWorkOrderReturn,
  saveBom,
  saveGoodsOwner,
  saveLot,
  savePriceList,
  saveTradeOrder,
  saveWarehouseBin,
  saveWorkOrder,
  supplyError,
} from "../lib/supply-api";
import {
  formatSupplyMinor,
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
  type WorkOrderReturnView,
  type WorkOrderView,
} from "../lib/supply-contracts";

type TabId = "wms" | "movements" | "manufacturing" | "trade";

const TABS: { id: TabId; label: string }[] = [
  { id: "wms", label: "WMS Owners & Bins" },
  { id: "movements", label: "Lots, Balances & Movements" },
  { id: "manufacturing", label: "Manufacturing & Costing" },
  { id: "trade", label: "Trade & 3PL Orders" },
];

type StockItemRef = { item_id: string; code: string; name: string };
type StockPlaceRef = {
  place_id: string;
  location_id: string;
  code: string;
  name: string;
};
type CounterpartyRef = { counterparty_id: string; display_name: string };
type LegalEntityRef = {
  legal_entity_id: string;
  code: string;
  legal_name: string;
  book: { book_id: string; base_currency: string } | null;
};
type AccountRef = {
  account_id: string;
  code: string;
  name: string;
  type: string;
};

function newId(): string {
  return crypto.randomUUID();
}

export function SupplyScreen({
  businessId,
  assignedLocationId,
  canWork,
  canManage,
}: {
  businessId: string;
  assignedLocationId: string | null;
  canWork: boolean;
  canManage: boolean;
}) {
  const [tab, setTab] = useState<TabId>("wms");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [stockItems, setStockItems] = useState<StockItemRef[]>([]);
  const [stockPlaces, setStockPlaces] = useState<StockPlaceRef[]>([]);
  const [counterparties, setCounterparties] = useState<CounterpartyRef[]>([]);
  const [legalEntities, setLegalEntities] = useState<LegalEntityRef[]>([]);
  const [accounts, setAccounts] = useState<AccountRef[]>([]);

  const [owners, setOwners] = useState<GoodsOwnerView[]>([]);
  const [bins, setBins] = useState<WarehouseBinView[]>([]);
  const [lots, setLots] = useState<LotView[]>([]);
  const [serials, setSerials] = useState<SerialUnitView[]>([]);
  const [balances, setBalances] = useState<LotBalanceView[]>([]);
  const [movements, setMovements] = useState<WmsMovementView[]>([]);
  const [boms, setBoms] = useState<BomView[]>([]);
  const [workOrders, setWorkOrders] = useState<WorkOrderView[]>([]);
  const [priceLists, setPriceLists] = useState<PriceListView[]>([]);
  const [tradeOrders, setTradeOrders] = useState<TradeOrderView[]>([]);

  const [selectedWoId, setSelectedWoId] = useState("");
  const [woIssues, setWoIssues] = useState<WorkOrderIssueView[]>([]);
  const [woReturns, setWoReturns] = useState<WorkOrderReturnView[]>([]);

  const [selectedOrderId, setSelectedOrderId] = useState("");
  const [orderShipments, setOrderShipments] = useState<OrderShipmentView[]>([]);
  const [orderReturns, setOrderReturns] = useState<OrderReturnView[]>([]);

  // Tab 1: Goods Owner form
  const [ownLoc, setOwnLoc] = useState("");
  const [ownCode, setOwnCode] = useState("");
  const [ownName, setOwnName] = useState("");
  const [ownKind, setOwnKind] = useState<GoodsOwnerKind>("company_entity");
  const [ownLeId, setOwnLeId] = useState("");
  const [ownCpId, setOwnCpId] = useState("");

  // Tab 1: Warehouse Bin form
  const [binLoc, setBinLoc] = useState("");
  const [binPlaceId, setBinPlaceId] = useState("");
  const [binZoneCode, setBinZoneCode] = useState("ZONE_A");
  const [binCode, setBinCode] = useState("");
  const [binKind, setBinKind] = useState<BinKind>("storage");
  const [binDedicatedOwner, setBinDedicatedOwner] = useState("");

  // Tab 1: Lot form
  const [lotOwnerId, setLotOwnerId] = useState("");
  const [lotItemId, setLotItemId] = useState("");
  const [lotCode, setLotCode] = useState("");
  const [lotUnitCost, setLotUnitCost] = useState("5000");

  // Tab 2: Inbound Putaway form
  const [inOwnerId, setInOwnerId] = useState("");
  const [inBinId, setInBinId] = useState("");
  const [inItemId, setInItemId] = useState("");
  const [inLotId, setInLotId] = useState("");
  const [inQty, setInQty] = useState("10");
  const [inAmount, setInAmount] = useState("500.00");
  const [inDate, setInDate] = useState("2026-10-01");

  // Tab 3: BOM form
  const [bomCode, setBomCode] = useState("");
  const [bomTitle, setBomTitle] = useState("");
  const [bomOutputItem, setBomOutputItem] = useState("");
  const [bomCompItem, setBomCompItem] = useState("");
  const [bomCompQty, setBomCompQty] = useState("2");
  const [bomLabor, setBomLabor] = useState("3000");
  const [bomOverhead, setBomOverhead] = useState("1000");

  // Tab 3: Work Order form
  const [woCode, setWoCode] = useState("");
  const [woOwnerId, setWoOwnerId] = useState("");
  const [woBomId, setWoBomId] = useState("");
  const [woPlaceId, setWoPlaceId] = useState("");
  const [woPlannedQty, setWoPlannedQty] = useState("2");

  // Tab 3: Work Order lifecycle sub-forms
  const [issBinId, setIssBinId] = useState("");
  const [issItemId, setIssItemId] = useState("");
  const [issLotId, setIssLotId] = useState("");
  const [issQty, setIssQty] = useState("5");
  const [issDate, setIssDate] = useState("2026-10-02");

  const [retIssueId, setRetIssueId] = useState("");
  const [retBinId, setRetBinId] = useState("");
  const [retQty, setRetQty] = useState("1");
  const [retDate, setRetDate] = useState("2026-10-03");

  const [qcPassedQty, setQcPassedQty] = useState("2");
  const [qcScrapQty, setQcScrapQty] = useState("0");

  const [outBinId, setOutBinId] = useState("");
  const [outLotCode, setOutLotCode] = useState("LOT-FG-UI-01");
  const [outDate, setOutDate] = useState("2026-10-04");

  // Tab 4: Price List form
  const [plCode, setPlCode] = useState("");
  const [plTitle, setPlTitle] = useState("");
  const [plChannel, setPlChannel] = useState<PriceChannel>("wholesale");
  const [plItemId, setPlItemId] = useState("");
  const [plMinQty, setPlMinQty] = useState("1");
  const [plUnitPrice, setPlUnitPrice] = useState("25000");

  // Tab 4: Trade Order form
  const [ordCode, setOrdCode] = useState("");
  const [ordKind, setOrdKind] = useState<TradeOrderKind>("wholesale_sale");
  const [ordOwnerId, setOrdOwnerId] = useState("");
  const [ordCustomerId, setOrdCustomerId] = useState("");
  const [ordPriceListId, setOrdPriceListId] = useState("");
  const [ordItemId, setOrdItemId] = useState("");
  const [ordQty, setOrdQty] = useState("2");
  const [ordUnitPrice, setOrdUnitPrice] = useState("25000");
  const [ordBookId, setOrdBookId] = useState("");
  const [ordArAccountId, setOrdArAccountId] = useState("");
  const [ordRevAccountId, setOrdRevAccountId] = useState("");

  // Tab 4: Shipment & Return sub-forms
  const [shpLineId, setShpLineId] = useState("");
  const [shpBinId, setShpBinId] = useState("");
  const [shpLotId, setShpLotId] = useState("");
  const [shpQty, setShpQty] = useState("2");
  const [shpDate, setShpDate] = useState("2026-10-05");

  const [cRetShipmentId, setCRetShipmentId] = useState("");
  const [cRetBinId, setCRetBinId] = useState("");
  const [cRetQty, setCRetQty] = useState("1");
  const [cRetDate, setCRetDate] = useState("2026-10-06");
  const [cRetReason, setCRetReason] = useState("Customer partial return");

  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const ordBookIdRef = useRef("");

  const books = useMemo(
    () =>
      legalEntities.flatMap((le) =>
        le.book
          ? [
              {
                book_id: le.book.book_id,
                code: le.code,
                base_currency: le.book.base_currency,
              },
            ]
          : [],
      ),
    [legalEntities],
  );
  const arAccounts = useMemo(
    () => accounts.filter((a) => a.type === "asset"),
    [accounts],
  );
  const revAccounts = useMemo(
    () => accounts.filter((a) => a.type === "revenue"),
    [accounts],
  );

  const loadBookAccounts = useCallback(
    async (bookId: string) => {
      if (!bookId) return;
      ordBookIdRef.current = bookId;
      setBusy(true);
      try {
        const acctRes = await managementFetch<{ items: AccountRef[] }>(
          `/v1/businesses/${businessId}/ledger/books/${bookId}/accounts?limit=100`,
        );
        const acctList = acctRes.items ?? [];
        setAccounts(acctList);
        const ar =
          acctList.find((a) => a.code === "1200") ??
          acctList.find((a) => a.type === "asset");
        const rev =
          acctList.find((a) => a.code === "4000") ??
          acctList.find((a) => a.type === "revenue");
        if (ar) setOrdArAccountId(ar.account_id);
        if (rev) setOrdRevAccountId(rev.account_id);
      } finally {
        setBusy(false);
      }
    },
    [businessId],
  );

  const selectedOrder = useMemo(
    () => tradeOrders.find((o) => o.order_id === selectedOrderId) ?? null,
    [tradeOrders, selectedOrderId],
  );

  const loadWorkOrderDetail = useCallback(
    async (woId: string) => {
      if (!woId) return;
      const [iss, ret] = await Promise.all([
        fetchWorkOrderIssues(businessId, woId),
        fetchWorkOrderReturns(businessId, woId),
      ]);
      setWoIssues(iss);
      setWoReturns(ret);
      const latestIss = iss[iss.length - 1];
      if (latestIss) {
        setRetIssueId(latestIss.issue_id);
        setRetBinId(latestIss.bin_id);
      }
    },
    [businessId],
  );

  const loadTradeOrderDetail = useCallback(
    async (ordId: string) => {
      if (!ordId) return;
      const [shps, rets] = await Promise.all([
        fetchOrderShipments(businessId, ordId),
        fetchOrderReturns(businessId, ordId),
      ]);
      setOrderShipments(shps);
      setOrderReturns(rets);
      const latestShp = shps[shps.length - 1];
      if (latestShp) {
        setCRetShipmentId(latestShp.shipment_id);
        setCRetBinId(latestShp.bin_id);
      }
    },
    [businessId],
  );

  const reloadAll = useCallback(
    async (opts?: { woId?: string; orderId?: string }) => {
      setLoading(true);
      setError(null);
      try {
        const [
          ws,
          ownList,
          binList,
          lotList,
          serList,
          balList,
          movList,
          bomList,
          woList,
          plList,
          ordList,
        ] = await Promise.all([
          fetchWorkspace(businessId),
          fetchGoodsOwners(businessId),
          fetchWarehouseBins(businessId),
          fetchLots(businessId),
          fetchSerialUnits(businessId),
          fetchLotBalances(businessId),
          fetchWmsMovements(businessId),
          fetchBoms(businessId),
          fetchWorkOrders(businessId),
          fetchPriceLists(businessId),
          fetchTradeOrders(businessId),
        ]);
        const locs = ws.locations.filter((l) =>
          assignedLocationId ? l.id === assignedLocationId : true,
        );
        setLocations(locs);
        setOwners(ownList);
        setBins(binList);
        setLots(lotList);
        setSerials(serList);
        setBalances(balList);
        setMovements(movList);
        setBoms(bomList);
        setWorkOrders(woList);
        setPriceLists(plList);
        setTradeOrders(ordList);

        const defaultLoc = assignedLocationId ?? locs[0]?.id ?? "";
        setOwnLoc((p) => p || defaultLoc);
        setBinLoc((p) => p || defaultLoc);

        try {
          const [itemsRes, placesRes, cpsRes, ledgerRes] = await Promise.all([
            managementFetch<{ items: StockItemRef[] }>(
              `/v1/businesses/${businessId}/inventory/items`,
            ),
            managementFetch<{ items: StockPlaceRef[] }>(
              `/v1/businesses/${businessId}/inventory/places`,
            ),
            managementFetch<{ items: CounterpartyRef[] }>(
              `/v1/businesses/${businessId}/counterparties`,
            ),
            managementFetch<{ items: LegalEntityRef[] }>(
              `/v1/businesses/${businessId}/ledger`,
            ),
          ]);
          const itList = itemsRes.items ?? [];
          const plPlaces = placesRes.items ?? [];
          const cpList = cpsRes.items ?? [];
          const leList = ledgerRes.items ?? [];
          setStockItems(itList);
          setStockPlaces(plPlaces);
          setCounterparties(cpList);
          setLegalEntities(leList);

          const firstLe = leList[0];
          if (firstLe) setOwnLeId((p) => p || firstLe.legal_entity_id);
          const firstCp = cpList[0];
          if (firstCp) {
            setOwnCpId((p) => p || firstCp.counterparty_id);
            setOrdCustomerId((p) => p || firstCp.counterparty_id);
          }
          const firstPlace = plPlaces[0];
          if (firstPlace) {
            setBinPlaceId((p) => p || firstPlace.place_id);
            setWoPlaceId((p) => p || firstPlace.place_id);
          }
          const firstItem = itList[0];
          if (firstItem) {
            const secondItemId = itList[1]?.item_id ?? firstItem.item_id;
            setLotItemId((p) => p || firstItem.item_id);
            setInItemId((p) => p || firstItem.item_id);
            setBomCompItem((p) => p || firstItem.item_id);
            setBomOutputItem((p) => p || secondItemId);
            setIssItemId((p) => p || firstItem.item_id);
            setPlItemId((p) => p || secondItemId);
            setOrdItemId((p) => p || secondItemId);
          }

          const firstBook = leList.find((l) => l.book)?.book;
          const activeBookId = ordBookIdRef.current || firstBook?.book_id || "";
          if (activeBookId) {
            ordBookIdRef.current = activeBookId;
            setOrdBookId((p) => p || activeBookId);
            const acctRes = await managementFetch<{ items: AccountRef[] }>(
              `/v1/businesses/${businessId}/ledger/books/${activeBookId}/accounts?limit=100`,
            );
            const acctList = acctRes.items ?? [];
            setAccounts(acctList);
            const ar =
              acctList.find((a) => a.code === "1200") ??
              acctList.find((a) => a.type === "asset");
            const rev =
              acctList.find((a) => a.code === "4000") ??
              acctList.find((a) => a.type === "revenue");
            if (ar) setOrdArAccountId((p) => p || ar.account_id);
            if (rev) setOrdRevAccountId((p) => p || rev.account_id);
          }
        } catch {
          // Optional reference endpoints when user lacks finance/counterparty permissions
        }

        const firstOwner = ownList[0];
        if (firstOwner) {
          setLotOwnerId((p) => p || firstOwner.goods_owner_id);
          setInOwnerId((p) => p || firstOwner.goods_owner_id);
          setWoOwnerId((p) => p || firstOwner.goods_owner_id);
          setOrdOwnerId((p) => p || firstOwner.goods_owner_id);
        }
        const firstBin = binList[0];
        if (firstBin) {
          setInBinId((p) => p || firstBin.bin_id);
          setIssBinId((p) => p || firstBin.bin_id);
          setRetBinId((p) => p || firstBin.bin_id);
          setOutBinId((p) => p || firstBin.bin_id);
          setShpBinId((p) => p || firstBin.bin_id);
          setCRetBinId((p) => p || firstBin.bin_id);
        }
        const firstLot = lotList[0];
        if (firstLot) {
          setInLotId((p) => p || firstLot.lot_id);
          setIssLotId((p) => p || firstLot.lot_id);
          setShpLotId((p) => p || firstLot.lot_id);
        }
        const firstBom = bomList[0];
        if (firstBom) {
          setWoBomId((p) => p || firstBom.bom_id);
        }
        const activeWo =
          opts?.woId || selectedWoId || woList[0]?.work_order_id || "";
        if (activeWo) {
          setSelectedWoId(activeWo);
          await loadWorkOrderDetail(activeWo);
        }
        const activeOrd =
          opts?.orderId || selectedOrderId || ordList[0]?.order_id || "";
        if (activeOrd) {
          setSelectedOrderId(activeOrd);
          const ordObj = ordList.find((o) => o.order_id === activeOrd);
          if (ordObj?.lines[0]) {
            setShpLineId(ordObj.lines[0].order_line_id);
          }
          await loadTradeOrderDetail(activeOrd);
        }
      } catch (err) {
        setError(supplyError(err));
      } finally {
        setLoading(false);
      }
    },
    [
      assignedLocationId,
      businessId,
      loadTradeOrderDetail,
      loadWorkOrderDetail,
      selectedOrderId,
      selectedWoId,
    ],
  );

  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    const timer = window.setTimeout(() => {
      if (!initializedRef.current) {
        initializedRef.current = true;
        void reloadAll();
      }
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [reloadAll]);

  function onTabKeyDown(idx: number, e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const nextIdx =
      e.key === "ArrowRight"
        ? (idx + 1) % TABS.length
        : (idx - 1 + TABS.length) % TABS.length;
    const nextTab = TABS[nextIdx];
    if (nextTab) {
      setTab(nextTab.id);
      tabRefs.current[nextIdx]?.focus();
    }
  }

  async function handleSaveOwner(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !ownLoc || !ownCode.trim() || !ownName.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveGoodsOwner(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: ownLoc,
        code: ownCode.trim().toUpperCase(),
        display_name: ownName.trim(),
        owner_kind: ownKind,
        legal_entity_id: ownKind === "company_entity" ? ownLeId || null : null,
        counterparty_id:
          ownKind === "counterparty_3pl" ? ownCpId || null : null,
      });
      setOwnCode("");
      setOwnName("");
      setLotOwnerId(created.goods_owner_id);
      setInOwnerId(created.goods_owner_id);
      if (created.owner_kind === "company_entity") {
        setWoOwnerId(created.goods_owner_id);
        setOrdOwnerId(created.goods_owner_id);
      }
      setNotice(`Saved goods owner ${created.code}`);
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveBin(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !binLoc || !binPlaceId || !binCode.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveWarehouseBin(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: binLoc,
        place_id: binPlaceId,
        zone_code: binZoneCode.trim().toUpperCase(),
        bin_code: binCode.trim().toUpperCase(),
        bin_kind: binKind,
        dedicated_owner_id: binDedicatedOwner || null,
      });
      setBinCode("");
      setInBinId(created.bin_id);
      setIssBinId(created.bin_id);
      setRetBinId(created.bin_id);
      setOutBinId(created.bin_id);
      setShpBinId(created.bin_id);
      setCRetBinId(created.bin_id);
      setNotice(`Saved warehouse bin ${created.bin_code}`);
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveLot(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !lotOwnerId || !lotItemId || !lotCode.trim()) return;
    const owner = owners.find((o) => o.goods_owner_id === lotOwnerId);
    if (!owner) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveLot(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: owner.location_id,
        goods_owner_id: lotOwnerId,
        item_id: lotItemId,
        lot_code: lotCode.trim().toUpperCase(),
        unit_cost_minor: Number(lotUnitCost) || 0,
      });
      setLotCode("");
      setInLotId(created.lot_id);
      setIssLotId(created.lot_id);
      setShpLotId(created.lot_id);
      setNotice(`Saved lot ${created.lot_code}`);
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleInboundPutaway(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !inOwnerId || !inBinId || !inItemId || !inLotId) return;
    const owner = owners.find((o) => o.goods_owner_id === inOwnerId);
    if (!owner) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const isCompany = owner.owner_kind === "company_entity";
      const mov = await postInboundPutaway(businessId, newId(), {
        location_id: owner.location_id,
        bin_id: inBinId,
        goods_owner_id: inOwnerId,
        item_id: inItemId,
        lot_id: inLotId,
        quantity: Number(inQty) || 1,
        auto_stock_receipt_date: isCompany ? inDate : null,
        auto_stock_receipt_reason: "purchase",
        auto_stock_receipt_amount: isCompany ? inAmount : null,
      });
      setNotice(`Recorded inbound putaway (${mov.quantity} units)`);
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveBom(e: FormEvent) {
    e.preventDefault();
    if (
      !canManage ||
      !bomCode.trim() ||
      !bomTitle.trim() ||
      !bomOutputItem ||
      !bomCompItem
    )
      return;
    const locId = ownLoc || locations[0]?.id || "";
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveBom(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        code: bomCode.trim().toUpperCase(),
        title: bomTitle.trim(),
        output_item_id: bomOutputItem,
        batch_output_quantity: 1,
        standard_labor_minor: Number(bomLabor) || 0,
        standard_overhead_minor: Number(bomOverhead) || 0,
        components: [
          {
            component_item_id: bomCompItem,
            quantity_per_batch: Number(bomCompQty) || 1,
          },
        ],
      });
      setBomCode("");
      setBomTitle("");
      setWoBomId(created.bom_id);
      setNotice(`Saved BOM ${created.code}`);
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateWorkOrder(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !woCode.trim() || !woOwnerId || !woBomId || !woPlaceId)
      return;
    const owner = owners.find((o) => o.goods_owner_id === woOwnerId);
    if (!owner) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveWorkOrder(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: owner.location_id,
        code: woCode.trim().toUpperCase(),
        goods_owner_id: woOwnerId,
        bom_id: woBomId,
        place_id: woPlaceId,
        planned_quantity: Number(woPlannedQty) || 1,
      });
      setWoCode("");
      setSelectedWoId(created.work_order_id);
      setNotice(`Created work order ${created.code}`);
      await reloadAll({ woId: created.work_order_id });
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePostWoIssue(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !selectedWoId || !issBinId || !issItemId || !issLotId)
      return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const iss = await postWorkOrderIssue(businessId, selectedWoId, newId(), {
        bin_id: issBinId,
        component_item_id: issItemId,
        lot_id: issLotId,
        quantity: Number(issQty) || 1,
        document_date: issDate,
      });
      setRetIssueId(iss.issue_id);
      setRetBinId(iss.bin_id);
      setNotice(
        `Issued ${iss.quantity} component units (STOCK-01 cost ${formatSupplyMinor(iss.cost_minor)})`,
      );
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePostWoReturn(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !selectedWoId || !retIssueId || !retBinId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const ret = await postWorkOrderReturn(businessId, selectedWoId, newId(), {
        issue_id: retIssueId,
        bin_id: retBinId,
        quantity: Number(retQty) || 1,
        document_date: retDate,
      });
      setNotice(
        `Returned ${ret.quantity} unused component units (cost restored ${formatSupplyMinor(ret.cost_returned_minor)})`,
      );
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePostWoQc(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !selectedWoId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const qc = await postWorkOrderQc(businessId, selectedWoId, newId(), {
        passed_quantity: Number(qcPassedQty) || 1,
        scrap_quantity: Number(qcScrapQty) || 0,
        notes: "QC passed in UI",
      });
      setNotice(`Recorded QC inspection (${qc.passed_quantity} passed)`);
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePostWoOutput(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !selectedWoId || !outBinId || !outLotCode.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const out = await postWorkOrderOutput(businessId, selectedWoId, newId(), {
        bin_id: outBinId,
        output_lot_code: outLotCode.trim().toUpperCase(),
        manufactured_on: outDate,
      });
      setShpLotId(out.output_lot_id);
      setShpBinId(out.bin_id);
      setNotice(
        `Posted finished output lot (${out.quantity} units, total cost ${formatSupplyMinor(out.total_cost_minor)})`,
      );
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePriceList(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !plCode.trim() || !plTitle.trim() || !plItemId) return;
    const locId = ownLoc || locations[0]?.id || "";
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await savePriceList(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        code: plCode.trim().toUpperCase(),
        title: plTitle.trim(),
        channel: plChannel,
        currency: "USD",
        items: [
          {
            item_id: plItemId,
            min_quantity: Number(plMinQty) || 1,
            unit_price_minor: Number(plUnitPrice) || 0,
          },
        ],
      });
      setPlCode("");
      setPlTitle("");
      setOrdPriceListId(created.price_list_id);
      setNotice(`Saved price list ${created.code}`);
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateTradeOrder(e: FormEvent) {
    e.preventDefault();
    if (
      !canWork ||
      !ordCode.trim() ||
      !ordOwnerId ||
      !ordCustomerId ||
      !ordItemId
    )
      return;
    const owner = owners.find((o) => o.goods_owner_id === ordOwnerId);
    if (!owner) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const isSale = ordKind === "wholesale_sale" || ordKind === "retail_sale";
      const created = await saveTradeOrder(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: owner.location_id,
        code: ordCode.trim().toUpperCase(),
        order_kind: ordKind,
        goods_owner_id: ordOwnerId,
        customer_counterparty_id: ordCustomerId,
        price_list_id: ordPriceListId || null,
        currency: "USD",
        book_id: isSale ? ordBookId || null : null,
        control_account_id: isSale ? ordArAccountId || null : null,
        revenue_account_id: isSale ? ordRevAccountId || null : null,
        lines: [
          {
            item_id: ordItemId,
            ordered_quantity: Number(ordQty) || 1,
            unit_price_minor: ordPriceListId ? null : Number(ordUnitPrice) || 0,
          },
        ],
      });
      setOrdCode("");
      setSelectedOrderId(created.order_id);
      if (created.lines[0]) {
        setShpLineId(created.lines[0].order_line_id);
      }
      setNotice(`Created trade order ${created.code}`);
      await reloadAll({ orderId: created.order_id });
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePostOrderShipment(e: FormEvent) {
    e.preventDefault();
    if (!canWork || !selectedOrderId || !shpLineId || !shpBinId || !shpLotId)
      return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const shp = await postOrderShipment(
        businessId,
        selectedOrderId,
        newId(),
        {
          order_line_id: shpLineId,
          bin_id: shpBinId,
          lot_id: shpLotId,
          quantity: Number(shpQty) || 1,
          document_date: shpDate,
        },
      );
      setCRetShipmentId(shp.shipment_id);
      setCRetBinId(shp.bin_id);
      setNotice(
        `Shipped ${shp.quantity} units (revenue ${formatSupplyMinor(shp.revenue_minor)}, COGS ${formatSupplyMinor(shp.cogs_minor)})`,
      );
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePostCustomerReturn(e: FormEvent) {
    e.preventDefault();
    if (
      !canWork ||
      !selectedOrderId ||
      !cRetShipmentId ||
      !cRetBinId ||
      !cRetReason.trim()
    )
      return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const ret = await postOrderReturn(businessId, selectedOrderId, newId(), {
        shipment_id: cRetShipmentId,
        bin_id: cRetBinId,
        quantity: Number(cRetQty) || 1,
        document_date: cRetDate,
        reason: cRetReason.trim(),
      });
      setNotice(
        `Processed customer return (${ret.quantity} units, refund ${formatSupplyMinor(ret.refund_minor)}, COGS restored ${formatSupplyMinor(ret.cogs_restored_minor)})`,
      );
      await reloadAll();
    } catch (err) {
      setError(supplyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="supply-shell">
      <header>
        <h1>Supply Chain, 3PL WMS &amp; Manufacturing</h1>
        <p>
          Multi-warehouse bin locations, goods-owner isolation (company vs 3PL
          bailors), lot/serial traceability, and manufacturing &amp; trade cost
          conservation extending STOCK-01 and FIN-03.
        </p>
      </header>

      {error ? (
        <div role="alert" className="mgmt-error">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div role="status" className="mgmt-notice">
          {notice}
        </div>
      ) : null}
      {loading ? <p>Loading supply chain workspace…</p> : null}

      <div
        className="supply-tabs"
        role="tablist"
        aria-label="Supply chain sections"
      >
        {TABS.map((t, idx) => (
          <button
            key={t.id}
            ref={(el) => {
              tabRefs.current[idx] = el;
            }}
            id={`tab-${t.id}`}
            type="button"
            role="tab"
            className="supply-tab"
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKeyDown(idx, e)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "wms" ? (
        <section
          id="panel-wms"
          role="tabpanel"
          aria-labelledby="tab-wms"
          className="supply-panel"
        >
          <div className="supply-card">
            <h2>Goods Owners (Company vs 3PL Bailors)</h2>
            <form onSubmit={handleSaveOwner}>
              <div className="supply-form-grid">
                <label>
                  Owner location
                  <select
                    value={ownLoc}
                    onChange={(e) => setOwnLoc(e.target.value)}
                  >
                    {locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Owner code
                  <input
                    value={ownCode}
                    onChange={(e) => setOwnCode(e.target.value)}
                    placeholder="OWN_CO_01"
                  />
                </label>
                <label>
                  Owner display name
                  <input
                    value={ownName}
                    onChange={(e) => setOwnName(e.target.value)}
                    placeholder="AMARKAL Supply Corp"
                  />
                </label>
                <label>
                  Owner kind
                  <select
                    value={ownKind}
                    onChange={(e) =>
                      setOwnKind(e.target.value as GoodsOwnerKind)
                    }
                  >
                    <option value="company_entity">company_entity</option>
                    <option value="counterparty_3pl">counterparty_3pl</option>
                  </select>
                </label>
                {ownKind === "company_entity" ? (
                  <label>
                    Legal entity
                    <select
                      value={ownLeId}
                      onChange={(e) => setOwnLeId(e.target.value)}
                    >
                      {legalEntities.map((le) => (
                        <option
                          key={le.legal_entity_id}
                          value={le.legal_entity_id}
                        >
                          {le.code} — {le.legal_name}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <label>
                    3PL Counterparty
                    <select
                      value={ownCpId}
                      onChange={(e) => setOwnCpId(e.target.value)}
                    >
                      {counterparties.map((cp) => (
                        <option
                          key={cp.counterparty_id}
                          value={cp.counterparty_id}
                        >
                          {cp.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save goods owner
                </button>
              </div>
            </form>
            <div
              className="supply-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Goods owners table"
            >
              <table className="supply-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Name</th>
                    <th>Kind</th>
                  </tr>
                </thead>
                <tbody>
                  {owners.map((o) => (
                    <tr key={o.goods_owner_id}>
                      <td>{o.code}</td>
                      <td>{o.display_name}</td>
                      <td>{o.owner_kind}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="supply-card">
            <h2>Warehouse Zones &amp; Bins</h2>
            <form onSubmit={handleSaveBin}>
              <div className="supply-form-grid">
                <label>
                  Bin location
                  <select
                    value={binLoc}
                    onChange={(e) => setBinLoc(e.target.value)}
                  >
                    {locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Stock place
                  <select
                    value={binPlaceId}
                    onChange={(e) => setBinPlaceId(e.target.value)}
                  >
                    {stockPlaces.map((p) => (
                      <option key={p.place_id} value={p.place_id}>
                        {p.code} — {p.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Zone code
                  <input
                    value={binZoneCode}
                    onChange={(e) => setBinZoneCode(e.target.value)}
                  />
                </label>
                <label>
                  Bin code
                  <input
                    value={binCode}
                    onChange={(e) => setBinCode(e.target.value)}
                    placeholder="BIN_A_01"
                  />
                </label>
                <label>
                  Bin kind
                  <select
                    value={binKind}
                    onChange={(e) => setBinKind(e.target.value as BinKind)}
                  >
                    <option value="storage">storage</option>
                    <option value="receiving">receiving</option>
                    <option value="picking">picking</option>
                    <option value="production">production</option>
                    <option value="shipping">shipping</option>
                  </select>
                </label>
                <label>
                  Dedicated goods owner
                  <select
                    value={binDedicatedOwner}
                    onChange={(e) => setBinDedicatedOwner(e.target.value)}
                  >
                    <option value="">(Shared bin)</option>
                    {owners.map((o) => (
                      <option key={o.goods_owner_id} value={o.goods_owner_id}>
                        {o.code} ({o.owner_kind})
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save warehouse bin
                </button>
              </div>
            </form>
            <div
              className="supply-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Warehouse bins table"
            >
              <table className="supply-table">
                <thead>
                  <tr>
                    <th>Zone</th>
                    <th>Bin</th>
                    <th>Kind</th>
                    <th>Dedicated Owner</th>
                  </tr>
                </thead>
                <tbody>
                  {bins.map((b) => (
                    <tr key={b.bin_id}>
                      <td>{b.zone_code}</td>
                      <td>{b.bin_code}</td>
                      <td>{b.bin_kind}</td>
                      <td>
                        {owners.find(
                          (o) => o.goods_owner_id === b.dedicated_owner_id,
                        )?.code ?? "Shared"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="supply-card">
            <h2>Lots / Batches</h2>
            <form onSubmit={handleSaveLot}>
              <div className="supply-form-grid">
                <label>
                  Lot goods owner
                  <select
                    value={lotOwnerId}
                    onChange={(e) => setLotOwnerId(e.target.value)}
                  >
                    {owners.map((o) => (
                      <option key={o.goods_owner_id} value={o.goods_owner_id}>
                        {o.code} ({o.owner_kind})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Lot stock item
                  <select
                    value={lotItemId}
                    onChange={(e) => setLotItemId(e.target.value)}
                  >
                    {stockItems.map((it) => (
                      <option key={it.item_id} value={it.item_id}>
                        {it.code} — {it.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Lot code
                  <input
                    value={lotCode}
                    onChange={(e) => setLotCode(e.target.value)}
                    placeholder="LOT-CO-01"
                  />
                </label>
                <label>
                  Lot unit cost minor
                  <input
                    type="number"
                    value={lotUnitCost}
                    onChange={(e) => setLotUnitCost(e.target.value)}
                  />
                </label>
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canWork}>
                  Save lot
                </button>
              </div>
            </form>
            <div
              className="supply-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Lots table"
            >
              <table className="supply-table">
                <thead>
                  <tr>
                    <th>Lot Code</th>
                    <th>Owner</th>
                    <th>Item</th>
                    <th>Unit Cost</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((l) => (
                    <tr key={l.lot_id}>
                      <td>{l.lot_code}</td>
                      <td>
                        {owners.find(
                          (o) => o.goods_owner_id === l.goods_owner_id,
                        )?.code ?? l.goods_owner_id}
                      </td>
                      <td>
                        {stockItems.find((i) => i.item_id === l.item_id)
                          ?.code ?? l.item_id}
                      </td>
                      <td>{formatSupplyMinor(l.unit_cost_minor)}</td>
                      <td>{l.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {tab === "movements" ? (
        <section
          id="panel-movements"
          role="tabpanel"
          aria-labelledby="tab-movements"
          className="supply-panel"
        >
          <div className="supply-card">
            <h2>Inbound Putaway (STOCK-01 Linked)</h2>
            <form onSubmit={handleInboundPutaway}>
              <div className="supply-form-grid">
                <label>
                  Inbound goods owner
                  <select
                    value={inOwnerId}
                    onChange={(e) => setInOwnerId(e.target.value)}
                  >
                    {owners.map((o) => (
                      <option key={o.goods_owner_id} value={o.goods_owner_id}>
                        {o.code} ({o.owner_kind})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Inbound bin
                  <select
                    value={inBinId}
                    onChange={(e) => setInBinId(e.target.value)}
                  >
                    {bins.map((b) => (
                      <option key={b.bin_id} value={b.bin_id}>
                        {b.bin_code} ({b.zone_code})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Inbound item
                  <select
                    value={inItemId}
                    onChange={(e) => setInItemId(e.target.value)}
                  >
                    {stockItems.map((it) => (
                      <option key={it.item_id} value={it.item_id}>
                        {it.code} — {it.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Inbound lot
                  <select
                    value={inLotId}
                    onChange={(e) => setInLotId(e.target.value)}
                  >
                    {lots.map((l) => (
                      <option key={l.lot_id} value={l.lot_id}>
                        {l.lot_code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Inbound quantity
                  <input
                    type="number"
                    value={inQty}
                    onChange={(e) => setInQty(e.target.value)}
                  />
                </label>
                <label>
                  Auto stock receipt amount
                  <input
                    value={inAmount}
                    onChange={(e) => setInAmount(e.target.value)}
                  />
                </label>
                <label>
                  Auto stock receipt date
                  <input
                    value={inDate}
                    onChange={(e) => setInDate(e.target.value)}
                  />
                </label>
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canWork}>
                  Post inbound putaway
                </button>
              </div>
            </form>
          </div>

          <div className="supply-card">
            <h2>Bin / Lot Running Balances</h2>
            <div
              className="supply-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Lot balances table"
            >
              <table className="supply-table">
                <thead>
                  <tr>
                    <th>Bin</th>
                    <th>Owner</th>
                    <th>Item</th>
                    <th>Lot</th>
                    <th>Quantity</th>
                  </tr>
                </thead>
                <tbody>
                  {balances.map((b) => (
                    <tr key={b.balance_id}>
                      <td>
                        {bins.find((x) => x.bin_id === b.bin_id)?.bin_code ??
                          b.bin_id}
                      </td>
                      <td>
                        {owners.find(
                          (o) => o.goods_owner_id === b.goods_owner_id,
                        )?.code ?? b.goods_owner_id}
                      </td>
                      <td>
                        {stockItems.find((i) => i.item_id === b.item_id)
                          ?.code ?? b.item_id}
                      </td>
                      <td>
                        {lots.find((l) => l.lot_id === b.lot_id)?.lot_code ??
                          b.lot_id}
                      </td>
                      <td>{b.quantity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="supply-card">
            <h2>WMS Movement Ledger ({serials.length} tracked serials)</h2>
            <div
              className="supply-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="WMS movements table"
            >
              <table className="supply-table">
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>Owner</th>
                    <th>Lot</th>
                    <th>Qty</th>
                    <th>STOCK-01 Linked</th>
                  </tr>
                </thead>
                <tbody>
                  {movements.map((m) => (
                    <tr key={m.movement_id}>
                      <td>{m.movement_kind}</td>
                      <td>
                        {owners.find(
                          (o) => o.goods_owner_id === m.goods_owner_id,
                        )?.code ?? m.goods_owner_id}
                      </td>
                      <td>
                        {lots.find((l) => l.lot_id === m.lot_id)?.lot_code ??
                          m.lot_id}
                      </td>
                      <td>{m.quantity}</td>
                      <td>
                        {m.stock_document_id ? "STOCK-01 Doc" : "3PL Off-Book"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {tab === "manufacturing" ? (
        <section
          id="panel-manufacturing"
          role="tabpanel"
          aria-labelledby="tab-manufacturing"
          className="supply-panel"
        >
          <div className="supply-card">
            <h2>Bills of Materials (BOMs)</h2>
            <form onSubmit={handleSaveBom}>
              <div className="supply-form-grid">
                <label>
                  BOM code
                  <input
                    value={bomCode}
                    onChange={(e) => setBomCode(e.target.value)}
                    placeholder="BOM_VALVE_01"
                  />
                </label>
                <label>
                  BOM title
                  <input
                    value={bomTitle}
                    onChange={(e) => setBomTitle(e.target.value)}
                    placeholder="Valve Assembly Specification"
                  />
                </label>
                <label>
                  Output item
                  <select
                    value={bomOutputItem}
                    onChange={(e) => setBomOutputItem(e.target.value)}
                  >
                    {stockItems.map((it) => (
                      <option key={it.item_id} value={it.item_id}>
                        {it.code} — {it.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Component item
                  <select
                    value={bomCompItem}
                    onChange={(e) => setBomCompItem(e.target.value)}
                  >
                    {stockItems.map((it) => (
                      <option key={it.item_id} value={it.item_id}>
                        {it.code} — {it.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Component qty per batch
                  <input
                    type="number"
                    value={bomCompQty}
                    onChange={(e) => setBomCompQty(e.target.value)}
                  />
                </label>
                <label>
                  Standard labor minor
                  <input
                    type="number"
                    value={bomLabor}
                    onChange={(e) => setBomLabor(e.target.value)}
                  />
                </label>
                <label>
                  Standard overhead minor
                  <input
                    type="number"
                    value={bomOverhead}
                    onChange={(e) => setBomOverhead(e.target.value)}
                  />
                </label>
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save BOM
                </button>
              </div>
            </form>
          </div>

          <div className="supply-card">
            <h2>Production Work Orders &amp; Cost Conservation</h2>
            <form onSubmit={handleCreateWorkOrder}>
              <div className="supply-form-grid">
                <label>
                  Work order code
                  <input
                    value={woCode}
                    onChange={(e) => setWoCode(e.target.value)}
                    placeholder="WO_001"
                  />
                </label>
                <label>
                  Work order goods owner
                  <select
                    value={woOwnerId}
                    onChange={(e) => setWoOwnerId(e.target.value)}
                  >
                    {owners.map((o) => (
                      <option key={o.goods_owner_id} value={o.goods_owner_id}>
                        {o.code} ({o.owner_kind})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Work order BOM
                  <select
                    value={woBomId}
                    onChange={(e) => setWoBomId(e.target.value)}
                  >
                    {boms.map((b) => (
                      <option key={b.bom_id} value={b.bom_id}>
                        {b.code} — {b.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Work order stock place
                  <select
                    value={woPlaceId}
                    onChange={(e) => setWoPlaceId(e.target.value)}
                  >
                    {stockPlaces.map((p) => (
                      <option key={p.place_id} value={p.place_id}>
                        {p.code} — {p.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Planned quantity
                  <input
                    type="number"
                    value={woPlannedQty}
                    onChange={(e) => setWoPlannedQty(e.target.value)}
                  />
                </label>
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canWork}>
                  Create work order
                </button>
              </div>
            </form>

            {workOrders.length > 0 ? (
              <>
                <div className="supply-form-grid">
                  <label>
                    Selected work order
                    <select
                      value={selectedWoId}
                      onChange={(e) => {
                        setSelectedWoId(e.target.value);
                        void loadWorkOrderDetail(e.target.value);
                      }}
                    >
                      {workOrders.map((wo) => (
                        <option key={wo.work_order_id} value={wo.work_order_id}>
                          {wo.code} ({wo.status})
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <form onSubmit={handlePostWoIssue}>
                  <h3>1. Issue Component Lot (STOCK-01 write_off)</h3>
                  <div className="supply-form-grid">
                    <label>
                      Issue bin
                      <select
                        value={issBinId}
                        onChange={(e) => setIssBinId(e.target.value)}
                      >
                        {bins.map((b) => (
                          <option key={b.bin_id} value={b.bin_id}>
                            {b.bin_code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Issue component item
                      <select
                        value={issItemId}
                        onChange={(e) => setIssItemId(e.target.value)}
                      >
                        {stockItems.map((it) => (
                          <option key={it.item_id} value={it.item_id}>
                            {it.code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Issue lot
                      <select
                        value={issLotId}
                        onChange={(e) => setIssLotId(e.target.value)}
                      >
                        {lots.map((l) => (
                          <option key={l.lot_id} value={l.lot_id}>
                            {l.lot_code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Issue quantity
                      <input
                        type="number"
                        value={issQty}
                        onChange={(e) => setIssQty(e.target.value)}
                      />
                    </label>
                    <label>
                      Issue date
                      <input
                        value={issDate}
                        onChange={(e) => setIssDate(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="supply-actions">
                    <button type="submit" disabled={busy || !canWork}>
                      Post component issue
                    </button>
                  </div>
                </form>

                <form onSubmit={handlePostWoReturn}>
                  <h3>2. Return Unused Material (STOCK-01 return)</h3>
                  <div className="supply-form-grid">
                    <label>
                      Return issue record
                      <select
                        value={retIssueId}
                        onChange={(e) => setRetIssueId(e.target.value)}
                      >
                        {woIssues.map((iss) => (
                          <option key={iss.issue_id} value={iss.issue_id}>
                            Issue {iss.quantity} units (returned{" "}
                            {iss.returned_quantity})
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Return bin
                      <select
                        value={retBinId}
                        onChange={(e) => setRetBinId(e.target.value)}
                      >
                        {bins.map((b) => (
                          <option key={b.bin_id} value={b.bin_id}>
                            {b.bin_code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Return quantity
                      <input
                        type="number"
                        value={retQty}
                        onChange={(e) => setRetQty(e.target.value)}
                      />
                    </label>
                    <label>
                      Return date
                      <input
                        value={retDate}
                        onChange={(e) => setRetDate(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="supply-actions">
                    <button
                      type="submit"
                      disabled={busy || !canWork || woIssues.length === 0}
                    >
                      Post material return
                    </button>
                  </div>
                </form>

                <form onSubmit={handlePostWoQc}>
                  <h3>3. Quality Control (QC) Inspection</h3>
                  <div className="supply-form-grid">
                    <label>
                      QC passed quantity
                      <input
                        type="number"
                        value={qcPassedQty}
                        onChange={(e) => setQcPassedQty(e.target.value)}
                      />
                    </label>
                    <label>
                      QC scrap quantity
                      <input
                        type="number"
                        value={qcScrapQty}
                        onChange={(e) => setQcScrapQty(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="supply-actions">
                    <button type="submit" disabled={busy || !canWork}>
                      Record QC inspection
                    </button>
                  </div>
                </form>

                <form onSubmit={handlePostWoOutput}>
                  <h3>4. Finished-Goods Lot Output (STOCK-01 receipt)</h3>
                  <div className="supply-form-grid">
                    <label>
                      Output bin
                      <select
                        value={outBinId}
                        onChange={(e) => setOutBinId(e.target.value)}
                      >
                        {bins.map((b) => (
                          <option key={b.bin_id} value={b.bin_id}>
                            {b.bin_code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Output lot code
                      <input
                        value={outLotCode}
                        onChange={(e) => setOutLotCode(e.target.value)}
                      />
                    </label>
                    <label>
                      Output date
                      <input
                        value={outDate}
                        onChange={(e) => setOutDate(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="supply-actions">
                    <button type="submit" disabled={busy || !canWork}>
                      Post finished output
                    </button>
                  </div>
                </form>
              </>
            ) : null}

            <div
              className="supply-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Work orders table"
            >
              <table className="supply-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Status</th>
                    <th>Issued Cost</th>
                    <th>Returned Cost</th>
                    <th>Completed Qty</th>
                    <th>Output Total Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {workOrders.map((wo) => (
                    <tr key={wo.work_order_id}>
                      <td>{wo.code}</td>
                      <td>{wo.status}</td>
                      <td>
                        {formatSupplyMinor(wo.issued_material_cost_minor)}
                      </td>
                      <td>
                        {formatSupplyMinor(wo.returned_material_cost_minor)}
                      </td>
                      <td>{wo.completed_quantity}</td>
                      <td>{formatSupplyMinor(wo.output_total_cost_minor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Selected WO activity: {woIssues.length} issues, {woReturns.length}{" "}
              returns.
            </p>
          </div>
        </section>
      ) : null}

      {tab === "trade" ? (
        <section
          id="panel-trade"
          role="tabpanel"
          aria-labelledby="tab-trade"
          className="supply-panel"
        >
          <div className="supply-card">
            <h2>Channel &amp; Contract Price Lists</h2>
            <form onSubmit={handleSavePriceList}>
              <div className="supply-form-grid">
                <label>
                  Price list code
                  <input
                    value={plCode}
                    onChange={(e) => setPlCode(e.target.value)}
                    placeholder="PL_WHOLESALE"
                  />
                </label>
                <label>
                  Price list title
                  <input
                    value={plTitle}
                    onChange={(e) => setPlTitle(e.target.value)}
                    placeholder="Wholesale Tiered List"
                  />
                </label>
                <label>
                  Price channel
                  <select
                    value={plChannel}
                    onChange={(e) =>
                      setPlChannel(e.target.value as PriceChannel)
                    }
                  >
                    <option value="wholesale">wholesale</option>
                    <option value="retail">retail</option>
                    <option value="contract_b2b">contract_b2b</option>
                  </select>
                </label>
                <label>
                  Price list item
                  <select
                    value={plItemId}
                    onChange={(e) => setPlItemId(e.target.value)}
                  >
                    {stockItems.map((it) => (
                      <option key={it.item_id} value={it.item_id}>
                        {it.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Tier min quantity
                  <input
                    type="number"
                    value={plMinQty}
                    onChange={(e) => setPlMinQty(e.target.value)}
                  />
                </label>
                <label>
                  Tier unit price minor
                  <input
                    type="number"
                    value={plUnitPrice}
                    onChange={(e) => setPlUnitPrice(e.target.value)}
                  />
                </label>
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save price list
                </button>
              </div>
            </form>
          </div>

          <div className="supply-card">
            <h2>Retail/Wholesale &amp; 3PL Fulfillment Orders</h2>
            <form onSubmit={handleCreateTradeOrder}>
              <div className="supply-form-grid">
                <label>
                  Order code
                  <input
                    value={ordCode}
                    onChange={(e) => setOrdCode(e.target.value)}
                    placeholder="ORD_001"
                  />
                </label>
                <label>
                  Order kind
                  <select
                    value={ordKind}
                    onChange={(e) =>
                      setOrdKind(e.target.value as TradeOrderKind)
                    }
                  >
                    <option value="wholesale_sale">wholesale_sale</option>
                    <option value="retail_sale">retail_sale</option>
                    <option value="3pl_fulfillment">3pl_fulfillment</option>
                  </select>
                </label>
                <label>
                  Order goods owner
                  <select
                    value={ordOwnerId}
                    onChange={(e) => setOrdOwnerId(e.target.value)}
                  >
                    {owners.map((o) => (
                      <option key={o.goods_owner_id} value={o.goods_owner_id}>
                        {o.code} ({o.owner_kind})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Customer counterparty
                  <select
                    value={ordCustomerId}
                    onChange={(e) => setOrdCustomerId(e.target.value)}
                  >
                    {counterparties.map((cp) => (
                      <option
                        key={cp.counterparty_id}
                        value={cp.counterparty_id}
                      >
                        {cp.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Order price list
                  <select
                    value={ordPriceListId}
                    onChange={(e) => setOrdPriceListId(e.target.value)}
                  >
                    <option value="">(Explicit line price)</option>
                    {priceLists.map((pl) => (
                      <option key={pl.price_list_id} value={pl.price_list_id}>
                        {pl.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Order item
                  <select
                    value={ordItemId}
                    onChange={(e) => setOrdItemId(e.target.value)}
                  >
                    {stockItems.map((it) => (
                      <option key={it.item_id} value={it.item_id}>
                        {it.code}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Ordered quantity
                  <input
                    type="number"
                    value={ordQty}
                    onChange={(e) => setOrdQty(e.target.value)}
                  />
                </label>
                <label>
                  Explicit unit price minor
                  <input
                    type="number"
                    value={ordUnitPrice}
                    onChange={(e) => setOrdUnitPrice(e.target.value)}
                  />
                </label>
                <label>
                  Order ledger book
                  <select
                    value={ordBookId}
                    onChange={(e) => {
                      setOrdBookId(e.target.value);
                      void loadBookAccounts(e.target.value);
                    }}
                  >
                    {books.map((b) => (
                      <option key={b.book_id} value={b.book_id}>
                        {b.code} — {b.base_currency}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  AR control account
                  <select
                    value={ordArAccountId}
                    onChange={(e) => setOrdArAccountId(e.target.value)}
                  >
                    {arAccounts.map((a) => (
                      <option key={a.account_id} value={a.account_id}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Revenue account
                  <select
                    value={ordRevAccountId}
                    onChange={(e) => setOrdRevAccountId(e.target.value)}
                  >
                    {revAccounts.map((a) => (
                      <option key={a.account_id} value={a.account_id}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="supply-actions">
                <button type="submit" disabled={busy || !canWork}>
                  Create trade order
                </button>
              </div>
            </form>

            {tradeOrders.length > 0 ? (
              <>
                <div className="supply-form-grid">
                  <label>
                    Selected trade order
                    <select
                      value={selectedOrderId}
                      onChange={(e) => {
                        const oid = e.target.value;
                        setSelectedOrderId(oid);
                        const o = tradeOrders.find((x) => x.order_id === oid);
                        if (o?.lines[0]) {
                          setShpLineId(o.lines[0].order_line_id);
                        }
                        void loadTradeOrderDetail(oid);
                      }}
                    >
                      {tradeOrders.map((o) => (
                        <option key={o.order_id} value={o.order_id}>
                          {o.code} ({o.status})
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <form onSubmit={handlePostOrderShipment}>
                  <h3>
                    Owner-Isolated Lot Shipment (STOCK-01 COGS + FIN-03 Invoice)
                  </h3>
                  <div className="supply-form-grid">
                    <label>
                      Shipment order line
                      <select
                        value={shpLineId}
                        onChange={(e) => setShpLineId(e.target.value)}
                      >
                        {(selectedOrder?.lines ?? []).map((ln) => (
                          <option
                            key={ln.order_line_id}
                            value={ln.order_line_id}
                          >
                            Line #{ln.line_no} (ordered {ln.ordered_quantity},
                            shipped {ln.shipped_quantity})
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Shipment bin
                      <select
                        value={shpBinId}
                        onChange={(e) => setShpBinId(e.target.value)}
                      >
                        {bins.map((b) => (
                          <option key={b.bin_id} value={b.bin_id}>
                            {b.bin_code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Shipment lot
                      <select
                        value={shpLotId}
                        onChange={(e) => setShpLotId(e.target.value)}
                      >
                        {lots.map((l) => (
                          <option key={l.lot_id} value={l.lot_id}>
                            {l.lot_code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Shipment quantity
                      <input
                        type="number"
                        value={shpQty}
                        onChange={(e) => setShpQty(e.target.value)}
                      />
                    </label>
                    <label>
                      Shipment date
                      <input
                        value={shpDate}
                        onChange={(e) => setShpDate(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="supply-actions">
                    <button type="submit" disabled={busy || !canWork}>
                      Post order shipment
                    </button>
                  </div>
                </form>

                <form onSubmit={handlePostCustomerReturn}>
                  <h3>
                    Customer Return (Restores Lot Balance + STOCK-01 Return +
                    FIN-03 Credit Note)
                  </h3>
                  <div className="supply-form-grid">
                    <label>
                      Return shipment record
                      <select
                        value={cRetShipmentId}
                        onChange={(e) => setCRetShipmentId(e.target.value)}
                      >
                        {orderShipments.map((s) => (
                          <option key={s.shipment_id} value={s.shipment_id}>
                            Shipped {s.quantity} units (returned{" "}
                            {s.returned_quantity})
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Customer return bin
                      <select
                        value={cRetBinId}
                        onChange={(e) => setCRetBinId(e.target.value)}
                      >
                        {bins.map((b) => (
                          <option key={b.bin_id} value={b.bin_id}>
                            {b.bin_code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Customer return quantity
                      <input
                        type="number"
                        value={cRetQty}
                        onChange={(e) => setCRetQty(e.target.value)}
                      />
                    </label>
                    <label>
                      Customer return date
                      <input
                        value={cRetDate}
                        onChange={(e) => setCRetDate(e.target.value)}
                      />
                    </label>
                    <label>
                      Customer return reason
                      <input
                        value={cRetReason}
                        onChange={(e) => setCRetReason(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="supply-actions">
                    <button
                      type="submit"
                      disabled={busy || !canWork || orderShipments.length === 0}
                    >
                      Post customer return
                    </button>
                  </div>
                </form>
              </>
            ) : null}

            <div
              className="supply-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Trade orders table"
            >
              <table className="supply-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Kind</th>
                    <th>Status</th>
                    <th>Ordered</th>
                    <th>Shipped</th>
                    <th>Returned</th>
                  </tr>
                </thead>
                <tbody>
                  {tradeOrders.map((o) => (
                    <tr key={o.order_id}>
                      <td>{o.code}</td>
                      <td>{o.order_kind}</td>
                      <td>{o.status}</td>
                      <td>{formatSupplyMinor(o.total_ordered_minor)}</td>
                      <td>{formatSupplyMinor(o.total_shipped_minor)}</td>
                      <td>{formatSupplyMinor(o.total_returned_minor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              Selected order activity: {orderShipments.length} shipments,{" "}
              {orderReturns.length} returns.
            </p>
          </div>
        </section>
      ) : null}
    </div>
  );
}
