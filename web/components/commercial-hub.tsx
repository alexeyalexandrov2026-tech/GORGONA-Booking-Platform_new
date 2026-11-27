"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import {
  approvePurchaseOrder,
  approveQuote,
  convertQuoteToStripePayment,
  createPurchaseOrder,
  createQuote,
  emailPurchaseOrderPortal,
  emailQuotePortal,
  fetchAgingReport,
  fetchApprovalPolicies,
  fetchCommercialSummary,
  fetchPurchaseOrders,
  fetchQuotes,
  fetchRecurringSchedules,
  matchPurchaseOrderVendorBill,
  recordPurchaseOrderReceipt,
  sharePurchaseOrderPortal,
  shareQuotePortal,
  updateApprovalPolicy,
  type AgingReportView,
  type ApprovalPolicyView,
  type CommercialSummaryView,
  type PaymentTerms,
  type PolicyEntityKind,
  type PurchaseOrderView,
  type QuoteView,
  type RecurringScheduleView,
} from "../lib/commercial-api";
import { CommercialAgingTab } from "./commercial-aging-tab";
import { CommercialRecurringTab } from "./commercial-recurring-tab";
import { formatDate } from "../lib/management-api";
import "../app/us-release-v2.css";

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

type TabId = "quotes" | "pos" | "recurring" | "aging" | "policies";

interface DraftLine {
  description: string;
  sku: string;
  quantity: string;
  unitPriceUsd: string;
}

const TERMS: PaymentTerms[] = [
  "Due on receipt",
  "Net 15",
  "Net 30",
  "Net 45",
  "Net 60",
];

export function CommercialHub({ businessId }: { businessId: string }) {
  const [tab, setTab] = useState<TabId>("quotes");
  const [summary, setSummary] = useState<CommercialSummaryView | null>(null);
  const [quotes, setQuotes] = useState<QuoteView[]>([]);
  const [pos, setPos] = useState<PurchaseOrderView[]>([]);
  const [policies, setPolicies] = useState<ApprovalPolicyView[]>([]);
  const [schedules, setSchedules] = useState<RecurringScheduleView[]>([]);
  const [aging, setAging] = useState<AgingReportView | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sharedLink, setSharedLink] = useState<{
    label: string;
    url: string;
  } | null>(null);

  // Quote builder state
  const qTitleId = useId();
  const qClientId = useId();
  const qEmailId = useId();
  const qTermsId = useId();
  const qDiscountId = useId();
  const qTaxId = useId();
  const [qTitle, setQTitle] = useState("");
  const [qClient, setQClient] = useState("");
  const [qEmail, setQEmail] = useState("");
  const [qTerms, setQTerms] = useState<PaymentTerms>("Net 30");
  const [qDiscountUsd, setQDiscountUsd] = useState("0");
  const [qTaxPct, setQTaxPct] = useState("0");
  const [qNotes, setQNotes] = useState("");
  const [qLines, setQLines] = useState<DraftLine[]>([
    { description: "", sku: "", quantity: "1", unitPriceUsd: "1250.00" },
  ]);

  // PO builder state
  const poTitleId = useId();
  const poVendorId = useId();
  const poEmailId = useId();
  const poTermsId = useId();
  const [poTitle, setPoTitle] = useState("");
  const [poVendor, setPoVendor] = useState("");
  const [poEmail, setPoEmail] = useState("");
  const [poTerms, setPoTerms] = useState<PaymentTerms>("Net 30");
  const [poNotes, setPoNotes] = useState("");
  const [poLines, setPoLines] = useState<DraftLine[]>([
    { description: "", sku: "", quantity: "1", unitPriceUsd: "800.00" },
  ]);

  // Inline 3-way match bill dialog state
  const [matchingPoId, setMatchingPoId] = useState<string | null>(null);
  const [billNumber, setBillNumber] = useState("");
  const [billAmountUsd, setBillAmountUsd] = useState("");

  useEffect(() => {
    let active = true;
    void Promise.all([
      fetchCommercialSummary(businessId),
      fetchQuotes(businessId),
      fetchPurchaseOrders(businessId),
      fetchApprovalPolicies(businessId),
      fetchRecurringSchedules(businessId).catch(() => []),
      fetchAgingReport(businessId).catch(() => null),
    ])
      .then(([sum, qList, poList, pols, scheds, agingRep]) => {
        if (!active) return;
        setSummary(sum);
        setQuotes(qList);
        setPos(poList);
        setPolicies(pols);
        setSchedules(scheds);
        setAging(agingRep);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof Error
            ? err.message
            : "Could not load commercial workspace.",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);

  const reload = () => {
    setTick((t) => t + 1);
  };

  async function handleCreateQuote(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const items = qLines
      .filter((l) => l.description.trim())
      .map((l) => ({
        description: l.description.trim(),
        sku: l.sku.trim() || null,
        quantity: Math.max(1, Math.round(Number(l.quantity) || 1)),
        unit_price_cents: Math.max(
          0,
          Math.round((Number(l.unitPriceUsd) || 0) * 100),
        ),
      }));
    if (items.length === 0) {
      setError("Add at least one line item with a description.");
      return;
    }
    setBusy(true);
    try {
      const created = await createQuote(businessId, {
        title: qTitle.trim(),
        counterparty_name: qClient.trim(),
        counterparty_email: qEmail.trim() || null,
        items,
        discount_cents: Math.max(
          0,
          Math.round((Number(qDiscountUsd) || 0) * 100),
        ),
        tax_rate_bps: Math.max(
          0,
          Math.min(2500, Math.round((Number(qTaxPct) || 0) * 100)),
        ),
        payment_terms: qTerms,
        notes: qNotes.trim(),
      });
      setQTitle("");
      setQClient("");
      setQEmail("");
      setQNotes("");
      setQLines([
        { description: "", sku: "", quantity: "1", unitPriceUsd: "1250.00" },
      ]);
      setNotice(
        created.status === "pending_approval"
          ? `Quote ${created.quote_number} created and routed for owner approval (above threshold).`
          : `Quote ${created.quote_number} created and auto-approved.`,
      );
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create quote.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreatePo(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const items = poLines
      .filter((l) => l.description.trim())
      .map((l) => ({
        description: l.description.trim(),
        sku: l.sku.trim() || null,
        quantity_ordered: Math.max(1, Math.round(Number(l.quantity) || 1)),
        unit_cost_cents: Math.max(
          0,
          Math.round((Number(l.unitPriceUsd) || 0) * 100),
        ),
      }));
    if (items.length === 0) {
      setError("Add at least one purchase order line item.");
      return;
    }
    setBusy(true);
    try {
      const created = await createPurchaseOrder(businessId, {
        title: poTitle.trim(),
        vendor_name: poVendor.trim(),
        vendor_email: poEmail.trim() || null,
        items,
        payment_terms: poTerms,
        notes: poNotes.trim(),
      });
      setPoTitle("");
      setPoVendor("");
      setPoEmail("");
      setPoNotes("");
      setPoLines([
        { description: "", sku: "", quantity: "1", unitPriceUsd: "800.00" },
      ]);
      setNotice(
        created.status === "pending_approval"
          ? `Purchase Order ${created.po_number} created and routed for approval.`
          : `Purchase Order ${created.po_number} created and auto-approved.`,
      );
      reload();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not create purchase order.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleSavePolicy(
    entityKind: PolicyEntityKind,
    thresholdUsd: string,
    autoBelow: boolean,
  ) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const cents = Math.max(0, Math.round((Number(thresholdUsd) || 0) * 100));
      const updated = await updateApprovalPolicy(businessId, entityKind, {
        threshold_cents: cents,
        require_owner_above_threshold: true,
        auto_approve_below_threshold: autoBelow,
      });
      setPolicies((prev) =>
        prev.map((p) => (p.entity_kind === entityKind ? updated : p)),
      );
      setNotice(
        `Updated ${entityKind === "quote" ? "Sales Quote" : "Purchase Order"} approval threshold to ${formatUsd(updated.threshold_cents)}.`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update policy.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mgmt-page">
      <div
        className="mgmt-section-header"
        style={{ marginTop: 0, flexWrap: "wrap", gap: "12px" }}
      >
        <div>
          <h1 style={{ margin: "0 0 6px" }}>Commercial &amp; Procurement</h1>
          <p className="usr-muted" style={{ margin: 0 }}>
            End-to-end B2B Deal-to-Cash: CPQ quotes, vendor purchase orders,
            3-way bill matching, approval workflows, and tokenized client/vendor
            portals.
          </p>
        </div>
        <div className="usr-inline">
          <Link
            href="/portal/?demo=1"
            className="button secondary usr-small-btn"
            style={{ textDecoration: "none" }}
          >
            Preview B2B Portal →
          </Link>
          <button
            type="button"
            className="secondary usr-small-btn"
            disabled={busy}
            onClick={reload}
          >
            Refresh
          </button>
        </div>
      </div>

      {summary && (
        <div className="mgmt-kpi-grid" aria-label="Commercial KPIs">
          <div className="mgmt-kpi-card">
            <div className="mgmt-kpi-label">Quote Pipeline</div>
            <div className="mgmt-kpi-number">
              {formatUsd(summary.quotes_pipeline_cents)}
            </div>
            <div className="usr-muted">{summary.quotes_open_count} open</div>
          </div>
          <div className="mgmt-kpi-card">
            <div className="mgmt-kpi-label">Accepted Quotes</div>
            <div className="mgmt-kpi-number">
              {formatUsd(summary.quotes_accepted_cents)}
            </div>
            <div className="usr-muted">
              {summary.quotes_accepted_count} won / converted
            </div>
          </div>
          <div className="mgmt-kpi-card">
            <div className="mgmt-kpi-label">Committed Spend (PO)</div>
            <div className="mgmt-kpi-number">
              {formatUsd(summary.po_committed_cents)}
            </div>
            <div className="usr-muted">{summary.po_open_count} open POs</div>
          </div>
          <div className="mgmt-kpi-card">
            <div className="mgmt-kpi-label">Pending Approvals</div>
            <div className="mgmt-kpi-number">
              {summary.quotes_pending_approval_count +
                summary.po_pending_approval_count}
            </div>
            <div className="usr-muted">
              {summary.po_matched_count} 3-way matched ·{" "}
              {summary.po_variance_count} variance
            </div>
          </div>
        </div>
      )}

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
      {sharedLink && (
        <div className="usr-secret" role="region" aria-label="B2B Portal Link">
          <p style={{ margin: "0 0 8px" }}>
            <strong>One-time B2B Portal link for {sharedLink.label}</strong>{" "}
            (copy and send to your client or vendor — raw token is shown once):
          </p>
          <div className="usr-inline">
            <input
              type="text"
              readOnly
              value={sharedLink.url}
              aria-label="Shareable B2B portal URL"
              style={{ flex: "1 1 320px", margin: 0 }}
            />
            <button
              type="button"
              className="secondary usr-small-btn"
              onClick={() => {
                void navigator.clipboard?.writeText(sharedLink.url);
                setNotice("Portal link copied to clipboard.");
              }}
            >
              Copy link
            </button>
            <a
              href={sharedLink.url}
              target="_blank"
              rel="noreferrer"
              className="button secondary usr-small-btn"
              style={{ textDecoration: "none" }}
            >
              Open portal
            </a>
          </div>
        </div>
      )}

      <div
        className="usr-tablist"
        role="tablist"
        aria-label="Commercial sections"
      >
        <button
          type="button"
          role="tab"
          aria-selected={tab === "quotes"}
          className="usr-tab"
          onClick={() => setTab("quotes")}
        >
          Sales Quotes (CPQ) ({quotes.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "pos"}
          className="usr-tab"
          onClick={() => setTab("pos")}
        >
          Purchase Orders &amp; 3-Way Match ({pos.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "recurring"}
          className="usr-tab"
          onClick={() => setTab("recurring")}
        >
          Recurring &amp; Retainers ({schedules.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "aging"}
          className="usr-tab"
          onClick={() => setTab("aging")}
        >
          AR / AP Aging &amp; CPA
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "policies"}
          className="usr-tab"
          onClick={() => setTab("policies")}
        >
          Approval Policies ({policies.length})
        </button>
      </div>

      {loading ? (
        <p className="usr-muted">Loading commercial workspace…</p>
      ) : tab === "quotes" ? (
        <>
          <section className="usr-card" aria-labelledby="new-quote-heading">
            <h2 id="new-quote-heading">Create B2B Commercial Quote (CPQ)</h2>
            <form
              onSubmit={(e) => void handleCreateQuote(e)}
              className="usr-stack"
            >
              <div className="usr-grid">
                <label htmlFor={qTitleId}>
                  Quote title
                  <input
                    id={qTitleId}
                    type="text"
                    required
                    placeholder="Q4 Dedicated Freight Lane — Chicago to Dallas"
                    value={qTitle}
                    onChange={(e) => setQTitle(e.target.value)}
                  />
                </label>
                <label htmlFor={qClientId}>
                  Client / Counterparty name
                  <input
                    id={qClientId}
                    type="text"
                    required
                    placeholder="Apex Freight LLC"
                    value={qClient}
                    onChange={(e) => setQClient(e.target.value)}
                  />
                </label>
                <label htmlFor={qEmailId}>
                  Client email (optional)
                  <input
                    id={qEmailId}
                    type="email"
                    placeholder="procurement@apexfreight.us"
                    value={qEmail}
                    onChange={(e) => setQEmail(e.target.value)}
                  />
                </label>
              </div>
              <div className="usr-grid">
                <label htmlFor={qTermsId}>
                  Payment terms
                  <select
                    id={qTermsId}
                    value={qTerms}
                    onChange={(e) => setQTerms(e.target.value as PaymentTerms)}
                  >
                    {TERMS.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </label>
                <label htmlFor={qDiscountId}>
                  Discount (USD)
                  <input
                    id={qDiscountId}
                    type="number"
                    min="0"
                    step="0.01"
                    value={qDiscountUsd}
                    onChange={(e) => setQDiscountUsd(e.target.value)}
                  />
                </label>
                <label htmlFor={qTaxId}>
                  Sales tax (%)
                  <input
                    id={qTaxId}
                    type="number"
                    min="0"
                    max="25"
                    step="0.01"
                    value={qTaxPct}
                    onChange={(e) => setQTaxPct(e.target.value)}
                  />
                </label>
              </div>
              <div className="usr-rows">
                {qLines.map((line, idx) => (
                  <div className="usr-row" key={idx}>
                    <label>
                      Line item description
                      <input
                        type="text"
                        required
                        placeholder="Linehaul dispatch / consulting / equipment"
                        value={line.description}
                        onChange={(e) =>
                          setQLines((prev) =>
                            prev.map((row, i) =>
                              i === idx
                                ? { ...row, description: e.target.value }
                                : row,
                            ),
                          )
                        }
                      />
                    </label>
                    <label>
                      Qty
                      <input
                        type="number"
                        min="1"
                        value={line.quantity}
                        onChange={(e) =>
                          setQLines((prev) =>
                            prev.map((row, i) =>
                              i === idx
                                ? { ...row, quantity: e.target.value }
                                : row,
                            ),
                          )
                        }
                      />
                    </label>
                    <label>
                      Unit USD
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={line.unitPriceUsd}
                        onChange={(e) =>
                          setQLines((prev) =>
                            prev.map((row, i) =>
                              i === idx
                                ? { ...row, unitPriceUsd: e.target.value }
                                : row,
                            ),
                          )
                        }
                      />
                    </label>
                    <button
                      type="button"
                      className="secondary usr-small-btn"
                      disabled={qLines.length === 1}
                      onClick={() =>
                        setQLines((prev) => prev.filter((_, i) => i !== idx))
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <div className="usr-inline">
                <button
                  type="button"
                  className="secondary usr-small-btn"
                  onClick={() =>
                    setQLines((prev) => [
                      ...prev,
                      {
                        description: "",
                        sku: "",
                        quantity: "1",
                        unitPriceUsd: "500.00",
                      },
                    ])
                  }
                >
                  + Add line item
                </button>
                <button type="submit" disabled={busy}>
                  {busy ? "Creating…" : "Create Commercial Quote"}
                </button>
              </div>
            </form>
          </section>

          <section className="usr-card" aria-labelledby="quotes-list-heading">
            <h2 id="quotes-list-heading">Commercial Quotes</h2>
            {quotes.length === 0 ? (
              <p className="usr-muted">
                No commercial quotes created yet. Build your first B2B quote
                above.
              </p>
            ) : (
              <div className="usr-table-wrap" tabIndex={0}>
                <table className="usr-table">
                  <thead>
                    <tr>
                      <th scope="col">Quote</th>
                      <th scope="col">Client</th>
                      <th scope="col">Total</th>
                      <th scope="col">Status</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quotes.map((q) => (
                      <tr key={q.id}>
                        <td>
                          <strong>{q.quote_number}</strong> · {q.title}
                          <div className="usr-muted">
                            {q.payment_terms} · {formatDate(q.created_at)}
                          </div>
                        </td>
                        <td>
                          {q.counterparty_name}
                          {q.accepted_by_name && (
                            <div className="usr-muted">
                              Signed by {q.accepted_by_name}
                            </div>
                          )}
                        </td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <strong>{formatUsd(q.total_cents)}</strong>
                        </td>
                        <td>
                          <span
                            className={
                              "usr-badge " +
                              (q.status === "accepted" ||
                              q.status === "converted"
                                ? "usr-badge-ai"
                                : q.status === "pending_approval"
                                  ? "usr-badge-fallback"
                                  : "usr-badge-off")
                            }
                          >
                            {q.status}
                          </span>
                        </td>
                        <td>
                          <div className="usr-inline">
                            {(q.status === "draft" ||
                              q.status === "pending_approval") && (
                              <button
                                type="button"
                                className="usr-small-btn"
                                disabled={busy}
                                onClick={() => {
                                  setBusy(true);
                                  setError(null);
                                  void approveQuote(businessId, q.id)
                                    .then(() => {
                                      setNotice(
                                        `Approved ${q.quote_number}. You can now share its B2B portal link.`,
                                      );
                                      reload();
                                    })
                                    .catch((e: unknown) =>
                                      setError(
                                        e instanceof Error
                                          ? e.message
                                          : "Approval failed.",
                                      ),
                                    )
                                    .finally(() => setBusy(false));
                                }}
                              >
                                Approve
                              </button>
                            )}
                            {["approved", "sent", "accepted"].includes(
                              q.status,
                            ) && (
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                disabled={busy}
                                onClick={() => {
                                  setBusy(true);
                                  setError(null);
                                  void shareQuotePortal(businessId, q.id)
                                    .then((res) => {
                                      setSharedLink({
                                        label: `${q.quote_number} (${q.counterparty_name})`,
                                        url: res.portal_url,
                                      });
                                      reload();
                                    })
                                    .catch((e: unknown) =>
                                      setError(
                                        e instanceof Error
                                          ? e.message
                                          : "Could not create portal link.",
                                      ),
                                    )
                                    .finally(() => setBusy(false));
                                }}
                              >
                                Share Portal Link
                              </button>
                            )}
                            {["approved", "sent", "accepted"].includes(
                              q.status,
                            ) && (
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                disabled={busy || !q.counterparty_email}
                                title={
                                  q.counterparty_email
                                    ? `Email secure portal link to ${q.counterparty_email}`
                                    : "Add a client email on the quote to send"
                                }
                                onClick={() => {
                                  setBusy(true);
                                  setError(null);
                                  void emailQuotePortal(businessId, q.id)
                                    .then((res) => {
                                      setNotice(
                                        `Emailed ${q.quote_number} to ${res.recipient_email} (${res.delivery_status} via ${res.provider_name}).`,
                                      );
                                      reload();
                                    })
                                    .catch((e: unknown) =>
                                      setError(
                                        e instanceof Error
                                          ? e.message
                                          : "Could not send quote email.",
                                      ),
                                    )
                                    .finally(() => setBusy(false));
                                }}
                              >
                                Email Client
                              </button>
                            )}
                            {["approved", "sent", "accepted"].includes(
                              q.status,
                            ) && (
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                disabled={busy}
                                onClick={() => {
                                  setBusy(true);
                                  setError(null);
                                  void convertQuoteToStripePayment(
                                    businessId,
                                    q.id,
                                  )
                                    .then((res) => {
                                      setSharedLink({
                                        label: `Stripe Checkout for ${q.quote_number}`,
                                        url: res.checkout_url,
                                      });
                                      setNotice(
                                        `Converted ${q.quote_number} into a live USD Stripe Checkout link (0% AMARKAL fee).`,
                                      );
                                      reload();
                                    })
                                    .catch((e: unknown) =>
                                      setError(
                                        e instanceof Error
                                          ? e.message
                                          : "Could not create Stripe link.",
                                      ),
                                    )
                                    .finally(() => setBusy(false));
                                }}
                              >
                                Create Stripe Link
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : tab === "pos" ? (
        <>
          <section className="usr-card" aria-labelledby="new-po-heading">
            <h2 id="new-po-heading">Create Vendor Purchase Order (PO)</h2>
            <form
              onSubmit={(e) => void handleCreatePo(e)}
              className="usr-stack"
            >
              <div className="usr-grid">
                <label htmlFor={poTitleId}>
                  Purchase Order title
                  <input
                    id={poTitleId}
                    type="text"
                    required
                    placeholder="Bulk Fleet Diesel & Tires Restock"
                    value={poTitle}
                    onChange={(e) => setPoTitle(e.target.value)}
                  />
                </label>
                <label htmlFor={poVendorId}>
                  Vendor / Supplier name
                  <input
                    id={poVendorId}
                    type="text"
                    required
                    placeholder="Midwest Diesel Supply Corp"
                    value={poVendor}
                    onChange={(e) => setPoVendor(e.target.value)}
                  />
                </label>
                <label htmlFor={poEmailId}>
                  Vendor email (optional)
                  <input
                    id={poEmailId}
                    type="email"
                    placeholder="orders@midwestdiesel.us"
                    value={poEmail}
                    onChange={(e) => setPoEmail(e.target.value)}
                  />
                </label>
              </div>
              <label htmlFor={poTermsId} style={{ maxWidth: "240px" }}>
                Payment terms
                <select
                  id={poTermsId}
                  value={poTerms}
                  onChange={(e) => setPoTerms(e.target.value as PaymentTerms)}
                >
                  {TERMS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <div className="usr-rows">
                {poLines.map((line, idx) => (
                  <div className="usr-row" key={idx}>
                    <label>
                      Item / Part description
                      <input
                        type="text"
                        required
                        placeholder="Heavy-duty steer tire 295/75R22.5"
                        value={line.description}
                        onChange={(e) =>
                          setPoLines((prev) =>
                            prev.map((row, i) =>
                              i === idx
                                ? { ...row, description: e.target.value }
                                : row,
                            ),
                          )
                        }
                      />
                    </label>
                    <label>
                      Qty
                      <input
                        type="number"
                        min="1"
                        value={line.quantity}
                        onChange={(e) =>
                          setPoLines((prev) =>
                            prev.map((row, i) =>
                              i === idx
                                ? { ...row, quantity: e.target.value }
                                : row,
                            ),
                          )
                        }
                      />
                    </label>
                    <label>
                      Unit Cost USD
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={line.unitPriceUsd}
                        onChange={(e) =>
                          setPoLines((prev) =>
                            prev.map((row, i) =>
                              i === idx
                                ? { ...row, unitPriceUsd: e.target.value }
                                : row,
                            ),
                          )
                        }
                      />
                    </label>
                    <button
                      type="button"
                      className="secondary usr-small-btn"
                      disabled={poLines.length === 1}
                      onClick={() =>
                        setPoLines((prev) => prev.filter((_, i) => i !== idx))
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <div className="usr-inline">
                <button
                  type="button"
                  className="secondary usr-small-btn"
                  onClick={() =>
                    setPoLines((prev) => [
                      ...prev,
                      {
                        description: "",
                        sku: "",
                        quantity: "1",
                        unitPriceUsd: "400.00",
                      },
                    ])
                  }
                >
                  + Add PO line
                </button>
                <button type="submit" disabled={busy}>
                  {busy ? "Creating…" : "Create Purchase Order"}
                </button>
              </div>
            </form>
          </section>

          <section className="usr-card" aria-labelledby="pos-list-heading">
            <h2 id="pos-list-heading">Purchase Orders &amp; 3-Way Match</h2>
            {pos.length === 0 ? (
              <p className="usr-muted">No vendor purchase orders yet.</p>
            ) : (
              <div className="usr-table-wrap" tabIndex={0}>
                <table className="usr-table">
                  <thead>
                    <tr>
                      <th scope="col">PO</th>
                      <th scope="col">Vendor</th>
                      <th scope="col">PO / Received / Bill</th>
                      <th scope="col">3-Way Match</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pos.map((po) => (
                      <tr key={po.id}>
                        <td>
                          <strong>{po.po_number}</strong> · {po.title}
                          <div className="usr-muted">
                            {po.status} · {po.payment_terms}
                          </div>
                        </td>
                        <td>
                          {po.vendor_name}
                          {po.vendor_acknowledged_by && (
                            <div className="usr-muted">
                              Ack: {po.vendor_acknowledged_by}
                            </div>
                          )}
                        </td>
                        <td>
                          <div>PO: {formatUsd(po.total_cents)}</div>
                          <div className="usr-muted">
                            Received: {formatUsd(po.received_total_cents)}
                          </div>
                          {po.vendor_bill_cents !== null && (
                            <div className="usr-muted">
                              Bill {po.vendor_bill_number}:{" "}
                              {formatUsd(po.vendor_bill_cents)}
                            </div>
                          )}
                        </td>
                        <td>
                          <span
                            className={
                              "usr-badge " +
                              (po.three_way_match_status === "matched"
                                ? "usr-badge-ai"
                                : po.three_way_match_status === "variance"
                                  ? "usr-badge-fallback"
                                  : "usr-badge-off")
                            }
                          >
                            {po.three_way_match_status}
                          </span>
                          {po.variance_cents !== 0 && (
                            <div className="usr-muted">
                              Var: {formatUsd(po.variance_cents)}
                            </div>
                          )}
                        </td>
                        <td>
                          <div className="usr-inline">
                            {(po.status === "draft" ||
                              po.status === "pending_approval") && (
                              <button
                                type="button"
                                className="usr-small-btn"
                                disabled={busy}
                                onClick={() => {
                                  setBusy(true);
                                  setError(null);
                                  void approvePurchaseOrder(businessId, po.id)
                                    .then(() => {
                                      setNotice(`Approved ${po.po_number}.`);
                                      reload();
                                    })
                                    .catch((e: unknown) =>
                                      setError(
                                        e instanceof Error
                                          ? e.message
                                          : "Approval failed.",
                                      ),
                                    )
                                    .finally(() => setBusy(false));
                                }}
                              >
                                Approve
                              </button>
                            )}
                            {["approved", "issued", "acknowledged"].includes(
                              po.status,
                            ) && (
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                disabled={busy}
                                onClick={() => {
                                  setBusy(true);
                                  setError(null);
                                  void sharePurchaseOrderPortal(
                                    businessId,
                                    po.id,
                                  )
                                    .then((res) => {
                                      setSharedLink({
                                        label: `Vendor Portal for ${po.po_number}`,
                                        url: res.portal_url,
                                      });
                                      reload();
                                    })
                                    .catch((e: unknown) =>
                                      setError(
                                        e instanceof Error
                                          ? e.message
                                          : "Could not share PO.",
                                      ),
                                    )
                                    .finally(() => setBusy(false));
                                }}
                              >
                                Vendor Link
                              </button>
                            )}
                            {["approved", "issued", "acknowledged"].includes(
                              po.status,
                            ) && (
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                disabled={busy || !po.vendor_email}
                                title={
                                  po.vendor_email
                                    ? `Email vendor portal link to ${po.vendor_email}`
                                    : "Add a vendor email on the PO to send"
                                }
                                onClick={() => {
                                  setBusy(true);
                                  setError(null);
                                  void emailPurchaseOrderPortal(
                                    businessId,
                                    po.id,
                                  )
                                    .then((res) => {
                                      setNotice(
                                        `Emailed ${po.po_number} to ${res.recipient_email} (${res.delivery_status} via ${res.provider_name}).`,
                                      );
                                      reload();
                                    })
                                    .catch((e: unknown) =>
                                      setError(
                                        e instanceof Error
                                          ? e.message
                                          : "Could not send vendor email.",
                                      ),
                                    )
                                    .finally(() => setBusy(false));
                                }}
                              >
                                Email Vendor
                              </button>
                            )}
                            {po.status !== "draft" &&
                              po.status !== "pending_approval" &&
                              po.status !== "cancelled" && (
                                <>
                                  <button
                                    type="button"
                                    className="secondary usr-small-btn"
                                    disabled={busy}
                                    onClick={() => {
                                      setBusy(true);
                                      setError(null);
                                      void recordPurchaseOrderReceipt(
                                        businessId,
                                        po.id,
                                        po.items.map((i) => i.quantity_ordered),
                                      )
                                        .then(() => {
                                          setNotice(
                                            `Recorded full receipt for ${po.po_number}.`,
                                          );
                                          reload();
                                        })
                                        .catch((e: unknown) =>
                                          setError(
                                            e instanceof Error
                                              ? e.message
                                              : "Could not record receipt.",
                                          ),
                                        )
                                        .finally(() => setBusy(false));
                                    }}
                                  >
                                    Receive All
                                  </button>
                                  <button
                                    type="button"
                                    className="secondary usr-small-btn"
                                    disabled={busy}
                                    onClick={() => {
                                      setMatchingPoId(po.id);
                                      setBillNumber(
                                        po.vendor_bill_number ||
                                          `BILL-${po.po_number}`,
                                      );
                                      setBillAmountUsd(
                                        (po.total_cents / 100).toFixed(2),
                                      );
                                    }}
                                  >
                                    Match Bill
                                  </button>
                                </>
                              )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {matchingPoId && (
              <div
                style={{
                  marginTop: "16px",
                  padding: "16px",
                  borderRadius: "12px",
                  border: "1px solid var(--line)",
                  background: "#f8f9fc",
                }}
              >
                <h3>3-Way Match Vendor Bill</h3>
                <div className="usr-grid">
                  <label>
                    Vendor bill number
                    <input
                      type="text"
                      value={billNumber}
                      onChange={(e) => setBillNumber(e.target.value)}
                    />
                  </label>
                  <label>
                    Vendor bill total (USD)
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={billAmountUsd}
                      onChange={(e) => setBillAmountUsd(e.target.value)}
                    />
                  </label>
                </div>
                <div className="usr-inline">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => {
                      setBusy(true);
                      setError(null);
                      const cents = Math.round(
                        (Number(billAmountUsd) || 0) * 100,
                      );
                      void matchPurchaseOrderVendorBill(
                        businessId,
                        matchingPoId,
                        billNumber.trim(),
                        cents,
                      )
                        .then((updated) => {
                          setNotice(
                            `3-way match result for ${updated.po_number}: ${updated.three_way_match_status.toUpperCase()} (variance ${formatUsd(updated.variance_cents)}).`,
                          );
                          setMatchingPoId(null);
                          reload();
                        })
                        .catch((e: unknown) =>
                          setError(
                            e instanceof Error
                              ? e.message
                              : "Could not match bill.",
                          ),
                        )
                        .finally(() => setBusy(false));
                    }}
                  >
                    Run 3-Way Match
                  </button>
                  <button
                    type="button"
                    className="secondary usr-small-btn"
                    onClick={() => setMatchingPoId(null)}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </section>
        </>
      ) : tab === "recurring" ? (
        <CommercialRecurringTab
          businessId={businessId}
          schedules={schedules}
          busy={busy}
          setBusy={setBusy}
          setError={setError}
          setNotice={setNotice}
          onReload={reload}
        />
      ) : tab === "aging" ? (
        <CommercialAgingTab
          businessId={businessId}
          report={aging}
          busy={busy}
          setBusy={setBusy}
          setError={setError}
          setNotice={setNotice}
        />
      ) : (
        <section className="usr-card" aria-labelledby="policies-heading">
          <h2 id="policies-heading">Approval Threshold Policies</h2>
          <p className="usr-muted">
            Control when B2B quotes and vendor purchase orders require explicit
            owner/manager sign-off before external sharing.
          </p>
          <div className="usr-connector-grid">
            {policies.map((pol) => (
              <PolicyCard
                key={pol.entity_kind}
                policy={pol}
                busy={busy}
                onSave={(usd, autoBelow) =>
                  void handleSavePolicy(pol.entity_kind, usd, autoBelow)
                }
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function PolicyCard({
  policy,
  busy,
  onSave,
}: {
  policy: ApprovalPolicyView;
  busy: boolean;
  onSave: (thresholdUsd: string, autoBelow: boolean) => void;
}) {
  const [thresholdUsd, setThresholdUsd] = useState(
    (policy.threshold_cents / 100).toFixed(2),
  );
  const [autoBelow, setAutoBelow] = useState(
    policy.auto_approve_below_threshold,
  );
  const inputId = useId();
  const checkId = useId();

  return (
    <div className="usr-connector">
      <h3>
        {policy.entity_kind === "quote"
          ? "Sales Quotes (CPQ)"
          : "Vendor Purchase Orders"}
      </h3>
      <p className="usr-muted">
        Documents above this USD amount automatically enter{" "}
        <code>pending_approval</code>.
      </p>
      <label htmlFor={inputId}>
        Approval threshold (USD)
        <input
          id={inputId}
          type="number"
          min="0"
          step="1"
          value={thresholdUsd}
          onChange={(e) => setThresholdUsd(e.target.value)}
        />
      </label>
      <label htmlFor={checkId} className="usr-check">
        <input
          id={checkId}
          type="checkbox"
          checked={autoBelow}
          onChange={(e) => setAutoBelow(e.target.checked)}
        />
        <span>Auto-approve documents at or below threshold</span>
      </label>
      <button
        type="button"
        className="usr-small-btn"
        disabled={busy}
        onClick={() => onSave(thresholdUsd, autoBelow)}
      >
        Save policy
      </button>
    </div>
  );
}
