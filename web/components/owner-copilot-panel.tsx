"use client";

import Link from "next/link";
import React, { useId, useState } from "react";
import { askOwnerCopilot, type OwnerCopilotResponse } from "../lib/growth-api";

const QUICK_PROMPTS = [
  "Give me an executive brief and top 3 priorities for this week.",
  "How can I recover waitlist and open Stripe checkout revenue?",
  "Audit my pricing, services, and 0% commission savings vs legacy platforms.",
  "Draft a concise, high-converting win-back email for past clients.",
] as const;

export function OwnerCopilotPanel({ salonId }: { salonId: string }) {
  const [data, setData] = useState<OwnerCopilotResponse | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const qId = useId();

  async function runCopilot(promptText?: string) {
    setAsking(true);
    setError(null);
    try {
      const res = await askOwnerCopilot(
        salonId,
        (promptText ?? question).trim() || undefined,
      );
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAsking(false);
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    await runCopilot();
  }

  return (
    <section
      aria-labelledby="owner-copilot-heading"
      className="mgmt-kpi-card"
      style={{
        marginTop: "24px",
        marginBottom: "24px",
        padding: "20px",
        display: "grid",
        gap: "14px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <div>
          <h3
            id="owner-copilot-heading"
            style={{ margin: 0, fontSize: "1.1rem" }}
          >
            AMARKAL AI Business Copilot
          </h3>
          <p
            style={{ margin: "4px 0 0", color: "#3f3832", fontSize: "0.88rem" }}
          >
            Governed AI grounded strictly in your live PostgreSQL 18 bookings,
            Stripe US payments, waitlist demand, and App Hub connectors.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          {data ? (
            <span className="mgmt-status-pill status-confirmed">
              {data.engine === "cloudflare"
                ? "Cloudflare Llama 3.3 70B"
                : data.engine === "gemini"
                  ? "Gemini Live"
                  : "Grounded Live"}
            </span>
          ) : (
            <button
              type="button"
              className="secondary usr-small-btn"
              disabled={asking}
              onClick={() => void runCopilot(QUICK_PROMPTS[0])}
            >
              {asking ? "Analyzing…" : "Run Executive Brief"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div role="alert" className="mgmt-error-banner">
          {error}
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
        {QUICK_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="secondary usr-small-btn"
            disabled={asking}
            onClick={() => {
              setQuestion(prompt);
              void runCopilot(prompt);
            }}
            style={{ fontSize: "0.82rem", minHeight: "36px" }}
          >
            {prompt}
          </button>
        ))}
      </div>

      {data && (
        <>
          <p
            role="status"
            style={{
              margin: 0,
              padding: "12px 14px",
              borderRadius: "6px",
              background: "var(--ivory)",
              color: "#1f1a17",
              fontSize: "0.93rem",
              lineHeight: 1.55,
              whiteSpace: "pre-wrap",
            }}
          >
            {data.reply}
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "10px",
            }}
          >
            {data.insights.map((ins) => (
              <div
                key={`${ins.category}:${ins.title}`}
                style={{
                  padding: "12px",
                  borderRadius: "6px",
                  border: "1px solid var(--line)",
                  background: "#ffffff",
                  display: "grid",
                  gap: "6px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: "8px",
                    alignItems: "center",
                  }}
                >
                  <strong style={{ fontSize: "0.9rem", color: "#1f1a17" }}>
                    {ins.title}
                  </strong>
                  <span className="mgmt-status-pill status-draft">
                    {ins.priority}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: "0.84rem", color: "#3f3832" }}>
                  {ins.detail}
                </p>
                <Link
                  href={ins.action_path}
                  className="legal-inline-link"
                  style={{ fontSize: "0.84rem", width: "fit-content" }}
                >
                  Review &amp; act →
                </Link>
              </div>
            ))}
          </div>
        </>
      )}

      <form
        onSubmit={(e) => void handleAsk(e)}
        style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}
      >
        <label htmlFor={qId} className="skip">
          Ask AI Business Copilot
        </label>
        <input
          id={qId}
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about your live business (EN / RU / ES)…"
          maxLength={500}
          style={{ flex: "1 1 240px" }}
        />
        <button type="submit" className="secondary" disabled={asking}>
          {asking ? "Analyzing..." : "Ask Copilot"}
        </button>
      </form>
    </section>
  );
}
