"use client";

import { useEffect, useState } from "react";
import { triggerCsvDownload } from "../lib/csv-export";
import {
  buildConsolidatedHoldingCsv,
  ConsolidatedStatementColumn,
  createIntercompanyTx,
  createSubsidiary,
  CurrencyCode,
  EntityRole,
  fetchHoldingOverview,
  HoldingOverviewResponse,
  IntercompanyStatus,
  IntercompanyTxKind,
  seedSampleHoldingGroup,
  updateIntercompanyStatus,
  upsertEntitySnapshot,
} from "../lib/holding-consolidation-api";
import { ManagementApiError } from "../lib/management-api";

type HoldingTab = "consolidated" | "intercompany" | "entities";

function currentMonthKey(): string {
  const d = new Date();
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

function formatUsd(cents: number): string {
  const neg = cents < 0;
  const abs = Math.abs(cents) / 100;
  return `${neg ? "-$" : "$"}${abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function parseDollarsToMinor(raw: string): number {
  const n = Number.parseFloat(raw.replace(/,/g, ""));
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

const STATEMENT_ROWS: readonly {
  label: string;
  key: keyof ConsolidatedStatementColumn;
  bold?: boolean;
  section?: "pnl" | "bs";
}[] = [
  { label: "Revenue", key: "revenue_cents", section: "pnl" },
  { label: "Cost of Goods Sold (COGS)", key: "cogs_cents", section: "pnl" },
  {
    label: "Gross Profit",
    key: "gross_profit_cents",
    bold: true,
    section: "pnl",
  },
  { label: "Operating Expenses (OpEx)", key: "opex_cents", section: "pnl" },
  {
    label: "Consolidated Net Income",
    key: "net_income_cents",
    bold: true,
    section: "pnl",
  },
  {
    label: "  Attributable to Parent (Controlling Interest)",
    key: "controlling_interest_net_income_cents",
    section: "pnl",
  },
  {
    label: "  Non-Controlling Interest (Minority NCI)",
    key: "nci_net_income_cents",
    section: "pnl",
  },
  { label: "Cash & Equivalents", key: "cash_cents", section: "bs" },
  {
    label: "Accounts Receivable (Net of Due From)",
    key: "ar_cents",
    section: "bs",
  },
  { label: "Inventory", key: "inventory_cents", section: "bs" },
  { label: "Fixed Assets", key: "fixed_assets_cents", section: "bs" },
  {
    label: "Total Consolidated Assets",
    key: "total_assets_cents",
    bold: true,
    section: "bs",
  },
  { label: "Accounts Payable (Net of Due To)", key: "ap_cents", section: "bs" },
  {
    label: "Debt & Intercompany Notes (Net)",
    key: "debt_cents",
    section: "bs",
  },
  {
    label: "Total Consolidated Liabilities",
    key: "total_liabilities_cents",
    bold: true,
    section: "bs",
  },
  {
    label: "Consolidated Equity",
    key: "equity_cents",
    bold: true,
    section: "bs",
  },
];

export function HoldingConsolidationHub({
  businessId,
}: {
  businessId: string;
}) {
  const [periodKey, setPeriodKey] = useState<string>(() => currentMonthKey());
  const [activeTab, setActiveTab] = useState<HoldingTab>("consolidated");
  const [data, setData] = useState<HoldingOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // New Subsidiary form
  const [subCode, setSubCode] = useState("UK-LON");
  const [subName, setSubName] = useState("AMARKAL UK Logistics Ltd");
  const [subRole, setSubRole] = useState<EntityRole>("operating_subsidiary");
  const [subCountry, setSubCountry] = useState("GB");
  const [subState, setSubState] = useState("LDN");
  const [subCurrency, setSubCurrency] = useState<CurrencyCode>("GBP");
  const [subOwnershipPct, setSubOwnershipPct] = useState("100");
  const [subTaxId, setSubTaxId] = useState("GB-***4912");

  // New Intercompany Transaction form
  const [icSrcId, setIcSrcId] = useState("");
  const [icTgtId, setIcTgtId] = useState("");
  const [icKind, setIcKind] = useState<IntercompanyTxKind>("management_fee");
  const [icCurrency, setIcCurrency] = useState<CurrencyCode>("USD");
  const [icAmount, setIcAmount] = useState("25000.00");
  const [icDesc, setIcDesc] = useState(
    "Shared Platform & Executive Management Allocation",
  );
  const [icAutoElim, setIcAutoElim] = useState(true);

  // Period Trial Balance Snapshot form
  const [snapSubId, setSnapSubId] = useState("");
  const [snapRev, setSnapRev] = useState("350000.00");
  const [snapCogs, setSnapCogs] = useState("140000.00");
  const [snapOpex, setSnapOpex] = useState("85000.00");
  const [snapCash, setSnapCash] = useState("220000.00");
  const [snapAr, setSnapAr] = useState("95000.00");
  const [snapAp, setSnapAp] = useState("48000.00");
  const [snapInv, setSnapInv] = useState("30000.00");
  const [snapFa, setSnapFa] = useState("180000.00");
  const [snapDebt, setSnapDebt] = useState("60000.00");
  const [snapEq, setSnapEq] = useState("417000.00");

  const reload = async (targetPeriod: string = periodKey) => {
    const ov = await fetchHoldingOverview(businessId, targetPeriod);
    setData(ov);
    const first = ov.subsidiaries[0];
    const second = ov.subsidiaries[1];
    if (first) {
      setSnapSubId((p) => p || first.id);
      setIcSrcId((p) => p || first.id);
    }
    if (second) {
      setIcTgtId((p) => p || second.id);
    }
  };

  useEffect(() => {
    let active = true;
    fetchHoldingOverview(businessId, periodKey)
      .then((ov) => {
        if (!active) return;
        setData(ov);
        const first = ov.subsidiaries[0];
        const second = ov.subsidiaries[1];
        if (first) {
          setSnapSubId((p) => p || first.id);
          setIcSrcId((p) => p || first.id);
        }
        if (second) {
          setIcTgtId((p) => p || second.id);
        }
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof ManagementApiError
            ? err.message
            : "Unable to load Holding consolidation overview.",
        );
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, periodKey]);

  const handleSeedSample = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await seedSampleHoldingGroup(businessId, periodKey);
      await reload(periodKey);
      setNotice(res.message);
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Unable to seed sample holding group.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleCreateSubsidiary = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const pct = Number.parseFloat(subOwnershipPct);
      const bps = Number.isFinite(pct)
        ? Math.max(0, Math.min(10000, Math.round(pct * 100)))
        : 10000;
      const created = await createSubsidiary(businessId, {
        entity_code: subCode.trim().toUpperCase(),
        legal_name: subName.trim(),
        entity_role: subRole,
        jurisdiction_country: subCountry.trim().toUpperCase(),
        jurisdiction_state: subState.trim(),
        functional_currency: subCurrency,
        ownership_bps: bps,
        tax_id_masked: subTaxId.trim(),
      });
      await reload(periodKey);
      setNotice(
        `Registered subsidiary ${created.entity_code} (${created.legal_name} · ${created.functional_currency}).`,
      );
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Unable to register subsidiary.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleUpsertSnapshot = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!snapSubId) {
      setError("Select a subsidiary first.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await upsertEntitySnapshot(businessId, {
        subsidiary_id: snapSubId,
        period_key: periodKey,
        revenue_minor: parseDollarsToMinor(snapRev),
        cogs_minor: parseDollarsToMinor(snapCogs),
        opex_minor: parseDollarsToMinor(snapOpex),
        cash_minor: parseDollarsToMinor(snapCash),
        ar_minor: parseDollarsToMinor(snapAr),
        ap_minor: parseDollarsToMinor(snapAp),
        inventory_minor: parseDollarsToMinor(snapInv),
        fixed_assets_minor: parseDollarsToMinor(snapFa),
        debt_minor: parseDollarsToMinor(snapDebt),
        equity_minor: parseDollarsToMinor(snapEq),
        notes: `Saved for ${periodKey}`,
      });
      await reload(periodKey);
      setNotice(`Saved trial balance snapshot for ${periodKey}.`);
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Unable to save trial balance snapshot.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handlePostIntercompany = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!icSrcId || !icTgtId) {
      setError("Select both Source (Due From) and Target (Due To) entities.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createIntercompanyTx(businessId, {
        period_key: periodKey,
        source_subsidiary_id: icSrcId,
        target_subsidiary_id: icTgtId,
        tx_kind: icKind,
        currency: icCurrency,
        amount_minor: Math.max(1, parseDollarsToMinor(icAmount)),
        description: icDesc.trim(),
        auto_eliminate: icAutoElim,
      });
      await reload(periodKey);
      setNotice(
        `Posted mirrored intercompany ${created.tx_number} (${created.source_code} → ${created.target_code}) for ${formatUsd(created.usd_equivalent_cents)}.`,
      );
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Unable to post intercompany transaction.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleStatusChange = async (
    txId: string,
    nextStatus: IntercompanyStatus,
  ) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await updateIntercompanyStatus(businessId, txId, nextStatus);
      await reload(periodKey);
      setNotice(`Updated intercompany entry status to "${nextStatus}".`);
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Unable to update intercompany status.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleExportCsv = () => {
    if (!data) return;
    triggerCsvDownload(
      `amarkal-holding-consolidated-${data.period_key}.csv`,
      buildConsolidatedHoldingCsv(data),
    );
    setNotice("Exported consolidated US GAAP / IFRS holding pack CSV.");
  };

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
                MULTI-ENTITY HOLDING · PG18 FORCE RLS
              </span>
              <span className="usr-badge">DUE TO / DUE FROM ELIMINATION</span>
              <span className="usr-badge">US GAAP / IFRS · FX TO USD</span>
            </div>
            <h1 style={{ margin: "0 0 6px", fontSize: "1.65rem" }}>
              Holding Multi-Entity &amp; Intercompany Consolidation
            </h1>
            <p className="usr-muted" style={{ margin: 0 }}>
              Consolidate unlimited domestic and international subsidiaries into
              USD, post mirrored Due To / Due From intercompany entries with
              automatic eliminations, and compute Controlling vs.
              Non-Controlling Interest (NCI).
            </p>
          </div>
          <div className="usr-inline">
            <label style={{ margin: 0 }}>
              <span className="sr-only">Consolidation period</span>
              <input
                type="month"
                aria-label="Consolidation period"
                value={periodKey}
                onChange={(e) => {
                  if (/^[0-9]{4}-[0-9]{2}$/.test(e.target.value)) {
                    setPeriodKey(e.target.value);
                  }
                }}
              />
            </label>
            <button
              type="button"
              className="button secondary usr-small-btn"
              disabled={busy || !data}
              onClick={handleExportCsv}
            >
              Export Consolidated CSV
            </button>
          </div>
        </div>

        <div
          role="tablist"
          aria-label="Holding consolidation workspace sections"
          className="usr-tablist"
          style={{ marginTop: "18px", marginBottom: 0 }}
        >
          <button
            type="button"
            role="tab"
            id="tab-holding-consolidated"
            aria-selected={activeTab === "consolidated"}
            aria-controls="panel-holding-consolidated"
            className="usr-tab"
            onClick={() => setActiveTab("consolidated")}
          >
            Consolidated P&amp;L &amp; Balance Sheet
          </button>
          <button
            type="button"
            role="tab"
            id="tab-holding-intercompany"
            aria-selected={activeTab === "intercompany"}
            aria-controls="panel-holding-intercompany"
            className="usr-tab"
            onClick={() => setActiveTab("intercompany")}
          >
            Intercompany (Due To / Due From ·{" "}
            {data?.intercompany_transactions.length ?? 0})
          </button>
          <button
            type="button"
            role="tab"
            id="tab-holding-entities"
            aria-selected={activeTab === "entities"}
            aria-controls="panel-holding-entities"
            className="usr-tab"
            onClick={() => setActiveTab("entities")}
          >
            Entities &amp; Snapshots ({data?.subsidiaries.length ?? 0})
          </button>
        </div>
      </section>

      {error ? (
        <div className="usr-errors" role="alert">
          <strong>Holding Consolidation error:</strong> {error}
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

      {data && data.subsidiaries.length === 0 ? (
        <section className="usr-card">
          <h2 style={{ marginBottom: "8px" }}>
            Configure your multi-entity holding group
          </h2>
          <p className="usr-muted" style={{ marginTop: 0 }}>
            Register your parent holding LLC and domestic/international
            subsidiaries — or load our realistic 4-entity US/EU/CA holding group
            (with EUR/CAD FX translation, 20% EU minority NCI, and automatic
            intercompany eliminations) in 1 click.
          </p>
          <div className="usr-inline">
            <button
              type="button"
              className="button usr-small-btn"
              disabled={busy}
              onClick={handleSeedSample}
            >
              Load Sample 4-Entity US/EU/CA Holding Group
            </button>
            <button
              type="button"
              className="button secondary usr-small-btn"
              onClick={() => setActiveTab("entities")}
            >
              Add First Subsidiary Manually →
            </button>
          </div>
        </section>
      ) : null}

      {data ? (
        <section aria-label="Consolidated holding KPI summary">
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(220px, 100%), 1fr))",
              gap: "16px",
            }}
          >
            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Consolidated Revenue (USD)</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#111318",
                }}
              >
                {formatUsd(data.consolidated.revenue_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Pre-elim: {formatUsd(data.pre_elimination.revenue_cents)} across{" "}
                {data.subsidiaries.length} entities
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Consolidated Net Income</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#165430",
                }}
              >
                {formatUsd(data.consolidated.net_income_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Parent:{" "}
                {formatUsd(
                  data.consolidated.controlling_interest_net_income_cents,
                )}{" "}
                · NCI: {formatUsd(data.consolidated.nci_net_income_cents)}
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Intercompany Eliminations</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#1f4e79",
                }}
              >
                {formatUsd(Math.abs(data.eliminations.ar_cents))}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Rev elim: {formatUsd(Math.abs(data.eliminations.revenue_cents))}{" "}
                · {data.due_to_due_from_matrix.length} active Due To/From pairs
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Consolidated Cash &amp; Assets</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#111318",
                }}
              >
                {formatUsd(data.consolidated.cash_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Total Assets: {formatUsd(data.consolidated.total_assets_cents)}
              </div>
            </article>
          </div>
        </section>
      ) : null}

      {activeTab === "consolidated" ? (
        <section
          id="panel-holding-consolidated"
          role="tabpanel"
          aria-labelledby="tab-holding-consolidated"
          className="usr-stack"
        >
          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 id="holding-consolidated-h" style={{ marginBottom: "6px" }}>
              Consolidated P&amp;L &amp; Balance Sheet ({periodKey} · USD)
            </h2>
            <p className="usr-muted" style={{ marginTop: 0 }}>
              Automatic currency translation via live FX rates and mirrored
              intercompany eliminations.
            </p>
            {loading || !data ? (
              <p className="usr-muted">Loading consolidated statement...</p>
            ) : (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Consolidated P&L and Balance Sheet table"
              >
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    minWidth: "640px",
                  }}
                >
                  <thead>
                    <tr
                      style={{
                        borderBottom: "2px solid var(--line)",
                        textAlign: "left",
                      }}
                    >
                      <th style={{ padding: "8px 10px" }}>
                        Statement Line (US GAAP / IFRS)
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Pre-Elimination
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Eliminations
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Consolidated USD
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {STATEMENT_ROWS.map((row) => {
                      const preVal = data.pre_elimination[row.key];
                      const elimVal = data.eliminations[row.key];
                      const consVal = data.consolidated[row.key];
                      return (
                        <tr
                          key={row.key}
                          style={{
                            borderBottom: "1px solid var(--line)",
                            background: row.bold ? "#f8f9fb" : "#ffffff",
                            fontWeight: row.bold ? 700 : 400,
                          }}
                        >
                          <td style={{ padding: "8px 10px" }}>{row.label}</td>
                          <td
                            style={{ padding: "8px 10px", textAlign: "right" }}
                          >
                            {formatUsd(preVal)}
                          </td>
                          <td
                            style={{
                              padding: "8px 10px",
                              textAlign: "right",
                              color: elimVal !== 0 ? "#1f4e79" : "#464b59",
                            }}
                          >
                            {elimVal === 0 ? "—" : formatUsd(elimVal)}
                          </td>
                          <td
                            style={{
                              padding: "8px 10px",
                              textAlign: "right",
                              color:
                                row.key === "net_income_cents"
                                  ? consVal >= 0
                                    ? "#165430"
                                    : "#8a1c19"
                                  : "#111318",
                            }}
                          >
                            {formatUsd(consVal)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {data && data.per_entity_usd.length > 0 ? (
            <div className="usr-card" style={{ marginBottom: 0 }}>
              <h2 style={{ marginBottom: "6px" }}>
                Per-Subsidiary FX Translation &amp; Ownership Breakdown
              </h2>
              <p className="usr-muted" style={{ marginTop: 0 }}>
                Standalone entity trial balances translated into USD with
                ownership percentages and Non-Controlling Interest (NCI).
              </p>
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Per-subsidiary USD translation table"
              >
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    minWidth: "900px",
                  }}
                >
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid var(--line)",
                        textAlign: "left",
                        whiteSpace: "nowrap",
                      }}
                    >
                      <th style={{ padding: "8px 10px" }}>Entity</th>
                      <th style={{ padding: "8px 10px" }}>Jurisdiction</th>
                      <th style={{ padding: "8px 10px" }}>FX Rate</th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Ownership
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Revenue (USD)
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Net Income
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        NCI Share
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Total Assets
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.per_entity_usd.map((ent) => (
                      <tr
                        key={ent.subsidiary_id}
                        style={{
                          borderBottom: "1px solid var(--line)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        <td style={{ padding: "8px 10px" }}>
                          <span
                            className="usr-badge"
                            style={{ marginRight: "6px" }}
                          >
                            {ent.entity_code}
                          </span>
                          <strong>{ent.legal_name}</strong>
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          {ent.jurisdiction}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          {ent.functional_currency} @{" "}
                          {(ent.fx_rate_micros / 1_000_000).toFixed(4)}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }}>
                          {ent.ownership_pct.toFixed(0)}%
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }}>
                          {formatUsd(ent.revenue_usd_cents)}
                        </td>
                        <td
                          style={{
                            padding: "8px 10px",
                            textAlign: "right",
                            fontWeight: 600,
                            color:
                              ent.net_income_usd_cents >= 0
                                ? "#165430"
                                : "#8a1c19",
                          }}
                        >
                          {formatUsd(ent.net_income_usd_cents)}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }}>
                          {ent.nci_net_income_cents === 0
                            ? "—"
                            : formatUsd(ent.nci_net_income_cents)}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }}>
                          {formatUsd(ent.total_assets_usd_cents)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {activeTab === "intercompany" ? (
        <section
          id="panel-holding-intercompany"
          role="tabpanel"
          aria-labelledby="tab-holding-intercompany"
          className="usr-stack"
        >
          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 style={{ marginBottom: "6px" }}>
              Due To / Due From Bilateral Settlement Matrix
            </h2>
            <p className="usr-muted" style={{ marginTop: 0 }}>
              Net intra-group balances owed between subsidiaries for period{" "}
              {periodKey}.
            </p>
            {!data || data.due_to_due_from_matrix.length === 0 ? (
              <p className="usr-muted" style={{ margin: 0 }}>
                No active intercompany balances in {periodKey}.
              </p>
            ) : (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Due To Due From bilateral settlement matrix"
              >
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid var(--line)",
                        textAlign: "left",
                      }}
                    >
                      <th style={{ padding: "8px 10px" }}>
                        Creditor (Due From)
                      </th>
                      <th style={{ padding: "8px 10px" }}>Debtor (Due To)</th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Transactions
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        Net Settlement (USD)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.due_to_due_from_matrix.map((pair) => (
                      <tr
                        key={`${pair.creditor_code}-${pair.debtor_code}`}
                        style={{ borderBottom: "1px solid var(--line)" }}
                      >
                        <td style={{ padding: "8px 10px" }}>
                          <span className="usr-badge usr-badge-ai">
                            {pair.creditor_code}
                          </span>{" "}
                          {pair.creditor_name}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span className="usr-badge">{pair.debtor_code}</span>{" "}
                          {pair.debtor_name}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }}>
                          {pair.tx_count}
                        </td>
                        <td
                          style={{
                            padding: "8px 10px",
                            textAlign: "right",
                            fontWeight: 700,
                          }}
                        >
                          {formatUsd(pair.net_due_usd_cents)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 style={{ marginBottom: "8px" }}>
              Post Mirrored Intercompany Transaction
            </h2>
            <form onSubmit={handlePostIntercompany} className="usr-stack">
              <div className="usr-grid">
                <label>
                  Source Entity (Due From / Billing)
                  <select
                    value={icSrcId}
                    onChange={(e) => setIcSrcId(e.target.value)}
                  >
                    {(data?.subsidiaries ?? []).map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.entity_code} · {s.legal_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Target Entity (Due To / Paying)
                  <select
                    value={icTgtId}
                    onChange={(e) => setIcTgtId(e.target.value)}
                  >
                    {(data?.subsidiaries ?? []).map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.entity_code} · {s.legal_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Transaction Type
                  <select
                    value={icKind}
                    onChange={(e) =>
                      setIcKind(e.target.value as IntercompanyTxKind)
                    }
                  >
                    <option value="management_fee">Management Fee</option>
                    <option value="intercompany_service">
                      Intercompany Service
                    </option>
                    <option value="inventory_transfer">
                      Inventory Transfer
                    </option>
                    <option value="intercompany_loan">Intercompany Loan</option>
                    <option value="cost_allocation">Cost Allocation</option>
                    <option value="dividend">Intra-Group Dividend</option>
                  </select>
                </label>
                <label>
                  Currency
                  <select
                    value={icCurrency}
                    onChange={(e) =>
                      setIcCurrency(e.target.value as CurrencyCode)
                    }
                  >
                    {(
                      [
                        "USD",
                        "EUR",
                        "GBP",
                        "CAD",
                        "MXN",
                        "CHF",
                        "AUD",
                        "JPY",
                      ] as const
                    ).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Amount (Major Units)
                  <input
                    type="text"
                    value={icAmount}
                    onChange={(e) => setIcAmount(e.target.value)}
                    required
                  />
                </label>
                <label>
                  Description
                  <input
                    type="text"
                    value={icDesc}
                    onChange={(e) => setIcDesc(e.target.value)}
                    required
                    minLength={2}
                  />
                </label>
              </div>
              <label className="usr-check">
                <input
                  type="checkbox"
                  checked={icAutoElim}
                  onChange={(e) => setIcAutoElim(e.target.checked)}
                />
                Automatically mark eliminated in consolidated statements
              </label>
              <div>
                <button
                  type="submit"
                  className="button usr-small-btn"
                  disabled={busy || (data?.subsidiaries.length ?? 0) < 2}
                >
                  Post Mirrored Intercompany Entry
                </button>
              </div>
            </form>
          </div>

          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 style={{ marginBottom: "8px" }}>
              Intercompany Audit Ledger ({periodKey})
            </h2>
            {!data || data.intercompany_transactions.length === 0 ? (
              <p className="usr-muted" style={{ margin: 0 }}>
                No intercompany transactions recorded for {periodKey}.
              </p>
            ) : (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Intercompany audit ledger table"
              >
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    minWidth: "780px",
                  }}
                >
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid var(--line)",
                        textAlign: "left",
                      }}
                    >
                      <th style={{ padding: "8px 10px" }}>Ref &amp; Route</th>
                      <th style={{ padding: "8px 10px" }}>
                        Mirrored Accounting Legs
                      </th>
                      <th style={{ padding: "8px 10px", textAlign: "right" }}>
                        USD Equivalent
                      </th>
                      <th style={{ padding: "8px 10px" }}>Status</th>
                      <th style={{ padding: "8px 10px" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.intercompany_transactions.map((tx) => (
                      <tr
                        key={tx.id}
                        style={{ borderBottom: "1px solid var(--line)" }}
                      >
                        <td style={{ padding: "8px 10px" }}>
                          <strong>{tx.tx_number}</strong>
                          <div
                            className="usr-muted"
                            style={{ fontSize: "0.8rem" }}
                          >
                            {tx.source_code} → {tx.target_code} · {tx.tx_kind}
                          </div>
                        </td>
                        <td
                          style={{ padding: "8px 10px", fontSize: "0.82rem" }}
                        >
                          <div>
                            <strong>{tx.description}</strong>
                          </div>
                          <div className="usr-muted">
                            {tx.source_code}: {tx.source_entry_label}
                          </div>
                          <div className="usr-muted">
                            {tx.target_code}: {tx.target_entry_label}
                          </div>
                        </td>
                        <td
                          style={{
                            padding: "8px 10px",
                            textAlign: "right",
                            fontWeight: 700,
                            whiteSpace: "nowrap",
                          }}
                        >
                          {formatUsd(tx.usd_equivalent_cents)}
                          <div
                            className="usr-muted"
                            style={{ fontSize: "0.75rem", fontWeight: 400 }}
                          >
                            {tx.currency} {(tx.amount_minor / 100).toFixed(2)}
                          </div>
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span
                            className={
                              tx.status === "eliminated"
                                ? "usr-badge usr-badge-ai"
                                : "usr-badge"
                            }
                          >
                            {tx.status.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <div className="usr-inline" style={{ gap: "6px" }}>
                            {tx.status !== "eliminated" ? (
                              <button
                                type="button"
                                className="button usr-small-btn"
                                disabled={busy}
                                onClick={() =>
                                  handleStatusChange(tx.id, "eliminated")
                                }
                              >
                                Eliminate
                              </button>
                            ) : (
                              <button
                                type="button"
                                className="button secondary usr-small-btn"
                                disabled={busy}
                                onClick={() =>
                                  handleStatusChange(tx.id, "posted")
                                }
                              >
                                Uneliminate
                              </button>
                            )}
                            {tx.status !== "void" ? (
                              <button
                                type="button"
                                className="usr-small-btn usr-danger"
                                disabled={busy}
                                onClick={() =>
                                  handleStatusChange(tx.id, "void")
                                }
                              >
                                Void
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      ) : null}

      {activeTab === "entities" ? (
        <section
          id="panel-holding-entities"
          role="tabpanel"
          aria-labelledby="tab-holding-entities"
          className="usr-stack"
        >
          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 style={{ marginBottom: "8px" }}>
              Register Subsidiary or Parent Legal Entity
            </h2>
            <form onSubmit={handleCreateSubsidiary} className="usr-stack">
              <div className="usr-grid">
                <label>
                  Entity Code
                  <input
                    type="text"
                    value={subCode}
                    onChange={(e) => setSubCode(e.target.value)}
                    required
                    minLength={2}
                    maxLength={32}
                  />
                </label>
                <label>
                  Legal Name
                  <input
                    type="text"
                    value={subName}
                    onChange={(e) => setSubName(e.target.value)}
                    required
                    minLength={2}
                  />
                </label>
                <label>
                  Entity Role
                  <select
                    value={subRole}
                    onChange={(e) => setSubRole(e.target.value as EntityRole)}
                  >
                    <option value="parent_holding">Parent Holding</option>
                    <option value="operating_subsidiary">
                      Operating Subsidiary
                    </option>
                    <option value="regional_branch">Regional Branch</option>
                    <option value="spv">Special Purpose Vehicle (SPV)</option>
                  </select>
                </label>
                <label>
                  Country (ISO-2)
                  <input
                    type="text"
                    value={subCountry}
                    onChange={(e) => setSubCountry(e.target.value)}
                    required
                    pattern="[A-Za-z]{2}"
                  />
                </label>
                <label>
                  State / Region
                  <input
                    type="text"
                    value={subState}
                    onChange={(e) => setSubState(e.target.value)}
                  />
                </label>
                <label>
                  Functional Currency
                  <select
                    value={subCurrency}
                    onChange={(e) =>
                      setSubCurrency(e.target.value as CurrencyCode)
                    }
                  >
                    {(
                      [
                        "USD",
                        "EUR",
                        "GBP",
                        "CAD",
                        "MXN",
                        "CHF",
                        "AUD",
                        "JPY",
                      ] as const
                    ).map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Parent Ownership %
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="0.01"
                    value={subOwnershipPct}
                    onChange={(e) => setSubOwnershipPct(e.target.value)}
                  />
                </label>
                <label>
                  Masked Tax ID / EIN / VAT
                  <input
                    type="text"
                    value={subTaxId}
                    onChange={(e) => setSubTaxId(e.target.value)}
                  />
                </label>
              </div>
              <div>
                <button
                  type="submit"
                  className="button usr-small-btn"
                  disabled={busy}
                >
                  Add Subsidiary Entity
                </button>
              </div>
            </form>
          </div>

          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 style={{ marginBottom: "8px" }}>
              Update Entity Period Trial Balance Snapshot ({periodKey})
            </h2>
            <p className="usr-muted" style={{ marginTop: 0 }}>
              Enter period P&amp;L and Balance Sheet figures in the
              subsidiary&apos;s functional currency (auto-translated to USD on
              save).
            </p>
            <form onSubmit={handleUpsertSnapshot} className="usr-stack">
              <div className="usr-grid">
                <label>
                  Subsidiary
                  <select
                    value={snapSubId}
                    onChange={(e) => setSnapSubId(e.target.value)}
                  >
                    {(data?.subsidiaries ?? []).map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.entity_code} · {s.legal_name} (
                        {s.functional_currency})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Revenue
                  <input
                    type="text"
                    value={snapRev}
                    onChange={(e) => setSnapRev(e.target.value)}
                  />
                </label>
                <label>
                  COGS
                  <input
                    type="text"
                    value={snapCogs}
                    onChange={(e) => setSnapCogs(e.target.value)}
                  />
                </label>
                <label>
                  Operating Expenses
                  <input
                    type="text"
                    value={snapOpex}
                    onChange={(e) => setSnapOpex(e.target.value)}
                  />
                </label>
                <label>
                  Cash
                  <input
                    type="text"
                    value={snapCash}
                    onChange={(e) => setSnapCash(e.target.value)}
                  />
                </label>
                <label>
                  Accounts Receivable
                  <input
                    type="text"
                    value={snapAr}
                    onChange={(e) => setSnapAr(e.target.value)}
                  />
                </label>
                <label>
                  Inventory
                  <input
                    type="text"
                    value={snapInv}
                    onChange={(e) => setSnapInv(e.target.value)}
                  />
                </label>
                <label>
                  Fixed Assets
                  <input
                    type="text"
                    value={snapFa}
                    onChange={(e) => setSnapFa(e.target.value)}
                  />
                </label>
                <label>
                  Accounts Payable
                  <input
                    type="text"
                    value={snapAp}
                    onChange={(e) => setSnapAp(e.target.value)}
                  />
                </label>
                <label>
                  Debt
                  <input
                    type="text"
                    value={snapDebt}
                    onChange={(e) => setSnapDebt(e.target.value)}
                  />
                </label>
                <label>
                  Equity
                  <input
                    type="text"
                    value={snapEq}
                    onChange={(e) => setSnapEq(e.target.value)}
                  />
                </label>
              </div>
              <div>
                <button
                  type="submit"
                  className="button usr-small-btn"
                  disabled={busy || !snapSubId}
                >
                  Save Trial Balance Snapshot
                </button>
              </div>
            </form>
          </div>
        </section>
      ) : null}
    </div>
  );
}
