"use client";

import React, { useCallback, useEffect, useId, useState } from "react";
import {
  fetchNotificationOutbox,
  fetchNotificationReadiness,
  NotificationOutboxItem,
  NotificationReadiness,
  sendTestNotification,
} from "../lib/notifications-api";

export function NotificationsPanel({ salonId }: { salonId: string }) {
  const [readiness, setReadiness] = useState<NotificationReadiness | null>(
    null,
  );
  const [outbox, setOutbox] = useState<NotificationOutboxItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [channel, setChannel] = useState<"email" | "sms">("email");
  const [templateCode, setTemplateCode] = useState("booking_confirmation");
  const [recipient, setRecipient] = useState("");
  const [sending, setSending] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  const channelId = useId();
  const templateId = useId();
  const recipientId = useId();

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [r, o] = await Promise.all([
        fetchNotificationReadiness(salonId),
        fetchNotificationOutbox(salonId, 10),
      ]);
      setReadiness(r);
      setOutbox(o);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [salonId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipient.trim()) return;
    setSending(true);
    setFeedback(null);
    setError(null);
    try {
      const item = await sendTestNotification(salonId, {
        channel,
        template_code: templateCode,
        recipient: recipient.trim(),
        variables: {
          business_name: "GORGONA Workspace",
          reference: `TEST-${Date.now().toString().slice(-6)}`,
          starts_at: "2026-12-01 10:00",
          role: "staff",
          amount: "$100.00",
        },
        idempotency_key: `ui-${channel}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      });
      setFeedback(
        `Dispatched (${item.status}) via ${item.provider_name} to ${item.recipient_masked}.`,
      );
      setRecipient("");
      await loadData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  };

  return (
    <section
      aria-labelledby="notifications-readiness-heading"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "16px",
        paddingTop: "12px",
        borderTop: "1px solid rgba(0,0,0,0.12)",
      }}
    >
      <div>
        <h3
          id="notifications-readiness-heading"
          style={{ margin: "0 0 6px", fontSize: "1.1rem" }}
        >
          Transactional Email &amp; SMS Notifications
        </h3>
        <p style={{ margin: 0, color: "#3f3832", fontSize: "0.9rem" }}>
          Channel readiness, sandbox verification, and masked delivery outbox
          (no raw recipient PII stored).
        </p>
      </div>

      {error && (
        <div role="alert" className="mgmt-error-banner">
          {error}
        </div>
      )}
      {feedback && (
        <div
          role="status"
          style={{
            padding: "10px 12px",
            borderRadius: "6px",
            background: "#eef6ee",
            color: "#1b4d1b",
            border: "1px solid #b8d8b8",
            fontSize: "0.9rem",
          }}
        >
          {feedback}
        </div>
      )}

      {loading && !readiness ? (
        <p style={{ color: "#3f3832" }}>Loading notification readiness...</p>
      ) : (
        readiness && (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                gap: "12px",
              }}
            >
              {(["email", "sms"] as const).map((ch) => {
                const info = readiness.channels[ch];
                return (
                  <div key={ch} className="mgmt-kpi-card">
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "8px",
                      }}
                    >
                      <span className="mgmt-kpi-label">
                        {ch === "email" ? "Email Channel" : "SMS Channel"}
                      </span>
                      <span
                        className={`mgmt-status-pill ${
                          info.mode === "live"
                            ? "status-confirmed"
                            : "status-draft"
                        }`}
                      >
                        {info.mode}
                      </span>
                    </div>
                    <p
                      style={{
                        margin: "8px 0 4px",
                        fontSize: "0.9rem",
                        color: "#2b241f",
                      }}
                    >
                      Provider: <code>{info.provider}</code>
                    </p>
                    {info.missing_production_env_vars.length > 0 && (
                      <p
                        style={{
                          margin: 0,
                          fontSize: "0.82rem",
                          color: "#3f3832",
                        }}
                      >
                        Production env vars required:{" "}
                        <code>
                          {info.missing_production_env_vars.join(", ")}
                        </code>
                      </p>
                    )}
                  </div>
                );
              })}
            </div>

            <form
              onSubmit={(e) => void handleSend(e)}
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: "12px",
                alignItems: "flex-end",
                padding: "12px",
                background: "var(--ivory)",
                borderRadius: "6px",
              }}
            >
              <label
                htmlFor={channelId}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "4px",
                  fontSize: "0.85rem",
                  color: "#2b241f",
                }}
              >
                Channel
                <select
                  id={channelId}
                  value={channel}
                  onChange={(e) =>
                    setChannel(e.target.value as "email" | "sms")
                  }
                >
                  <option value="email">Email</option>
                  <option value="sms">SMS (E.164)</option>
                </select>
              </label>

              <label
                htmlFor={templateId}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "4px",
                  fontSize: "0.85rem",
                  color: "#2b241f",
                }}
              >
                Template
                <select
                  id={templateId}
                  value={templateCode}
                  onChange={(e) => setTemplateCode(e.target.value)}
                >
                  {readiness.templates.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>

              <label
                htmlFor={recipientId}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "4px",
                  fontSize: "0.85rem",
                  color: "#2b241f",
                  flex: "1 1 200px",
                }}
              >
                Recipient
                <input
                  id={recipientId}
                  type="text"
                  value={recipient}
                  onChange={(e) => setRecipient(e.target.value)}
                  placeholder={
                    channel === "email" ? "owner@example.com" : "+14155550199"
                  }
                  required
                />
              </label>

              <button type="submit" disabled={sending}>
                {sending ? "Sending..." : "Send test notification"}
              </button>
            </form>

            <div className="mgmt-table-container" tabIndex={0}>
              <table className="mgmt-table">
                <thead>
                  <tr>
                    <th scope="col">Channel</th>
                    <th scope="col">Template</th>
                    <th scope="col">Recipient (masked)</th>
                    <th scope="col">Status</th>
                    <th scope="col">Provider</th>
                    <th scope="col">Attempts</th>
                  </tr>
                </thead>
                <tbody>
                  {outbox.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        style={{ textAlign: "center", color: "#3f3832" }}
                      >
                        No notifications sent yet.
                      </td>
                    </tr>
                  ) : (
                    outbox.map((item) => (
                      <tr key={item.id}>
                        <td>{item.channel}</td>
                        <td>
                          <code>{item.template_code}</code>
                        </td>
                        <td>
                          <code>{item.recipient_masked}</code>
                        </td>
                        <td>
                          <span
                            className={`mgmt-status-pill ${
                              item.status === "sent"
                                ? "status-confirmed"
                                : "status-draft"
                            }`}
                          >
                            {item.status}
                          </span>
                        </td>
                        <td>{item.provider_name || "pending"}</td>
                        <td>
                          {item.attempt_count}/{item.max_attempts}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )
      )}
    </section>
  );
}