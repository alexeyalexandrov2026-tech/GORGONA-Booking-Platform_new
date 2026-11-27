"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { AmarkalLogo } from "./amarkal-logo";
import {
  fetchPublicPortalDocument,
  respondPublicPortalDocument,
  type PortalPublicDocument,
} from "../lib/commercial-api";
import "../app/us-release-v2.css";

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

const DEMO_QUOTE_DOC: PortalPublicDocument = {
  entity_kind: "quote",
  business_name: "Apex Freight Logistics LLC",
  expires_at: "2026-12-27T00:00:00Z",
  responded_at: null,
  checkout_url: null,
  purchase_order: null,
  quote: {
    id: "demo-q-1",
    quote_number: "Q-2026-1042",
    title: "Q4 Dedicated Midwest Freight & Cross-Docking",
    counterparty_id: null,
    counterparty_name: "Great Lakes Industrial Supply",
    counterparty_email: "ap@greatlakesindustrial.us",
    currency: "USD",
    items: [
      {
        description: "53' Dry Van Dedicated Linehaul (Chicago -> Dallas)",
        sku: "LN-CHI-DAL",
        quantity: 4,
        unit_price_cents: 185000,
        line_total_cents: 740000,
      },
      {
        description: "Cross-Dock Pallet Handling & Cold-Chain Inspection",
        sku: "XD-PAL-02",
        quantity: 12,
        unit_price_cents: 4500,
        line_total_cents: 54000,
      },
    ],
    subtotal_cents: 794000,
    discount_cents: 24000,
    tax_cents: 0,
    total_cents: 770000,
    payment_terms: "Net 30",
    valid_until: "2026-12-15",
    notes:
      "Includes real-time GPS telemetry, digital Bill of Lading (BOL), and 0% AMARKAL platform processing fee on direct ACH settlement.",
    status: "sent",
    approval_required: true,
    approved_at: "2026-11-27T08:00:00Z",
    accepted_by_name: null,
    accepted_at: null,
    declined_reason: null,
    payment_session_id: null,
    converted_invoice_ref: null,
    created_at: "2026-11-27T07:55:00Z",
    updated_at: "2026-11-27T08:00:00Z",
  },
};

export function B2bPortal() {
  const actorId = useId();
  const reasonId = useId();
  const [token, setToken] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState(false);
  const [doc, setDoc] = useState<PortalPublicDocument | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [actorName, setActorName] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(window.location.search);
    const rawToken = params.get("token")?.trim() || null;
    const isDemo = params.get("demo") === "1" || !rawToken;

    void Promise.resolve().then(async () => {
      if (!active) return;
      if (isDemo && !rawToken) {
        setDemoMode(true);
        setDoc(DEMO_QUOTE_DOC);
        setLoading(false);
        return;
      }
      setToken(rawToken);
      try {
        const fetched = await fetchPublicPortalDocument(rawToken!);
        if (!active) return;
        setDoc(fetched);
      } catch (err) {
        if (!active) return;
        setError(
          err instanceof Error
            ? err.message
            : "This B2B portal link is invalid or expired.",
        );
      } finally {
        if (active) setLoading(false);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  async function submitAction(action: "accept" | "decline" | "acknowledge") {
    if (actorName.trim().length < 2) {
      setError("Enter your full name to sign or confirm this B2B record.");
      return;
    }
    setError(null);
    setNotice(null);

    if (demoMode && doc?.quote) {
      setDoc({
        ...doc,
        responded_at: new Date().toISOString(),
        quote: {
          ...doc.quote,
          status: action === "accept" ? "accepted" : "declined",
          accepted_by_name: action === "accept" ? actorName.trim() : null,
          declined_reason: action === "decline" ? reason.trim() || null : null,
        },
      });
      setNotice(
        action === "accept"
          ? `Demo preview: Quote ${doc.quote.quote_number} accepted by ${actorName.trim()}.`
          : `Demo preview: Quote ${doc.quote.quote_number} declined.`,
      );
      return;
    }

    if (!token) return;
    setBusy(true);
    try {
      const updated = await respondPublicPortalDocument(token, {
        action,
        actor_name: actorName.trim(),
        reason: reason.trim() || null,
      });
      setDoc(updated);
      setNotice(
        action === "accept"
          ? "Quote accepted and recorded with timestamp."
          : action === "acknowledge"
            ? "Purchase Order acknowledged and recorded."
            : "Response recorded.",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not record response.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#fbfbfd",
        padding: "24px 16px 48px",
      }}
    >
      <div style={{ maxWidth: "820px", margin: "0 auto" }}>
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "12px",
            marginBottom: "24px",
          }}
        >
          <Link href="/" style={{ textDecoration: "none" }}>
            <AmarkalLogo variant="light" height={22} />
          </Link>
          <div className="usr-inline no-print">
            {doc && (
              <button
                type="button"
                className="secondary usr-small-btn"
                onClick={() => window.print()}
              >
                Print / Save PDF
              </button>
            )}
            <span className="usr-badge">
              {demoMode ? "B2B Portal Preview" : "Verified B2B Portal"}
            </span>
          </div>
        </header>

        <main id="main-content">
          {loading ? (
            <section className="usr-card">
              <p className="usr-muted">Verifying secure B2B portal token…</p>
            </section>
          ) : error && !doc ? (
            <section className="usr-card" role="alert">
              <h1>Portal link unavailable</h1>
              <p>{error}</p>
              <Link href="/" className="button secondary">
                Return to AMARKAL Platform
              </Link>
            </section>
          ) : doc?.quote ? (
            <section className="usr-card">
              <div
                className="usr-inline"
                style={{ justifyContent: "space-between" }}
              >
                <div>
                  <p className="usr-muted" style={{ margin: "0 0 4px" }}>
                    Issued by {doc.business_name}
                  </p>
                  <h1 style={{ margin: 0 }}>
                    {doc.quote.quote_number} — {doc.quote.title}
                  </h1>
                </div>
                <span
                  className={
                    "usr-badge " +
                    (doc.quote.status === "accepted" ||
                    doc.quote.status === "converted"
                      ? "usr-badge-ai"
                      : "usr-badge-fallback")
                  }
                >
                  {doc.quote.status}
                </span>
              </div>

              <p className="usr-muted" style={{ marginTop: "12px" }}>
                Prepared for <strong>{doc.quote.counterparty_name}</strong> ·
                Payment terms: <strong>{doc.quote.payment_terms}</strong>
                {doc.quote.valid_until
                  ? ` · Valid until ${doc.quote.valid_until}`
                  : ""}
              </p>

              {error && (
                <div className="usr-errors" role="alert">
                  <p style={{ margin: 0 }}>{error}</p>
                </div>
              )}
              {notice && (
                <p role="status" className="hold-note">
                  {notice}
                </p>
              )}

              <div className="usr-table-wrap" style={{ marginTop: "16px" }}>
                <table className="usr-table">
                  <thead>
                    <tr>
                      <th scope="col">Description</th>
                      <th scope="col">Qty</th>
                      <th scope="col">Unit Price</th>
                      <th scope="col">Line Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.quote.items.map((item, idx) => (
                      <tr key={idx}>
                        <td>
                          <strong>{item.description}</strong>
                          {item.sku && (
                            <div className="usr-muted">SKU: {item.sku}</div>
                          )}
                        </td>
                        <td>{item.quantity}</td>
                        <td>{formatUsd(item.unit_price_cents)}</td>
                        <td>
                          <strong>{formatUsd(item.line_total_cents)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <dl className="usr-ue-grid" style={{ marginTop: "16px" }}>
                <div>
                  <dt>Subtotal</dt>
                  <dd>{formatUsd(doc.quote.subtotal_cents)}</dd>
                </div>
                <div>
                  <dt>Discount</dt>
                  <dd>{formatUsd(doc.quote.discount_cents)}</dd>
                </div>
                <div>
                  <dt>Tax</dt>
                  <dd>{formatUsd(doc.quote.tax_cents)}</dd>
                </div>
                <div>
                  <dt>Total Due (USD)</dt>
                  <dd>{formatUsd(doc.quote.total_cents)}</dd>
                </div>
              </dl>

              {doc.quote.notes && (
                <p className="usr-muted" style={{ marginTop: "16px" }}>
                  {doc.quote.notes}
                </p>
              )}

              {doc.checkout_url && (
                <div style={{ marginTop: "16px" }}>
                  <a
                    href={doc.checkout_url}
                    target="_blank"
                    rel="noreferrer"
                    className="button"
                    style={{ textDecoration: "none" }}
                  >
                    Pay {formatUsd(doc.quote.total_cents)} via Stripe Checkout
                  </a>
                </div>
              )}

              {["approved", "sent"].includes(doc.quote.status) && (
                <div
                  style={{
                    marginTop: "24px",
                    paddingTop: "20px",
                    borderTop: "1px solid var(--line)",
                  }}
                >
                  <h2>Electronic Acceptance</h2>
                  <div className="usr-grid">
                    <label htmlFor={actorId}>
                      Authorized signer full name
                      <input
                        id={actorId}
                        type="text"
                        placeholder="Jordan Rivera, VP Operations"
                        value={actorName}
                        onChange={(e) => setActorName(e.target.value)}
                      />
                    </label>
                    <label htmlFor={reasonId}>
                      Note or decline reason (optional)
                      <input
                        id={reasonId}
                        type="text"
                        placeholder="Approved for Q4 dispatch"
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="usr-inline" style={{ marginTop: "12px" }}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void submitAction("accept")}
                    >
                      Accept &amp; Sign Quote
                    </button>
                    <button
                      type="button"
                      className="secondary usr-danger"
                      disabled={busy}
                      onClick={() => void submitAction("decline")}
                    >
                      Decline Quote
                    </button>
                  </div>
                </div>
              )}
            </section>
          ) : doc?.purchase_order ? (
            <section className="usr-card">
              <div
                className="usr-inline"
                style={{ justifyContent: "space-between" }}
              >
                <div>
                  <p className="usr-muted" style={{ margin: "0 0 4px" }}>
                    Purchase Order from {doc.business_name}
                  </p>
                  <h1 style={{ margin: 0 }}>
                    {doc.purchase_order.po_number} — {doc.purchase_order.title}
                  </h1>
                </div>
                <span className="usr-badge usr-badge-ai">
                  {doc.purchase_order.status}
                </span>
              </div>

              <p className="usr-muted" style={{ marginTop: "12px" }}>
                Vendor: <strong>{doc.purchase_order.vendor_name}</strong> ·
                Terms: <strong>{doc.purchase_order.payment_terms}</strong>
              </p>

              {error && (
                <div className="usr-errors" role="alert">
                  <p style={{ margin: 0 }}>{error}</p>
                </div>
              )}
              {notice && (
                <p role="status" className="hold-note">
                  {notice}
                </p>
              )}

              <div className="usr-table-wrap" style={{ marginTop: "16px" }}>
                <table className="usr-table">
                  <thead>
                    <tr>
                      <th scope="col">Item</th>
                      <th scope="col">Qty Ordered</th>
                      <th scope="col">Unit Cost</th>
                      <th scope="col">Line Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {doc.purchase_order.items.map((item, idx) => (
                      <tr key={idx}>
                        <td>{item.description}</td>
                        <td>{item.quantity_ordered}</td>
                        <td>{formatUsd(item.unit_cost_cents)}</td>
                        <td>
                          <strong>{formatUsd(item.line_total_cents)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <p style={{ marginTop: "16px", fontSize: "1.1rem" }}>
                <strong>
                  Order Total: {formatUsd(doc.purchase_order.total_cents)} USD
                </strong>
              </p>

              {["approved", "issued"].includes(doc.purchase_order.status) && (
                <div
                  style={{
                    marginTop: "24px",
                    paddingTop: "20px",
                    borderTop: "1px solid var(--line)",
                  }}
                >
                  <h2>Vendor Acknowledgement</h2>
                  <label htmlFor={actorId} style={{ maxWidth: "360px" }}>
                    Vendor representative full name
                    <input
                      id={actorId}
                      type="text"
                      placeholder="Sam Patel, Account Manager"
                      value={actorName}
                      onChange={(e) => setActorName(e.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void submitAction("acknowledge")}
                  >
                    Acknowledge Purchase Order
                  </button>
                </div>
              )}
            </section>
          ) : null}
        </main>
      </div>
    </div>
  );
}
