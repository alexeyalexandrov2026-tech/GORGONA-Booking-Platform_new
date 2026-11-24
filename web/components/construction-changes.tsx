"use client";

// O7a (package O): change orders on the contract. A proposal adds scope (a priced line) or removes
// scope (a contract line and a quantity); the customer's answer carries its source, a withdrawal by the
// business none. The server checks every answer (O2 decisions 3-4; scope, completed and billed limits).
import React, { useId, useState } from "react";
import {
  decide,
  fetchChangeOrder,
  proposeChange,
  refusal,
  type ChangeLineBody,
  type DecisionBody,
  type Source,
} from "../lib/construction-api";
import type {
  ChangeOrder,
  ChangeOrderSummary,
  Estimate,
  Project,
} from "../lib/construction-contracts";
import {
  formatMinor,
  quantityText,
  validQuantity,
} from "../lib/construction-rules";
import {
  KIND_LABEL,
  LineFields,
  SOURCES,
  SOURCE_LABEL,
  blankLine,
  lineBody,
  siteTime,
  type LineRow,
} from "./construction-estimates";

const STATE_LABEL: Record<ChangeOrderSummary["state"], string> = {
  proposed: "Proposed",
  approved: "Approved",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};
const ANSWERS: [DecisionBody["decision"], string][] = [
  ["approved", "Approve"],
  ["rejected", "Reject"],
  ["withdrawn", "Withdraw"],
];

type ChangeRow = LineRow & { action: "add" | "remove"; contract: string };
const blankChange = (): ChangeRow => ({
  ...blankLine(),
  action: "add",
  contract: "",
});

export function ChangeOrders({
  businessId,
  project,
  places,
  original,
  orders,
  onChanged,
}: {
  businessId: string;
  project: Project;
  places: number;
  original: Estimate;
  orders: ChangeOrderSummary[];
  onChanged: (text: string) => Promise<void>;
}) {
  const headingId = useId();
  const [detail, setDetail] = useState<ChangeOrder | null>(null);
  const [error, setError] = useState<string | null>(null);
  const money = (minor: number) => formatMinor(minor, places);

  async function open(number: number) {
    setError(null);
    try {
      setDetail(await fetchChangeOrder(businessId, project.project_id, number));
    } catch (failure) {
      setError(`The change order could not be read: ${refusal(failure)}`);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Change orders</h3>
      {orders.length === 0 ? (
        <p className="muted">No change orders yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Change orders table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Change orders">
            <thead>
              <tr>
                <th scope="col">Number</th>
                <th scope="col">Title</th>
                <th scope="col">State</th>
                <th scope="col">Days</th>
                <th scope="col">Cost ({project.currency})</th>
                <th scope="col">Price ({project.currency})</th>
                <th scope="col">Answered</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.number}>
                  <th scope="row">
                    <button
                      type="button"
                      className="link-button"
                      aria-pressed={detail?.number === o.number}
                      onClick={() => void open(o.number)}
                    >
                      {`Change order ${o.number}`}
                    </button>
                  </th>
                  <td>{o.title}</td>
                  <td>{STATE_LABEL[o.state]}</td>
                  <td>{o.days_delta}</td>
                  <td>{money(o.cost_minor)}</td>
                  <td>{money(o.price_minor)}</td>
                  <td>
                    {o.decided_at
                      ? `${siteTime(o.decided_at, project.time_zone)}${o.source ? ` · ${SOURCE_LABEL[o.source]}` : ""}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {detail && (
        <>
          <h4>{`Change order ${detail.number}: ${detail.title}`}</h4>
          {detail.reason && <p className="muted">{detail.reason}</p>}
          <div
            className="mgmt-table-container"
            role="region"
            aria-label={`Change order ${detail.number} lines table`}
            tabIndex={0}
          >
            <table
              className="mgmt-table"
              aria-label={`Change order ${detail.number} lines`}
            >
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">Action</th>
                  <th scope="col">Contract line</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Description</th>
                  <th scope="col">Phase</th>
                  <th scope="col">Quantity</th>
                  <th scope="col">Cost</th>
                  <th scope="col">Price</th>
                </tr>
              </thead>
              <tbody>
                {detail.lines.map((line) => (
                  <tr key={line.position}>
                    <th scope="row">{line.position}</th>
                    <td>{line.action === "add" ? "Add" : "Remove"}</td>
                    <td>{line.contract_position ?? "—"}</td>
                    <td>{KIND_LABEL[line.kind]}</td>
                    <td>{line.description}</td>
                    <td>{line.phase}</td>
                    <td>{`${quantityText(line.quantity)} ${line.unit}`}</td>
                    <td>{money(line.cost_minor)}</td>
                    <td>{money(line.price_minor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {detail.state === "proposed" && (
            <AnswerForm
              key={detail.number}
              businessId={businessId}
              project={project}
              number={detail.number}
              onAnswered={async (answered) => {
                setDetail(answered);
                await onChanged(
                  `Change order ${answered.number} is ${STATE_LABEL[answered.state].toLowerCase()}.`,
                );
              }}
            />
          )}
        </>
      )}
      <ProposeForm
        businessId={businessId}
        project={project}
        places={places}
        original={original}
        onProposed={(order) =>
          onChanged(`Change order ${order.number} proposed.`)
        }
      />
    </section>
  );
}

function AnswerForm({
  businessId,
  project,
  number,
  onAnswered,
}: {
  businessId: string;
  project: Project;
  number: number;
  onAnswered: (order: ChangeOrder) => Promise<void>;
}) {
  const [decision, setDecision] = useState<DecisionBody["decision"] | "">("");
  const [source, setSource] = useState<Source | "">("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const withdrawal = decision === "withdrawn";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!decision || (!withdrawal && !source)) return;
    setError(null);
    setBusy(true);
    try {
      const answered = await decide(businessId, project.project_id, number, {
        schema_version: 1,
        decision,
        source: withdrawal ? null : (source as Source),
        note: note.trim() || null,
      });
      await onAnswered(answered);
    } catch (failure) {
      setError(`The answer was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form aria-label={`Answer change order ${number}`} onSubmit={submit}>
      <label>
        Answer
        <select
          value={decision}
          onChange={(e) =>
            setDecision(e.target.value as DecisionBody["decision"] | "")
          }
          required
        >
          <option value="">Choose</option>
          {ANSWERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Source
        <select
          value={withdrawal ? "" : source}
          onChange={(e) => setSource(e.target.value as Source | "")}
          disabled={withdrawal}
          required={!withdrawal}
        >
          <option value="">
            {withdrawal ? "None: the business withdraws it" : "Choose"}
          </option>
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
          Record the answer
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

function ProposeForm({
  businessId,
  project,
  places,
  original,
  onProposed,
}: {
  businessId: string;
  project: Project;
  places: number;
  original: Estimate;
  onProposed: (order: ChangeOrder) => Promise<void>;
}) {
  const headingId = useId();
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [days, setDays] = useState("0");
  const [rows, setRows] = useState<ChangeRow[]>(() => [blankChange()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const change = (index: number, field: keyof ChangeRow, value: string) =>
    setRows((list) =>
      list.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );

  function body(row: ChangeRow, name: string): ChangeLineBody | string {
    if (row.action === "add") {
      const line = lineBody(row, places, name);
      return typeof line === "string" ? line : { action: "add", ...line };
    }
    if (!row.contract) return `${name}: choose a contract line.`;
    if (!validQuantity(row.quantity.trim()))
      return `${name}: the quantity must be above 0 with at most 4 decimal places.`;
    return {
      action: "remove",
      contract_position: Number(row.contract),
      quantity: row.quantity.trim(),
    };
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^-?\d{1,4}$/.test(days.trim()) || Math.abs(Number(days)) > 3650) {
      setError("Days are a whole number between -3650 and 3650.");
      return;
    }
    const lines: ChangeLineBody[] = [];
    for (const [index, row] of rows.entries()) {
      const line = body(row, `Change line ${index + 1}`);
      if (typeof line === "string") {
        setError(line);
        return;
      }
      lines.push(line);
    }
    setBusy(true);
    try {
      const order = await proposeChange(businessId, project.project_id, {
        schema_version: 1,
        title: title.trim(),
        reason: reason.trim() || null,
        days_delta: Number(days.trim()),
        lines,
      });
      setTitle("");
      setReason("");
      setDays("0");
      setRows([blankChange()]);
      await onProposed(order);
    } catch (failure) {
      setError(`The change order was not proposed: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h4 id={headingId}>Propose a change order</h4>
      <form aria-label="Propose a change order" onSubmit={submit}>
        <label>
          Title
          <input
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            required
          />
        </label>
        <label>
          Reason
          <input
            value={reason}
            maxLength={1000}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <label>
          Days
          <input
            value={days}
            inputMode="numeric"
            onChange={(e) => setDays(e.target.value)}
            required
          />
        </label>
        {rows.map((row, index) => {
          const name = `Change line ${index + 1}`;
          return (
            <div
              key={row.key}
              className="construction-line"
              role="group"
              aria-label={name}
            >
              <label>
                {name} action
                <select
                  value={row.action}
                  onChange={(e) => change(index, "action", e.target.value)}
                >
                  <option value="add">Add scope</option>
                  <option value="remove">Remove scope</option>
                </select>
              </label>
              {row.action === "add" ? (
                <LineFields
                  row={row}
                  name={name}
                  onChange={(field, value) => change(index, field, value)}
                />
              ) : (
                <>
                  <label>
                    {name} contract line
                    <select
                      value={row.contract}
                      onChange={(e) =>
                        change(index, "contract", e.target.value)
                      }
                      required
                    >
                      <option value="">Choose</option>
                      {original.lines.map((line) => (
                        <option key={line.position} value={line.position}>
                          {`${line.position} · ${line.description} · ${quantityText(line.quantity)} ${line.unit}`}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {name} quantity
                    <input
                      value={row.quantity}
                      inputMode="decimal"
                      onChange={(e) =>
                        change(index, "quantity", e.target.value)
                      }
                      required
                    />
                  </label>
                </>
              )}
              {rows.length > 1 && (
                <button
                  type="button"
                  onClick={() =>
                    setRows((list) => list.filter((_, i) => i !== index))
                  }
                >
                  {`Remove change line ${index + 1}`}
                </button>
              )}
            </div>
          );
        })}
        <div className="mgmt-form-actions">
          {rows.length < 200 && (
            <button
              type="button"
              onClick={() => setRows((list) => [...list, blankChange()])}
            >
              Add a change line
            </button>
          )}
          <button type="submit" disabled={busy}>
            Propose
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
