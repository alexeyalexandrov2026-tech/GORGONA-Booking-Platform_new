"use client";

import Link from "next/link";
import React, { useEffect, useState } from "react";
import {
  downloadBusinessSnapshot,
  fetchLaunchReadiness,
  type LaunchReadiness,
} from "../lib/growth-api";

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
}

/** Live Go-Live Launchpad + Zero-Lock-In Portable Business Export card on /overview/. */
export function BusinessLaunchpadCard({ businessId }: { businessId: string }) {
  const [data, setData] = useState<LaunchReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportNote, setExportNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchLaunchReadiness(businessId)
      .then((res) => {
        if (!active) return;
        setData(res);
        setError(null);
      })
      .catch(() => {
        if (!active) return;
        setData(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  async function handleExport() {
    if (!data) return;
    setExporting(true);
    setError(null);
    setExportNote(null);
    try {
      await downloadBusinessSnapshot(businessId, data.slug);
      setExportNote(
        "Portable business JSON exported. Zero vendor lock-in — your data stays 100% yours.",
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not export business data.",
      );
    } finally {
      setExporting(false);
    }
  }

  if (loading || !data) return null;

  return (
    <section
      aria-labelledby="business-launchpad-heading"
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
          gap: "10px",
        }}
      >
        <div>
          <h3
            id="business-launchpad-heading"
            style={{ margin: 0, fontSize: "1.1rem" }}
          >
            Go-Live Launchpad &amp; Data Portability
          </h3>
          <p
            style={{
              margin: "4px 0 0",
              color: "var(--muted)",
              fontSize: "0.88rem",
            }}
          >
            <strong>{data.score_percent}% ready</strong> ({data.completed_steps}
            /{data.total_steps} operational milestones) &bull; 0% platform
            commission
            {data.commission_saved_vs_5pct_cents > 0
              ? ` · Est. ${formatUsd(data.commission_saved_vs_5pct_cents)} saved vs 5% take-rate platforms (30d)`
              : ""}
          </p>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
          <span
            className={`mgmt-status-pill ${data.stripe_live_ready ? "status-confirmed" : "status-draft"}`}
          >
            {data.stripe_live_ready ? "Stripe US Live" : "0% Commission Core"}
          </span>
          <button
            type="button"
            className="secondary usr-small-btn"
            disabled={exporting}
            onClick={() => void handleExport()}
          >
            {exporting ? "Exporting…" : "Export Business JSON"}
          </button>
        </div>
      </div>

      <div
        role="progressbar"
        aria-label="Go-Live readiness progress"
        aria-valuenow={data.score_percent}
        aria-valuemin={0}
        aria-valuemax={100}
        style={{
          height: "8px",
          width: "100%",
          borderRadius: "999px",
          background: "#e6e8ee",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${data.score_percent}%`,
            background: "#111318",
            borderRadius: "999px",
            transition: "width 0.25s ease",
          }}
        />
      </div>

      {exportNote && (
        <p role="status" className="hold-note" style={{ margin: 0 }}>
          {exportNote}
        </p>
      )}
      {error && (
        <div role="alert" className="mgmt-error-banner" style={{ margin: 0 }}>
          {error}
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
          gap: "10px",
        }}
      >
        {data.steps.map((step) => (
          <div
            key={step.key}
            style={{
              padding: "14px",
              borderRadius: "12px",
              border: "1px solid var(--line)",
              background: step.completed ? "#f6fbf8" : "#ffffff",
              display: "grid",
              gap: "6px",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <strong style={{ fontSize: "0.88rem", color: "var(--ink)" }}>
                {step.completed ? "✓ " : "○ "}
                {step.title}
              </strong>
              <span
                className={`mgmt-status-pill ${step.completed ? "status-confirmed" : "status-draft"}`}
              >
                {step.completed ? "Ready" : "Action"}
              </span>
            </div>
            <p
              style={{ margin: 0, fontSize: "0.82rem", color: "var(--muted)" }}
            >
              {step.detail}
            </p>
            <Link
              href={step.action_path}
              className="legal-inline-link"
              style={{ fontSize: "0.82rem", width: "fit-content" }}
            >
              {step.action_label} →
            </Link>
          </div>
        ))}
      </div>
    </section>
  );
}
