"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { buildPayrollRunCsv, triggerCsvDownload } from "../lib/csv-export";
import {
  createFxEntry,
  createPayrollProfile,
  createPayrollRun,
  fetchFxEntries,
  fetchFxRates,
  fetchPaymentRails,
  fetchPayrollProfiles,
  fetchPayrollRuns,
  fetchTaxProfiles,
  previewInternationalTax,
  settleFxEntry,
  transitionPayrollRun,
  upsertFxRate,
  type CurrencyCode,
  type FilingStatus,
  type FxLedgerEntry,
  type FxRate,
  type OvertimeRule,
  type PaymentRail,
  type PayrollProfile,
  type PayrollRun,
  type TaxPreview,
  type TaxProfile,
} from "../lib/global-finance-api";

type TabId = "payroll" | "fx" | "tax_rails";

function fmtUsd(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}$${(abs / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

function fmtMoney(minor: number, currency: string): string {
  const sign = minor < 0 ? "-" : "";
  const abs = Math.abs(minor);
  return `${sign}${(abs / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })} ${currency}`;
}

function fmtRate(micros: number): string {
  return (micros / 1_000_000).toFixed(4);
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Operation failed.";
}

const OT_LABELS: Record<OvertimeRule, string> = {
  flsa_weekly_40: "FLSA Weekly (>40h @ 1.5x)",
  california_daily_8_12: "California §510 (8h OT / 12h DT)",
  union_cba_custom: "Union CBA (8h OT / 10h DT)",
};

export function GlobalFinanceHub({ businessId }: { businessId: string }) {
  const [activeTab, setActiveTab] = useState<TabId>("payroll");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [profiles, setProfiles] = useState<PayrollProfile[]>([]);
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [rates, setRates] = useState<FxRate[]>([]);
  const [fxEntries, setFxEntries] = useState<FxLedgerEntry[]>([]);
  const [taxProfiles, setTaxProfiles] = useState<TaxProfile[]>([]);
  const [rails, setRails] = useState<PaymentRail[]>([]);

  // Employee Payroll Profile form
  const [empCode, setEmpCode] = useState("");
  const [empName, setEmpName] = useState("");
  const [empState, setEmpState] = useState("CA");
  const [empPayType, setEmpPayType] = useState<"hourly" | "salaried">("hourly");
  const [empRateUsd, setEmpRateUsd] = useState("42.00");
  const [empOtRule, setEmpOtRule] = useState<OvertimeRule>(
    "california_daily_8_12",
  );
  const [empUnion, setEmpUnion] = useState("IBT Local 705");
  const [empUnionDues, setEmpUnionDues] = useState("45");
  const [empHealthUsd, setEmpHealthUsd] = useState("150");
  const [emp401kPct, setEmp401kPct] = useState("4");
  const [empFiling, setEmpFiling] = useState<FilingStatus>("single");
  const [savingEmp, setSavingEmp] = useState(false);

  // Payroll Run form
  const [runEmpId, setRunEmpId] = useState("");
  const [runDailyHoursCsv, setRunDailyHoursCsv] = useState("10, 9, 8, 8, 8");
  const [runBonusUsd, setRunBonusUsd] = useState("0");
  const [runNotes, setRunNotes] = useState("");
  const [creatingRun, setCreatingRun] = useState(false);

  // FX Rate form
  const [rateCcy, setRateCcy] = useState<CurrencyCode>("EUR");
  const [rateVal, setRateVal] = useState("1.1050");
  const [savingRate, setSavingRate] = useState(false);

  // FX Ledger Entry form
  const [fxDesc, setFxDesc] = useState("");
  const [fxCp, setFxCp] = useState("");
  const [fxCcy, setFxCcy] = useState<CurrencyCode>("EUR");
  const [fxAmount, setFxAmount] = useState("10000");
  const [fxKind, setFxKind] = useState<
    "receivable" | "payable" | "cash_balance"
  >("receivable");
  const [savingFx, setSavingFx] = useState(false);

  // International Tax Calculator
  const [taxProfId, setTaxProfId] = useState("");
  const [taxSubAmt, setTaxSubAmt] = useState("2500");
  const [taxB2bCross, setTaxB2bCross] = useState(false);
  const [taxReduced, setTaxReduced] = useState(false);
  const [taxPreview, setTaxPreview] = useState<TaxPreview | null>(null);

  // Accessible label IDs
  const empCodeId = useId();
  const empNameId = useId();
  const empStateId = useId();
  const empTypeId = useId();
  const empRateId = useId();
  const empOtId = useId();
  const empUnionId = useId();
  const empDuesId = useId();
  const empHealthId = useId();
  const emp401kId = useId();
  const empFilingId = useId();
  const runEmpInputId = useId();
  const runHoursId = useId();
  const runBonusId = useId();
  const runNotesId = useId();
  const rateCcyId = useId();
  const rateValId = useId();
  const fxDescId = useId();
  const fxCpId = useId();
  const fxCcyId = useId();
  const fxAmtId = useId();
  const fxKindId = useId();
  const taxProfInputId = useId();
  const taxSubId = useId();
  const taxB2bId = useId();
  const taxRedId = useId();

  const reloadAll = useCallback(async () => {
    const [p, pr, fr, fe, tp, rl] = await Promise.all([
      fetchPayrollProfiles(businessId),
      fetchPayrollRuns(businessId),
      fetchFxRates(businessId),
      fetchFxEntries(businessId),
      fetchTaxProfiles(businessId),
      fetchPaymentRails(businessId),
    ]);
    setProfiles(p);
    setRuns(pr);
    setRates(fr);
    setFxEntries(fe);
    setTaxProfiles(tp);
    setRails(rl);
    const firstProf = p[0];
    if (firstProf) setRunEmpId((cur) => cur || firstProf.id);
    const firstTax = tp[0];
    if (firstTax) setTaxProfId((cur) => cur || firstTax.id);
  }, [businessId]);

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        await reloadAll();
      } catch (err) {
        if (active) setError(errText(err));
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, [reloadAll]);

  async function onAddEmployee(e: React.FormEvent) {
    e.preventDefault();
    setSavingEmp(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createPayrollProfile(businessId, {
        employee_code: empCode.trim().toUpperCase(),
        full_name: empName.trim(),
        work_state: empState.trim().toUpperCase(),
        pay_type: empPayType,
        base_rate_cents: Math.round(Number(empRateUsd || "0") * 100),
        overtime_rule: empOtRule,
        union_local_code: empUnion.trim(),
        union_dues_cents: Math.round(Number(empUnionDues || "0") * 100),
        health_insurance_pretax_cents: Math.round(
          Number(empHealthUsd || "0") * 100,
        ),
        retirement_401k_bps: Math.round(Number(emp401kPct || "0") * 100),
        filing_status: empFiling,
        external_payroll_provider: "gusto",
      });
      setProfiles((prev) => [...prev, created]);
      setRunEmpId(created.id);
      setEmpCode("");
      setEmpName("");
      setNotice(
        `US Payroll profile ${created.employee_code} (${created.full_name}, ${created.work_state}) created.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingEmp(false);
    }
  }

  async function onCreatePayrollRun(e: React.FormEvent) {
    e.preventDefault();
    if (!runEmpId) return;
    setCreatingRun(true);
    setError(null);
    setNotice(null);
    try {
      const dailyHrs = runDailyHoursCsv
        .split(",")
        .map((s) => Math.max(0, Math.round(Number(s.trim() || "0") * 1000)))
        .filter((n) => !Number.isNaN(n));
      const today = new Date().toISOString().slice(0, 10);
      const created = await createPayrollRun(businessId, {
        period_start: today,
        period_end: today,
        pay_date: today,
        export_provider: "csv_adp_gusto",
        notes: runNotes.trim(),
        entries: [
          {
            profile_id: runEmpId,
            daily_hours_milli: dailyHrs.length > 0 ? dailyHrs : [40000],
            bonus_cents: Math.round(Number(runBonusUsd || "0") * 100),
          },
        ],
      });
      await reloadAll();
      setRunNotes("");
      setNotice(
        `Draft Payroll Prep run ${created.run_number} calculated (Gross ${fmtUsd(created.total_gross_cents)} → Net ${fmtUsd(created.total_net_cents)}). Owner approval required before export.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setCreatingRun(false);
    }
  }

  async function onTransitionPayroll(
    runId: string,
    action: "approve" | "export" | "void",
  ) {
    setError(null);
    setNotice(null);
    try {
      const updated = await transitionPayrollRun(businessId, runId, action);
      await reloadAll();
      setNotice(`Payroll run ${updated.run_number} -> ${updated.status}.`);
    } catch (err) {
      setError(errText(err));
    }
  }

  function onDownloadPayrollCsv(run: PayrollRun) {
    const csv = buildPayrollRunCsv(run);
    const safeName = `${run.run_number.replace(/[^A-Za-z0-9_-]/g, "_")}_gusto_adp.csv`;
    triggerCsvDownload(safeName, csv);
    setNotice(
      `Downloaded ${safeName} (${run.lines.length} employee line(s)) ready for Gusto, ADP, or Check import.`,
    );
  }

  async function onUpdateFxRate(e: React.FormEvent) {
    e.preventDefault();
    setSavingRate(true);
    setError(null);
    setNotice(null);
    try {
      const micros = Math.max(
        1,
        Math.round(Number(rateVal || "1") * 1_000_000),
      );
      const res = await upsertFxRate(businessId, {
        base_currency: rateCcy,
        rate_micros: micros,
        source: "manual",
      });
      await reloadAll();
      setNotice(
        `Updated 1 ${res.rate.base_currency} = $${fmtRate(res.rate.rate_micros)} USD — auto-revalued ${res.revalued_open_entries} open ledger entry(ies) on the fly.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingRate(false);
    }
  }

  async function onCreateFxEntry(e: React.FormEvent) {
    e.preventDefault();
    setSavingFx(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createFxEntry(businessId, {
        description: fxDesc.trim(),
        counterparty_name: fxCp.trim(),
        currency: fxCcy,
        amount_minor: Math.max(1, Math.round(Number(fxAmount || "100") * 100)),
        entry_kind: fxKind,
      });
      await reloadAll();
      setFxDesc("");
      setFxCp("");
      setNotice(
        `Recorded ${created.entry_number} (${fmtMoney(created.amount_minor, created.currency)} = ${fmtUsd(created.booked_usd_cents)} USD).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingFx(false);
    }
  }

  async function onSettleFx(entry: FxLedgerEntry) {
    setError(null);
    setNotice(null);
    try {
      const latest = rates.find((r) => r.base_currency === entry.currency);
      const settleRate = latest?.rate_micros ?? entry.current_rate_micros;
      const updated = await settleFxEntry(businessId, entry.id, settleRate);
      await reloadAll();
      setNotice(
        `Settled ${updated.entry_number} at ${fmtRate(settleRate)} — Realized FX Gain/Loss: ${fmtUsd(updated.realized_fx_gain_loss_cents)}.`,
      );
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onCalculateTax(e: React.FormEvent) {
    e.preventDefault();
    if (!taxProfId) return;
    setError(null);
    try {
      const res = await previewInternationalTax(businessId, {
        profile_id: taxProfId,
        subtotal_minor: Math.max(0, Math.round(Number(taxSubAmt || "0") * 100)),
        is_b2b_cross_border: taxB2bCross,
        use_reduced_rate: taxReduced,
      });
      setTaxPreview(res);
    } catch (err) {
      setError(errText(err));
    }
  }

  const totalUnrealizedFx = fxEntries
    .filter((e) => e.status === "open")
    .reduce((sum, e) => sum + e.fx_gain_loss_cents, 0);
  const totalRealizedFx = fxEntries
    .filter((e) => e.status === "settled")
    .reduce((sum, e) => sum + e.realized_fx_gain_loss_cents, 0);

  return (
    <div className="usr-stack">
      <div className="mgmt-section-header">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.6rem" }}>
            US Payroll Compliance, Multi-Currency FX Ledger &amp; Global Tax
          </h1>
          <p className="usr-muted" style={{ margin: "4px 0 0" }}>
            FLSA / California / Union CBA payroll preparation with human
            approval, real-time multi-currency FX Gain/Loss revaluation, and
            EU/UK/CA/MX VAT &amp; local payment rails.
          </p>
        </div>
      </div>

      {/* KPI Strip */}
      <div className="usr-grid">
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            US Payroll Profiles
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {profiles.length} ({runs.length} runs)
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Unrealized FX Gain / Loss
          </div>
          <div
            style={{
              fontSize: "1.4rem",
              fontWeight: 700,
              marginTop: 4,
              color: totalUnrealizedFx >= 0 ? "#15803d" : "#b91c1c",
            }}
          >
            {fmtUsd(totalUnrealizedFx)}
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Realized FX Gain / Loss
          </div>
          <div
            style={{
              fontSize: "1.4rem",
              fontWeight: 700,
              marginTop: 4,
              color: totalRealizedFx >= 0 ? "#15803d" : "#b91c1c",
            }}
          >
            {fmtUsd(totalRealizedFx)}
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Tax Jurisdictions &amp; Rails
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {taxProfiles.length} Tax · {rails.length} Rails
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="Global Finance & Payroll sections"
        className="usr-inline"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "payroll"}
          className={
            activeTab === "payroll"
              ? "usr-small-btn"
              : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("payroll")}
        >
          US Payroll &amp; Union Compliance ({profiles.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "fx"}
          className={
            activeTab === "fx" ? "usr-small-btn" : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("fx")}
        >
          Multi-Currency FX Ledger ({fxEntries.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "tax_rails"}
          className={
            activeTab === "tax_rails"
              ? "usr-small-btn"
              : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("tax_rails")}
        >
          International Tax &amp; Payment Rails ({taxProfiles.length})
        </button>
      </div>

      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="hold-note" style={{ margin: 0 }}>
          {notice}
        </p>
      )}
      {loading && (
        <p className="mgmt-loading" aria-live="polite">
          Loading Global Finance &amp; US Payroll…
        </p>
      )}

      {/* TAB 1: US Payroll & Union Compliance */}
      {!loading && activeTab === "payroll" && (
        <div className="usr-stack">
          <section className="usr-card" aria-labelledby="payroll-profiles-h">
            <h2 id="payroll-profiles-h" style={{ margin: "0 0 8px" }}>
              US Employee Compensation, State Tax &amp; Union CBA Profiles (
              {profiles.length})
            </h2>
            <p className="usr-muted" style={{ margin: "0 0 12px" }}>
              Prep &amp; Compliance Engine: calculates FLSA weekly 40h,
              California §510 daily 8h/12h double-time, union CBA multipliers,
              health/401(k) pre-tax deductions, and Federal/State/FICA estimates
              for human-approved export to Gusto, ADP, or Check Embedded.
            </p>
            <form
              onSubmit={(e) => void onAddEmployee(e)}
              className="usr-grid"
              style={{ marginBottom: 14 }}
            >
              <label htmlFor={empCodeId}>
                Employee Code
                <input
                  id={empCodeId}
                  required
                  value={empCode}
                  onChange={(e) => setEmpCode(e.target.value)}
                  placeholder="EMP-104"
                />
              </label>
              <label htmlFor={empNameId}>
                Full Name
                <input
                  id={empNameId}
                  required
                  value={empName}
                  onChange={(e) => setEmpName(e.target.value)}
                  placeholder="Jordan Vance"
                />
              </label>
              <label htmlFor={empStateId}>
                Work State (2-letter US)
                <input
                  id={empStateId}
                  required
                  maxLength={2}
                  value={empState}
                  onChange={(e) => setEmpState(e.target.value.toUpperCase())}
                />
              </label>
              <label htmlFor={empTypeId}>
                Pay Basis
                <select
                  id={empTypeId}
                  value={empPayType}
                  onChange={(e) =>
                    setEmpPayType(e.target.value as "hourly" | "salaried")
                  }
                >
                  <option value="hourly">Hourly</option>
                  <option value="salaried">Salaried (per period)</option>
                </select>
              </label>
              <label htmlFor={empRateId}>
                Base Rate (USD)
                <input
                  id={empRateId}
                  type="number"
                  step="0.01"
                  min="0"
                  value={empRateUsd}
                  onChange={(e) => setEmpRateUsd(e.target.value)}
                />
              </label>
              <label htmlFor={empOtId}>
                Overtime / Compliance Rule
                <select
                  id={empOtId}
                  value={empOtRule}
                  onChange={(e) => setEmpOtRule(e.target.value as OvertimeRule)}
                >
                  <option value="california_daily_8_12">
                    California §510 (8h OT / 12h DT)
                  </option>
                  <option value="flsa_weekly_40">FLSA Weekly (40h OT)</option>
                  <option value="union_cba_custom">
                    Union CBA (8h OT / 10h DT)
                  </option>
                </select>
              </label>
              <label htmlFor={empUnionId}>
                Union Local (optional)
                <input
                  id={empUnionId}
                  value={empUnion}
                  onChange={(e) => setEmpUnion(e.target.value)}
                  placeholder="IBT Local 705"
                />
              </label>
              <label htmlFor={empDuesId}>
                Union Dues / Period (USD)
                <input
                  id={empDuesId}
                  type="number"
                  step="1"
                  min="0"
                  value={empUnionDues}
                  onChange={(e) => setEmpUnionDues(e.target.value)}
                />
              </label>
              <label htmlFor={empHealthId}>
                Pre-Tax Health Ins. (USD)
                <input
                  id={empHealthId}
                  type="number"
                  step="1"
                  min="0"
                  value={empHealthUsd}
                  onChange={(e) => setEmpHealthUsd(e.target.value)}
                />
              </label>
              <label htmlFor={emp401kId}>
                401(k) Contribution (%)
                <input
                  id={emp401kId}
                  type="number"
                  step="0.5"
                  min="0"
                  max="50"
                  value={emp401kPct}
                  onChange={(e) => setEmp401kPct(e.target.value)}
                />
              </label>
              <label htmlFor={empFilingId}>
                W-4 Filing Status
                <select
                  id={empFilingId}
                  value={empFiling}
                  onChange={(e) => setEmpFiling(e.target.value as FilingStatus)}
                >
                  <option value="single">Single</option>
                  <option value="married_joint">Married Filing Jointly</option>
                  <option value="head_of_household">Head of Household</option>
                </select>
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingEmp}
                >
                  {savingEmp ? "Saving…" : "+ Add Employee Profile"}
                </button>
              </div>
            </form>

            {profiles.length > 0 && (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="US payroll profiles table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Employee</th>
                      <th>State</th>
                      <th>Base Rate</th>
                      <th>Compliance Rule</th>
                      <th>Union / Benefits</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profiles.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <code>{p.employee_code}</code>
                        </td>
                        <td>
                          <strong>{p.full_name}</strong>
                        </td>
                        <td>{p.work_state}</td>
                        <td>
                          {fmtUsd(p.base_rate_cents)}/
                          {p.pay_type === "hourly" ? "hr" : "period"}
                        </td>
                        <td>{OT_LABELS[p.overtime_rule]}</td>
                        <td>
                          {p.union_local_code || "Non-Union"} · Health{" "}
                          {fmtUsd(p.health_insurance_pretax_cents)} · 401k{" "}
                          {(p.retirement_401k_bps / 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="usr-card" aria-labelledby="payroll-run-h">
            <h2 id="payroll-run-h" style={{ margin: "0 0 10px" }}>
              Run US Payroll Prep &amp; Gross-to-Net Compliance Calculation
            </h2>
            <form
              onSubmit={(e) => void onCreatePayrollRun(e)}
              className="usr-grid"
              style={{ marginBottom: 16 }}
            >
              <label htmlFor={runEmpInputId}>
                Employee
                <select
                  id={runEmpInputId}
                  required
                  value={runEmpId}
                  onChange={(e) => setRunEmpId(e.target.value)}
                >
                  <option value="">Select employee…</option>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.employee_code} — {p.full_name} ({p.work_state})
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={runHoursId}>
                Daily Hours Worked (comma-separated)
                <input
                  id={runHoursId}
                  required
                  value={runDailyHoursCsv}
                  onChange={(e) => setRunDailyHoursCsv(e.target.value)}
                  placeholder="14, 10, 8, 8, 8"
                />
              </label>
              <label htmlFor={runBonusId}>
                Bonus / Safety Incentive (USD)
                <input
                  id={runBonusId}
                  type="number"
                  step="1"
                  min="0"
                  value={runBonusUsd}
                  onChange={(e) => setRunBonusUsd(e.target.value)}
                />
              </label>
              <label htmlFor={runNotesId}>
                Run Notes
                <input
                  id={runNotesId}
                  value={runNotes}
                  onChange={(e) => setRunNotes(e.target.value)}
                  placeholder="Week 48 Dispatch & Warehouse"
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={creatingRun || !runEmpId}
                >
                  {creatingRun ? "Calculating…" : "Calculate Draft Payroll Run"}
                </button>
              </div>
            </form>

            {runs.map((run) => (
              <article
                key={run.id}
                className="usr-card"
                style={{ background: "#fafafa", marginBottom: 14 }}
              >
                <div
                  className="usr-inline"
                  style={{
                    justifyContent: "space-between",
                    gap: 10,
                    marginBottom: 10,
                  }}
                >
                  <div>
                    <strong>{run.run_number}</strong> · Status:{" "}
                    <strong>{run.status}</strong> · Gross{" "}
                    <strong>{fmtUsd(run.total_gross_cents)}</strong> → Net{" "}
                    <strong>{fmtUsd(run.total_net_cents)}</strong> (Emp Taxes{" "}
                    {fmtUsd(run.total_employee_taxes_cents)} · Employer Taxes{" "}
                    {fmtUsd(run.total_employer_taxes_cents)})
                  </div>
                  <div className="usr-inline" style={{ gap: 6 }}>
                    <button
                      type="button"
                      className="secondary usr-small-btn"
                      onClick={() => onDownloadPayrollCsv(run)}
                    >
                      Download Gusto / ADP CSV
                    </button>
                    {run.status === "draft" && (
                      <button
                        type="button"
                        className="usr-small-btn"
                        onClick={() =>
                          void onTransitionPayroll(run.id, "approve")
                        }
                      >
                        Owner Approve Run
                      </button>
                    )}
                    {run.status === "approved" && (
                      <button
                        type="button"
                        className="usr-small-btn"
                        onClick={() =>
                          void onTransitionPayroll(run.id, "export")
                        }
                      >
                        Mark Exported (Gusto / ADP / Check)
                      </button>
                    )}
                  </div>
                </div>
                <div
                  style={{ overflowX: "auto" }}
                  tabIndex={0}
                  role="region"
                  aria-label="Payroll run breakdown table"
                >
                  <table className="mgmt-table">
                    <thead>
                      <tr>
                        <th>Employee</th>
                        <th>Reg / OT / DT</th>
                        <th>Gross</th>
                        <th>Fed + State</th>
                        <th>FICA</th>
                        <th>Pre-Tax &amp; Union</th>
                        <th>Net Pay</th>
                      </tr>
                    </thead>
                    <tbody>
                      {run.lines.map((l) => (
                        <tr key={l.id}>
                          <td>
                            <strong>{l.employee_name}</strong> ({l.work_state})
                            <div
                              className="usr-muted"
                              style={{ fontSize: "0.78rem" }}
                            >
                              {l.compliance_notes}
                            </div>
                          </td>
                          <td>
                            {(l.regular_hours_milli / 1000).toFixed(1)}h /{" "}
                            {(l.overtime_hours_milli / 1000).toFixed(1)}h /{" "}
                            {(l.doubletime_hours_milli / 1000).toFixed(1)}h
                          </td>
                          <td>{fmtUsd(l.gross_pay_cents)}</td>
                          <td>
                            {fmtUsd(l.federal_income_tax_cents)} +{" "}
                            {fmtUsd(l.state_income_tax_cents)}
                          </td>
                          <td>
                            {fmtUsd(l.social_security_cents + l.medicare_cents)}
                          </td>
                          <td>
                            {fmtUsd(
                              l.pretax_health_cents +
                                l.pretax_401k_cents +
                                l.union_dues_cents,
                            )}
                          </td>
                          <td>
                            <strong>{fmtUsd(l.net_pay_cents)}</strong>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>
            ))}
          </section>
        </div>
      )}

      {/* TAB 2: Multi-Currency FX Ledger */}
      {!loading && activeTab === "fx" && (
        <div className="usr-stack">
          <section className="usr-card" aria-labelledby="fx-rates-h">
            <h2 id="fx-rates-h" style={{ margin: "0 0 8px" }}>
              Live Multi-Currency Exchange Rates (Auto Mark-to-Market)
            </h2>
            <p className="usr-muted" style={{ margin: "0 0 12px" }}>
              Updating any currency spot rate automatically revalues every open
              foreign-currency Receivable, Payable, and Cash Balance in exact
              USD cents on the fly.
            </p>
            <form
              onSubmit={(e) => void onUpdateFxRate(e)}
              className="usr-grid"
              style={{ marginBottom: 14 }}
            >
              <label htmlFor={rateCcyId}>
                Base Currency
                <select
                  id={rateCcyId}
                  value={rateCcy}
                  onChange={(e) => setRateCcy(e.target.value as CurrencyCode)}
                >
                  <option value="EUR">EUR — Euro</option>
                  <option value="GBP">GBP — British Pound</option>
                  <option value="CAD">CAD — Canadian Dollar</option>
                  <option value="MXN">MXN — Mexican Peso</option>
                  <option value="CHF">CHF — Swiss Franc</option>
                  <option value="AUD">AUD — Australian Dollar</option>
                </select>
              </label>
              <label htmlFor={rateValId}>
                USD per 1 Unit (e.g. 1.1050)
                <input
                  id={rateValId}
                  type="number"
                  step="0.0001"
                  min="0.0001"
                  value={rateVal}
                  onChange={(e) => setRateVal(e.target.value)}
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingRate}
                >
                  {savingRate ? "Revaluing…" : "Update Rate & Revalue Ledger"}
                </button>
              </div>
            </form>

            <div
              style={{ overflowX: "auto" }}
              tabIndex={0}
              role="region"
              aria-label="FX exchange rates table"
            >
              <table className="mgmt-table">
                <thead>
                  <tr>
                    <th>Currency Pair</th>
                    <th>Spot Rate</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <strong>
                          1 {r.base_currency} / {r.quote_currency}
                        </strong>
                      </td>
                      <td>
                        <code>${fmtRate(r.rate_micros)} USD</code>
                      </td>
                      <td>{r.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="usr-card" aria-labelledby="fx-ledger-h">
            <h2 id="fx-ledger-h" style={{ margin: "0 0 10px" }}>
              Multi-Currency Ledger Entries &amp; FX Gain/Loss (
              {fxEntries.length})
            </h2>
            <form
              onSubmit={(e) => void onCreateFxEntry(e)}
              className="usr-grid"
              style={{ marginBottom: 14 }}
            >
              <label htmlFor={fxDescId}>
                Description
                <input
                  id={fxDescId}
                  required
                  value={fxDesc}
                  onChange={(e) => setFxDesc(e.target.value)}
                  placeholder="Hamburg Port Logistics Invoice #EU-402"
                />
              </label>
              <label htmlFor={fxCpId}>
                Counterparty
                <input
                  id={fxCpId}
                  value={fxCp}
                  onChange={(e) => setFxCp(e.target.value)}
                  placeholder="Nordic Cargo GmbH"
                />
              </label>
              <label htmlFor={fxCcyId}>
                Currency
                <select
                  id={fxCcyId}
                  value={fxCcy}
                  onChange={(e) => setFxCcy(e.target.value as CurrencyCode)}
                >
                  <option value="EUR">EUR</option>
                  <option value="GBP">GBP</option>
                  <option value="CAD">CAD</option>
                  <option value="MXN">MXN</option>
                  <option value="CHF">CHF</option>
                  <option value="AUD">AUD</option>
                  <option value="USD">USD</option>
                </select>
              </label>
              <label htmlFor={fxAmtId}>
                Foreign Amount
                <input
                  id={fxAmtId}
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={fxAmount}
                  onChange={(e) => setFxAmount(e.target.value)}
                />
              </label>
              <label htmlFor={fxKindId}>
                Ledger Position
                <select
                  id={fxKindId}
                  value={fxKind}
                  onChange={(e) =>
                    setFxKind(
                      e.target.value as
                        "receivable" | "payable" | "cash_balance",
                    )
                  }
                >
                  <option value="receivable">Receivable (AR)</option>
                  <option value="payable">Payable (AP)</option>
                  <option value="cash_balance">Foreign Cash Account</option>
                </select>
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingFx}
                >
                  {savingFx ? "Booking…" : "+ Book Multi-Currency Entry"}
                </button>
              </div>
            </form>

            {fxEntries.length > 0 && (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Multi-currency FX ledger entries table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      <th>Entry</th>
                      <th>Position</th>
                      <th>Foreign Amount</th>
                      <th>Booked USD</th>
                      <th>Current USD</th>
                      <th>FX Gain / Loss</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fxEntries.map((e) => {
                      const gl =
                        e.status === "settled"
                          ? e.realized_fx_gain_loss_cents
                          : e.fx_gain_loss_cents;
                      return (
                        <tr key={e.id}>
                          <td>
                            <code>{e.entry_number}</code>
                            <div style={{ fontWeight: 600 }}>
                              {e.description}
                            </div>
                            <div
                              className="usr-muted"
                              style={{ fontSize: "0.78rem" }}
                            >
                              {e.counterparty_name || "Direct"} · {e.status}
                            </div>
                          </td>
                          <td>{e.entry_kind}</td>
                          <td>{fmtMoney(e.amount_minor, e.currency)}</td>
                          <td>
                            {fmtUsd(e.booked_usd_cents)}
                            <div
                              className="usr-muted"
                              style={{ fontSize: "0.75rem" }}
                            >
                              @{fmtRate(e.booking_rate_micros)}
                            </div>
                          </td>
                          <td>
                            {fmtUsd(e.revalued_usd_cents)}
                            <div
                              className="usr-muted"
                              style={{ fontSize: "0.75rem" }}
                            >
                              @{fmtRate(e.current_rate_micros)}
                            </div>
                          </td>
                          <td
                            style={{
                              fontWeight: 700,
                              color: gl >= 0 ? "#15803d" : "#b91c1c",
                            }}
                          >
                            {gl > 0 ? "+" : ""}
                            {fmtUsd(gl)}
                          </td>
                          <td>
                            {e.status === "open" ? (
                              <button
                                type="button"
                                className="secondary usr-small-btn"
                                onClick={() => void onSettleFx(e)}
                              >
                                Settle &amp; Realize FX
                              </button>
                            ) : (
                              <span className="usr-muted">Settled</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 3: International Tax & Local Payment Rails */}
      {!loading && activeTab === "tax_rails" && (
        <div className="usr-stack">
          <section className="usr-card" aria-labelledby="intl-tax-h">
            <h2 id="intl-tax-h" style={{ margin: "0 0 10px" }}>
              International Tax Jurisdictions (US Sales Tax, EU/UK VAT, GST/HST,
              IVA)
            </h2>
            <div
              style={{ overflowX: "auto", marginBottom: 16 }}
              tabIndex={0}
              role="region"
              aria-label="International tax profiles table"
            >
              <table className="mgmt-table">
                <thead>
                  <tr>
                    <th>Jurisdiction</th>
                    <th>Tax Regime</th>
                    <th>Standard / Reduced</th>
                    <th>B2B Reverse Charge</th>
                    <th>Reporting Std</th>
                  </tr>
                </thead>
                <tbody>
                  {taxProfiles.map((tp) => (
                    <tr key={tp.id}>
                      <td>
                        <strong>
                          {tp.country_code} — {tp.region_label}
                        </strong>
                      </td>
                      <td>{tp.tax_name}</td>
                      <td>
                        {(tp.standard_rate_bps / 100).toFixed(2)}% /{" "}
                        {(tp.reduced_rate_bps / 100).toFixed(2)}%
                      </td>
                      <td>
                        {tp.reverse_charge_b2b ? "Supported (0%)" : "N/A"}
                      </td>
                      <td>
                        <code>{tp.reporting_standard}</code> (
                        {tp.default_currency})
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 style={{ margin: "0 0 8px" }}>
              Live Cross-Border VAT / Sales Tax Calculator
            </h3>
            <form onSubmit={(e) => void onCalculateTax(e)} className="usr-grid">
              <label htmlFor={taxProfInputId}>
                Tax Profile
                <select
                  id={taxProfInputId}
                  value={taxProfId}
                  onChange={(e) => setTaxProfId(e.target.value)}
                >
                  {taxProfiles.map((tp) => (
                    <option key={tp.id} value={tp.id}>
                      {tp.country_code} — {tp.tax_name} (
                      {(tp.standard_rate_bps / 100).toFixed(2)}%)
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={taxSubId}>
                Invoice Net Subtotal
                <input
                  id={taxSubId}
                  type="number"
                  step="0.01"
                  min="0"
                  value={taxSubAmt}
                  onChange={(e) => setTaxSubAmt(e.target.value)}
                />
              </label>
              <label htmlFor={taxB2bId} className="usr-check">
                <input
                  id={taxB2bId}
                  type="checkbox"
                  checked={taxB2bCross}
                  onChange={(e) => setTaxB2bCross(e.target.checked)}
                />
                Cross-border B2B (apply EU/UK Reverse Charge if eligible)
              </label>
              <label htmlFor={taxRedId} className="usr-check">
                <input
                  id={taxRedId}
                  type="checkbox"
                  checked={taxReduced}
                  onChange={(e) => setTaxReduced(e.target.checked)}
                />
                Use Reduced Tax Rate
              </label>
              <div style={{ alignSelf: "end" }}>
                <button type="submit" className="usr-small-btn">
                  Calculate Tax
                </button>
              </div>
            </form>
            {taxPreview && (
              <p role="status" className="hold-note" style={{ marginTop: 12 }}>
                <strong>{taxPreview.tax_label}</strong> (
                {taxPreview.reporting_standard}) — Subtotal{" "}
                {(taxPreview.subtotal_minor / 100).toFixed(2)} + Tax{" "}
                {(taxPreview.tax_minor / 100).toFixed(2)} ={" "}
                <strong>{(taxPreview.total_minor / 100).toFixed(2)}</strong>
              </p>
            )}
          </section>

          <section className="usr-card" aria-labelledby="payment-rails-h">
            <h2 id="payment-rails-h" style={{ margin: "0 0 10px" }}>
              Local &amp; International Payment Rails (0% AMARKAL Fee)
            </h2>
            <div
              style={{ overflowX: "auto" }}
              tabIndex={0}
              role="region"
              aria-label="Local payment rails table"
            >
              <table className="mgmt-table">
                <thead>
                  <tr>
                    <th>Payment Rail</th>
                    <th>Country</th>
                    <th>Currency</th>
                    <th>Settlement Instructions</th>
                  </tr>
                </thead>
                <tbody>
                  {rails.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <strong>{r.display_name}</strong>
                      </td>
                      <td>{r.country_code}</td>
                      <td>
                        <code>{r.currency}</code>
                      </td>
                      <td>{r.settlement_instructions}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
