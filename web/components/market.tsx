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
  fetchListings,
  fetchMarketOrders,
  fetchMarketplaces,
  fetchOperatorFees,
  fetchPublicCatalog,
  fetchSellerConnections,
  fetchStorefronts,
  marketError,
  postBasketCheckout,
  postMarketOrderRefund,
  saveListing,
  saveMarketplace,
  saveSellerConnection,
  saveStorefront,
} from "../lib/market-api";
import {
  ALL_PUBLIC_FIELDS,
  formatMarketMinor,
  type ListingView,
  type MarketplaceView,
  type MarketOrderView,
  type ModerationStatus,
  type OperatorFeeView,
  type PublicField,
  type PublicStorefrontCatalog,
  type SellerConnectionView,
  type StorefrontView,
} from "../lib/market-contracts";

type TabId = "storefronts" | "marketplaces" | "checkout";

const TABS: { id: TabId; label: string }[] = [
  { id: "storefronts", label: "Storefronts & Publishing" },
  { id: "marketplaces", label: "Client-Operated Marketplaces" },
  { id: "checkout", label: "Multi-Seller Checkout & Settlement" },
];

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
type BookPostingAccounts = { arId: string; revId: string };

function newId(): string {
  return crypto.randomUUID();
}

export function MarketScreen({
  businessId,
  assignedLocationId,
  canManage,
}: {
  businessId: string;
  assignedLocationId: string | null;
  canManage: boolean;
}) {
  const [tab, setTab] = useState<TabId>("storefronts");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [counterparties, setCounterparties] = useState<CounterpartyRef[]>([]);
  const [legalEntities, setLegalEntities] = useState<LegalEntityRef[]>([]);
  const [bookAccounts, setBookAccounts] = useState<
    Record<string, BookPostingAccounts>
  >({});

  const [storefronts, setStorefronts] = useState<StorefrontView[]>([]);
  const [listings, setListings] = useState<ListingView[]>([]);
  const [marketplaces, setMarketplaces] = useState<MarketplaceView[]>([]);
  const [connections, setConnections] = useState<SellerConnectionView[]>([]);
  const [orders, setOrders] = useState<MarketOrderView[]>([]);
  const [operatorFees, setOperatorFees] = useState<OperatorFeeView[]>([]);

  // Public catalog projection preview
  const [previewSfId, setPreviewSfId] = useState("");
  const [publicCatalog, setPublicCatalog] =
    useState<PublicStorefrontCatalog | null>(null);

  // Tab 1: Storefront form
  const [sfLoc, setSfLoc] = useState("");
  const [sfLeId, setSfLeId] = useState("");
  const [sfSlug, setSfSlug] = useState("");
  const [sfName, setSfName] = useState("");
  const [sfCity, setSfCity] = useState("Chicago");
  const [sfFields, setSfFields] = useState<PublicField[]>([
    "title",
    "price",
    "currency",
    "availability",
    "location_city",
  ]);
  const [sfPublished, setSfPublished] = useState(true);

  // Tab 1: Listing form
  const [lstSfId, setLstSfId] = useState("");
  const [lstSku, setLstSku] = useState("");
  const [lstTitle, setLstTitle] = useState("");
  const [lstDesc, setLstDesc] = useState("Unselected internal description");
  const [lstCategory, setLstCategory] = useState("equipment");
  const [lstPrice, setLstPrice] = useState("20000");
  const [lstQty, setLstQty] = useState("10");
  const [lstInternalCost, setLstInternalCost] = useState("8500");
  const [lstInternalNotes, setLstInternalNotes] = useState(
    "SECRET MARGIN 57% DO NOT PUBLISH",
  );
  const [lstFields, setLstFields] = useState<PublicField[]>([
    "title",
    "price",
    "currency",
    "sku",
    "description",
  ]);
  const [lstStatus, setLstStatus] = useState<ModerationStatus>("published");

  // Tab 2: Marketplace & Seller Connection forms
  const [mpLoc, setMpLoc] = useState("");
  const [mpSlug, setMpSlug] = useState("");
  const [mpTitle, setMpTitle] = useState("");
  const [mpFeeBps, setMpFeeBps] = useState("300");

  const [selectedMpId, setSelectedMpId] = useState("");
  const [connSellerCpId, setConnSellerCpId] = useState("");
  const [connSfSlug, setConnSfSlug] = useState("");

  // Tab 3: Multi-Seller Basket Checkout form (2 seller lines)
  const [chkCustomerId, setChkCustomerId] = useState("");
  const [chkMpId, setChkMpId] = useState("");
  const [chkDate, setChkDate] = useState("2026-10-10");
  const [chkSellerCpId, setChkSellerCpId] = useState("");
  const [chkLine1ListingId, setChkLine1ListingId] = useState("");
  const [chkLine1Qty, setChkLine1Qty] = useState("2");
  const [chkLine1BookId, setChkLine1BookId] = useState("");
  const [chkLine2ListingId, setChkLine2ListingId] = useState("");
  const [chkLine2Qty, setChkLine2Qty] = useState("1");
  const [chkLine2BookId, setChkLine2BookId] = useState("");

  // Tab 3: Refund form
  const [refOrderId, setRefOrderId] = useState("");
  const [refMinor, setRefMinor] = useState("10000");
  const [refDate, setRefDate] = useState("2026-10-12");
  const [refReason, setRefReason] = useState("Partial customer refund");

  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const books = useMemo(
    () =>
      legalEntities.flatMap((le) =>
        le.book
          ? [
              {
                book_id: le.book.book_id,
                legal_entity_id: le.legal_entity_id,
                code: le.code,
                base_currency: le.book.base_currency,
              },
            ]
          : [],
      ),
    [legalEntities],
  );

  const loadMpConnections = useCallback(
    async (mpId: string) => {
      if (!mpId) {
        setConnections([]);
        return;
      }
      const list = await fetchSellerConnections(businessId, mpId);
      setConnections(list);
    },
    [businessId],
  );

  const reloadAll = useCallback(
    async (opts?: { mpId?: string; orderId?: string }) => {
      setLoading(true);
      setError(null);
      try {
        const [ws, sfList, lstList, mpList, ordList, feeList] =
          await Promise.all([
            fetchWorkspace(businessId),
            fetchStorefronts(businessId),
            fetchListings(businessId),
            fetchMarketplaces(businessId),
            fetchMarketOrders(businessId),
            fetchOperatorFees(businessId),
          ]);
        const locs = ws.locations.filter((l) =>
          assignedLocationId ? l.id === assignedLocationId : true,
        );
        setLocations(locs);
        setStorefronts(sfList);
        setListings(lstList);
        setMarketplaces(mpList);
        setOrders(ordList);
        setOperatorFees(feeList);

        const defaultLoc = assignedLocationId ?? locs[0]?.id ?? "";
        setSfLoc((p) => p || defaultLoc);
        setMpLoc((p) => p || defaultLoc);

        try {
          const [cpsRes, ledgerRes] = await Promise.all([
            managementFetch<{ items: CounterpartyRef[] }>(
              `/v1/businesses/${businessId}/counterparties`,
            ),
            managementFetch<{ items: LegalEntityRef[] }>(
              `/v1/businesses/${businessId}/ledger`,
            ),
          ]);
          const cpList = cpsRes.items ?? [];
          const leList = ledgerRes.items ?? [];
          setCounterparties(cpList);
          setLegalEntities(leList);

          const firstLe = leList[0];
          if (firstLe) setSfLeId((p) => p || firstLe.legal_entity_id);
          const firstCp = cpList[0];
          if (firstCp) {
            const sellerCpId =
              cpList[1]?.counterparty_id ?? firstCp.counterparty_id;
            setChkCustomerId((p) => p || firstCp.counterparty_id);
            setConnSellerCpId((p) => p || sellerCpId);
            setChkSellerCpId((p) => p || sellerCpId);
          }

          const leBooks = leList.flatMap((le) =>
            le.book ? [le.book.book_id] : [],
          );
          const firstBookId = leBooks[0];
          if (firstBookId) {
            const acctPairs = await Promise.all(
              leBooks.map(async (bid) => {
                const res = await managementFetch<{ items: AccountRef[] }>(
                  `/v1/businesses/${businessId}/ledger/books/${bid}/accounts?limit=100`,
                );
                const list = res.items ?? [];
                const ar =
                  list.find((a) => a.code === "1200") ??
                  list.find((a) => a.type === "asset");
                const rev =
                  list.find((a) => a.code === "4000") ??
                  list.find((a) => a.type === "revenue");
                return [
                  bid,
                  { arId: ar?.account_id ?? "", revId: rev?.account_id ?? "" },
                ] as const;
              }),
            );
            setBookAccounts(Object.fromEntries(acctPairs));
            const secondBookId = leBooks[1] ?? firstBookId;
            setChkLine1BookId((p) => p || firstBookId);
            setChkLine2BookId((p) => p || secondBookId);
          }
        } catch {
          // Optional reference endpoints if user lacks finance/counterparty permissions
        }

        const firstSf = sfList[0];
        if (firstSf) {
          setLstSfId((p) => p || firstSf.storefront_id);
          setPreviewSfId((p) => p || firstSf.storefront_id);
        }
        const pubListings = lstList.filter(
          (l) => l.moderation_status === "published",
        );
        const firstPub = pubListings[0];
        if (firstPub) {
          const secondPubId = pubListings[1]?.listing_id ?? firstPub.listing_id;
          setChkLine1ListingId((p) => p || firstPub.listing_id);
          setChkLine2ListingId((p) => p || secondPubId);
        }
        const activeMp =
          opts?.mpId || selectedMpId || mpList[0]?.marketplace_id || "";
        if (activeMp) {
          setSelectedMpId(activeMp);
          setChkMpId((p) => p || activeMp);
          await loadMpConnections(activeMp);
        }
        const activeOrd =
          opts?.orderId || refOrderId || ordList[0]?.order_id || "";
        if (activeOrd) {
          setRefOrderId(activeOrd);
        }
      } catch (err) {
        setError(marketError(err));
      } finally {
        setLoading(false);
      }
    },
    [
      assignedLocationId,
      businessId,
      loadMpConnections,
      refOrderId,
      selectedMpId,
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

  function toggleField(
    current: PublicField[],
    field: PublicField,
    setter: (next: PublicField[]) => void,
  ) {
    if (current.includes(field)) {
      if (current.length <= 1) return;
      setter(current.filter((f) => f !== field));
    } else {
      setter([...current, field]);
    }
  }

  async function handleSaveStorefront(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !sfLoc || !sfLeId || !sfSlug.trim() || !sfName.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveStorefront(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: sfLoc,
        legal_entity_id: sfLeId,
        slug: sfSlug.trim().toLowerCase(),
        display_name: sfName.trim(),
        description: "Internal storefront description",
        location_city: sfCity.trim() || null,
        currency: "USD",
        published_fields: sfFields,
        is_published: sfPublished,
      });
      setSfSlug("");
      setSfName("");
      setLstSfId(created.storefront_id);
      setPreviewSfId(created.storefront_id);
      setNotice(`Saved storefront ${created.slug}`);
      await reloadAll();
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveListing(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !lstSfId || !lstSku.trim() || !lstTitle.trim()) return;
    const sf = storefronts.find((s) => s.storefront_id === lstSfId);
    if (!sf) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveListing(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: sf.location_id,
        storefront_id: lstSfId,
        sku: lstSku.trim().toUpperCase(),
        title: lstTitle.trim(),
        description: lstDesc.trim() || null,
        category: lstCategory.trim() || "equipment",
        brand: "GorgonaPartner",
        currency: "USD",
        price_minor: Number(lstPrice) || 0,
        available_quantity: Number(lstQty) || 0,
        internal_cost_minor: Number(lstInternalCost) || 0,
        internal_notes: lstInternalNotes.trim() || null,
        published_fields: lstFields,
        moderation_status: lstStatus,
      });
      setLstSku("");
      setLstTitle("");
      setNotice(`Saved listing ${created.sku} (${created.moderation_status})`);
      await reloadAll();
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePreviewPublicCatalog() {
    if (!previewSfId) return;
    setBusy(true);
    setError(null);
    try {
      const cat = await fetchPublicCatalog(businessId, previewSfId);
      setPublicCatalog(cat);
      setNotice(
        `Loaded public catalog for ${cat.storefront_slug} (${cat.items.length} published listing(s))`,
      );
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveMarketplace(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !mpLoc || !mpSlug.trim() || !mpTitle.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveMarketplace(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: mpLoc,
        slug: mpSlug.trim().toLowerCase(),
        title: mpTitle.trim(),
        operator_fee_bps: Number(mpFeeBps) || 0,
        is_active: true,
      });
      setMpSlug("");
      setMpTitle("");
      setSelectedMpId(created.marketplace_id);
      setChkMpId(created.marketplace_id);
      setNotice(
        `Saved marketplace ${created.slug} (GORGONA commission ${created.gorgona_commission_bps} bps)`,
      );
      await reloadAll({ mpId: created.marketplace_id });
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleConnectSeller(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !selectedMpId || !connSellerCpId || !connSfSlug.trim()) {
      return;
    }
    const mp = marketplaces.find((m) => m.marketplace_id === selectedMpId);
    if (!mp) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveSellerConnection(
        businessId,
        selectedMpId,
        newId(),
        newId(),
        {
          expected_revision: 0,
          location_id: mp.location_id,
          seller_counterparty_id: connSellerCpId,
          seller_storefront_slug: connSfSlug.trim().toLowerCase(),
          granted_scopes: ["publish", "reports_read"],
          status: "active",
        },
      );
      setConnSfSlug("");
      setNotice(`Connected seller ${created.seller_storefront_slug}`);
      await reloadAll({ mpId: selectedMpId });
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleConnectionStatusChange(
    conn: SellerConnectionView,
    nextStatus: "revoked" | "active",
  ) {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await saveSellerConnection(
        businessId,
        conn.marketplace_id,
        conn.connection_id,
        newId(),
        {
          expected_revision: conn.revision,
          location_id: conn.location_id,
          seller_counterparty_id: conn.seller_counterparty_id,
          seller_storefront_slug: conn.seller_storefront_slug,
          granted_scopes: conn.granted_scopes,
          status: nextStatus,
        },
      );
      setNotice(
        `Updated seller ${updated.seller_storefront_slug} status to ${updated.status}`,
      );
      await reloadAll({ mpId: conn.marketplace_id });
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleBasketCheckout(e: FormEvent) {
    e.preventDefault();
    if (
      !canManage ||
      !chkCustomerId ||
      !chkLine1ListingId ||
      !chkLine2ListingId ||
      !chkLine1BookId ||
      !chkLine2BookId
    ) {
      return;
    }
    const l1 = listings.find((l) => l.listing_id === chkLine1ListingId);
    const l2 = listings.find((l) => l.listing_id === chkLine2ListingId);
    if (!l1 || !l2) return;
    const accts1 = bookAccounts[chkLine1BookId];
    const accts2 = bookAccounts[chkLine2BookId];
    if (!accts1 || !accts2) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const sellerConfigs = [
        {
          storefront_id: l1.storefront_id,
          book_id: chkLine1BookId,
          control_account_id: accts1.arId,
          revenue_account_id: accts1.revId,
          seller_counterparty_id: chkSellerCpId || null,
        },
      ];
      if (l2.storefront_id !== l1.storefront_id) {
        sellerConfigs.push({
          storefront_id: l2.storefront_id,
          book_id: chkLine2BookId,
          control_account_id: accts2.arId,
          revenue_account_id: accts2.revId,
          seller_counterparty_id: chkSellerCpId || null,
        });
      }
      const basket = await postBasketCheckout(businessId, newId(), {
        location_id: l1.location_id,
        customer_counterparty_id: chkCustomerId,
        marketplace_id: chkMpId || null,
        currency: "USD",
        order_date: chkDate,
        items: [
          { listing_id: l1.listing_id, quantity: Number(chkLine1Qty) || 1 },
          { listing_id: l2.listing_id, quantity: Number(chkLine2Qty) || 1 },
        ],
        seller_configs: sellerConfigs,
      });
      const firstOrder = basket.orders[0];
      setNotice(
        `Split multi-seller basket into ${basket.split_order_count} isolated single-seller order(s)`,
      );
      await reloadAll({ orderId: firstOrder?.order_id });
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRefundOrder(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !refOrderId || !refReason.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await postMarketOrderRefund(
        businessId,
        refOrderId,
        newId(),
        {
          refund_minor: Number(refMinor) || 1,
          refund_date: refDate,
          reason: refReason.trim(),
        },
      );
      setNotice(
        `Processed refund on ${updated.order_number} (${formatMarketMinor(updated.refunded_minor, updated.currency)}, status ${updated.status})`,
      );
      await reloadAll({ orderId: updated.order_id });
    } catch (err) {
      setError(marketError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="market-shell">
      <header>
        <h1>Storefronts &amp; Client-Operated Marketplaces</h1>
        <p>
          Explicit published_fields allow-list storefronts, client-operated
          marketplaces with zero GORGONA transaction commission, and
          single-seller order/invoice isolation.
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
      {loading ? <p>Loading marketplace workspace…</p> : null}

      <div
        className="market-tabs"
        role="tablist"
        aria-label="Marketplace sections"
      >
        {TABS.map((t, idx) => (
          <button
            key={t.id}
            ref={(el) => {
              tabRefs.current[idx] = el;
            }}
            id={`mkt-tab-${t.id}`}
            type="button"
            role="tab"
            className="market-tab"
            aria-selected={tab === t.id}
            aria-controls={`mkt-panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKeyDown(idx, e)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "storefronts" ? (
        <section
          id="mkt-panel-storefronts"
          role="tabpanel"
          aria-labelledby="mkt-tab-storefronts"
          className="market-panel"
        >
          <div className="market-card">
            <h2>Business Storefronts (Explicit Public Allow-List)</h2>
            <form onSubmit={handleSaveStorefront}>
              <div className="market-form-grid">
                <label>
                  Storefront location
                  <select
                    value={sfLoc}
                    onChange={(e) => setSfLoc(e.target.value)}
                  >
                    {locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Seller legal entity
                  <select
                    value={sfLeId}
                    onChange={(e) => setSfLeId(e.target.value)}
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
                <label>
                  Storefront slug
                  <input
                    value={sfSlug}
                    onChange={(e) => setSfSlug(e.target.value)}
                    placeholder="alpha-shop"
                  />
                </label>
                <label>
                  Storefront display name
                  <input
                    value={sfName}
                    onChange={(e) => setSfName(e.target.value)}
                    placeholder="Seller Alpha Shop"
                  />
                </label>
                <label>
                  Storefront city
                  <input
                    value={sfCity}
                    onChange={(e) => setSfCity(e.target.value)}
                  />
                </label>
                <label>
                  Storefront visibility
                  <select
                    value={sfPublished ? "published" : "private"}
                    onChange={(e) =>
                      setSfPublished(e.target.value === "published")
                    }
                  >
                    <option value="published">published</option>
                    <option value="private">private</option>
                  </select>
                </label>
              </div>
              <fieldset className="market-fieldset">
                <legend>Storefront published_fields allow-list</legend>
                <div className="market-check-grid">
                  {ALL_PUBLIC_FIELDS.map((field) => (
                    <label key={field}>
                      <input
                        type="checkbox"
                        checked={sfFields.includes(field)}
                        onChange={() =>
                          toggleField(sfFields, field, setSfFields)
                        }
                      />
                      <span>sf:{field}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="market-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save storefront
                </button>
              </div>
            </form>
            <div
              className="market-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Storefronts table"
            >
              <table className="market-table">
                <thead>
                  <tr>
                    <th>Slug</th>
                    <th>Display Name</th>
                    <th>Published</th>
                    <th>Allowed Fields</th>
                  </tr>
                </thead>
                <tbody>
                  {storefronts.map((sf) => (
                    <tr key={sf.storefront_id}>
                      <td>{sf.slug}</td>
                      <td>{sf.display_name}</td>
                      <td>{sf.is_published ? "Yes" : "No"}</td>
                      <td>{sf.published_fields.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="market-card">
            <h2>Seller Listings (Private Cost vs Public Projection)</h2>
            <form onSubmit={handleSaveListing}>
              <div className="market-form-grid">
                <label>
                  Listing storefront
                  <select
                    value={lstSfId}
                    onChange={(e) => setLstSfId(e.target.value)}
                  >
                    {storefronts.map((sf) => (
                      <option key={sf.storefront_id} value={sf.storefront_id}>
                        {sf.slug} — {sf.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Listing SKU
                  <input
                    value={lstSku}
                    onChange={(e) => setLstSku(e.target.value)}
                    placeholder="ALPHA-01"
                  />
                </label>
                <label>
                  Listing title
                  <input
                    value={lstTitle}
                    onChange={(e) => setLstTitle(e.target.value)}
                    placeholder="Alpha Hydraulic Motor"
                  />
                </label>
                <label>
                  Listing description
                  <input
                    value={lstDesc}
                    onChange={(e) => setLstDesc(e.target.value)}
                  />
                </label>
                <label>
                  Listing category
                  <input
                    value={lstCategory}
                    onChange={(e) => setLstCategory(e.target.value)}
                  />
                </label>
                <label>
                  Price minor
                  <input
                    type="number"
                    value={lstPrice}
                    onChange={(e) => setLstPrice(e.target.value)}
                  />
                </label>
                <label>
                  Available quantity
                  <input
                    type="number"
                    value={lstQty}
                    onChange={(e) => setLstQty(e.target.value)}
                  />
                </label>
                <label>
                  Internal cost minor (private)
                  <input
                    type="number"
                    value={lstInternalCost}
                    onChange={(e) => setLstInternalCost(e.target.value)}
                  />
                </label>
                <label>
                  Internal notes (private)
                  <input
                    value={lstInternalNotes}
                    onChange={(e) => setLstInternalNotes(e.target.value)}
                  />
                </label>
                <label>
                  Moderation status
                  <select
                    value={lstStatus}
                    onChange={(e) =>
                      setLstStatus(e.target.value as ModerationStatus)
                    }
                  >
                    <option value="published">published</option>
                    <option value="draft">draft</option>
                    <option value="pending_review">pending_review</option>
                    <option value="suspended">suspended</option>
                  </select>
                </label>
              </div>
              <fieldset className="market-fieldset">
                <legend>Listing published_fields allow-list</legend>
                <div className="market-check-grid">
                  {ALL_PUBLIC_FIELDS.map((field) => (
                    <label key={field}>
                      <input
                        type="checkbox"
                        checked={lstFields.includes(field)}
                        onChange={() =>
                          toggleField(lstFields, field, setLstFields)
                        }
                      />
                      <span>lst:{field}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="market-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save listing
                </button>
              </div>
            </form>
          </div>

          <div className="market-card">
            <h2>Public Catalog Projection Preview</h2>
            <div className="market-form-grid">
              <label>
                Preview storefront
                <select
                  value={previewSfId}
                  onChange={(e) => setPreviewSfId(e.target.value)}
                >
                  {storefronts.map((sf) => (
                    <option key={sf.storefront_id} value={sf.storefront_id}>
                      {sf.slug}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="market-actions">
              <button
                type="button"
                disabled={busy || !previewSfId}
                onClick={() => void handlePreviewPublicCatalog()}
              >
                Load public catalog
              </button>
            </div>
            {publicCatalog ? (
              <pre className="market-pre" data-testid="public-catalog-json">
                {JSON.stringify(publicCatalog, null, 2)}
              </pre>
            ) : null}
          </div>
        </section>
      ) : null}

      {tab === "marketplaces" ? (
        <section
          id="mkt-panel-marketplaces"
          role="tabpanel"
          aria-labelledby="mkt-tab-marketplaces"
          className="market-panel"
        >
          <div className="market-card">
            <h2>Client-Operated Marketplaces (Zero GORGONA Commission)</h2>
            <form onSubmit={handleSaveMarketplace}>
              <div className="market-form-grid">
                <label>
                  Marketplace location
                  <select
                    value={mpLoc}
                    onChange={(e) => setMpLoc(e.target.value)}
                  >
                    {locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Marketplace slug
                  <input
                    value={mpSlug}
                    onChange={(e) => setMpSlug(e.target.value)}
                    placeholder="industrial-hub"
                  />
                </label>
                <label>
                  Marketplace title
                  <input
                    value={mpTitle}
                    onChange={(e) => setMpTitle(e.target.value)}
                    placeholder="Industrial Hub B2B"
                  />
                </label>
                <label>
                  Operator commercial fee (bps)
                  <input
                    type="number"
                    value={mpFeeBps}
                    onChange={(e) => setMpFeeBps(e.target.value)}
                  />
                </label>
              </div>
              <div className="market-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save marketplace
                </button>
              </div>
            </form>
            <div
              className="market-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Marketplaces table"
            >
              <table className="market-table">
                <thead>
                  <tr>
                    <th>Slug</th>
                    <th>Title</th>
                    <th>GORGONA Commission</th>
                    <th>Operator Fee (bps)</th>
                  </tr>
                </thead>
                <tbody>
                  {marketplaces.map((mp) => (
                    <tr key={mp.marketplace_id}>
                      <td>{mp.slug}</td>
                      <td>{mp.title}</td>
                      <td>{mp.gorgona_commission_bps} bps (0%)</td>
                      <td>{mp.operator_fee_bps} bps</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="market-card">
            <h2>Independent Seller Connections (Revocable)</h2>
            <div className="market-form-grid">
              <label>
                Active marketplace
                <select
                  value={selectedMpId}
                  onChange={(e) => {
                    setSelectedMpId(e.target.value);
                    void loadMpConnections(e.target.value);
                  }}
                >
                  {marketplaces.map((mp) => (
                    <option key={mp.marketplace_id} value={mp.marketplace_id}>
                      {mp.slug} — {mp.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <form onSubmit={handleConnectSeller}>
              <div className="market-form-grid">
                <label>
                  Seller counterparty
                  <select
                    value={connSellerCpId}
                    onChange={(e) => setConnSellerCpId(e.target.value)}
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
                  Seller storefront slug
                  <input
                    value={connSfSlug}
                    onChange={(e) => setConnSfSlug(e.target.value)}
                    placeholder="independent-seller"
                  />
                </label>
              </div>
              <div className="market-actions">
                <button
                  type="submit"
                  disabled={busy || !canManage || !selectedMpId}
                >
                  Connect seller
                </button>
              </div>
            </form>
            <div
              className="market-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Seller connections table"
            >
              <table className="market-table">
                <thead>
                  <tr>
                    <th>Seller Storefront</th>
                    <th>Scopes</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {connections.map((c) => (
                    <tr key={c.connection_id}>
                      <td>{c.seller_storefront_slug}</td>
                      <td>{c.granted_scopes.join(", ")}</td>
                      <td>{c.status}</td>
                      <td>
                        {c.status === "revoked" ? (
                          <button
                            type="button"
                            disabled={busy || !canManage}
                            onClick={() =>
                              void handleConnectionStatusChange(c, "active")
                            }
                          >
                            Attempt reactivate {c.seller_storefront_slug}
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={busy || !canManage}
                            onClick={() =>
                              void handleConnectionStatusChange(c, "revoked")
                            }
                          >
                            Revoke {c.seller_storefront_slug}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {tab === "checkout" ? (
        <section
          id="mkt-panel-checkout"
          role="tabpanel"
          aria-labelledby="mkt-tab-checkout"
          className="market-panel"
        >
          <div className="market-card">
            <h2>Multi-Seller Basket Checkout (Single-Seller Split)</h2>
            <form onSubmit={handleBasketCheckout}>
              <div className="market-form-grid">
                <label>
                  Buyer counterparty
                  <select
                    value={chkCustomerId}
                    onChange={(e) => setChkCustomerId(e.target.value)}
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
                  Checkout marketplace
                  <select
                    value={chkMpId}
                    onChange={(e) => setChkMpId(e.target.value)}
                  >
                    <option value="">(Direct storefront)</option>
                    {marketplaces.map((mp) => (
                      <option key={mp.marketplace_id} value={mp.marketplace_id}>
                        {mp.slug}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Seller fee counterparty
                  <select
                    value={chkSellerCpId}
                    onChange={(e) => setChkSellerCpId(e.target.value)}
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
                  Order date
                  <input
                    value={chkDate}
                    onChange={(e) => setChkDate(e.target.value)}
                  />
                </label>
                <label>
                  Basket line 1 listing
                  <select
                    value={chkLine1ListingId}
                    onChange={(e) => setChkLine1ListingId(e.target.value)}
                  >
                    {listings.map((l) => (
                      <option key={l.listing_id} value={l.listing_id}>
                        {l.sku} — {l.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Basket line 1 quantity
                  <input
                    type="number"
                    value={chkLine1Qty}
                    onChange={(e) => setChkLine1Qty(e.target.value)}
                  />
                </label>
                <label>
                  Line 1 seller book
                  <select
                    value={chkLine1BookId}
                    onChange={(e) => setChkLine1BookId(e.target.value)}
                  >
                    {books.map((b) => (
                      <option key={b.book_id} value={b.book_id}>
                        {b.code} — {b.base_currency}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Basket line 2 listing
                  <select
                    value={chkLine2ListingId}
                    onChange={(e) => setChkLine2ListingId(e.target.value)}
                  >
                    {listings.map((l) => (
                      <option key={l.listing_id} value={l.listing_id}>
                        {l.sku} — {l.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Basket line 2 quantity
                  <input
                    type="number"
                    value={chkLine2Qty}
                    onChange={(e) => setChkLine2Qty(e.target.value)}
                  />
                </label>
                <label>
                  Line 2 seller book
                  <select
                    value={chkLine2BookId}
                    onChange={(e) => setChkLine2BookId(e.target.value)}
                  >
                    {books.map((b) => (
                      <option key={b.book_id} value={b.book_id}>
                        {b.code} — {b.base_currency}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="market-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Checkout multi-seller basket
                </button>
              </div>
            </form>
          </div>

          <div className="market-card">
            <h2>Isolated Single-Seller Orders &amp; Customer Refund</h2>
            <form onSubmit={handleRefundOrder}>
              <div className="market-form-grid">
                <label>
                  Refund order
                  <select
                    value={refOrderId}
                    onChange={(e) => setRefOrderId(e.target.value)}
                  >
                    {orders.map((o) => (
                      <option key={o.order_id} value={o.order_id}>
                        {o.order_number} (
                        {formatMarketMinor(o.total_minor, o.currency)})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Refund amount minor
                  <input
                    type="number"
                    value={refMinor}
                    onChange={(e) => setRefMinor(e.target.value)}
                  />
                </label>
                <label>
                  Refund date
                  <input
                    value={refDate}
                    onChange={(e) => setRefDate(e.target.value)}
                  />
                </label>
                <label>
                  Refund reason
                  <input
                    value={refReason}
                    onChange={(e) => setRefReason(e.target.value)}
                  />
                </label>
              </div>
              <div className="market-actions">
                <button
                  type="submit"
                  disabled={busy || !canManage || !refOrderId}
                >
                  Post order refund
                </button>
              </div>
            </form>
            <div
              className="market-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Market orders table"
            >
              <table className="market-table">
                <thead>
                  <tr>
                    <th>Order #</th>
                    <th>Storefront</th>
                    <th>Total</th>
                    <th>Refunded</th>
                    <th>Status</th>
                    <th>FIN-03 Invoice</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.order_id}>
                      <td>{o.order_number}</td>
                      <td>
                        {storefronts.find(
                          (s) => s.storefront_id === o.storefront_id,
                        )?.slug ?? o.storefront_id}
                      </td>
                      <td>{formatMarketMinor(o.total_minor, o.currency)}</td>
                      <td>{formatMarketMinor(o.refunded_minor, o.currency)}</td>
                      <td>{o.status}</td>
                      <td>{o.invoice_document_id.slice(0, 8)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="market-card">
            <h2>Separate Operator Commercial Fees (Zero GORGONA Commission)</h2>
            <div
              className="market-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Operator fees table"
            >
              <table className="market-table">
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>GORGONA Commission</th>
                    <th>Operator Fee</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {operatorFees.map((f) => (
                    <tr key={f.fee_id}>
                      <td>{f.order_id.slice(0, 8)}</td>
                      <td>
                        {formatMarketMinor(
                          f.gorgona_commission_minor,
                          f.currency,
                        )}
                      </td>
                      <td>
                        {formatMarketMinor(f.operator_fee_minor, f.currency)}
                      </td>
                      <td>{f.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
