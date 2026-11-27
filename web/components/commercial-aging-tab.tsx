"use client";

import {
  downloadCpaExportCsv,
  type AgingReportView,
} from "../lib/commercial-api";

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

export function CommercialAgingTab({
  businessId,
  report,
  busy,
  setBusy,
  setError,
  setNotice,
}: {
  businessId: string;
  report: AgingReportView | null;
  busy: boolean;
  setBusy: (b: boolean) => void;
  setError: (e: string | null) => void;
  setNotice: (n: string | null) => void;
}) {
  async function handleDownloadCsv() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const csvText = await downloadCpaExportCsv(businessId);
      const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "amarkal-cpa-ar-ap-export.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setNotice("Downloaded US CPA AR/AP Aging CSV export.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not export CPA CSV.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!report) {
    return (
      <section className="usr-card">
        <p className="usr-muted">Loading AR / AP aging report…</p>
      </section>
    );
  }

  return (
    <section className="usr-card" aria-labelledby="aging-heading">
      <div
        className="usr-inline"
        style={{ justifyContent: "space-between", alignItems: "baseline" }}
      >
        <div>
          <h2 id="aging-heading">AR / AP Aging &amp; US CPA Export</h2>
          <p className="usr-muted" style={{ margin: 0 }}>
            Real-time receivables (AR) and vendor payables (AP) as of{" "}
            {report.as_of}. Export clean CSV directly for QuickBooks, Xero, or
            your CPA.
          </p>
        </div>
        <button
          type="button"
          className="usr-small-btn"
          disabled={busy}
          onClick={() => void handleDownloadCsv()}
        >
          Download CPA CSV Export
        </button>
      </div>

      <div
        className="usr-table-wrap"
        style={{ marginTop: "18px" }}
        tabIndex={0}
      >
        <table className="usr-table">
          <thead>
            <tr>
              <th scope="col">Ledger Side</th>
              <th scope="col">Current</th>
              <th scope="col">1–30 Days</th>
              <th scope="col">31–60 Days</th>
              <th scope="col">61–90 Days</th>
              <th scope="col">90+ Days</th>
              <th scope="col">Total Open</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <strong>Accounts Receivable (AR)</strong>
                <div className="usr-muted">{report.ar.open_count} item(s)</div>
              </td>
              <td>{formatUsd(report.ar.current_cents)}</td>
              <td>{formatUsd(report.ar.days_1_30_cents)}</td>
              <td>{formatUsd(report.ar.days_31_60_cents)}</td>
              <td>{formatUsd(report.ar.days_61_90_cents)}</td>
              <td>{formatUsd(report.ar.days_90_plus_cents)}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                <strong>{formatUsd(report.ar.total_cents)}</strong>
              </td>
            </tr>
            <tr>
              <td>
                <strong>Accounts Payable (AP)</strong>
                <div className="usr-muted">{report.ap.open_count} item(s)</div>
              </td>
              <td>{formatUsd(report.ap.current_cents)}</td>
              <td>{formatUsd(report.ap.days_1_30_cents)}</td>
              <td>{formatUsd(report.ap.days_31_60_cents)}</td>
              <td>{formatUsd(report.ap.days_61_90_cents)}</td>
              <td>{formatUsd(report.ap.days_90_plus_cents)}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                <strong>{formatUsd(report.ap.total_cents)}</strong>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h3 style={{ marginTop: "24px" }}>Open Receivables &amp; Payables</h3>
      {report.items.length === 0 ? (
        <p className="usr-muted">
          No open receivables or vendor payables right now.
        </p>
      ) : (
        <div className="usr-table-wrap" tabIndex={0}>
          <table className="usr-table">
            <thead>
              <tr>
                <th scope="col">Side</th>
                <th scope="col">Document</th>
                <th scope="col">Counterparty</th>
                <th scope="col">Due Date</th>
                <th scope="col">Bucket</th>
                <th scope="col">Amount</th>
              </tr>
            </thead>
            <tbody>
              {report.items.map((item) => (
                <tr key={`${item.side}-${item.reference_number}`}>
                  <td>
                    <span
                      className={
                        "usr-badge " +
                        (item.side === "AR"
                          ? "usr-badge-ai"
                          : "usr-badge-fallback")
                      }
                    >
                      {item.side}
                    </span>
                  </td>
                  <td>
                    <strong>{item.reference_number}</strong> · {item.doc_type}
                    <div className="usr-muted">{item.status}</div>
                  </td>
                  <td>{item.counterparty_name}</td>
                  <td>
                    {item.due_date}
                    {item.days_past_due > 0 && (
                      <div className="usr-muted">
                        {item.days_past_due}d past due
                      </div>
                    )}
                  </td>
                  <td>{item.bucket}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <strong>{formatUsd(item.amount_cents)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
