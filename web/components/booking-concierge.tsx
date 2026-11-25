"use client";

import React, { useId, useState } from "react";
import { appointmentTime, money } from "../lib/api";
import {
  askCustomerConcierge,
  type CustomerConciergeResponse,
  type RecommendedSlot,
} from "../lib/growth-api";

export function BookingConcierge({
  locationId,
  onPickSlot,
}: {
  locationId: string;
  onPickSlot: (slot: RecommendedSlot) => void;
}) {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CustomerConciergeResponse | null>(null);
  const inputId = useId();

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    const clean = message.trim();
    if (clean.length < 2) return;
    setLoading(true);
    setError(null);
    try {
      const data = await askCustomerConcierge({
        message: clean,
        location_id: locationId,
      });
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <details
      className="policy"
      style={{
        marginBottom: "20px",
        padding: "14px 16px",
        borderRadius: "8px",
        border: "1px solid var(--line)",
        background: "var(--ivory)",
      }}
    >
      <summary style={{ cursor: "pointer", fontWeight: 600, color: "#1f1a17" }}>
        AI Booking Concierge — ask in plain language (EN / RU / ES)
      </summary>
      <div style={{ marginTop: "12px", display: "grid", gap: "12px" }}>
        <p style={{ margin: 0, fontSize: "0.88rem", color: "#3f3832" }}>
          Ask for open times, budget options, or preferred specialists. Every
          suggested slot is checked live against real availability.
        </p>
        <form
          onSubmit={(e) => void handleAsk(e)}
          style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}
        >
          <label htmlFor={inputId} className="skip">
            Ask AI Booking Concierge
          </label>
          <input
            id={inputId}
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="e.g. Anything open tomorrow afternoon under $60?"
            minLength={2}
            maxLength={500}
            style={{ flex: "1 1 220px" }}
            required
          />
          <button type="submit" disabled={loading}>
            {loading ? "Checking live slots..." : "Find slots"}
          </button>
        </form>

        {error && (
          <p role="alert" className="error" style={{ margin: 0 }}>
            {error}
          </p>
        )}

        {result && (
          <div style={{ display: "grid", gap: "10px" }}>
            <p
              role="status"
              style={{
                margin: 0,
                padding: "10px 12px",
                borderRadius: "6px",
                background: "#ffffff",
                border: "1px solid var(--line)",
                color: "#1f1a17",
                fontSize: "0.92rem",
              }}
            >
              {result.reply}
            </p>
            {result.recommended_slots.length > 0 && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: "8px",
                }}
              >
                {result.recommended_slots.map((s) => (
                  <button
                    key={`${s.variant_id}:${s.resource_id}:${s.start_at}`}
                    type="button"
                    className="secondary"
                    style={{
                      textAlign: "left",
                      display: "grid",
                      gap: "2px",
                      padding: "10px 12px",
                    }}
                    onClick={() => onPickSlot(s)}
                  >
                    <strong>
                      {s.day} · {appointmentTime(s.start_at, s.timezone)}
                    </strong>
                    <span>
                      {s.service_name} ({s.variant_name})
                    </span>
                    <small>
                      {s.resource_name} · {money(s.price_cents, s.currency)} ·{" "}
                      {s.duration_minutes} min
                    </small>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </details>
  );
}
