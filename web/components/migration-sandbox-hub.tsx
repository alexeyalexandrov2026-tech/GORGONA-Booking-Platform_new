"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { triggerCsvDownload } from "../lib/csv-export";
import {
  clearSampleSandbox,
  importMigrationCsv,
  seedSampleSandbox,
  type MigrationEntityKind,
  type MigrationImportResponse,
  type SampleSandboxResponse,
  type SourcePlatform,
} from "../lib/migration-api";

const PLATFORM_LABELS: Record<SourcePlatform, string> = {
  quickbooks: "QuickBooks Online",
  zoho: "Zoho CRM / Books / One",
  odoo: "Odoo ERP",
  shopify: "Shopify",
  square: "Square",
  excel_csv: "Excel / Generic CSV",
};

const ENTITY_LABELS: Record<MigrationEntityKind, string> = {
  counterparties: "Clients & Vendors (Counterparties)",
  mrp_materials: "MRP II Materials, Inventory & SKUs",
  eam_assets: "Fleet & Industrial IoT Assets (EAM)",
  payroll_profiles: "US Payroll Employee Profiles",
};

const SAMPLE_TEMPLATES: Record<MigrationEntityKind, string> = {
  counterparties:
    "Company Name,Email Address,Phone Number,Contact Type\nMidwest Freight Solutions,billing@midwestfreight.example,+1-312-555-0140,Customer\nGreat Lakes Steel Supply,orders@glsteel.example,+1-312-555-0188,Vendor\n",
  mrp_materials:
    "Item Code,Product Name,Type,UOM,Qty,Unit Cost,Supplier\nSTL-4130,Chromoly Steel Tubing,raw,ton,8.5,1120.00,Nucor Steel\nCOAT-EPX,Marine Epoxy Primer,raw,gallon,45,38.50,PPG Industrial\n",
  eam_assets:
    "Unit Number,Vehicle,Category,VIN,Yard,Engine Hours\nTRK-205,Kenworth T680 Sleeper,fleet_vehicle,1XKYDP9X-DEMO,Chicago Yard B,1240\nCNC-09,Haas VF-4 Mill,cnc_industrial,HAAS-VF4-9921,Plant Floor 1,3100\n",
  payroll_profiles:
    "Emp ID,Employee Name,State,Pay Type,Hourly Rate,Union Local\nEMP-201,Taylor Brooks,CA,hourly,46.00,IBT Local 705\nEMP-202,Morgan Reed,TX,hourly,34.50,\n",
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Operation failed.";
}

export function MigrationSandboxHub({ businessId }: { businessId: string }) {
  const [sourcePlatform, setSourcePlatform] =
    useState<SourcePlatform>("quickbooks");
  const [entityKind, setEntityKind] =
    useState<MigrationEntityKind>("counterparties");
  const [csvText, setCsvText] = useState<string>(
    SAMPLE_TEMPLATES.counterparties,
  );
  const [busyImport, setBusyImport] = useState(false);
  const [busySandbox, setBusySandbox] = useState(false);
  const [result, setResult] = useState<MigrationImportResponse | null>(null);
  const [sandboxResult, setSandboxResult] =
    useState<SampleSandboxResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const platformId = useId();
  const entityId = useId();
  const fileInputId = useId();
  const csvAreaId = useId();

  function onSelectEntity(next: MigrationEntityKind) {
    setEntityKind(next);
    setCsvText(SAMPLE_TEMPLATES[next]);
    setResult(null);
    setError(null);
  }

  async function onFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 250_000) {
      setError("Please upload CSV files under 250 KB (up to 500 rows/batch).");
      return;
    }
    const text = await file.text();
    setCsvText(text);
    setResult(null);
    setError(null);
    setNotice(`Loaded ${file.name} (${text.length.toLocaleString()} chars).`);
  }

  async function onRunImport(dryRun: boolean) {
    if (!csvText.trim()) {
      setError("Paste CSV text or upload a .csv file first.");
      return;
    }
    setBusyImport(true);
    setError(null);
    setNotice(null);
    try {
      const res = await importMigrationCsv(businessId, {
        source_platform: sourcePlatform,
        entity_kind: entityKind,
        csv_text: csvText,
        dry_run: dryRun,
      });
      setResult(res);
      setNotice(
        dryRun
          ? `Preview ready: ${res.parsed_count} valid row(s), ${res.errors.length} error(s). Review below before importing.`
          : `Migration complete from ${PLATFORM_LABELS[res.source_platform]}: ${res.imported_count} imported, ${res.skipped_count} skipped, ${res.errors.length} error(s).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusyImport(false);
    }
  }

  async function onSeedSandbox() {
    setBusySandbox(true);
    setError(null);
    setNotice(null);
    try {
      const res = await seedSampleSandbox(businessId);
      setSandboxResult(res);
      setNotice(res.message);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusySandbox(false);
    }
  }

  async function onClearSandbox() {
    setBusySandbox(true);
    setError(null);
    setNotice(null);
    try {
      const res = await clearSampleSandbox(businessId);
      setSandboxResult(res);
      setNotice(res.message);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusySandbox(false);
    }
  }

  const previewColumns =
    result && result.preview_rows.length > 0
      ? Object.keys(result.preview_rows[0] ?? {})
      : [];

  return (
    <div className="usr-stack">
      <div className="mgmt-section-header">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.6rem" }}>
            1-Click Competitor Migration &amp; Enterprise Sample Sandbox
          </h1>
          <p className="usr-muted" style={{ margin: "4px 0 0" }}>
            Move customers, vendors, MRP II materials, fleet assets, and US
            payroll profiles from QuickBooks, Zoho, Odoo, Shopify, Square, or
            Excel in minutes — or populate realistic <code>[DEMO]</code> records
            across all modules in 1 click.
          </p>
        </div>
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

      {/* 1-Click Sample Enterprise Sandbox */}
      <section className="usr-card" aria-labelledby="sandbox-heading">
        <div
          className="usr-inline"
          style={{ justifyContent: "space-between", gap: 12 }}
        >
          <div>
            <h2 id="sandbox-heading" style={{ margin: 0 }}>
              1-Click Enterprise Sample Sandbox (<code>[DEMO]</code> Data)
            </h2>
            <p className="usr-muted" style={{ margin: "6px 0 0" }}>
              Test every flagship module immediately without typing test forms:
              loads sample MRP II BOM recipe, IoT truck &amp; 500h predictive
              rule, Omnichannel Inbox thread, California §510 Payroll profile,
              open EUR FX receivable, and No-Code Kanban board. All sample items
              are clearly tagged <code>[DEMO]</code> and removable in 1 click.
            </p>
          </div>
          <div className="usr-inline" style={{ gap: 8 }}>
            <button
              type="button"
              className="usr-small-btn"
              disabled={busySandbox}
              onClick={() => void onSeedSandbox()}
            >
              {busySandbox ? "Working…" : "Load Sample Business Data"}
            </button>
            <button
              type="button"
              className="secondary usr-small-btn"
              disabled={busySandbox}
              onClick={() => void onClearSandbox()}
            >
              Clear [DEMO] Records
            </button>
          </div>
        </div>

        {sandboxResult && (
          <div className="usr-inline" style={{ marginTop: 14, gap: 8 }}>
            <Link
              href="/industrial/"
              className="button secondary usr-small-btn"
            >
              Inspect MRP II &amp; IoT →
            </Link>
            <Link href="/inbox/" className="button secondary usr-small-btn">
              Open Client Inbox →
            </Link>
            <Link
              href="/global-finance/"
              className="button secondary usr-small-btn"
            >
              Open US Payroll &amp; FX →
            </Link>
            <Link href="/workspace/" className="button secondary usr-small-btn">
              Open Kanban Studio →
            </Link>
          </div>
        )}
      </section>

      {/* 1-Click Competitor CSV Migration Wizard */}
      <section className="usr-card" aria-labelledby="csv-wizard-heading">
        <h2 id="csv-wizard-heading" style={{ margin: "0 0 8px" }}>
          Competitor CSV Migration Wizard (Up to 500 Rows / Batch)
        </h2>
        <p className="usr-muted" style={{ margin: "0 0 14px" }}>
          Automatically maps column headers from QuickBooks, Zoho, Odoo,
          Shopify, Square, and Excel. Run a dry-run validation preview first so
          zero malformed rows ever touch your isolated PostgreSQL 18 workspace.
        </p>

        <div className="usr-grid" style={{ marginBottom: 14 }}>
          <label htmlFor={platformId}>
            Migrating From
            <select
              id={platformId}
              value={sourcePlatform}
              onChange={(e) =>
                setSourcePlatform(e.target.value as SourcePlatform)
              }
            >
              {Object.entries(PLATFORM_LABELS).map(([k, lbl]) => (
                <option key={k} value={k}>
                  {lbl}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={entityId}>
            Target AMARKAL Module
            <select
              id={entityId}
              value={entityKind}
              onChange={(e) =>
                onSelectEntity(e.target.value as MigrationEntityKind)
              }
            >
              {Object.entries(ENTITY_LABELS).map(([k, lbl]) => (
                <option key={k} value={k}>
                  {lbl}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={fileInputId}>
            Upload CSV File (optional)
            <input
              id={fileInputId}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => void onFileUpload(e)}
            />
          </label>
        </div>

        <label htmlFor={csvAreaId}>
          CSV Content (editable before import)
          <textarea
            id={csvAreaId}
            className="usr-textarea"
            rows={7}
            value={csvText}
            onChange={(e) => setCsvText(e.target.value)}
            style={{ fontFamily: "monospace", fontSize: "0.84rem" }}
          />
        </label>

        <div className="usr-inline" style={{ marginTop: 12, gap: 8 }}>
          <button
            type="button"
            className="secondary usr-small-btn"
            onClick={() =>
              triggerCsvDownload(
                `amarkal_${entityKind}_template.csv`,
                SAMPLE_TEMPLATES[entityKind],
              )
            }
          >
            Download Template CSV
          </button>
          <button
            type="button"
            className="secondary usr-small-btn"
            disabled={busyImport}
            onClick={() => void onRunImport(true)}
          >
            {busyImport ? "Validating…" : "Preview & Validate (Dry-Run)"}
          </button>
          <button
            type="button"
            className="usr-small-btn"
            disabled={busyImport}
            onClick={() => void onRunImport(false)}
          >
            {busyImport ? "Importing…" : "Import Records into AMARKAL"}
          </button>
        </div>

        {result && (
          <div className="usr-stack" style={{ marginTop: 16 }}>
            <div className="usr-inline" style={{ gap: 8 }}>
              <span className="usr-badge usr-badge-ai">
                Parsed: {result.parsed_count}
              </span>
              {!result.dry_run && (
                <span className="usr-badge usr-badge-ai">
                  Imported: {result.imported_count}
                </span>
              )}
              {result.skipped_count > 0 && (
                <span className="usr-badge usr-badge-fallback">
                  Skipped (existing): {result.skipped_count}
                </span>
              )}
              {result.errors.length > 0 && (
                <span className="usr-badge usr-badge-off">
                  Row errors: {result.errors.length}
                </span>
              )}
            </div>

            {result.errors.length > 0 && (
              <ul className="usr-field-error" style={{ margin: 0 }}>
                {result.errors.slice(0, 10).map((er) => (
                  <li key={`${er.row_number}-${er.message}`}>
                    Row {er.row_number}: {er.message}
                  </li>
                ))}
              </ul>
            )}

            {result.preview_rows.length > 0 && (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="CSV migration preview table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      {previewColumns.map((col) => (
                        <th key={col}>{col}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.preview_rows.map((row, idx) => (
                      <tr key={idx}>
                        {previewColumns.map((col) => (
                          <td key={col}>{String(row[col] ?? "—")}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
