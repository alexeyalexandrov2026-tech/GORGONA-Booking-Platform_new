"use client";

import Link from "next/link";
import React, { useEffect, useId, useState } from "react";
import { askOwnerCopilot, type OwnerCopilotResponse } from "../lib/growth-api";

export function OwnerCopilotPanel({ salonId }: { salonId: string }) {
  const [data, setData] = useState<OwnerCopilotResponse | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const qId = useId();

  useEffect(() => {
    let active = true;
    askOwnerCopilot(salonId)
      .then((res) => {
        if (!active) return;
        setData(res);
        setError(null);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [salonId]);

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    setAsking(true);
    setError(null);
    try {
      const res = await askOwnerCopilot(salonId, question.trim() || undefined);
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAsking(false);
    }
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
            GORGONA AI Business Copilot
          </h3>
          <p
            style={{ margin: "4px 0 0", color: "#3f3832", fontSize: "0.88rem" }}
          >
            Read-only live insights grounded in your PostgreSQL bookings,
            waitlist demand, and growth configuration.
          </p>
        </div>
        {data && (
          <span className="mgmt-status-pill status-confirmed">
            {data.engine === "cloudflare"
              ? "Cloudflare Workers AI"
              : data.engine === "gemini"
                ? "Gemini Live"
                : "Grounded Live"}
          </span>
        )}
      </div>

      {error && (
        <div role="alert" className="mgmt-error-banner">
          {error}
        </div>
      )}

      {loading && !data ? (
        <p style={{ margin: 0, color: "#3f3832" }}>
          Analyzing live business metrics...
        </p>
      ) : (
        data && (
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
                lineHeight: 1.5,
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
                  <p
                    style={{ margin: 0, fontSize: "0.84rem", color: "#3f3832" }}
                  >
                    {ins.detail}
                  </p>
                  <Link
                    href={ins.action_path}
                    style={{ fontSize: "0.84rem", fontWeight: 600 }}
                  >
                    Open workspace →
                  </Link>
                </div>
              ))}
            </div>

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
                placeholder="Ask Copilot (e.g. How much waitlist revenue can we recover?)"
                maxLength={500}
                style={{ flex: "1 1 240px" }}
              />
              <button type="submit" className="secondary" disabled={asking}>
                {asking ? "Analyzing..." : "Ask Copilot"}
              </button>
            </form>
          </>
        )
      )}
    </section>
  );
}
