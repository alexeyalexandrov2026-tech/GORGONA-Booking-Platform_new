"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import {
  createStorefrontItem,
  createStorefrontPromo,
  deleteStorefrontItem,
  deleteStorefrontPromo,
  fetchB2COrders,
  fetchStorefrontConfig,
  fetchStorefrontItems,
  fetchStorefrontPromos,
  saveStorefrontConfig,
  syncServicesToStorefront,
  type B2CItemKind,
  type B2COrder,
  type PromoCode,
  type PromoDiscountKind,
  type StorefrontConfig,
  type StorefrontItem,
} from "../lib/b2c-shop-api";

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function fmtUsd(cents: number): string {
  return `$${(cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

export function B2CStorefrontBuilder({ businessId }: { businessId: string }) {
  const [config, setConfig] = useState<StorefrontConfig | null>(null);
  const [items, setItems] = useState<StorefrontItem[]>([]);
  const [promos, setPromos] = useState<PromoCode[]>([]);
  const [orders, setOrders] = useState<B2COrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Storefront settings
  const [storeName, setStoreName] = useState("");
  const [publicSlug, setPublicSlug] = useState("");
  const [tagline, setTagline] = useState("");
  const [accentHex, setAccentHex] = useState("#111111");
  const [supportEmail, setSupportEmail] = useState("");
  const [isPublished, setIsPublished] = useState(true);
  const [allowPromos, setAllowPromos] = useState(true);
  const [savingCfg, setSavingCfg] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Item form
  const [sku, setSku] = useState("");
  const [itemTitle, setItemTitle] = useState("");
  const [itemCategory, setItemCategory] = useState("Featured");
  const [itemKind, setItemKind] = useState<B2CItemKind>("product");
  const [priceUsd, setPriceUsd] = useState("49.00");
  const [compareUsd, setCompareUsd] = useState("");
  const [itemDesc, setItemDesc] = useState("");
  const [addingItem, setAddingItem] = useState(false);

  // Promo form
  const [promoCode, setPromoCode] = useState("");
  const [promoKind, setPromoKind] = useState<PromoDiscountKind>("percent");
  const [promoValue, setPromoValue] = useState("15");
  const [minSubUsd, setMinSubUsd] = useState("0");
  const [addingPromo, setAddingPromo] = useState(false);

  const nameId = useId();
  const slugId = useId();
  const tagId = useId();
  const hexId = useId();
  const emailId = useId();
  const skuId = useId();
  const itTitleId = useId();
  const itCatId = useId();
  const itKindId = useId();
  const itPriceId = useId();
  const itCompId = useId();
  const itDescId = useId();
  const pCodeId = useId();
  const pKindId = useId();
  const pValId = useId();
  const pMinId = useId();

  useEffect(() => {
    let active = true;
    void Promise.all([
      fetchStorefrontConfig(businessId),
      fetchStorefrontItems(businessId),
      fetchStorefrontPromos(businessId),
      fetchB2COrders(businessId).catch(() => []),
    ])
      .then(([cfg, itList, prList, ordList]) => {
        if (!active) return;
        setConfig(cfg);
        if (cfg.configured) {
          setStoreName(cfg.store_name ?? "");
          setPublicSlug(cfg.public_slug ?? "");
          setTagline(cfg.tagline ?? "");
          setAccentHex(cfg.accent_hex ?? "#111111");
          setSupportEmail(cfg.support_email ?? "");
          setIsPublished(cfg.is_published);
          setAllowPromos(cfg.allow_promo_codes);
        }
        setItems(itList);
        setPromos(prList);
        setOrders(ordList);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  async function onSaveConfig(e: React.FormEvent) {
    e.preventDefault();
    setSavingCfg(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveStorefrontConfig(businessId, {
        store_name: storeName.trim(),
        public_slug:
          publicSlug.trim().toLowerCase() ||
          storeName
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .slice(0, 48),
        tagline: tagline.trim(),
        accent_hex: accentHex.trim(),
        support_email: supportEmail.trim() || null,
        is_published: isPublished,
        show_services: true,
        allow_promo_codes: allowPromos,
      });
      setConfig(saved);
      setPublicSlug(saved.public_slug ?? "");
      setNotice(
        `B2C Storefront saved and ${saved.is_published ? "published" : "saved as draft"} at /shop/?store=${saved.public_slug ?? ""}.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingCfg(false);
    }
  }

  async function onSyncServices() {
    setSyncing(true);
    setError(null);
    setNotice(null);
    try {
      const res = await syncServicesToStorefront(businessId);
      const refreshed = await fetchStorefrontItems(businessId);
      setItems(refreshed);
      setNotice(
        `Synced ${res.synced_count} published service(s) from your AMARKAL catalog into your B2C Shop.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSyncing(false);
    }
  }

  async function onAddItem(e: React.FormEvent) {
    e.preventDefault();
    setAddingItem(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createStorefrontItem(businessId, {
        sku: sku.trim().toUpperCase(),
        title: itemTitle.trim(),
        category: itemCategory.trim() || "Featured",
        item_kind: itemKind,
        description: itemDesc.trim(),
        price_cents: Math.round(Number(priceUsd) * 100),
        compare_at_cents: compareUsd.trim()
          ? Math.round(Number(compareUsd) * 100)
          : null,
      });
      setItems((prev) => [...prev, created]);
      setSku("");
      setItemTitle("");
      setItemDesc("");
      setCompareUsd("");
      setNotice(
        `Added "${created.title}" (${fmtUsd(created.price_cents)}) to B2C Shop.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setAddingItem(false);
    }
  }

  async function onAddPromo(e: React.FormEvent) {
    e.preventDefault();
    setAddingPromo(true);
    setError(null);
    setNotice(null);
    try {
      const rawVal = Number(promoValue);
      const discountValue =
        promoKind === "percent" ? Math.round(rawVal) : Math.round(rawVal * 100);
      const created = await createStorefrontPromo(businessId, {
        code: promoCode.trim().toUpperCase(),
        discount_kind: promoKind,
        discount_value: discountValue,
        min_subtotal_cents: Math.round(Number(minSubUsd || "0") * 100),
      });
      setPromos((prev) => [created, ...prev]);
      setPromoCode("");
      setNotice(`Promo code ${created.code} created.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setAddingPromo(false);
    }
  }

  const publicUrl = config?.public_slug
    ? `/shop/?store=${encodeURIComponent(config.public_slug)}`
    : "/shop/?demo=1";

  return (
    <div className="usr-stack">
      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="hold-note" style={{ margin: 0 }}>
          {notice}
        </p>
      )}
      {loading && (
        <p className="mgmt-loading" aria-live="polite">
          Loading B2C Storefront Builder…
        </p>
      )}

      {!loading && (
        <>
          <section className="usr-card" aria-labelledby="b2c-builder-heading">
            <div
              className="usr-inline"
              style={{ justifyContent: "space-between" }}
            >
              <div>
                <h3 id="b2c-builder-heading" style={{ margin: 0 }}>
                  1-Click B2C Storefront Builder (0% Commission Shop)
                </h3>
                <p className="usr-muted" style={{ margin: "4px 0 0" }}>
                  Turn your AMARKAL services and products into a modern public
                  retail storefront with shopping cart, promo codes, and direct
                  Stripe US checkout (Cards, Apple Pay, Google Pay — 0% AMARKAL
                  fee).
                </p>
              </div>
              <div className="usr-inline">
                <Link
                  href={publicUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="button secondary usr-small-btn"
                >
                  {config?.configured && config.is_published
                    ? "Open Live Storefront ↗"
                    : "Preview Demo Storefront ↗"}
                </Link>
              </div>
            </div>

            <form
              onSubmit={(e) => void onSaveConfig(e)}
              aria-label="Configure B2C storefront"
              style={{ marginTop: 14 }}
            >
              <div className="usr-grid">
                <label htmlFor={nameId}>
                  Storefront name
                  <input
                    id={nameId}
                    type="text"
                    required
                    minLength={2}
                    maxLength={120}
                    value={storeName}
                    placeholder="Acme US Supply & Services Shop"
                    onChange={(e) => setStoreName(e.target.value)}
                  />
                </label>
                <label htmlFor={slugId}>
                  Public URL slug (/shop/?store=...)
                  <input
                    id={slugId}
                    type="text"
                    required
                    minLength={3}
                    maxLength={63}
                    value={publicSlug}
                    placeholder="acme-shop"
                    onChange={(e) => setPublicSlug(e.target.value)}
                  />
                </label>
              </div>
              <div className="usr-grid">
                <label htmlFor={tagId}>
                  Hero tagline
                  <input
                    id={tagId}
                    type="text"
                    maxLength={240}
                    value={tagline}
                    placeholder="Direct-to-customer pricing with zero marketplace markup."
                    onChange={(e) => setTagline(e.target.value)}
                  />
                </label>
                <label htmlFor={hexId}>
                  Accent hex (WCAG AA ≥ 4.5:1)
                  <input
                    id={hexId}
                    type="text"
                    pattern="^#[0-9A-Fa-f]{6}$"
                    maxLength={7}
                    value={accentHex}
                    onChange={(e) => setAccentHex(e.target.value)}
                  />
                </label>
                <label htmlFor={emailId}>
                  Support email (optional)
                  <input
                    id={emailId}
                    type="email"
                    maxLength={160}
                    value={supportEmail}
                    placeholder="orders@company.com"
                    onChange={(e) => setSupportEmail(e.target.value)}
                  />
                </label>
              </div>
              <div className="usr-inline" style={{ margin: "12px 0" }}>
                <label className="usr-check">
                  <input
                    type="checkbox"
                    checked={isPublished}
                    onChange={(e) => setIsPublished(e.target.checked)}
                  />
                  <span>Publish storefront live on /shop/</span>
                </label>
                <label className="usr-check">
                  <input
                    type="checkbox"
                    checked={allowPromos}
                    onChange={(e) => setAllowPromos(e.target.checked)}
                  />
                  <span>Enable promo codes at checkout</span>
                </label>
              </div>
              <div className="usr-inline">
                <button type="submit" disabled={savingCfg}>
                  {savingCfg ? "Publishing…" : "Save & Publish Storefront"}
                </button>
                <button
                  type="button"
                  className="secondary usr-small-btn"
                  disabled={syncing}
                  onClick={() => void onSyncServices()}
                >
                  {syncing
                    ? "Syncing services…"
                    : "1-Click Sync AMARKAL Services"}
                </button>
              </div>
            </form>
          </section>

          <section className="usr-card" aria-labelledby="b2c-items-heading">
            <h3 id="b2c-items-heading" style={{ marginTop: 0 }}>
              Storefront Products &amp; Services ({items.length})
            </h3>
            <form
              onSubmit={(e) => void onAddItem(e)}
              aria-label="Add storefront item"
            >
              <div className="usr-grid">
                <label htmlFor={skuId}>
                  SKU
                  <input
                    id={skuId}
                    type="text"
                    required
                    minLength={2}
                    maxLength={48}
                    value={sku}
                    placeholder="KIT-001"
                    onChange={(e) => setSku(e.target.value)}
                  />
                </label>
                <label htmlFor={itTitleId}>
                  Product / Service title
                  <input
                    id={itTitleId}
                    type="text"
                    required
                    minLength={2}
                    maxLength={160}
                    value={itemTitle}
                    placeholder="Commercial Safety Starter Kit"
                    onChange={(e) => setItemTitle(e.target.value)}
                  />
                </label>
                <label htmlFor={itCatId}>
                  Category
                  <input
                    id={itCatId}
                    type="text"
                    value={itemCategory}
                    onChange={(e) => setItemCategory(e.target.value)}
                  />
                </label>
                <label htmlFor={itKindId}>
                  Type
                  <select
                    id={itKindId}
                    value={itemKind}
                    onChange={(e) => setItemKind(e.target.value as B2CItemKind)}
                  >
                    <option value="product">Physical Product</option>
                    <option value="service">Service / Package</option>
                    <option value="package">Bundle</option>
                    <option value="digital">Digital / Guide</option>
                  </select>
                </label>
                <label htmlFor={itPriceId}>
                  Price (USD)
                  <input
                    id={itPriceId}
                    type="number"
                    required
                    min="0.50"
                    step="0.01"
                    value={priceUsd}
                    onChange={(e) => setPriceUsd(e.target.value)}
                  />
                </label>
                <label htmlFor={itCompId}>
                  Compare-at price (optional)
                  <input
                    id={itCompId}
                    type="number"
                    min="0.50"
                    step="0.01"
                    value={compareUsd}
                    placeholder="69.00"
                    onChange={(e) => setCompareUsd(e.target.value)}
                  />
                </label>
              </div>
              <label htmlFor={itDescId}>
                Short description
                <input
                  id={itDescId}
                  type="text"
                  maxLength={1000}
                  value={itemDesc}
                  placeholder="Ships within 24h across all 50 US states."
                  onChange={(e) => setItemDesc(e.target.value)}
                />
              </label>
              <button
                type="submit"
                disabled={addingItem}
                style={{ marginTop: 10 }}
              >
                {addingItem ? "Adding…" : "+ Add Storefront Item"}
              </button>
            </form>

            {items.length > 0 && (
              <div
                className="usr-table-wrap"
                tabIndex={0}
                style={{ marginTop: 14 }}
              >
                <table className="usr-table">
                  <thead>
                    <tr>
                      <th scope="col">SKU</th>
                      <th scope="col">Title</th>
                      <th scope="col">Category</th>
                      <th scope="col">Price</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => (
                      <tr key={it.id}>
                        <td>
                          <code>{it.sku}</code>
                        </td>
                        <td>
                          <strong>{it.title}</strong>
                        </td>
                        <td>{it.category}</td>
                        <td>
                          {fmtUsd(it.price_cents)}
                          {it.compare_at_cents ? (
                            <span
                              className="usr-muted"
                              style={{
                                marginLeft: 6,
                                textDecoration: "line-through",
                              }}
                            >
                              {fmtUsd(it.compare_at_cents)}
                            </span>
                          ) : null}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="usr-danger usr-small-btn"
                            onClick={() =>
                              void deleteStorefrontItem(businessId, it.id).then(
                                () =>
                                  setItems((prev) =>
                                    prev.filter((x) => x.id !== it.id),
                                  ),
                              )
                            }
                          >
                            Remove
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="usr-card" aria-labelledby="b2c-promos-heading">
            <h3 id="b2c-promos-heading" style={{ marginTop: 0 }}>
              Promo Codes &amp; Discounts ({promos.length})
            </h3>
            <form
              onSubmit={(e) => void onAddPromo(e)}
              aria-label="Create promo code"
            >
              <div className="usr-grid">
                <label htmlFor={pCodeId}>
                  Code
                  <input
                    id={pCodeId}
                    type="text"
                    required
                    minLength={3}
                    maxLength={32}
                    value={promoCode}
                    placeholder="WELCOME15"
                    onChange={(e) => setPromoCode(e.target.value)}
                  />
                </label>
                <label htmlFor={pKindId}>
                  Discount type
                  <select
                    id={pKindId}
                    value={promoKind}
                    onChange={(e) =>
                      setPromoKind(e.target.value as PromoDiscountKind)
                    }
                  >
                    <option value="percent">Percentage (%)</option>
                    <option value="fixed_cents">Fixed USD off ($)</option>
                  </select>
                </label>
                <label htmlFor={pValId}>
                  {promoKind === "percent" ? "Percent off (1-95)" : "USD off"}
                  <input
                    id={pValId}
                    type="number"
                    required
                    min="1"
                    step={promoKind === "percent" ? "1" : "0.01"}
                    value={promoValue}
                    onChange={(e) => setPromoValue(e.target.value)}
                  />
                </label>
                <label htmlFor={pMinId}>
                  Minimum order (USD)
                  <input
                    id={pMinId}
                    type="number"
                    min="0"
                    step="0.01"
                    value={minSubUsd}
                    onChange={(e) => setMinSubUsd(e.target.value)}
                  />
                </label>
              </div>
              <button
                type="submit"
                disabled={addingPromo}
                style={{ marginTop: 10 }}
              >
                {addingPromo ? "Creating…" : "+ Create Promo Code"}
              </button>
            </form>

            {promos.length > 0 && (
              <ul
                className="usr-rows"
                style={{ listStyle: "none", padding: 0, marginTop: 12 }}
              >
                {promos.map((p) => (
                  <li key={p.id} className="usr-connector">
                    <div
                      className="usr-inline"
                      style={{ justifyContent: "space-between" }}
                    >
                      <strong>
                        <code>{p.code}</code> —{" "}
                        {p.discount_kind === "percent"
                          ? `${p.discount_value}% off`
                          : `${fmtUsd(p.discount_value)} off`}
                      </strong>
                      <button
                        type="button"
                        className="usr-danger usr-small-btn"
                        onClick={() =>
                          void deleteStorefrontPromo(businessId, p.id).then(
                            () =>
                              setPromos((prev) =>
                                prev.filter((x) => x.id !== p.id),
                              ),
                          )
                        }
                      >
                        Delete
                      </button>
                    </div>
                    <span className="usr-muted">
                      Min order: {fmtUsd(p.min_subtotal_cents)} · Used{" "}
                      {p.redemptions_count} time(s)
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {orders.length > 0 && (
            <section className="usr-card" aria-labelledby="b2c-orders-heading">
              <h3 id="b2c-orders-heading" style={{ marginTop: 0 }}>
                Recent Storefront Orders ({orders.length})
              </h3>
              <div className="usr-table-wrap" tabIndex={0}>
                <table className="usr-table">
                  <thead>
                    <tr>
                      <th scope="col">Order #</th>
                      <th scope="col">Customer</th>
                      <th scope="col">Promo</th>
                      <th scope="col">Total</th>
                      <th scope="col">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((o) => (
                      <tr key={o.id}>
                        <td>
                          <code>{o.order_number}</code>
                        </td>
                        <td>{o.customer_name}</td>
                        <td>{o.promo_code ?? "—"}</td>
                        <td>{fmtUsd(o.total_cents)}</td>
                        <td>{o.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
