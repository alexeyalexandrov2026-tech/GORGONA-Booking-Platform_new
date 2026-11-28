"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { AmarkalLogo } from "./amarkal-logo";
import {
  fetchPublicShopCatalog,
  quotePublicShopCart,
  submitPublicShopCheckout,
  type PublicQuoteCart,
  type PublicShopCatalog,
  type StorefrontItem,
} from "../lib/b2c-shop-api";
import "../app/us-release-v2.css";

const DEMO_SHOP: PublicShopCatalog = {
  public_slug: "demo",
  store_name: "AMARKAL Flagship B2C Shop (Interactive Demo)",
  tagline:
    "Modern 1-click retail & service storefront powered by AMARKAL Business OS — 0% platform commission.",
  hero_image_url: null,
  accent_hex: "#111111",
  support_email: "support@amarkal-platform.com",
  allow_promo_codes: true,
  items: [
    {
      id: "01950000-0000-7000-8000-000000001001",
      sku: "SVC-DIAG-01",
      title: "Full Fleet Preventive Maintenance Inspection",
      category: "Services",
      item_kind: "service",
      description:
        "Comprehensive 60-point DOT & mechanical safety inspection with instant digital compliance report.",
      price_cents: 18500,
      compare_at_cents: 22500,
      currency: "USD",
      image_url: null,
      stock_qty: null,
      is_active: true,
      display_order: 0,
    },
    {
      id: "01950000-0000-7000-8000-000000001002",
      sku: "KIT-SAFETY-PRO",
      title: "OSHA Commercial Jobsite Safety Bundle",
      category: "Equipment",
      item_kind: "product",
      description:
        "ANSI Type II hard hats, Class 3 hi-vis vests, and first-aid trauma kit shipped nationwide.",
      price_cents: 12900,
      compare_at_cents: 15900,
      currency: "USD",
      image_url: null,
      stock_qty: 24,
      is_active: true,
      display_order: 1,
    },
    {
      id: "01950000-0000-7000-8000-000000001003",
      sku: "PKG-QTR-RETAIN",
      title: "Quarterly Priority Dispatch & Support Pass",
      category: "Packages",
      item_kind: "package",
      description:
        "Prepaid 90-day priority scheduling bundle with dedicated account hotline and zero booking fees.",
      price_cents: 45000,
      compare_at_cents: null,
      currency: "USD",
      image_url: null,
      stock_qty: null,
      is_active: true,
      display_order: 2,
    },
  ],
};

function fmtUsd(cents: number): string {
  return `$${(cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

export function PublicB2CShop() {
  const [slug, setSlug] = useState<string>("demo");
  const [isDemo, setIsDemo] = useState(true);
  const [shop, setShop] = useState<PublicShopCatalog | null>(null);
  const [category, setCategory] = useState<string>("All");
  const [search, setSearch] = useState("");
  const [cart, setCart] = useState<Record<string, number>>({});
  const [promoInput, setPromoInput] = useState("");
  const [quote, setQuote] = useState<PublicQuoteCart | null>(null);
  const [promoErr, setPromoErr] = useState<string | null>(null);
  const [custName, setCustName] = useState("");
  const [custEmail, setCustEmail] = useState("");
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [checkoutMsg, setCheckoutMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const searchId = useId();
  const promoId = useId();
  const nameId = useId();
  const emailId = useId();

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(window.location.search);
    const storeParam = params.get("store")?.trim() ?? "";
    const demoFlag = params.get("demo") === "1" || !storeParam;
    const checkoutParam = params.get("checkout");

    async function loadStorefront() {
      if (demoFlag) {
        await Promise.resolve();
        if (!active) return;
        setIsDemo(true);
        setSlug("demo");
        setShop(DEMO_SHOP);
        if (checkoutParam === "success") {
          setCheckoutMsg("Payment completed! Thank you for your order.");
        }
        return;
      }
      try {
        const data = await fetchPublicShopCatalog(storeParam);
        if (!active) return;
        setIsDemo(false);
        setSlug(storeParam);
        setShop(data);
        setError(null);
        if (checkoutParam === "success") {
          setCheckoutMsg("Payment completed! Thank you for your order.");
        }
      } catch (err: unknown) {
        if (!active) return;
        setIsDemo(false);
        setSlug(storeParam);
        setError(
          err instanceof Error ? err.message : "Could not load storefront.",
        );
      }
    }

    void loadStorefront();
    return () => {
      active = false;
    };
  }, []);

  const categories = shop
    ? ["All", ...Array.from(new Set(shop.items.map((i) => i.category)))]
    : ["All"];

  const visibleItems = (shop?.items ?? []).filter((it) => {
    if (category !== "All" && it.category !== category) return false;
    const q = search.trim().toLowerCase();
    if (
      q &&
      !`${it.title} ${it.description} ${it.sku}`.toLowerCase().includes(q)
    )
      return false;
    return true;
  });

  function updateQty(item: StorefrontItem, delta: number) {
    setCart((prev) => {
      const next = (prev[item.id] ?? 0) + delta;
      const copy = { ...prev };
      if (next <= 0) delete copy[item.id];
      else copy[item.id] = Math.min(next, 50);
      return copy;
    });
    setQuote(null);
    setPromoErr(null);
  }

  const cartEntries = Object.entries(cart)
    .map(([itemId, quantity]) => ({
      item: shop?.items.find((i) => i.id === itemId),
      quantity,
    }))
    .filter((x): x is { item: StorefrontItem; quantity: number } =>
      Boolean(x.item),
    );

  const localSubtotal = cartEntries.reduce(
    (sum, x) => sum + x.item.price_cents * x.quantity,
    0,
  );
  const effectiveSubtotal = quote?.subtotal_cents ?? localSubtotal;
  const effectiveDiscount = quote?.discount_cents ?? 0;
  const effectiveTotal = quote?.total_cents ?? localSubtotal;

  async function onApplyPromo() {
    setPromoErr(null);
    if (!cartEntries.length) {
      setPromoErr("Add at least one item to your cart first.");
      return;
    }
    const clean = promoInput.trim().toUpperCase();
    if (!clean) return;
    if (isDemo) {
      if (clean === "WELCOME15") {
        const disc = Math.floor((localSubtotal * 15) / 100);
        setQuote({
          lines: cartEntries.map((x) => ({
            item_id: x.item.id,
            sku: x.item.sku,
            title: x.item.title,
            unit_price_cents: x.item.price_cents,
            quantity: x.quantity,
            line_total_cents: x.item.price_cents * x.quantity,
          })),
          subtotal_cents: localSubtotal,
          discount_cents: disc,
          total_cents: localSubtotal - disc,
          applied_promo_code: "WELCOME15",
          promo_message: "15% off applied (WELCOME15 — Demo)",
        });
      } else {
        setPromoErr('In Demo Mode, try promo code "WELCOME15" for 15% off.');
      }
      return;
    }
    try {
      const res = await quotePublicShopCart(
        slug,
        cartEntries.map((x) => ({
          item_id: x.item.id,
          quantity: x.quantity,
        })),
        clean,
      );
      setQuote(res);
    } catch (err) {
      setPromoErr(err instanceof Error ? err.message : "Invalid promo code.");
    }
  }

  async function onCheckout(e: React.FormEvent) {
    e.preventDefault();
    if (!cartEntries.length) return;
    setCheckoutBusy(true);
    setError(null);
    setCheckoutMsg(null);
    try {
      if (isDemo) {
        setCheckoutMsg(
          `Demo checkout prepared for ${custName.trim()} (${fmtUsd(effectiveTotal)} USD, 0% AMARKAL commission). Publish your own storefront in Workspace Studio -> B2C Shop Builder to accept live Stripe US payments!`,
        );
        return;
      }
      const order = await submitPublicShopCheckout(slug, {
        customer_name: custName.trim(),
        customer_email: custEmail.trim(),
        items: cartEntries.map((x) => ({
          item_id: x.item.id,
          quantity: x.quantity,
        })),
        promo_code: quote?.applied_promo_code ?? undefined,
      });
      if (order.checkout_url) {
        window.location.assign(order.checkout_url);
        return;
      }
      setCheckoutMsg(
        `Order ${order.order_number} recorded (${fmtUsd(order.total_cents)} USD).`,
      );
      setCart({});
      setQuote(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Checkout failed.");
    } finally {
      setCheckoutBusy(false);
    }
  }

  const accent = shop?.accent_hex ?? "#111111";

  return (
    <div className="management-shell">
      <header className="mgmt-header">
        <div className="mgmt-brand-area">
          <Link href="/" className="mgmt-brand">
            <AmarkalLogo variant="light" height={20} />
          </Link>
        </div>
        <div className="mgmt-header-actions">
          <Link href="/" className="mgmt-nav-link">
            AMARKAL Platform
          </Link>
          <Link href="/workspace/" className="mgmt-nav-link">
            Build Your Shop
          </Link>
        </div>
      </header>

      <main
        id="main-content"
        className="mgmt-main"
        style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 16px" }}
      >
        {error && (
          <div className="mgmt-error-banner" role="alert">
            <p>{error}</p>
          </div>
        )}
        {checkoutMsg && (
          <p role="status" className="hold-note">
            {checkoutMsg}
          </p>
        )}

        {shop && (
          <div className="usr-stack">
            <section
              className="usr-card"
              style={{ borderTop: `4px solid ${accent}` }}
            >
              <div
                className="usr-inline"
                style={{ justifyContent: "space-between" }}
              >
                <div>
                  <h1 style={{ margin: 0, fontSize: "1.8rem" }}>
                    {shop.store_name}
                  </h1>
                  <p className="usr-muted" style={{ margin: "6px 0 0" }}>
                    {shop.tagline}
                  </p>
                </div>
                <span className="usr-badge usr-badge-ai">
                  0% Platform Commission · Direct Stripe US
                </span>
              </div>
              <div className="usr-inline" style={{ marginTop: 16 }}>
                {categories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    className={
                      category === cat
                        ? "usr-small-btn"
                        : "secondary usr-small-btn"
                    }
                    style={
                      category === cat
                        ? { background: accent, borderColor: accent }
                        : undefined
                    }
                    onClick={() => setCategory(cat)}
                  >
                    {cat}
                  </button>
                ))}
                <label
                  htmlFor={searchId}
                  style={{ margin: 0, marginLeft: "auto" }}
                >
                  <span className="sr-only">Search catalog</span>
                  <input
                    id={searchId}
                    type="search"
                    placeholder="Search products or services…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    style={{ minWidth: 220 }}
                  />
                </label>
              </div>
            </section>

            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(auto-fit, minmax(min(100%, 320px), 1fr))",
                gap: 20,
                alignItems: "start",
              }}
            >
              <section aria-label="Catalog items" className="usr-stack">
                {visibleItems.length === 0 ? (
                  <p className="usr-muted">No matching items found.</p>
                ) : (
                  visibleItems.map((it) => {
                    const inCart = cart[it.id] ?? 0;
                    return (
                      <article key={it.id} className="usr-card">
                        <div
                          className="usr-inline"
                          style={{ justifyContent: "space-between" }}
                        >
                          <span className="usr-badge usr-badge-off">
                            {it.category}
                          </span>
                          <code className="usr-muted">{it.sku}</code>
                        </div>
                        <h2
                          style={{ margin: "10px 0 6px", fontSize: "1.15rem" }}
                        >
                          {it.title}
                        </h2>
                        <p className="usr-muted" style={{ margin: "0 0 12px" }}>
                          {it.description}
                        </p>
                        <div
                          className="usr-inline"
                          style={{ justifyContent: "space-between" }}
                        >
                          <div>
                            <strong style={{ fontSize: "1.15rem" }}>
                              {fmtUsd(it.price_cents)}
                            </strong>
                            {it.compare_at_cents ? (
                              <span
                                className="usr-muted"
                                style={{
                                  marginLeft: 8,
                                  textDecoration: "line-through",
                                }}
                              >
                                {fmtUsd(it.compare_at_cents)}
                              </span>
                            ) : null}
                          </div>
                          {inCart === 0 ? (
                            <button
                              type="button"
                              className="usr-small-btn"
                              style={{
                                background: accent,
                                borderColor: accent,
                              }}
                              onClick={() => updateQty(it, 1)}
                            >
                              + Add to Cart
                            </button>
                          ) : (
                            <div className="usr-inline">
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                aria-label={`Decrease quantity for ${it.title}`}
                                onClick={() => updateQty(it, -1)}
                              >
                                −
                              </button>
                              <strong>{inCart}</strong>
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                aria-label={`Increase quantity for ${it.title}`}
                                onClick={() => updateQty(it, 1)}
                              >
                                +
                              </button>
                            </div>
                          )}
                        </div>
                      </article>
                    );
                  })
                )}
              </section>

              <aside className="usr-card" aria-labelledby="shop-cart-heading">
                <h2
                  id="shop-cart-heading"
                  style={{ marginTop: 0, fontSize: "1.2rem" }}
                >
                  Shopping Cart (
                  {cartEntries.reduce((s, x) => s + x.quantity, 0)})
                </h2>
                {cartEntries.length === 0 ? (
                  <p className="usr-muted">
                    Your cart is empty. Add products or services to check out
                    with Cards, Apple Pay, or Google Pay.
                  </p>
                ) : (
                  <div className="usr-stack">
                    <ul
                      style={{
                        listStyle: "none",
                        padding: 0,
                        margin: 0,
                        display: "grid",
                        gap: 8,
                      }}
                    >
                      {cartEntries.map(({ item, quantity }) => (
                        <li
                          key={item.id}
                          className="usr-inline"
                          style={{
                            justifyContent: "space-between",
                            borderBottom: "1px solid var(--line)",
                            paddingBottom: 6,
                          }}
                        >
                          <span>
                            {quantity}× {item.title}
                          </span>
                          <strong>{fmtUsd(item.price_cents * quantity)}</strong>
                        </li>
                      ))}
                    </ul>

                    {shop.allow_promo_codes && (
                      <div>
                        <label htmlFor={promoId}>
                          Promo code {isDemo ? "(try WELCOME15)" : ""}
                        </label>
                        <div className="usr-inline">
                          <input
                            id={promoId}
                            type="text"
                            maxLength={32}
                            value={promoInput}
                            placeholder="WELCOME15"
                            onChange={(e) => setPromoInput(e.target.value)}
                          />
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            onClick={() => void onApplyPromo()}
                          >
                            Apply
                          </button>
                        </div>
                        {quote?.promo_message && (
                          <p className="usr-muted" role="status">
                            {quote.promo_message}
                          </p>
                        )}
                        {promoErr && (
                          <p className="usr-field-error" role="alert">
                            {promoErr}
                          </p>
                        )}
                      </div>
                    )}

                    <div
                      style={{
                        borderTop: "1px solid var(--line)",
                        paddingTop: 10,
                        display: "grid",
                        gap: 4,
                      }}
                    >
                      <div
                        className="usr-inline"
                        style={{ justifyContent: "space-between" }}
                      >
                        <span className="usr-muted">Subtotal</span>
                        <span>{fmtUsd(effectiveSubtotal)}</span>
                      </div>
                      {effectiveDiscount > 0 && (
                        <div
                          className="usr-inline"
                          style={{ justifyContent: "space-between" }}
                        >
                          <span className="usr-muted">Promo discount</span>
                          <strong>−{fmtUsd(effectiveDiscount)}</strong>
                        </div>
                      )}
                      <div
                        className="usr-inline"
                        style={{
                          justifyContent: "space-between",
                          fontSize: "1.1rem",
                        }}
                      >
                        <strong>Total (USD)</strong>
                        <strong>{fmtUsd(effectiveTotal)}</strong>
                      </div>
                    </div>

                    <form
                      onSubmit={(e) => void onCheckout(e)}
                      aria-label="Complete B2C checkout"
                      className="usr-stack"
                    >
                      <label htmlFor={nameId}>
                        Full name
                        <input
                          id={nameId}
                          type="text"
                          required
                          minLength={2}
                          maxLength={160}
                          value={custName}
                          placeholder="Jordan Taylor"
                          onChange={(e) => setCustName(e.target.value)}
                        />
                      </label>
                      <label htmlFor={emailId}>
                        Receipt email
                        <input
                          id={emailId}
                          type="email"
                          required
                          maxLength={160}
                          value={custEmail}
                          placeholder="jordan@example.com"
                          onChange={(e) => setCustEmail(e.target.value)}
                        />
                      </label>
                      <button
                        type="submit"
                        disabled={checkoutBusy}
                        style={{ background: accent, borderColor: accent }}
                      >
                        {checkoutBusy
                          ? "Creating secure checkout…"
                          : `Pay ${fmtUsd(effectiveTotal)} USD`}
                      </button>
                    </form>
                  </div>
                )}
              </aside>
            </div>
          </div>
        )}
      </main>

      <footer className="mgmt-footer">
        <span>© 2026 Alexey AAA Logistics LLC — AMARKAL Platform</span>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}
