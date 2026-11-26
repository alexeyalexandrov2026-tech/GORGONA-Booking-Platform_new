"use client";

import { useEffect, useId, useState } from "react";
import {
  createCheckoutSession,
  fetchPaymentSessions,
  fetchPaymentsConfig,
  refundPaymentSession,
  syncPaymentSession,
  type PaymentSession,
  type PaymentsConfig,
} from "../lib/payments-api";
import { formatDate, formatTime } from "../lib/management-api";
import "../app/us-release-v2.css";

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

export function StripePaymentsPanel({ businessId }: { businessId: string }) {
  const amountId = useId();
  const descId = useId();
  const kindId = useId();
  const refId = useId();
  const nameId = useId();
  const emailId = useId();
  const achId = useId();

  const [config, setConfig] = useState<PaymentsConfig | null>(null);
  const [sessions, setSessions] = useState<PaymentSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [amountUsd, setAmountUsd] = useState("150.00");
  const [description, setDescription] = useState("");
  const [referenceKind, setReferenceKind] = useState<
    "invoice" | "order" | "deposit" | "service" | "custom"
  >("invoice");
  const [referenceId, setReferenceId] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [allowAch, setAllowAch] = useState(true);

  useEffect(() => {
    let active = true;
    void Promise.all([fetchPaymentsConfig(), fetchPaymentSessions(businessId)])
      .then(([cfg, list]) => {
        if (!active) return;
        setConfig(cfg);
        setSessions(list);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof Error
            ? err.message
            : "Could not load online payments.",
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
    setLoading(true);
    setError(null);
    setTick((t) => t + 1);
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const parsed = Math.round(Number(amountUsd) * 100);
    if (!Number.isFinite(parsed) || parsed < 50 || parsed > 99_999_999) {
      setError("Enter a USD amount between $0.50 and $999,999.99.");
      return;
    }
    if (!description.trim()) {
      setError("Enter a payment description for the customer receipt.");
      return;
    }
    setBusy(true);
    try {
      const created = await createCheckoutSession(businessId, {
        amount_cents: parsed,
        description: description.trim(),
        reference_kind: referenceKind,
        reference_id: referenceId.trim() || null,
        customer_name: customerName.trim(),
        customer_email: customerEmail.trim() || null,
        allow_ach: allowAch,
      });
      setSessions((prev) => [created, ...prev]);
      setDescription("");
      setReferenceId("");
      setNotice("Stripe Checkout payment link created.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not create Stripe Checkout session.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleSync = async (sessionId: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await syncPaymentSession(businessId, sessionId);
      setSessions((prev) =>
        prev.map((s) => (s.id === updated.id ? updated : s)),
      );
      setNotice(`Synced status with Stripe: ${updated.status}.`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not sync with Stripe.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleRefund = async (sessionId: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await refundPaymentSession(businessId, sessionId);
      setSessions((prev) =>
        prev.map((s) => (s.id === updated.id ? updated : s)),
      );
      setNotice("Refund issued through Stripe.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not issue refund.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="usr-card"
      aria-labelledby="stripe-payments-heading"
      style={{ marginTop: "24px" }}
    >
      <div className="usr-inline" style={{ justifyContent: "space-between" }}>
        <div>
          <h2 id="stripe-payments-heading">
            Online Payments (Stripe US — Cards, Apple Pay, ACH)
          </h2>
          <p className="usr-muted">
            Create hosted USD Stripe Checkout payment links, verify signed
            webhooks automatically, sync status, and issue refunds.
          </p>
        </div>
        {config && (
          <div className="usr-inline">
            <span
              className={
                "usr-badge " +
                (config.stripe_configured ? "usr-badge-ai" : "usr-badge-off")
              }
            >
              {config.stripe_configured
                ? config.stripe_livemode
                  ? "Stripe Live USD"
                  : "Stripe Test USD"
                : "Stripe key pending"}
            </span>
            <span
              className={
                "usr-badge " +
                (config.webhook_configured ? "usr-badge-ai" : "usr-badge-off")
              }
            >
              {config.webhook_configured
                ? "Signed webhook active"
                : "Webhook secret pending"}
            </span>
          </div>
        )}
      </div>

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

      <form onSubmit={(e) => void handleCreate(e)} className="usr-stack">
        <div className="usr-grid">
          <label htmlFor={amountId}>
            Amount (USD)
            <input
              id={amountId}
              type="number"
              min="0.50"
              max="999999.99"
              step="0.01"
              required
              value={amountUsd}
              onChange={(e) => setAmountUsd(e.target.value)}
            />
          </label>
          <label htmlFor={kindId}>
            Payment type
            <select
              id={kindId}
              value={referenceKind}
              onChange={(e) =>
                setReferenceKind(
                  e.target.value as
                    "invoice" | "order" | "deposit" | "service" | "custom",
                )
              }
            >
              <option value="invoice">Invoice</option>
              <option value="order">Order</option>
              <option value="deposit">Deposit</option>
              <option value="service">Service</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <label htmlFor={refId}>
            Reference # (optional)
            <input
              id={refId}
              type="text"
              placeholder="INV-1042"
              value={referenceId}
              onChange={(e) => setReferenceId(e.target.value)}
            />
          </label>
        </div>

        <div className="usr-grid">
          <label htmlFor={descId}>
            Description shown on Stripe Checkout
            <input
              id={descId}
              type="text"
              required
              placeholder="Freight dispatch invoice #1042"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label htmlFor={nameId}>
            Customer name (optional)
            <input
              id={nameId}
              type="text"
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
            />
          </label>
          <label htmlFor={emailId}>
            Customer email (optional)
            <input
              id={emailId}
              type="email"
              placeholder="client@company.com"
              value={customerEmail}
              onChange={(e) => setCustomerEmail(e.target.value)}
            />
          </label>
        </div>

        <label htmlFor={achId} className="usr-check">
          <input
            id={achId}
            type="checkbox"
            checked={allowAch}
            onChange={(e) => setAllowAch(e.target.checked)}
          />
          <span>
            Allow US Bank Account (ACH) in addition to cards, Apple Pay, and
            Google Pay
          </span>
        </label>

        <div className="usr-inline">
          <button
            type="submit"
            disabled={busy || loading || !config?.stripe_configured}
          >
            {busy ? "Creating link…" : "Create Stripe payment link"}
          </button>
          <button
            type="button"
            className="secondary usr-small-btn"
            disabled={busy || loading}
            onClick={reload}
          >
            Refresh
          </button>
        </div>
      </form>

      <h3 style={{ marginTop: "24px" }}>Recent payment links</h3>
      {loading ? (
        <p className="usr-muted">Loading payment sessions…</p>
      ) : sessions.length === 0 ? (
        <p className="usr-muted">
          No Stripe Checkout links created yet for this business.
        </p>
      ) : (
        <div
          className="usr-table-wrap"
          tabIndex={0}
          aria-label="Stripe payment sessions"
        >
          <table className="usr-table">
            <thead>
              <tr>
                <th scope="col">Created</th>
                <th scope="col">Description</th>
                <th scope="col">Amount</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td>
                    {formatDate(s.created_at)} · {formatTime(s.created_at)}
                    <div className="usr-muted">
                      {s.livemode ? "Live" : "Test"} · {s.reference_kind}
                      {s.reference_id ? ` #${s.reference_id}` : ""}
                    </div>
                  </td>
                  <td>
                    {s.description}
                    {s.customer_email ? (
                      <div className="usr-muted">{s.customer_email}</div>
                    ) : null}
                  </td>
                  <td>
                    <strong>{formatUsd(s.amount_cents)}</strong>
                  </td>
                  <td>
                    <span
                      className={
                        "usr-badge " +
                        (s.status === "paid"
                          ? "usr-badge-ai"
                          : s.status === "open"
                            ? "usr-badge-fallback"
                            : "usr-badge-off")
                      }
                    >
                      {s.status}
                    </span>
                  </td>
                  <td>
                    <div className="usr-inline">
                      {s.status === "open" && (
                        <a
                          href={s.checkout_url}
                          target="_blank"
                          rel="noreferrer"
                          className="button secondary usr-small-btn"
                        >
                          Open Checkout
                        </a>
                      )}
                      <button
                        type="button"
                        className="secondary usr-small-btn"
                        disabled={busy}
                        onClick={() => void handleSync(s.id)}
                      >
                        Sync
                      </button>
                      {s.status === "paid" && s.provider_payment_intent_id && (
                        <button
                          type="button"
                          className="secondary usr-small-btn usr-danger"
                          disabled={busy}
                          onClick={() => void handleRefund(s.id)}
                        >
                          Refund
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
  );
}
