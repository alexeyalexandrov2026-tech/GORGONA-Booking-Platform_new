"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  BiDashboardResponse,
  BiPeriodDays,
  buildBoardPackCsv,
  computeGanttBounds,
  fetchBiDashboard,
  GanttSourceKind,
} from "../lib/analytics-bi-api";
import { triggerCsvDownload } from "../lib/csv-export";
import { ManagementApiError } from "../lib/management-api";

type WidgetKey = "kpis" | "cashflow" | "funnel" | "gantt" | "fx";

const ALL_WIDGETS: readonly { key: WidgetKey; label: string }[] = [
  { key: "kpis", label: "KPI Strip" },
  { key: "cashflow", label: "Cashflow & P&L" },
  { key: "funnel", label: "CPQ Sales Funnel" },
  { key: "gantt", label: "Executive Gantt" },
  { key: "fx", label: "FX Exposure" },
];

const DEFAULT_WIDGETS: Record<WidgetKey, boolean> = {
  kpis: true,
  cashflow: true,
  funnel: true,
  gantt: true,
  fx: true,
};

const PERIOD_OPTIONS: readonly { days: BiPeriodDays; label: string }[] = [
  { days: 30, label: "30 Days" },
  { days: 90, label: "90 Days" },
  { days: 180, label: "180 Days" },
  { days: 365, label: "12 Months" },
];

function formatUsd(cents: number): string {
  const neg = cents < 0;
  const abs = Math.abs(cents) / 100;
  const formatted = abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${neg ? "-$" : "$"}${formatted}`;
}

function formatCompactUsd(cents: number): string {
  const abs = Math.abs(cents) / 100;
  const prefix = cents < 0 ? "-$" : "$";
  if (abs >= 1_000_000) {
    return `${prefix}${(abs / 1_000_000).toFixed(1)}M`;
  }
  if (abs >= 1_000) {
    return `${prefix}${(abs / 1_000).toFixed(1)}k`;
  }
  return `${prefix}${abs.toFixed(0)}`;
}

function sourceLabel(source: GanttSourceKind): string {
  if (source === "mrp_run") return "MRP II";
  if (source === "eam_wo") return "EAM IoT";
  return "Kanban";
}

function sourceColor(source: GanttSourceKind): string {
  if (source === "mrp_run") return "#1f4e79";
  if (source === "eam_wo") return "#8a4b08";
  return "#165430";
}

function readSavedWidgets(storageKey: string): Record<WidgetKey, boolean> {
  if (typeof window === "undefined") {
    return DEFAULT_WIDGETS;
  }
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return DEFAULT_WIDGETS;
    const parsed = JSON.parse(raw) as Partial<Record<WidgetKey, boolean>>;
    return {
      kpis: parsed.kpis ?? true,
      cashflow: parsed.cashflow ?? true,
      funnel: parsed.funnel ?? true,
      gantt: parsed.gantt ?? true,
      fx: parsed.fx ?? true,
    };
  } catch {
    return DEFAULT_WIDGETS;
  }
}

export function AnalyticsBiHub({ businessId }: { businessId: string }) {
  const storageKey = `amarkal_bi_widgets_${businessId}`;
  const [periodDays, setPeriodDays] = useState<BiPeriodDays>(90);
  const [data, setData] = useState<BiDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [ganttFilter, setGanttFilter] = useState<"all" | GanttSourceKind>(
    "all",
  );
  const [widgets, setWidgets] = useState<Record<WidgetKey, boolean>>(() =>
    readSavedWidgets(storageKey),
  );

  const toggleWidget = (key: WidgetKey) => {
    setWidgets((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        // Ignore storage quota errors in private mode.
      }
      return next;
    });
  };

  const resetWidgets = () => {
    setWidgets(DEFAULT_WIDGETS);
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(DEFAULT_WIDGETS));
    } catch {
      // Ignore storage quota errors in private mode.
    }
  };

  const handleSelectPeriod = (days: BiPeriodDays) => {
    setPeriodDays(days);
    setLoading(true);
    setError(null);
  };

  useEffect(() => {
    let active = true;
    fetchBiDashboard(businessId, periodDays)
      .then((res) => {
        if (!active) return;
        setData(res);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof ManagementApiError
            ? err.message
            : "Unable to load Executive BI data.",
        );
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, periodDays]);

  const filteredGantt = useMemo(() => {
    if (!data) return [];
    if (ganttFilter === "all") return data.gantt_items;
    return data.gantt_items.filter((item) => item.source === ganttFilter);
  }, [data, ganttFilter]);

  const ganttBounds = useMemo(
    () => computeGanttBounds(filteredGantt),
    [filteredGantt],
  );

  const handleExportBoardPack = () => {
    if (!data) return;
    const csv = buildBoardPackCsv(data);
    triggerCsvDownload(
      `amarkal-executive-bi-board-pack-${data.period_end}.csv`,
      csv,
    );
    setNotice("Board Pack CSV downloaded for executive reporting.");
  };

  const handlePrintPdf = () => {
    if (typeof window !== "undefined") {
      window.print();
    }
  };

  const isCompletelyEmpty =
    data !== null &&
    data.kpis.total_inflow_cents === 0 &&
    data.kpis.total_outflow_cents === 0 &&
    data.sales_funnel.every((s) => s.count === 0) &&
    data.gantt_items.length === 0 &&
    data.fx_exposure.length === 0;

  // Cashflow SVG geometry
  const maxBarCents = useMemo(() => {
    if (!data || data.monthly_cashflow.length === 0) return 100;
    const peak = Math.max(
      ...data.monthly_cashflow.flatMap((p) => [
        p.inflow_cents,
        p.outflow_cents,
      ]),
      100,
    );
    return peak;
  }, [data]);

  return (
    <div className="usr-stack">
      <section className="usr-card">
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "16px",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div className="usr-inline" style={{ marginBottom: "8px" }}>
              <span className="usr-badge usr-badge-ai">
                LIVE PG18 FORCE RLS BI ENGINE
              </span>
              <span className="usr-badge">0% PLATFORM FEE</span>
              {data ? (
                <span className="usr-badge">
                  {data.period_start} → {data.period_end}
                </span>
              ) : null}
            </div>
            <h1 style={{ margin: "0 0 6px", fontSize: "1.65rem" }}>
              Executive BI &amp; Visual Analytics
            </h1>
            <p className="usr-muted" style={{ margin: 0 }}>
              Live financial cashflow, B2B CPQ sales funnel, cross-module Gantt
              schedule (MRP II, Predictive EAM, Kanban), and multi-currency FX
              exposure — aggregated directly from your double-entry workspace.
            </p>
          </div>

          <div className="usr-inline">
            <button
              type="button"
              className="button usr-small-btn"
              onClick={handleExportBoardPack}
              disabled={!data || loading}
            >
              Export Board Pack CSV
            </button>
            <button
              type="button"
              className="button secondary usr-small-btn"
              onClick={handlePrintPdf}
              disabled={!data || loading}
            >
              Print / Save PDF
            </button>
          </div>
        </div>

        <div
          style={{
            marginTop: "18px",
            paddingTop: "16px",
            borderTop: "1px solid var(--line)",
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "12px",
          }}
        >
          <div
            className="usr-inline"
            role="group"
            aria-label="Reporting window"
          >
            <span className="usr-muted" style={{ fontWeight: 600 }}>
              Window:
            </span>
            {PERIOD_OPTIONS.map((opt) => (
              <button
                key={opt.days}
                type="button"
                aria-pressed={periodDays === opt.days}
                className="usr-tab"
                style={
                  periodDays === opt.days
                    ? {
                        background: "#111318",
                        color: "#ffffff",
                        borderColor: "#111318",
                      }
                    : undefined
                }
                onClick={() => handleSelectPeriod(opt.days)}
              >
                {opt.label}
              </button>
            ))}
          </div>

          <div
            className="usr-inline"
            role="group"
            aria-label="Customize dashboard widgets"
          >
            <span className="usr-muted" style={{ fontWeight: 600 }}>
              Widgets:
            </span>
            {ALL_WIDGETS.map((w) => (
              <button
                key={w.key}
                type="button"
                aria-pressed={widgets[w.key]}
                className="usr-small-btn"
                style={{
                  borderRadius: "999px",
                  border: "1px solid var(--line)",
                  background: widgets[w.key] ? "#e9f6ee" : "#f4f5f8",
                  color: widgets[w.key] ? "#165430" : "#464b59",
                  cursor: "pointer",
                  fontWeight: 600,
                }}
                onClick={() => toggleWidget(w.key)}
              >
                {widgets[w.key] ? "✓ " : "+ "}
                {w.label}
              </button>
            ))}
            <button
              type="button"
              className="usr-small-btn"
              style={{
                borderRadius: "999px",
                border: "1px solid var(--line)",
                background: "#ffffff",
                color: "#111318",
                cursor: "pointer",
              }}
              onClick={resetWidgets}
            >
              Reset layout
            </button>
          </div>
        </div>
      </section>

      {error ? (
        <div className="usr-errors" role="alert">
          <strong>BI aggregation error:</strong> {error}
        </div>
      ) : null}

      {notice ? (
        <div
          className="usr-card"
          role="status"
          style={{
            padding: "14px 20px",
            background: "#e9f6ee",
            borderColor: "#a9dbb9",
            color: "#165430",
          }}
        >
          {notice}
        </div>
      ) : null}

      {loading && !data ? (
        <section className="usr-card">
          <p className="usr-muted" style={{ margin: 0 }}>
            Aggregating real-time executive analytics across finance, CPQ, MRP
            II, EAM, Kanban, and FX...
          </p>
        </section>
      ) : null}

      {isCompletelyEmpty ? (
        <section className="usr-card">
          <h2 style={{ marginBottom: "8px" }}>
            Your BI canvas is ready for live business data
          </h2>
          <p className="usr-muted" style={{ marginTop: 0 }}>
            No financial transactions, commercial quotes, or production runs
            were recorded in the selected {periodDays}-day window yet. Populate
            an instant executive demo dataset or import your QuickBooks / Zoho /
            Odoo CSV files in 1 click.
          </p>
          <div className="usr-inline">
            <Link href="/migrate/" className="button usr-small-btn">
              Load 1-Click Sample [DEMO] Data →
            </Link>
            <Link
              href="/commercial/"
              className="button secondary usr-small-btn"
            >
              Create First B2B Quote
            </Link>
          </div>
        </section>
      ) : null}

      {data && widgets.kpis ? (
        <section aria-label="Executive KPI summary">
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(280px, 100%), 1fr))",
              gap: "16px",
            }}
          >
            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Gross Inflow ({periodDays}d)</span>
              <div
                style={{
                  fontSize: "1.6rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#165430",
                }}
              >
                {formatUsd(data.kpis.total_inflow_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Net: {formatUsd(data.kpis.net_cashflow_cents)} (
                {data.kpis.gross_margin_pct.toFixed(1)}% margin)
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Operating Outflow</span>
              <div
                style={{
                  fontSize: "1.6rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#8a1c19",
                }}
              >
                {formatUsd(data.kpis.total_outflow_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                AP Bills + Purchase Orders + US Payroll
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">B2B Quote Pipeline</span>
              <div
                style={{
                  fontSize: "1.6rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#111318",
                }}
              >
                {formatUsd(data.kpis.quote_pipeline_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Win Rate: {data.kpis.quote_win_rate_pct.toFixed(1)}% across
                active deals
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">0% Commission Savings</span>
              <div
                style={{
                  fontSize: "1.6rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#165430",
                }}
              >
                {formatUsd(data.kpis.commission_saved_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Retained vs 2.5% legacy SaaS fee
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Multi-Currency FX P&amp;L</span>
              <div
                style={{
                  fontSize: "1.6rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color:
                    data.kpis.fx_net_gain_loss_cents >= 0
                      ? "#165430"
                      : "#8a1c19",
                }}
              >
                {formatUsd(data.kpis.fx_net_gain_loss_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Unrealized + realized across {data.fx_exposure.length} FX
                currencies
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Operations &amp; Fleet Health</span>
              <div
                style={{
                  fontSize: "1.6rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#111318",
                }}
              >
                {data.kpis.fleet_avg_health_score}%
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                {data.kpis.assets_at_risk_count} assets at risk ·{" "}
                {data.kpis.open_inbox_threads} open inbox threads (
                {data.kpis.unread_inbox_messages} unread)
              </div>
            </article>
          </div>
        </section>
      ) : null}

      {data && widgets.cashflow ? (
        <section className="usr-card" aria-labelledby="bi-cashflow-heading">
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "12px",
              marginBottom: "14px",
            }}
          >
            <div>
              <h2 id="bi-cashflow-heading" style={{ marginBottom: "4px" }}>
                Monthly Cashflow &amp; Operating Outflow
              </h2>
              <p className="usr-muted" style={{ margin: 0 }}>
                Double-entry receivables &amp; Stripe settlements compared
                against AP, procurement POs, and US payroll runs.
              </p>
            </div>
            <div className="usr-inline" style={{ fontSize: "0.85rem" }}>
              <span className="usr-badge usr-badge-ai">■ Inflow</span>
              <span
                className="usr-badge"
                style={{
                  background: "#fcf0ee",
                  borderColor: "#d99a91",
                  color: "#8a1c19",
                }}
              >
                ■ Outflow
              </span>
            </div>
          </div>

          <div
            style={{
              border: "1px solid var(--line)",
              borderRadius: "12px",
              padding: "16px",
              background: "#fafbfc",
              marginBottom: "18px",
            }}
          >
            <svg
              role="img"
              aria-label="Monthly Cashflow Inflow versus Outflow Bar Chart"
              viewBox="0 0 760 250"
              style={{ width: "100%", height: "auto", display: "block" }}
            >
              {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
                const y = 205 - frac * 175;
                const tickVal = Math.round(maxBarCents * frac);
                return (
                  <g key={frac}>
                    <line
                      x1="68"
                      y1={y}
                      x2="740"
                      y2={y}
                      stroke="#dfe3ec"
                      strokeWidth="1"
                    />
                    <text
                      x="60"
                      y={y + 4}
                      textAnchor="end"
                      fontSize="11"
                      fill="#464b59"
                    >
                      {formatCompactUsd(tickVal)}
                    </text>
                  </g>
                );
              })}

              {data.monthly_cashflow.map((pt, idx) => {
                const count = Math.max(1, data.monthly_cashflow.length);
                const slotWidth = 660 / count;
                const groupX = 74 + idx * slotWidth;
                const barWidth = Math.max(
                  10,
                  Math.min(28, (slotWidth - 16) / 2),
                );
                const centerOffset = (slotWidth - barWidth * 2 - 6) / 2;
                const inflowH = Math.max(
                  pt.inflow_cents > 0 ? 4 : 0,
                  (pt.inflow_cents / maxBarCents) * 175,
                );
                const outflowH = Math.max(
                  pt.outflow_cents > 0 ? 4 : 0,
                  (pt.outflow_cents / maxBarCents) * 175,
                );

                return (
                  <g key={pt.month_key}>
                    <rect
                      x={groupX + centerOffset}
                      y={205 - inflowH}
                      width={barWidth}
                      height={inflowH}
                      rx="4"
                      fill="#165430"
                    >
                      <title>
                        {pt.month_label} Inflow: {formatUsd(pt.inflow_cents)}
                      </title>
                    </rect>
                    <rect
                      x={groupX + centerOffset + barWidth + 6}
                      y={205 - outflowH}
                      width={barWidth}
                      height={outflowH}
                      rx="4"
                      fill="#8a1c19"
                    >
                      <title>
                        {pt.month_label} Outflow: {formatUsd(pt.outflow_cents)}
                      </title>
                    </rect>
                    <text
                      x={groupX + slotWidth / 2}
                      y="228"
                      textAnchor="middle"
                      fontSize="11"
                      fill="#2f3440"
                    >
                      {pt.month_label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          <div
            style={{ overflowX: "auto" }}
            tabIndex={0}
            role="region"
            aria-label="Monthly Cashflow breakdown table"
          >
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--line)",
                    textAlign: "left",
                  }}
                >
                  <th style={{ padding: "8px 10px" }}>Month</th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>
                    Inflow
                  </th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>
                    Outflow
                  </th>
                  <th style={{ padding: "8px 10px", textAlign: "right" }}>
                    Net Cashflow
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.monthly_cashflow.map((pt) => (
                  <tr
                    key={pt.month_key}
                    style={{ borderBottom: "1px solid var(--line)" }}
                  >
                    <td style={{ padding: "8px 10px", fontWeight: 600 }}>
                      {pt.month_label}
                    </td>
                    <td
                      style={{
                        padding: "8px 10px",
                        textAlign: "right",
                        color: "#165430",
                      }}
                    >
                      {formatUsd(pt.inflow_cents)}
                    </td>
                    <td
                      style={{
                        padding: "8px 10px",
                        textAlign: "right",
                        color: "#8a1c19",
                      }}
                    >
                      {formatUsd(pt.outflow_cents)}
                    </td>
                    <td
                      style={{
                        padding: "8px 10px",
                        textAlign: "right",
                        fontWeight: 600,
                        color: pt.net_cents >= 0 ? "#165430" : "#8a1c19",
                      }}
                    >
                      {formatUsd(pt.net_cents)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {data && widgets.funnel ? (
        <section className="usr-card" aria-labelledby="bi-funnel-heading">
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "12px",
              marginBottom: "14px",
            }}
          >
            <div>
              <h2 id="bi-funnel-heading" style={{ marginBottom: "4px" }}>
                Commercial CPQ Sales Funnel
              </h2>
              <p className="usr-muted" style={{ margin: 0 }}>
                Cumulative B2B quote conversion from draft through client
                acceptance and FIN-03 invoice issuance.
              </p>
            </div>
            <Link
              href="/commercial/"
              className="button secondary usr-small-btn"
            >
              Open Commercial &amp; PO →
            </Link>
          </div>

          <div
            style={{
              border: "1px solid var(--line)",
              borderRadius: "12px",
              padding: "16px",
              background: "#fafbfc",
            }}
          >
            <svg
              role="img"
              aria-label="Commercial CPQ Sales Funnel Chart"
              viewBox="0 0 760 196"
              style={{ width: "100%", height: "auto", display: "block" }}
            >
              {data.sales_funnel.map((stage, idx) => {
                const y = 12 + idx * 45;
                const fillColors = ["#111318", "#1f4e79", "#1e6b45", "#165430"];
                const barWidth = Math.max(
                  stage.count > 0 ? 18 : 6,
                  (stage.conversion_pct / 100) * 380,
                );
                return (
                  <g key={stage.stage_key}>
                    <text
                      x="6"
                      y={y + 21}
                      fontSize="12"
                      fontWeight="600"
                      fill="#111318"
                    >
                      {stage.label}
                    </text>
                    <rect
                      x="185"
                      y={y + 4}
                      width="380"
                      height="26"
                      rx="6"
                      fill="#e9ecf2"
                    />
                    <rect
                      x="185"
                      y={y + 4}
                      width={barWidth}
                      height="26"
                      rx="6"
                      fill={fillColors[idx % fillColors.length] ?? "#111318"}
                    >
                      <title>
                        {stage.label}: {stage.count} quotes (
                        {formatUsd(stage.value_cents)}) —{" "}
                        {stage.conversion_pct.toFixed(1)}%
                      </title>
                    </rect>
                    <text
                      x="578"
                      y={y + 21}
                      fontSize="12"
                      fontWeight="600"
                      fill="#111318"
                    >
                      {stage.count} · {formatCompactUsd(stage.value_cents)} (
                      {stage.conversion_pct.toFixed(1)}%)
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </section>
      ) : null}

      {data && widgets.gantt ? (
        <section className="usr-card" aria-labelledby="bi-gantt-heading">
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "12px",
              marginBottom: "14px",
            }}
          >
            <div>
              <h2 id="bi-gantt-heading" style={{ marginBottom: "4px" }}>
                Executive Gantt Timeline
              </h2>
              <p className="usr-muted" style={{ margin: 0 }}>
                Unified schedule across MRP II production runs, Predictive EAM
                maintenance work orders, and Kanban board deliverables.
              </p>
            </div>
            <div
              className="usr-inline"
              role="group"
              aria-label="Filter Gantt items by module"
            >
              {(
                [
                  { id: "all", label: "All Modules" },
                  { id: "mrp_run", label: "MRP II" },
                  { id: "eam_wo", label: "Predictive EAM" },
                  { id: "kanban_card", label: "Kanban" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  aria-pressed={ganttFilter === tab.id}
                  className="usr-small-btn"
                  style={{
                    borderRadius: "999px",
                    border: "1px solid var(--line)",
                    background: ganttFilter === tab.id ? "#111318" : "#f4f5f8",
                    color: ganttFilter === tab.id ? "#ffffff" : "#2f3440",
                    cursor: "pointer",
                  }}
                  onClick={() => setGanttFilter(tab.id)}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {filteredGantt.length === 0 ? (
            <p className="usr-muted" style={{ margin: 0 }}>
              No scheduled MRP II runs, EAM work orders, or Kanban tasks match
              this filter yet.
            </p>
          ) : (
            <div
              style={{ overflowX: "auto" }}
              tabIndex={0}
              role="region"
              aria-label="Executive Gantt timeline table"
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: "0.78rem",
                  color: "#464b59",
                  marginBottom: "8px",
                  minWidth: "640px",
                }}
              >
                <span>Timeline Start: {ganttBounds.minDate}</span>
                <span>Span: {ganttBounds.totalDays} days</span>
                <span>Timeline End: {ganttBounds.maxDate}</span>
              </div>

              <div
                style={{
                  display: "grid",
                  gap: "10px",
                  minWidth: "640px",
                }}
              >
                {filteredGantt.map((item) => {
                  const bar = ganttBounds.bars[item.id] ?? {
                    leftPct: 0,
                    widthPct: 25,
                  };
                  const color = sourceColor(item.source);
                  return (
                    <div
                      key={item.id}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "230px 1fr 78px",
                        alignItems: "center",
                        gap: "12px",
                        padding: "10px 12px",
                        border: "1px solid var(--line)",
                        borderRadius: "10px",
                        background: "#ffffff",
                      }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div
                          className="usr-inline"
                          style={{ gap: "6px", marginBottom: "2px" }}
                        >
                          <span
                            className="usr-badge"
                            style={{
                              background: color,
                              color: "#ffffff",
                              borderColor: color,
                            }}
                          >
                            {sourceLabel(item.source)}
                          </span>
                          <span
                            className="usr-muted"
                            style={{ fontSize: "0.76rem", fontWeight: 600 }}
                          >
                            {item.code}
                          </span>
                        </div>
                        <Link
                          href={item.module_href}
                          style={{
                            color: "#111318",
                            fontWeight: 600,
                            fontSize: "0.88rem",
                            textDecoration: "none",
                            display: "block",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={item.title}
                        >
                          {item.title}
                        </Link>
                        <div
                          className="usr-muted"
                          style={{ fontSize: "0.74rem" }}
                        >
                          {item.start_date} → {item.end_date} · {item.status}
                        </div>
                      </div>

                      <div
                        role="progressbar"
                        aria-valuenow={item.progress_pct}
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-label={`${item.title}: ${item.progress_pct}% complete from ${item.start_date} to ${item.end_date}`}
                        style={{
                          position: "relative",
                          height: "24px",
                          background: "#eef1f6",
                          borderRadius: "999px",
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            position: "absolute",
                            left: `${bar.leftPct}%`,
                            width: `${bar.widthPct}%`,
                            top: 0,
                            bottom: 0,
                            background: `${color}30`,
                            border: `1px solid ${color}`,
                            borderRadius: "999px",
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              width: `${item.progress_pct}%`,
                              height: "100%",
                              background: color,
                            }}
                          />
                        </div>
                      </div>

                      <div
                        style={{
                          textAlign: "right",
                          fontWeight: 700,
                          fontSize: "0.85rem",
                          color: "#111318",
                        }}
                      >
                        {item.progress_pct}%
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>
      ) : null}

      {data && widgets.fx ? (
        <section className="usr-card" aria-labelledby="bi-fx-heading">
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "12px",
              marginBottom: "14px",
            }}
          >
            <div>
              <h2 id="bi-fx-heading" style={{ marginBottom: "4px" }}>
                Multi-Currency FX Exposure &amp; Revaluation P&amp;L
              </h2>
              <p className="usr-muted" style={{ margin: 0 }}>
                Open foreign-currency receivables, payables, and cash balances
                marked to market in USD.
              </p>
            </div>
            <Link
              href="/global-finance/"
              className="button secondary usr-small-btn"
            >
              Manage FX &amp; Tax →
            </Link>
          </div>

          {data.fx_exposure.length === 0 ? (
            <p className="usr-muted" style={{ margin: 0 }}>
              No multi-currency FX ledger positions recorded yet. Add EUR, GBP,
              CAD, or MXN entries under Payroll &amp; FX Tax.
            </p>
          ) : (
            <div
              style={{ overflowX: "auto" }}
              tabIndex={0}
              role="region"
              aria-label="Multi-currency FX exposure table"
            >
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--line)",
                      textAlign: "left",
                    }}
                  >
                    <th style={{ padding: "8px 10px" }}>Currency</th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>
                      Entries
                    </th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>
                      Open AR (USD)
                    </th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>
                      Open AP (USD)
                    </th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>
                      Net Exposure
                    </th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>
                      Unrealized FX
                    </th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>
                      Realized FX
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.fx_exposure.map((fx) => (
                    <tr
                      key={fx.currency}
                      style={{ borderBottom: "1px solid var(--line)" }}
                    >
                      <td style={{ padding: "8px 10px", fontWeight: 700 }}>
                        <span className="usr-badge">{fx.currency}</span>
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>
                        {fx.entry_count}
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>
                        {formatUsd(fx.receivable_usd_cents)}
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>
                        {formatUsd(fx.payable_usd_cents)}
                      </td>
                      <td
                        style={{
                          padding: "8px 10px",
                          textAlign: "right",
                          fontWeight: 600,
                        }}
                      >
                        {formatUsd(fx.net_exposure_usd_cents)}
                      </td>
                      <td
                        style={{
                          padding: "8px 10px",
                          textAlign: "right",
                          color:
                            fx.unrealized_fx_cents >= 0 ? "#165430" : "#8a1c19",
                        }}
                      >
                        {formatUsd(fx.unrealized_fx_cents)}
                      </td>
                      <td
                        style={{
                          padding: "8px 10px",
                          textAlign: "right",
                          color:
                            fx.realized_fx_cents >= 0 ? "#165430" : "#8a1c19",
                        }}
                      >
                        {formatUsd(fx.realized_fx_cents)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}
    </div>
  );
}
