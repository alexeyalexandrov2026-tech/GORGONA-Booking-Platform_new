"use client";

import Link from "next/link";
import React, { useId, useState } from "react";
import {
  askOwnerCopilot,
  executeCopilotAction,
  type ActionProposal,
  type ExecuteCopilotActionResult,
  type OwnerCopilotResponse,
} from "../lib/growth-api";

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
  const [pendingActionId, setPendingActionId] = useState<string | null>(null);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [actionOutcome, setActionOutcome] =
    useState<ExecuteCopilotActionResult | null>(null);
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

  async function handleApproveAction(proposal: ActionProposal) {
    setExecutingId(proposal.id);
    setPendingActionId(null);
    setError(null);
    setActionOutcome(null);
    try {
      const outcome = await executeCopilotAction(
        salonId,
        proposal.kind,
        proposal.params,
      );
      setActionOutcome(outcome);
      if (
        outcome.kind === "export_business_snapshot" &&
        outcome.result.snapshot
      ) {
        const blob = new Blob(
          [JSON.stringify(outcome.result.snapshot, null, 2)],
          { type: "application/json;charset=utf-8" },
        );
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "amarkal-business-snapshot.json";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setExecutingId(null);
    }
  }

  const checkoutUrl =
    typeof actionOutcome?.result.checkout_url === "string"
      ? actionOutcome.result.checkout_url
      : null;
  const secretToken =
    typeof actionOutcome?.result.secret_token === "string"
      ? actionOutcome.result.secret_token
      : null;

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
            AMARKAL AI Command Copilot
          </h3>
          <p
            style={{ margin: "4px 0 0", color: "#3f3832", fontSize: "0.88rem" }}
          >
            Governed AI grounded strictly in live PostgreSQL 18 bookings, Stripe
            US payments, waitlist demand, and App Hub — with human-approved
            action execution.
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

      {actionOutcome && (
        <div
          role="status"
          className="hold-note"
          style={{ margin: 0, display: "grid", gap: "8px" }}
        >
          <strong>Approved action completed:</strong> {actionOutcome.summary}
          {checkoutUrl && (
            <div>
              <a
                href={checkoutUrl}
                target="_blank"
                rel="noreferrer"
                className="button secondary usr-small-btn"
              >
                Open Stripe Checkout Link →
              </a>
            </div>
          )}
          {secretToken && (
            <div style={{ display: "grid", gap: "4px" }}>
              <small>
                One-time Native MCP API Key (store securely now; shown once):
              </small>
              <code
                style={{
                  padding: "8px 10px",
                  background: "#fff",
                  border: "1px solid var(--line)",
                  borderRadius: "4px",
                  wordBreak: "break-all",
                }}
              >
                {secretToken}
              </code>
            </div>
          )}
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
              padding: "14px 16px",
              borderRadius: "12px",
              background: "#f4f5f8",
              border: "1px solid var(--line)",
              color: "var(--ink)",
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
                  padding: "14px",
                  borderRadius: "12px",
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
                  <strong style={{ fontSize: "0.9rem", color: "var(--ink)" }}>
                    {ins.title}
                  </strong>
                  <span className="mgmt-status-pill status-draft">
                    {ins.priority}
                  </span>
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: "0.84rem",
                    color: "var(--muted)",
                  }}
                >
                  {ins.detail}
                </p>
                <Link
                  href={ins.action_path}
                  className="legal-inline-link"
                  style={{ fontSize: "0.84rem", width: "fit-content" }}
                >
                  Open workspace →
                </Link>
              </div>
            ))}
          </div>

          {data.action_proposals.length > 0 && (
            <div style={{ display: "grid", gap: "10px", marginTop: "4px" }}>
              <strong style={{ fontSize: "0.92rem", color: "var(--ink)" }}>
                Governed Action Proposals (Human Approval Required)
              </strong>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                  gap: "10px",
                }}
              >
                {data.action_proposals.map((prop) => (
                  <div
                    key={prop.id}
                    style={{
                      padding: "14px",
                      borderRadius: "12px",
                      border: "1px solid var(--line)",
                      background: "#f4f5f8",
                      display: "grid",
                      gap: "8px",
                    }}
                  >
                    <strong
                      style={{ fontSize: "0.88rem", color: "var(--ink)" }}
                    >
                      {prop.title}
                    </strong>
                    <p
                      style={{
                        margin: 0,
                        fontSize: "0.82rem",
                        color: "var(--muted)",
                      }}
                    >
                      {prop.description}
                    </p>
                    <small
                      style={{ color: "var(--muted)", fontSize: "0.78rem" }}
                    >
                      {prop.impact_summary}
                    </small>
                    <div
                      style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}
                    >
                      {pendingActionId === prop.id ? (
                        <>
                          <button
                            type="button"
                            className="usr-small-btn"
                            disabled={executingId !== null}
                            onClick={() => void handleApproveAction(prop)}
                          >
                            {executingId === prop.id
                              ? "Executing…"
                              : "Confirm & Execute"}
                          </button>
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            disabled={executingId !== null}
                            onClick={() => setPendingActionId(null)}
                          >
                            Cancel
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="secondary usr-small-btn"
                          disabled={executingId !== null}
                          onClick={() => setPendingActionId(prop.id)}
                        >
                          Review &amp; Approve
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      <form
        onSubmit={(e) => void handleAsk(e)}
        style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}
      >
        <label htmlFor={qId} className="skip">
          Ask AI Command Copilot
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
