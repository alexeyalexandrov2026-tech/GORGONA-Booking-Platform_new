"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AccountType,
  BankFeedsSummary,
  BankStatementImportResponse,
  BankTransactionView,
  buildBankFeedCsv,
  createBankAccount,
  fetchBankFeedsSummary,
  fetchBankTransactions,
  importBankStatement,
  reconcileBankTransaction,
  ReconciliationStatus,
  SAMPLE_CHASE_CSV,
  SAMPLE_WELLS_FARGO_OFX,
  savePlaidCredentials,
  syncPlaidSandboxFeed,
} from "../lib/bank-feeds-api";
import { triggerCsvDownload } from "../lib/csv-export";
import { ManagementApiError } from "../lib/management-api";

type BankTab = "feed" | "import" | "plaid";

const CATEGORY_OPTIONS = [
  "client_payment",
  "revenue_inflow",
  "payroll",
  "fleet_fuel",
  "operating_expense",
  "software_cloud",
  "facilities_rent",
  "tax_payment",
  "bank_fee",
] as const;

function formatUsd(cents: number): string {
  const neg = cents < 0;
  const abs = Math.abs(cents) / 100;
  return `${neg ? "-$" : "$"}${abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function statusBadgeStyle(status: ReconciliationStatus): React.CSSProperties {
  if (status === "reconciled") {
    return {
      background: "#e9f6ee",
      borderColor: "#a9dbb9",
      color: "#165430",
    };
  }
  if (status === "suggested") {
    return {
      background: "#eef4fc",
      borderColor: "#a7c4eb",
      color: "#1f4e79",
    };
  }
  if (status === "excluded") {
    return {
      background: "#f1f3f7",
      borderColor: "#d4d8e2",
      color: "#464b59",
    };
  }
  return {
    background: "#fbf7ee",
    borderColor: "#e0cfa6",
    color: "#6b4e16",
  };
}

export function BankFeedsHub({ businessId }: { businessId: string }) {
  const [activeTab, setActiveTab] = useState<BankTab>("feed");
  const [summary, setSummary] = useState<BankFeedsSummary | null>(null);
  const [transactions, setTransactions] = useState<BankTransactionView[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Filters
  const [filterAccountId, setFilterAccountId] = useState<string>("");
  const [filterStatus, setFilterStatus] = useState<"" | ReconciliationStatus>(
    "",
  );
  const [selectedCategories, setSelectedCategories] = useState<
    Record<string, string>
  >({});

  // Add Account form
  const [showAddAccount, setShowAddAccount] = useState(false);
  const [instName, setInstName] = useState("Chase Business");
  const [acctName, setAcctName] = useState("Operating Checking");
  const [acctMask, setAcctMask] = useState("4821");
  const [acctType, setAcctType] = useState<AccountType>("checking");
  const [acctBalanceUsd, setAcctBalanceUsd] = useState("148250.00");

  // Import Statement form
  const [importAccountId, setImportAccountId] = useState<string>("");
  const [importFormat, setImportFormat] = useState<
    "auto" | "ofx" | "qfx" | "qbo" | "csv"
  >("auto");
  const [rawStatement, setRawStatement] = useState<string>("");
  const [importResult, setImportResult] =
    useState<BankStatementImportResponse | null>(null);

  // Plaid BYOK & Sandbox form
  const [plaidEnv, setPlaidEnv] = useState<"sandbox" | "production">("sandbox");
  const [plaidClientId, setPlaidClientId] = useState("");
  const [plaidSecret, setPlaidSecret] = useState("");
  const [sandboxBank, setSandboxBank] = useState("Chase Business");
  const [sandboxMask, setSandboxMask] = useState("4821");

  const reloadAll = async (
    acctId: string = filterAccountId,
    st: "" | ReconciliationStatus = filterStatus,
  ) => {
    const [sum, txs] = await Promise.all([
      fetchBankFeedsSummary(businessId),
      fetchBankTransactions(businessId, {
        account_id: acctId || undefined,
        reconciliation_status: st || undefined,
      }),
    ]);
    setSummary(sum);
    setTransactions(txs);
    if (!importAccountId && sum.accounts[0]) {
      setImportAccountId(sum.accounts[0].id);
    }
  };

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchBankFeedsSummary(businessId),
      fetchBankTransactions(businessId, {
        account_id: filterAccountId || undefined,
        reconciliation_status: filterStatus || undefined,
      }),
    ])
      .then(([sum, txs]) => {
        if (!active) return;
        setSummary(sum);
        setTransactions(txs);
        const firstAcct = sum.accounts[0];
        if (firstAcct) {
          setImportAccountId((prev) => prev || firstAcct.id);
        }
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof ManagementApiError
            ? err.message
            : "Unable to load US Bank Feeds.",
        );
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, filterAccountId, filterStatus]);

  const effectiveImportAccountId = useMemo(() => {
    if (importAccountId) return importAccountId;
    return summary?.accounts[0]?.id ?? "";
  }, [importAccountId, summary]);

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const parsedBal = Number.parseFloat(acctBalanceUsd.replace(/,/g, ""));
      const balCents = Number.isFinite(parsedBal)
        ? Math.round(parsedBal * 100)
        : 0;
      const created = await createBankAccount(businessId, {
        institution_name: instName.trim(),
        account_name: acctName.trim(),
        account_mask: acctMask.trim(),
        account_type: acctType,
        currency: "USD",
        current_balance_cents: balCents,
      });
      setImportAccountId(created.id);
      setShowAddAccount(false);
      await reloadAll();
      setNotice(
        `Connected ${created.institution_name} (${created.account_name} ••${created.account_mask}).`,
      );
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Failed to register US bank account.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleStatementImport = async (dryRun: boolean) => {
    if (!effectiveImportAccountId) {
      setError("Create or select a US bank account first.");
      return;
    }
    if (rawStatement.trim().length < 8) {
      setError("Upload or paste an OFX, QFX, QBO, or CSV bank statement.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await importBankStatement(
        businessId,
        effectiveImportAccountId,
        {
          source_format: importFormat,
          raw_content: rawStatement,
          dry_run: dryRun,
        },
      );
      setImportResult(res);
      if (!dryRun) {
        await reloadAll();
        setNotice(
          `Imported ${res.imported_count} transactions (${res.detected_format.toUpperCase()}); ${res.duplicate_skipped_count} duplicates skipped, ${res.suggested_match_count} smart matches ready for approval.`,
        );
      } else {
        setNotice(
          `Dry-run preview parsed ${res.parsed_count} transactions (${res.detected_format.toUpperCase()}) with ${res.suggested_match_count} auto-match suggestions. Zero rows written yet.`,
        );
      }
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Unable to parse bank statement.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleFilePick = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const txt = await file.text();
      setRawStatement(txt);
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext === "ofx" || ext === "qfx" || ext === "qbo" || ext === "csv") {
        setImportFormat(ext);
      } else {
        setImportFormat("auto");
      }
      setNotice(`Loaded statement file "${file.name}" (${txt.length} bytes).`);
    } catch {
      setError("Could not read selected statement file.");
    }
  };

  const handleReconcile = async (
    tx: BankTransactionView,
    action: "confirm_match" | "manual_category" | "exclude" | "unmatch",
  ) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const chosenCat = selectedCategories[tx.id] ?? tx.category_hint;
      await reconcileBankTransaction(businessId, tx.id, {
        action,
        category_hint: chosenCat,
      });
      await reloadAll();
      const labelMap = {
        confirm_match: "Confirmed ledger match and reconciled transaction.",
        manual_category: `Categorized transaction under "${chosenCat}" and marked reconciled.`,
        exclude: "Excluded transaction from reconciliation queue.",
        unmatch: "Returned transaction to unmatched queue.",
      };
      setNotice(labelMap[action]);
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Reconciliation update failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleSavePlaid = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await savePlaidCredentials(businessId, {
        plaid_env: plaidEnv,
        client_id: plaidClientId.trim(),
        secret: plaidSecret.trim(),
      });
      setPlaidClientId("");
      setPlaidSecret("");
      await reloadAll();
      setNotice(
        `Saved Plaid ${plaidEnv.toUpperCase()} BYOK credentials in AMARKAL AES-256-GCM Secret Vault.`,
      );
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Failed to save encrypted Plaid credentials.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handlePlaidSandboxSync = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await syncPlaidSandboxFeed(businessId, {
        institution_name: sandboxBank,
        account_name: "Operating Checking",
        account_mask: sandboxMask,
      });
      setImportAccountId(res.account.id);
      await reloadAll();
      setActiveTab("feed");
      setNotice(res.message);
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Plaid sandbox feed sync failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const handleExportCsv = () => {
    const csv = buildBankFeedCsv(transactions);
    triggerCsvDownload("amarkal-us-bank-reconciliation.csv", csv);
    setNotice("Exported US bank feed reconciliation CSV.");
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
                US BANK FEEDS · PG18 FORCE RLS
              </span>
              <span className="usr-badge">OFX / QFX / QBO / CSV + PLAID</span>
              <span className="usr-badge">HUMAN-IN-THE-LOOP MATCHING</span>
            </div>
            <h1 style={{ margin: "0 0 6px", fontSize: "1.65rem" }}>
              US Bank Feeds &amp; Auto-Reconciliation
            </h1>
            <p className="usr-muted" style={{ margin: 0 }}>
              Connect Chase, Bank of America, Wells Fargo, Mercury, or Relay via
              encrypted Plaid BYOK or instant OFX / QFX / QBO / CSV statement
              upload, and reconcile bank lines against FIN-03 invoices, POs,
              Stripe settlements, and US Payroll runs.
            </p>
          </div>
          <div className="usr-inline">
            <button
              type="button"
              className="button usr-small-btn"
              onClick={() => setShowAddAccount((prev) => !prev)}
            >
              {showAddAccount ? "Close Form" : "+ Add US Bank Account"}
            </button>
            <button
              type="button"
              className="button secondary usr-small-btn"
              onClick={handleExportCsv}
              disabled={transactions.length === 0}
            >
              Export Reconciled CSV
            </button>
          </div>
        </div>

        <div
          role="tablist"
          aria-label="US Bank Feeds workspace sections"
          className="usr-tablist"
          style={{ marginTop: "18px", marginBottom: 0 }}
        >
          <button
            type="button"
            role="tab"
            id="tab-bank-feed"
            aria-selected={activeTab === "feed"}
            aria-controls="panel-bank-feed"
            className="usr-tab"
            onClick={() => setActiveTab("feed")}
          >
            Reconciliation Feed ({summary?.total_transactions ?? 0})
          </button>
          <button
            type="button"
            role="tab"
            id="tab-bank-import"
            aria-selected={activeTab === "import"}
            aria-controls="panel-bank-import"
            className="usr-tab"
            onClick={() => setActiveTab("import")}
          >
            Import OFX / QFX / QBO / CSV
          </button>
          <button
            type="button"
            role="tab"
            id="tab-bank-plaid"
            aria-selected={activeTab === "plaid"}
            aria-controls="panel-bank-plaid"
            className="usr-tab"
            onClick={() => setActiveTab("plaid")}
          >
            Direct US Bank Feeds (Plaid BYOK)
          </button>
        </div>
      </section>

      {error ? (
        <div className="usr-errors" role="alert">
          <strong>Bank Feed error:</strong> {error}
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

      {showAddAccount ? (
        <section className="usr-card" aria-labelledby="add-bank-acct-h">
          <h2 id="add-bank-acct-h" style={{ marginBottom: "12px" }}>
            Register US Business Bank Account
          </h2>
          <form onSubmit={handleCreateAccount} className="usr-stack">
            <div className="usr-grid">
              <label>
                US Institution Name
                <input
                  type="text"
                  value={instName}
                  onChange={(e) => setInstName(e.target.value)}
                  required
                  minLength={2}
                  maxLength={120}
                />
              </label>
              <label>
                Account Label
                <input
                  type="text"
                  value={acctName}
                  onChange={(e) => setAcctName(e.target.value)}
                  required
                  minLength={2}
                  maxLength={120}
                />
              </label>
              <label>
                Last 4 Digits (Mask)
                <input
                  type="text"
                  value={acctMask}
                  onChange={(e) => setAcctMask(e.target.value)}
                  required
                  pattern="[0-9A-Za-z]{2,8}"
                />
              </label>
              <label>
                Account Type
                <select
                  value={acctType}
                  onChange={(e) => setAcctType(e.target.value as AccountType)}
                >
                  <option value="checking">Business Checking</option>
                  <option value="savings">Business Savings</option>
                  <option value="credit_card">Corporate Credit Card</option>
                  <option value="treasury">Treasury / Sweep</option>
                </select>
              </label>
              <label>
                Opening / Current Balance (USD)
                <input
                  type="text"
                  value={acctBalanceUsd}
                  onChange={(e) => setAcctBalanceUsd(e.target.value)}
                />
              </label>
            </div>
            <div className="usr-inline">
              <button
                type="submit"
                className="button usr-small-btn"
                disabled={busy}
              >
                Save US Bank Account
              </button>
              <button
                type="button"
                className="button secondary usr-small-btn"
                onClick={() => setShowAddAccount(false)}
              >
                Cancel
              </button>
            </div>
          </form>
        </section>
      ) : null}

      {summary ? (
        <section aria-label="US Bank Feeds KPI summary">
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(220px, 100%), 1fr))",
              gap: "16px",
            }}
          >
            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Connected US Balance</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#111318",
                }}
              >
                {formatUsd(summary.total_balance_cents)}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                {summary.accounts.length} active US bank accounts
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Reconciliation Rate</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#165430",
                }}
              >
                {summary.reconciliation_rate_pct.toFixed(1)}%
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                {summary.reconciled_count} reconciled of{" "}
                {summary.total_transactions - summary.excluded_count} active
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Smart Matches Ready</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#1f4e79",
                }}
              >
                {summary.suggested_count}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Awaiting 1-click Human-in-the-Loop confirmation
              </div>
            </article>

            <article className="usr-card" style={{ marginBottom: 0 }}>
              <span className="usr-muted">Unmatched Queue</span>
              <div
                style={{
                  fontSize: "1.55rem",
                  fontWeight: 700,
                  margin: "6px 0 4px",
                  color: "#6b4e16",
                }}
              >
                {summary.unmatched_count}
              </div>
              <div className="usr-muted" style={{ fontSize: "0.82rem" }}>
                Plaid BYOK:{" "}
                {summary.plaid_status.configured
                  ? `${summary.plaid_status.plaid_env.toUpperCase()} Ready`
                  : "Sandbox Ready"}
              </div>
            </article>
          </div>
        </section>
      ) : null}

      {activeTab === "feed" ? (
        <section
          id="panel-bank-feed"
          role="tabpanel"
          aria-labelledby="tab-bank-feed"
          className="usr-card"
        >
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "12px",
              marginBottom: "16px",
            }}
          >
            <div>
              <h2 id="bank-feed-heading" style={{ marginBottom: "4px" }}>
                Bank Transaction Reconciliation Queue
              </h2>
              <p className="usr-muted" style={{ margin: 0 }}>
                Review auto-matched FIN-03 invoices, POs, Stripe settlements,
                and US payroll runs — or categorize unmatched items in 1 click.
              </p>
            </div>
            <div className="usr-inline">
              <label style={{ margin: 0 }}>
                <span className="sr-only">Filter by bank account</span>
                <select
                  aria-label="Filter by bank account"
                  value={filterAccountId}
                  onChange={(e) => setFilterAccountId(e.target.value)}
                >
                  <option value="">All US Accounts</option>
                  {summary?.accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.institution_name} · ••{a.account_mask}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ margin: 0 }}>
                <span className="sr-only">Filter by reconciliation status</span>
                <select
                  aria-label="Filter by reconciliation status"
                  value={filterStatus}
                  onChange={(e) =>
                    setFilterStatus(e.target.value as "" | ReconciliationStatus)
                  }
                >
                  <option value="">All Statuses</option>
                  <option value="suggested">Suggested Matches</option>
                  <option value="unmatched">Unmatched</option>
                  <option value="reconciled">Reconciled</option>
                  <option value="excluded">Excluded</option>
                </select>
              </label>
            </div>
          </div>

          {loading ? (
            <p className="usr-muted">Loading US bank transactions...</p>
          ) : transactions.length === 0 ? (
            <div
              style={{
                padding: "20px",
                border: "1px dashed var(--line)",
                borderRadius: "12px",
                background: "#fafbfc",
              }}
            >
              <p style={{ marginTop: 0, fontWeight: 600 }}>
                No US bank transactions imported yet.
              </p>
              <p className="usr-muted">
                Upload an OFX / QFX / QBO / CSV statement from Chase, Bank of
                America, Wells Fargo, or Mercury — or run a 1-click Plaid
                Sandbox sync to test live reconciliation immediately.
              </p>
              <div className="usr-inline">
                <button
                  type="button"
                  className="button usr-small-btn"
                  disabled={busy}
                  onClick={handlePlaidSandboxSync}
                >
                  Sync Plaid Sandbox Feed (Chase ••4821)
                </button>
                <button
                  type="button"
                  className="button secondary usr-small-btn"
                  onClick={() => setActiveTab("import")}
                >
                  Upload OFX / CSV Statement →
                </button>
              </div>
            </div>
          ) : (
            <div
              style={{ overflowX: "auto" }}
              tabIndex={0}
              role="region"
              aria-label="Bank reconciliation transactions table"
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
                    <th style={{ padding: "8px 10px" }}>Date</th>
                    <th style={{ padding: "8px 10px" }}>
                      Account &amp; Description
                    </th>
                    <th style={{ padding: "8px 10px", textAlign: "right" }}>
                      Amount
                    </th>
                    <th style={{ padding: "8px 10px" }}>Status &amp; Match</th>
                    <th style={{ padding: "8px 10px" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => {
                    const currentCat =
                      selectedCategories[tx.id] ?? tx.category_hint;
                    return (
                      <tr
                        key={tx.id}
                        style={{ borderBottom: "1px solid var(--line)" }}
                      >
                        <td
                          style={{
                            padding: "10px",
                            whiteSpace: "nowrap",
                            fontWeight: 600,
                          }}
                        >
                          {tx.posted_date}
                          <div
                            className="usr-muted"
                            style={{ fontSize: "0.74rem" }}
                          >
                            {tx.source_format.toUpperCase()}
                          </div>
                        </td>
                        <td style={{ padding: "10px" }}>
                          <div style={{ fontWeight: 600, color: "#111318" }}>
                            {tx.description}
                          </div>
                          <div
                            className="usr-muted"
                            style={{ fontSize: "0.78rem" }}
                          >
                            {tx.account_label} · {tx.merchant_name}
                          </div>
                        </td>
                        <td
                          style={{
                            padding: "10px",
                            textAlign: "right",
                            fontWeight: 700,
                            whiteSpace: "nowrap",
                            color:
                              tx.direction === "credit" ? "#165430" : "#8a1c19",
                          }}
                        >
                          {tx.direction === "credit" ? "+" : "-"}
                          {formatUsd(tx.amount_cents)}
                        </td>
                        <td style={{ padding: "10px" }}>
                          <span
                            className="usr-badge"
                            style={statusBadgeStyle(tx.reconciliation_status)}
                          >
                            {tx.reconciliation_status.toUpperCase()}
                            {tx.match_confidence > 0
                              ? ` · ${tx.match_confidence}%`
                              : ""}
                          </span>
                          {tx.matched_entity_label ? (
                            <div
                              style={{
                                fontSize: "0.8rem",
                                marginTop: "4px",
                                color: "#111318",
                              }}
                            >
                              {tx.matched_entity_label}
                            </div>
                          ) : (
                            <div
                              className="usr-muted"
                              style={{ fontSize: "0.78rem", marginTop: "4px" }}
                            >
                              Hint: {tx.category_hint}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "10px" }}>
                          <div className="usr-inline" style={{ gap: "6px" }}>
                            {tx.reconciliation_status === "suggested" ? (
                              <button
                                type="button"
                                className="button usr-small-btn"
                                disabled={busy}
                                onClick={() =>
                                  handleReconcile(tx, "confirm_match")
                                }
                              >
                                Confirm Match
                              </button>
                            ) : null}

                            {tx.reconciliation_status === "unmatched" ||
                            tx.reconciliation_status === "suggested" ? (
                              <>
                                <select
                                  aria-label={`Category for ${tx.description}`}
                                  value={currentCat}
                                  onChange={(e) =>
                                    setSelectedCategories((prev) => ({
                                      ...prev,
                                      [tx.id]: e.target.value,
                                    }))
                                  }
                                  style={{ minHeight: "36px", padding: "4px" }}
                                >
                                  {CATEGORY_OPTIONS.map((c) => (
                                    <option key={c} value={c}>
                                      {c}
                                    </option>
                                  ))}
                                </select>
                                <button
                                  type="button"
                                  className="button secondary usr-small-btn"
                                  disabled={busy}
                                  onClick={() =>
                                    handleReconcile(tx, "manual_category")
                                  }
                                >
                                  Reconcile
                                </button>
                                <button
                                  type="button"
                                  className="usr-small-btn usr-danger"
                                  disabled={busy}
                                  onClick={() => handleReconcile(tx, "exclude")}
                                >
                                  Exclude
                                </button>
                              </>
                            ) : (
                              <button
                                type="button"
                                className="button secondary usr-small-btn"
                                disabled={busy}
                                onClick={() => handleReconcile(tx, "unmatch")}
                              >
                                Unmatch
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}

      {activeTab === "import" ? (
        <section
          id="panel-bank-import"
          role="tabpanel"
          aria-labelledby="tab-bank-import"
          className="usr-card"
        >
          <h2 id="bank-import-heading" style={{ marginBottom: "6px" }}>
            Universal US Bank Statement Importer (OFX / QFX / QBO / CSV)
          </h2>
          <p className="usr-muted" style={{ marginTop: 0 }}>
            Upload or paste statements exported from Chase, Bank of America,
            Wells Fargo, Mercury, or Relay. Deterministic FITID &amp; SHA-256
            deduplication prevents duplicate imports when date ranges overlap.
          </p>

          <div className="usr-stack">
            <div className="usr-grid">
              <label>
                Target US Bank Account
                <select
                  value={effectiveImportAccountId}
                  onChange={(e) => setImportAccountId(e.target.value)}
                >
                  {summary?.accounts.length ? (
                    summary.accounts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.institution_name} · {a.account_name} (••
                        {a.account_mask})
                      </option>
                    ))
                  ) : (
                    <option value="">
                      No accounts yet — add one above first
                    </option>
                  )}
                </select>
              </label>

              <label>
                Statement Format
                <select
                  value={importFormat}
                  onChange={(e) =>
                    setImportFormat(
                      e.target.value as "auto" | "ofx" | "qfx" | "qbo" | "csv",
                    )
                  }
                >
                  <option value="auto">Auto-Detect (OFX / QFX / CSV)</option>
                  <option value="ofx">OFX (Open Financial Exchange)</option>
                  <option value="qfx">QFX (Quicken Web Connect)</option>
                  <option value="qbo">QBO (QuickBooks Web Connect)</option>
                  <option value="csv">US Bank CSV</option>
                </select>
              </label>

              <label>
                Upload Statement File (.ofx, .qfx, .qbo, .csv)
                <input
                  type="file"
                  accept=".ofx,.qfx,.qbo,.csv,.txt"
                  onChange={handleFilePick}
                />
              </label>
            </div>

            <div className="usr-inline">
              <button
                type="button"
                className="button secondary usr-small-btn"
                onClick={() => {
                  setImportFormat("csv");
                  setRawStatement(SAMPLE_CHASE_CSV);
                }}
              >
                Load Chase CSV Sample
              </button>
              <button
                type="button"
                className="button secondary usr-small-btn"
                onClick={() => {
                  setImportFormat("ofx");
                  setRawStatement(SAMPLE_WELLS_FARGO_OFX);
                }}
              >
                Load Wells Fargo OFX Sample
              </button>
            </div>

            <label>
              Statement Payload (OFX / QFX / QBO / CSV)
              <textarea
                className="usr-textarea"
                rows={8}
                value={rawStatement}
                onChange={(e) => setRawStatement(e.target.value)}
                placeholder="Paste Chase/BofA/Wells Fargo CSV or OFX/QBO XML/SGML text..."
              />
            </label>

            <div className="usr-inline">
              <button
                type="button"
                className="button secondary usr-small-btn"
                disabled={busy || !effectiveImportAccountId}
                onClick={() => handleStatementImport(true)}
              >
                Preview (Dry Run)
              </button>
              <button
                type="button"
                className="button usr-small-btn"
                disabled={busy || !effectiveImportAccountId}
                onClick={() => handleStatementImport(false)}
              >
                Import &amp; Run Auto-Match
              </button>
            </div>

            {importResult ? (
              <div
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: "12px",
                  padding: "16px",
                  background: "#fafbfc",
                }}
              >
                <div className="usr-inline" style={{ marginBottom: "10px" }}>
                  <span className="usr-badge usr-badge-ai">
                    Format: {importResult.detected_format.toUpperCase()}
                  </span>
                  <span className="usr-badge">
                    Parsed: {importResult.parsed_count}
                  </span>
                  <span className="usr-badge">
                    Auto-Matches: {importResult.suggested_match_count}
                  </span>
                  {importResult.detected_balance_cents !== null ? (
                    <span className="usr-badge">
                      Ledger Balance:{" "}
                      {formatUsd(importResult.detected_balance_cents)}
                    </span>
                  ) : null}
                </div>

                {importResult.errors.length > 0 ? (
                  <ul
                    style={{
                      color: "#8a1c19",
                      fontSize: "0.86rem",
                      margin: "0 0 12px",
                    }}
                  >
                    {importResult.errors.map((errMsg, i) => (
                      <li key={i}>{errMsg}</li>
                    ))}
                  </ul>
                ) : null}

                {importResult.preview.length > 0 ? (
                  <div
                    style={{ overflowX: "auto" }}
                    tabIndex={0}
                    role="region"
                    aria-label="Statement import preview table"
                  >
                    <table
                      style={{ width: "100%", borderCollapse: "collapse" }}
                    >
                      <thead>
                        <tr
                          style={{
                            borderBottom: "1px solid var(--line)",
                            textAlign: "left",
                          }}
                        >
                          <th style={{ padding: "6px 8px" }}>Date</th>
                          <th style={{ padding: "6px 8px" }}>Description</th>
                          <th style={{ padding: "6px 8px" }}>Category Hint</th>
                          <th
                            style={{ padding: "6px 8px", textAlign: "right" }}
                          >
                            Amount
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {importResult.preview.map((row) => (
                          <tr
                            key={row.external_tx_id}
                            style={{ borderBottom: "1px solid var(--line)" }}
                          >
                            <td style={{ padding: "6px 8px" }}>
                              {row.posted_date}
                            </td>
                            <td style={{ padding: "6px 8px" }}>
                              {row.description}
                            </td>
                            <td style={{ padding: "6px 8px" }}>
                              <span className="usr-badge">
                                {row.category_hint}
                              </span>
                            </td>
                            <td
                              style={{
                                padding: "6px 8px",
                                textAlign: "right",
                                fontWeight: 600,
                                color:
                                  row.direction === "credit"
                                    ? "#165430"
                                    : "#8a1c19",
                              }}
                            >
                              {row.direction === "credit" ? "+" : "-"}
                              {formatUsd(row.amount_cents)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {activeTab === "plaid" ? (
        <section
          id="panel-bank-plaid"
          role="tabpanel"
          aria-labelledby="tab-bank-plaid"
          className="usr-stack"
        >
          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 id="plaid-sandbox-heading" style={{ marginBottom: "6px" }}>
              1-Click Plaid Sandbox US Bank Sync
            </h2>
            <p className="usr-muted" style={{ marginTop: 0 }}>
              Test end-to-end US bank feed ingestion and Human-in-the-Loop
              reconciliation immediately with realistic ACH / wire / payroll /
              fuel transactions before switching to live Plaid Production keys.
            </p>
            <div className="usr-grid">
              <label>
                US Bank Institution
                <select
                  value={sandboxBank}
                  onChange={(e) => setSandboxBank(e.target.value)}
                >
                  {(summary?.plaid_status.supported_institutions ?? []).map(
                    (inst) => (
                      <option key={inst.id} value={inst.name}>
                        {inst.name} ({inst.rail})
                      </option>
                    ),
                  )}
                </select>
              </label>
              <label>
                Account Mask (Last 4 Digits)
                <input
                  type="text"
                  value={sandboxMask}
                  onChange={(e) => setSandboxMask(e.target.value)}
                  pattern="[0-9A-Za-z]{2,8}"
                />
              </label>
            </div>
            <button
              type="button"
              className="button usr-small-btn"
              disabled={busy}
              onClick={handlePlaidSandboxSync}
            >
              Sync Plaid Sandbox Feed Now
            </button>
          </div>

          <div className="usr-card" style={{ marginBottom: 0 }}>
            <div className="usr-inline" style={{ marginBottom: "8px" }}>
              <span className="usr-badge usr-badge-ai">
                AES-256-GCM TENANT SECRET VAULT
              </span>
              <span className="usr-badge">
                Status:{" "}
                {summary?.plaid_status.configured
                  ? `Configured (${summary.plaid_status.plaid_env.toUpperCase()} · ${summary.plaid_status.client_id_hint ?? "stored"})`
                  : "Not yet configured"}
              </span>
            </div>
            <h2 style={{ marginBottom: "6px" }}>
              Plaid Direct US Bank Connector (BYOK Credentials)
            </h2>
            <p className="usr-muted" style={{ marginTop: 0 }}>
              Connect 12,000+ US financial institutions directly using your own
              Plaid Sandbox or Production keys. Credentials are encrypted
              per-tenant with AES-256-GCM AAD and never exposed back to the
              browser.
            </p>
            <form onSubmit={handleSavePlaid} className="usr-stack">
              <div className="usr-grid">
                <label>
                  Plaid Environment
                  <select
                    value={plaidEnv}
                    onChange={(e) =>
                      setPlaidEnv(e.target.value as "sandbox" | "production")
                    }
                  >
                    <option value="sandbox">Plaid Sandbox (Free Test)</option>
                    <option value="production">
                      Plaid Production (Live US Banks)
                    </option>
                  </select>
                </label>
                <label>
                  Plaid Client ID
                  <input
                    type="text"
                    value={plaidClientId}
                    onChange={(e) => setPlaidClientId(e.target.value)}
                    placeholder="66f1a2b3c4d5e6f7..."
                    required
                    minLength={6}
                  />
                </label>
                <label>
                  Plaid Secret
                  <input
                    type="password"
                    value={plaidSecret}
                    onChange={(e) => setPlaidSecret(e.target.value)}
                    placeholder="Encrypted immediately in Vault"
                    required
                    minLength={8}
                  />
                </label>
              </div>
              <div className="usr-inline">
                <button
                  type="submit"
                  className="button usr-small-btn"
                  disabled={busy}
                >
                  Save Encrypted Plaid Keys
                </button>
              </div>
            </form>
          </div>
        </section>
      ) : null}
    </div>
  );
}
