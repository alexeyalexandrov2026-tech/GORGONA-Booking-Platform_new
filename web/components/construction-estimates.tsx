"use client";

// O7a (package O): estimate versions with the server's totals, the editor of the next version, the
// proposal and the customer's acceptance (the original contract, frozen). ADR-0035 decisions 3-6.
import React, { useId, useState } from "react";
import { businessDateTime } from "../lib/business-time";
import {
  acceptProposal,
  propose,
  refusal,
  saveEstimate,
  type LineBody,
  type Source,
} from "../lib/construction-api";
import type {
  Contract,
  Estimate,
  EstimateSummary,
  Line,
  LineKind,
  Project,
} from "../lib/construction-contracts";
import {
  formatMinor,
  quantityText,
  toMinor,
  validQuantity,
} from "../lib/construction-rules";

export const KINDS: [LineKind, string][] = [
  ["material", "Material"],
  ["labor", "Labor"],
  ["equipment", "Equipment"],
  ["subcontract", "Subcontract"],
  ["other", "Other"],
];
export const KIND_LABEL = Object.fromEntries(KINDS) as Record<LineKind, string>;
export const SOURCES: [Source, string][] = [
  ["paper", "Signed paper"],
  ["email", "Email"],
];
export const SOURCE_LABEL: Record<string, string> = {
  platform: "On the platform",
  paper: "Signed paper",
  email: "Email",
};

/** An instant in the site's own time zone, with the zone named. */
export function siteTime(instant: string, zone: string): string {
  const { date, time } = businessDateTime(instant, zone);
  return `${date} ${time} (${zone})`;
}

export type LineRow = {
  key: string;
  kind: LineKind | "";
  description: string;
  phase: string;
  quantity: string;
  unit: string;
  cost: string;
  price: string;
  material_id: string | null;
};
export const blankLine = (): LineRow => ({
  key: crypto.randomUUID(),
  kind: "",
  description: "",
  phase: "",
  quantity: "",
  unit: "",
  cost: "",
  price: "",
  material_id: null,
});
const rowOf = (line: Line, places: number): LineRow => ({
  key: crypto.randomUUID(),
  kind: line.kind,
  description: line.description,
  phase: line.phase,
  quantity: quantityText(line.quantity),
  unit: line.unit,
  cost: formatMinor(line.unit_cost_minor, places),
  price: formatMinor(line.unit_price_minor, places),
  material_id: line.material_id,
});

/** The line as the server takes it, or why it cannot be sent. */
export function lineBody(
  row: LineRow,
  places: number,
  name: string,
): LineBody | string {
  if (!row.kind) return `${name}: choose a kind.`;
  if (!validQuantity(row.quantity.trim()))
    return `${name}: the quantity must be above 0 with at most 4 decimal places.`;
  const cost = toMinor(row.cost, places);
  const price = toMinor(row.price, places);
  if (cost === null || price === null)
    return `${name}: amounts are not negative and have at most ${places} decimal places.`;
  return {
    kind: row.kind,
    description: row.description.trim(),
    phase: row.phase.trim(),
    quantity: row.quantity.trim(),
    unit: row.unit.trim(),
    unit_cost_minor: cost,
    unit_price_minor: price,
    material_id: row.material_id,
  };
}

/** The fields of one priced line; each label names its line ("Line 1 kind"). */
export function LineFields({
  row,
  name,
  onChange,
}: {
  row: LineRow;
  name: string;
  onChange: (field: keyof LineRow, value: string) => void;
}) {
  return (
    <>
      <label>
        {name} kind
        <select
          value={row.kind}
          onChange={(e) => onChange("kind", e.target.value)}
          required
        >
          <option value="">Choose</option>
          {KINDS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        {name} description
        <input
          value={row.description}
          maxLength={500}
          onChange={(e) => onChange("description", e.target.value)}
          required
        />
      </label>
      <label>
        {name} phase
        <input
          value={row.phase}
          maxLength={64}
          onChange={(e) => onChange("phase", e.target.value)}
          required
        />
      </label>
      <label>
        {name} quantity
        <input
          value={row.quantity}
          inputMode="decimal"
          onChange={(e) => onChange("quantity", e.target.value)}
          required
        />
      </label>
      <label>
        {name} unit
        <input
          value={row.unit}
          maxLength={16}
          onChange={(e) => onChange("unit", e.target.value)}
          required
        />
      </label>
      <label>
        {name} unit cost
        <input
          value={row.cost}
          inputMode="decimal"
          onChange={(e) => onChange("cost", e.target.value)}
          required
        />
      </label>
      <label>
        {name} unit price
        <input
          value={row.price}
          inputMode="decimal"
          onChange={(e) => onChange("price", e.target.value)}
          required
        />
      </label>
    </>
  );
}

export function Estimates({
  businessId,
  project,
  places,
  estimates,
  shown,
  contracted,
  onShow,
  onChanged,
}: {
  businessId: string;
  project: Project;
  places: number;
  estimates: EstimateSummary[];
  shown: Estimate | null;
  contracted: boolean;
  onShow: (version: number) => void;
  onChanged: (text: string) => Promise<void>;
}) {
  const headingId = useId();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const latest = estimates[estimates.length - 1];
  const money = (minor: number) => formatMinor(minor, places);

  async function send(version: number) {
    setError(null);
    setBusy(true);
    try {
      await propose(businessId, project.project_id, version);
      await onChanged(`Version ${version} sent as the proposal.`);
    } catch (failure) {
      setError(`The proposal was not sent: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Estimate versions</h3>
      {estimates.length === 0 ? (
        <p className="muted">No estimate versions yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Estimate versions table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Estimate versions">
            <thead>
              <tr>
                <th scope="col">Version</th>
                <th scope="col">Based on</th>
                <th scope="col">Note</th>
                <th scope="col">Proposal</th>
                <th scope="col">Cost ({project.currency})</th>
                <th scope="col">Price ({project.currency})</th>
              </tr>
            </thead>
            <tbody>
              {estimates.map((e) => (
                <tr key={e.version}>
                  <th scope="row">
                    <button
                      type="button"
                      className="link-button"
                      aria-pressed={shown?.version === e.version}
                      onClick={() => onShow(e.version)}
                    >
                      {`Version ${e.version}`}
                    </button>
                  </th>
                  <td>{e.based_on ? `Version ${e.based_on}` : "—"}</td>
                  <td>{e.note ?? "—"}</td>
                  <td>
                    {e.proposed_at
                      ? `Proposed ${siteTime(e.proposed_at, project.time_zone)}`
                      : "Draft"}
                  </td>
                  <td>{money(e.cost_total_minor)}</td>
                  <td>{money(e.price_total_minor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {latest && !latest.proposed_at && !contracted && (
        <div className="mgmt-form-actions">
          <button
            type="button"
            disabled={busy}
            onClick={() => void send(latest.version)}
          >
            {`Send version ${latest.version} as proposal`}
          </button>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {shown && (
        <>
          <h4>{`Version ${shown.version} lines`}</h4>
          <div
            className="mgmt-table-container"
            role="region"
            aria-label="Estimate lines table"
            tabIndex={0}
          >
            <table className="mgmt-table" aria-label="Estimate lines">
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Description</th>
                  <th scope="col">Phase</th>
                  <th scope="col">Quantity</th>
                  <th scope="col">Unit cost</th>
                  <th scope="col">Unit price</th>
                  <th scope="col">Cost</th>
                  <th scope="col">Price</th>
                </tr>
              </thead>
              <tbody>
                {shown.lines.map((line) => (
                  <tr key={line.position}>
                    <th scope="row">{line.position}</th>
                    <td>{KIND_LABEL[line.kind]}</td>
                    <td>{line.description}</td>
                    <td>{line.phase}</td>
                    <td>{`${quantityText(line.quantity)} ${line.unit}`}</td>
                    <td>{money(line.unit_cost_minor)}</td>
                    <td>{money(line.unit_price_minor)}</td>
                    <td>{money(line.cost_minor)}</td>
                    <td>{money(line.price_minor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

export function EstimateEditor({
  businessId,
  project,
  places,
  latest,
  onSaved,
}: {
  businessId: string;
  project: Project;
  places: number;
  latest: Estimate | null;
  onSaved: (version: number) => void;
}) {
  const headingId = useId();
  const [rows, setRows] = useState<LineRow[]>(() =>
    latest ? latest.lines.map((l) => rowOf(l, places)) : [blankLine()],
  );
  const [note, setNote] = useState(latest?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const change = (index: number, field: keyof LineRow, value: string) =>
    setRows((list) =>
      list.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const lines: LineBody[] = [];
    for (const [index, row] of rows.entries()) {
      const body = lineBody(row, places, `Line ${index + 1}`);
      if (typeof body === "string") {
        setError(body);
        return;
      }
      lines.push(body);
    }
    setBusy(true);
    try {
      const saved = await saveEstimate(businessId, project.project_id, {
        schema_version: 1,
        based_on: project.latest_version,
        note: note.trim() || null,
        lines,
      });
      onSaved(saved.version);
    } catch (failure) {
      setError(`The version was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>
        {latest
          ? `New version based on version ${latest.version}`
          : "First estimate version"}
      </h3>
      <p className="muted">
        Amounts in {project.currency}; the server adds up the totals.
      </p>
      <form aria-label="Estimate version" onSubmit={submit}>
        {rows.map((row, index) => (
          <div
            key={row.key}
            className="construction-line"
            role="group"
            aria-label={`Line ${index + 1}`}
          >
            <LineFields
              row={row}
              name={`Line ${index + 1}`}
              onChange={(field, value) => change(index, field, value)}
            />
            {rows.length > 1 && (
              <button
                type="button"
                onClick={() =>
                  setRows((list) => list.filter((_, i) => i !== index))
                }
              >
                {`Remove line ${index + 1}`}
              </button>
            )}
          </div>
        ))}
        <label>
          Note
          <input
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <div className="mgmt-form-actions">
          {rows.length < 500 && (
            <button
              type="button"
              onClick={() => setRows((list) => [...list, blankLine()])}
            >
              Add a line
            </button>
          )}
          <button type="submit" disabled={busy}>
            Save version
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

export function ContractPanel({
  businessId,
  project,
  places,
  estimates,
  contract,
  onChanged,
}: {
  businessId: string;
  project: Project;
  places: number;
  estimates: EstimateSummary[];
  contract: Contract | null;
  onChanged: (text: string) => Promise<void>;
}) {
  const headingId = useId();
  const [signatory, setSignatory] = useState("");
  const [source, setSource] = useState<Source | "">("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const latest = estimates[estimates.length - 1];
  const proposal = latest?.proposed_at ? latest : null;
  const money = (minor: number) => formatMinor(minor, places);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!proposal || !source) return;
    setError(null);
    setBusy(true);
    try {
      await acceptProposal(businessId, project.project_id, {
        schema_version: 1,
        version: proposal.version,
        signatory: signatory.trim(),
        source,
        note: note.trim() || null,
      });
      await onChanged(
        `The customer's acceptance of version ${proposal.version} is recorded.`,
      );
    } catch (failure) {
      setError(`The acceptance was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Contract</h3>
      {contract ? (
        <>
          <p>
            {`Version ${contract.version} accepted by ${contract.signatory} (${SOURCE_LABEL[contract.source]}) on ${siteTime(contract.recorded_at, project.time_zone)}.`}
          </p>
          {contract.note && <p className="muted">{contract.note}</p>}
          <p>{`Approved days: ${contract.approved_days}`}</p>
          <div
            className="mgmt-table-container"
            role="region"
            aria-label="Sums table"
            tabIndex={0}
          >
            <table className="mgmt-table" aria-label="Contract sums">
              <thead>
                <tr>
                  <th scope="col">Sum</th>
                  <th scope="col">Cost ({project.currency})</th>
                  <th scope="col">Price ({project.currency})</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">Original</th>
                  <td>{money(contract.original_cost_minor)}</td>
                  <td>{money(contract.original_price_minor)}</td>
                </tr>
                <tr>
                  <th scope="row">Approved changes</th>
                  <td>{money(contract.approved_cost_minor)}</td>
                  <td>{money(contract.approved_price_minor)}</td>
                </tr>
                <tr>
                  <th scope="row">Current</th>
                  <td>{money(contract.current_cost_minor)}</td>
                  <td>{money(contract.current_price_minor)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      ) : proposal ? (
        <form aria-label="Customer's acceptance" onSubmit={submit}>
          <p className="muted">
            {`The customer's acceptance makes version ${proposal.version} the original contract; it is never edited afterwards.`}
          </p>
          <label>
            Signatory
            <input
              value={signatory}
              maxLength={200}
              onChange={(e) => setSignatory(e.target.value)}
              required
            />
          </label>
          <label>
            Source
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as Source | "")}
              required
            >
              <option value="">Choose</option>
              {SOURCES.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Note
            <input
              value={note}
              maxLength={1000}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Record acceptance
            </button>
          </div>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
        </form>
      ) : (
        <p className="muted">
          No contract yet. Send the latest version as the proposal first.
        </p>
      )}
    </section>
  );
}
