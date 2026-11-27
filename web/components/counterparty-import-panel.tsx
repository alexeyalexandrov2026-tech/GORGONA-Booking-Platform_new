"use client";

import { useId, useState } from "react";
import { authorizedResponse } from "../lib/management-api";

type CounterpartyKind = "organization" | "person";
type CounterpartyRole = "customer" | "supplier" | "contractor" | "partner";

interface ImportRowResult {
  row_number: number;
  display_name: string;
  kind: CounterpartyKind;
  email: string | null;
  phone: string | null;
  roles: CounterpartyRole[];
  status: "valid" | "created" | "duplicate" | "error";
  message: string;
  counterparty_id: string | null;
}

interface ImportResponse {
  dry_run: boolean;
  total_rows: number;
  valid_count: number;
  created_count: number;
  duplicate_count: number;
  error_count: number;
  rows: ImportRowResult[];
}

const SAMPLE_CSV = `display_name,legal_name,kind,roles,email,phone,tax_id
Apex Freight LLC,Apex Freight Logistics LLC,organization,customer,billing@apexfreight.us,+1-312-555-0140,84-1234567
Midwest Diesel Supply,Midwest Diesel Supply Corp,organization,supplier,ap@midwestdiesel.us,+1-312-555-0199,36-7654321`;

export function CounterpartyImportPanel({
  businessId,
  enabled,
  onImported,
}: {
  businessId: string;
  enabled: boolean;
  onImported: () => void;
}) {
  const fileId = useId();
  const csvId = useId();
  const kindId = useId();
  const roleId = useId();
  const dupId = useId();

  const [csvText, setCsvText] = useState("");
  const [defaultKind, setDefaultKind] =
    useState<CounterpartyKind>("organization");
  const [defaultRole, setDefaultRole] = useState<CounterpartyRole>("customer");
  const [skipDuplicates, setSkipDuplicates] = useState(true);
  const [preview, setPreview] = useState<ImportResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function runImport(dryRun: boolean) {
    if (!csvText.trim()) {
      setError("Upload a CSV file or paste CSV rows first.");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await authorizedResponse(
        `/v1/businesses/${encodeURIComponent(businessId)}/counterparties/import`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": crypto.randomUUID(),
          },
          body: JSON.stringify({
            csv_text: csvText,
            dry_run: dryRun,
            skip_duplicates: skipDuplicates,
            default_kind: defaultKind,
            default_role: defaultRole,
          }),
        },
      );
      const data = (await res.json()) as ImportResponse;
      setPreview(data);
      if (dryRun) {
        setNotice(
          `Dry-run complete: ${data.valid_count} ready, ${data.duplicate_count} duplicate(s), ${data.error_count} error(s).`,
        );
      } else {
        setNotice(
          `Imported ${data.created_count} counterparty card(s). Skipped ${data.duplicate_count} duplicate(s).`,
        );
        if (data.created_count > 0) {
          onImported();
        }
      }
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not process CSV import.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 262_144) {
      setError(
        "CSV file must be 256 KB or smaller (up to 250 rows per batch).",
      );
      return;
    }
    const text = await file.text();
    setCsvText(text);
    setPreview(null);
    setError(null);
    setNotice(`Loaded ${file.name}. Run dry-run preview before importing.`);
  }

  return (
    <section aria-label="CSV counterparty import" className="mgmt-card">
      <details>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          Bulk CSV Import (QuickBooks, Square, Stripe, HubSpot, Excel)
        </summary>
        <div style={{ marginTop: "16px" }}>
          <p>
            Migrate up to 250 customers, suppliers, contractors, or partners per
            batch. Headers are auto-mapped and checked for duplicates before
            saving.
          </p>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {notice && <p role="status">{notice}</p>}
          <div className="cp-fields">
            <label htmlFor={fileId}>
              Upload CSV file (.csv, max 256 KB)
              <input
                id={fileId}
                type="file"
                accept=".csv,text/csv"
                disabled={!enabled || busy}
                onChange={(e) => void handleFileChange(e)}
              />
            </label>
            <label htmlFor={kindId}>
              Default entity type
              <select
                id={kindId}
                value={defaultKind}
                disabled={!enabled || busy}
                onChange={(e) => {
                  setDefaultKind(e.target.value as CounterpartyKind);
                  setPreview(null);
                }}
              >
                <option value="organization">Organization (B2B)</option>
                <option value="person">Person / Contact</option>
              </select>
            </label>
            <label htmlFor={roleId}>
              Default relationship role
              <select
                id={roleId}
                value={defaultRole}
                disabled={!enabled || busy}
                onChange={(e) => {
                  setDefaultRole(e.target.value as CounterpartyRole);
                  setPreview(null);
                }}
              >
                <option value="customer">Customer</option>
                <option value="supplier">Supplier / Vendor</option>
                <option value="contractor">Contractor / Carrier</option>
                <option value="partner">Partner</option>
              </select>
            </label>
          </div>

          <label htmlFor={dupId}>
            <input
              id={dupId}
              type="checkbox"
              checked={skipDuplicates}
              disabled={!enabled || busy}
              onChange={(e) => {
                setSkipDuplicates(e.target.checked);
                setPreview(null);
              }}
            />
            <span>
              Skip duplicate records matching existing email, phone, EIN/tax ID,
              or display name
            </span>
          </label>

          <label htmlFor={csvId}>
            CSV content
            <textarea
              id={csvId}
              rows={6}
              value={csvText}
              disabled={!enabled || busy}
              placeholder="display_name,legal_name,kind,roles,email,phone,tax_id"
              onChange={(e) => {
                setCsvText(e.target.value);
                setPreview(null);
              }}
            />
          </label>

          <div>
            <button
              type="button"
              disabled={!enabled || busy || !csvText.trim()}
              onClick={() => void runImport(true)}
            >
              {busy ? "Validating…" : "Preview import (dry run)"}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={!enabled || busy}
              onClick={() => {
                setCsvText(SAMPLE_CSV);
                setPreview(null);
                setError(null);
              }}
            >
              Load sample B2B CSV
            </button>
            {preview && preview.dry_run && preview.valid_count > 0 && (
              <button
                type="button"
                disabled={!enabled || busy}
                onClick={() => void runImport(false)}
              >
                Confirm &amp; import {preview.valid_count} counterparties
              </button>
            )}
          </div>

          {preview && (
            <div style={{ marginTop: "16px" }}>
              <p>
                <strong>
                  {preview.dry_run ? "Dry-run summary" : "Import receipt"}:
                </strong>{" "}
                {preview.total_rows} rows ·{" "}
                {preview.dry_run
                  ? `${preview.valid_count} ready`
                  : `${preview.created_count} created`}{" "}
                · {preview.duplicate_count} duplicate(s) · {preview.error_count}{" "}
                error(s)
              </p>
              {preview.rows.length > 0 && (
                <div className="mgmt-table-container">
                  <table className="mgmt-table">
                    <thead>
                      <tr>
                        <th scope="col">Row</th>
                        <th scope="col">Counterparty</th>
                        <th scope="col">Type / Roles</th>
                        <th scope="col">Status</th>
                        <th scope="col">Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.slice(0, 50).map((row) => (
                        <tr key={`${row.row_number}-${row.display_name}`}>
                          <td>{row.row_number}</td>
                          <td>
                            <strong>{row.display_name || "—"}</strong>
                            {row.email ? (
                              <div className="usr-muted">{row.email}</div>
                            ) : null}
                          </td>
                          <td>
                            {row.kind}
                            {row.roles.length
                              ? ` · ${row.roles.join(", ")}`
                              : ""}
                          </td>
                          <td>
                            <span
                              className={
                                "mgmt-status-pill " +
                                (row.status === "created" ||
                                row.status === "valid"
                                  ? "status-active"
                                  : row.status === "duplicate"
                                    ? "status-hold"
                                    : "status-cancelled")
                              }
                            >
                              {row.status}
                            </span>
                          </td>
                          <td>{row.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </details>
    </section>
  );
}
