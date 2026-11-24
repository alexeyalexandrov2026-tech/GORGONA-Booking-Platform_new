"use client";

// O7b (package O): the budget per line and phase as the server derives it (O3a decision 1) and the
// commitments against it: subcontracts and purchase orders, revised as a whole with the revision read.
import React, { useId, useState } from "react";
import {
  createCommitment,
  fetchCommitment,
  refusal,
  reviseCommitment,
  type CommitmentLineBody,
} from "../lib/construction-api";
import type {
  Budget,
  BudgetLine,
  Commitment,
  CommitmentSummary,
  Project,
} from "../lib/construction-contracts";
import { formatMinor, toMinor } from "../lib/construction-rules";
import type { Party } from "./construction";

const KIND_LABEL: Record<CommitmentSummary["kind"], string> = {
  subcontract: "Subcontract",
  purchase_order: "Purchase order",
};
const ROLE: Record<CommitmentSummary["kind"], string> = {
  subcontract: "contractor",
  purchase_order: "supplier",
};

/** "Contract line 2" or "Change order 1 line 3": the scope a figure belongs to. */
export function lineName(changeOrder: number | null, position: number): string {
  return changeOrder === null
    ? `Contract line ${position}`
    : `Change order ${changeOrder} line ${position}`;
}
export const lineKey = (changeOrder: number | null, position: number) =>
  `${changeOrder ?? 0}:${position}`;
export const lineLabel = (line: {
  change_order: number | null;
  position: number;
  phase: string;
  description: string;
}) =>
  `${lineName(line.change_order, line.position)} · ${line.phase} · ${line.description}`;

function flags(row: { over_committed: boolean; over_budget: boolean }) {
  const words = [
    row.over_committed ? "Over committed" : "",
    row.over_budget ? "Over budget" : "",
  ].filter(Boolean);
  return words.length ? words.join(", ") : "—";
}

export function BudgetPanel({
  project,
  places,
  budget,
}: {
  project: Project;
  places: number;
  budget: Budget;
}) {
  const headingId = useId();
  const money = (minor: number) => formatMinor(minor, places);
  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Budget</h3>
      <p className="muted">
        {`Budget ${money(budget.budget_minor)}, committed ${money(budget.committed_minor)}, actual ${money(budget.actual_minor)}, remaining ${money(budget.remaining_minor)} ${project.currency}.`}
      </p>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Budget lines table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Budget lines">
          <thead>
            <tr>
              <th scope="col">Line</th>
              <th scope="col">Phase</th>
              <th scope="col">Description</th>
              <th scope="col">Budget</th>
              <th scope="col">Committed</th>
              <th scope="col">Uncommitted</th>
              <th scope="col">Actual</th>
              <th scope="col">Remaining</th>
              <th scope="col">Flags</th>
            </tr>
          </thead>
          <tbody>
            {budget.lines.map((line) => (
              <tr key={lineKey(line.change_order, line.position)}>
                <th scope="row">
                  {lineName(line.change_order, line.position)}
                </th>
                <td>{line.phase}</td>
                <td>{line.description}</td>
                <td>{money(line.budget_minor)}</td>
                <td>{money(line.committed_minor)}</td>
                <td>{money(line.uncommitted_minor)}</td>
                <td>{money(line.actual_minor)}</td>
                <td>{money(line.remaining_minor)}</td>
                <td>{flags(line)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Budget by phase table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Budget by phase">
          <thead>
            <tr>
              <th scope="col">Phase</th>
              <th scope="col">Budget</th>
              <th scope="col">Committed</th>
              <th scope="col">Actual</th>
              <th scope="col">Remaining</th>
              <th scope="col">Flags</th>
            </tr>
          </thead>
          <tbody>
            {budget.phases.map((phase) => (
              <tr key={phase.phase}>
                <th scope="row">{phase.phase}</th>
                <td>{money(phase.budget_minor)}</td>
                <td>{money(phase.committed_minor)}</td>
                <td>{money(phase.actual_minor)}</td>
                <td>{money(phase.remaining_minor)}</td>
                <td>{flags(phase)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

type Row = { key: string; line: string; amount: string };
const blankRow = (): Row => ({
  key: crypto.randomUUID(),
  line: "",
  amount: "",
});

export function Commitments({
  businessId,
  project,
  places,
  budget,
  commitments,
  parties,
  onChanged,
}: {
  businessId: string;
  project: Project;
  places: number;
  budget: Budget;
  commitments: CommitmentSummary[];
  parties: Party[];
  onChanged: (text: string) => Promise<void>;
}) {
  const headingId = useId();
  const [editing, setEditing] = useState<Commitment | null>(null);
  // A saved form starts again empty: its key changes.
  const [round, setRound] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const money = (minor: number) => formatMinor(minor, places);
  const partyName = (id: string) =>
    parties.find((p) => p.id === id)?.name ?? "Unknown counterparty";

  async function open(number: number) {
    setError(null);
    try {
      setEditing(await fetchCommitment(businessId, project.project_id, number));
    } catch (failure) {
      setError(`The commitment could not be read: ${refusal(failure)}`);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Commitments</h3>
      {commitments.length === 0 ? (
        <p className="muted">No commitments yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Commitments table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Commitments">
            <thead>
              <tr>
                <th scope="col">Number</th>
                <th scope="col">Kind</th>
                <th scope="col">Counterparty</th>
                <th scope="col">Title</th>
                <th scope="col">State</th>
                <th scope="col">Revision</th>
                <th scope="col">Total ({project.currency})</th>
              </tr>
            </thead>
            <tbody>
              {commitments.map((c) => (
                <tr key={c.number}>
                  <th scope="row">
                    <button
                      type="button"
                      className="link-button"
                      aria-pressed={editing?.number === c.number}
                      onClick={() => void open(c.number)}
                    >
                      {`Commitment ${c.number}`}
                    </button>
                  </th>
                  <td>{KIND_LABEL[c.kind]}</td>
                  <td>{partyName(c.counterparty_id)}</td>
                  <td>{c.title}</td>
                  <td>{c.state === "open" ? "Open" : "Cancelled"}</td>
                  <td>{c.revision}</td>
                  <td>{money(c.total_minor)}</td>
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
      <CommitmentForm
        key={editing ? `${editing.number}:${editing.revision}` : `new:${round}`}
        businessId={businessId}
        project={project}
        places={places}
        lines={budget.lines}
        parties={parties}
        editing={editing}
        onCancel={() => setEditing(null)}
        onSaved={async (saved) => {
          setEditing(null);
          setRound((n) => n + 1);
          await onChanged(
            `Commitment ${saved.number} saved as revision ${saved.revision}.`,
          );
        }}
      />
    </section>
  );
}

function CommitmentForm({
  businessId,
  project,
  places,
  lines,
  parties,
  editing,
  onCancel,
  onSaved,
}: {
  businessId: string;
  project: Project;
  places: number;
  lines: BudgetLine[];
  parties: Party[];
  editing: Commitment | null;
  onCancel: () => void;
  onSaved: (saved: Commitment) => Promise<void>;
}) {
  const [kind, setKind] = useState<CommitmentSummary["kind"] | "">(
    editing?.kind ?? "",
  );
  const [party, setParty] = useState(editing?.counterparty_id ?? "");
  const [state, setState] = useState<CommitmentSummary["state"]>(
    editing?.state ?? "open",
  );
  const [title, setTitle] = useState(editing?.title ?? "");
  const [reference, setReference] = useState(editing?.reference ?? "");
  const [note, setNote] = useState(editing?.note ?? "");
  const [rows, setRows] = useState<Row[]>(() =>
    editing
      ? editing.lines.map((l) => ({
          key: crypto.randomUUID(),
          line: lineKey(l.change_order, l.position),
          amount: formatMinor(l.amount_minor, places),
        }))
      : [blankRow()],
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const eligible = kind
    ? parties.filter((p) => p.roles.includes(ROLE[kind]))
    : [];
  const change = (index: number, field: "line" | "amount", value: string) =>
    setRows((list) =>
      list.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const body: CommitmentLineBody[] = [];
    for (const [index, row] of rows.entries()) {
      const line = lines.find(
        (l) => lineKey(l.change_order, l.position) === row.line,
      );
      const amount = toMinor(row.amount, places);
      if (!line || amount === null || amount < 1) {
        setError(
          `Commitment line ${index + 1}: choose a budget line and an amount above 0 with at most ${places} decimal places.`,
        );
        return;
      }
      body.push({
        change_order: line.change_order,
        position: line.position,
        amount_minor: amount,
      });
    }
    setBusy(true);
    try {
      const common = {
        title: title.trim(),
        reference: reference.trim() || null,
        note: note.trim() || null,
        lines: body,
      };
      const saved = editing
        ? await reviseCommitment(
            businessId,
            project.project_id,
            editing.number,
            {
              schema_version: 1,
              expected_revision: editing.revision,
              state,
              ...common,
            },
          )
        : await createCommitment(businessId, project.project_id, {
            schema_version: 1,
            kind: kind as CommitmentSummary["kind"],
            counterparty_id: party,
            ...common,
          });
      await onSaved(saved);
    } catch (failure) {
      setError(`The commitment was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      aria-label={
        editing ? `Revise commitment ${editing.number}` : "Commitment"
      }
      onSubmit={submit}
    >
      <h4>
        {editing
          ? `Revise commitment ${editing.number} (revision ${editing.revision})`
          : "New commitment"}
      </h4>
      <label>
        Kind
        <select
          value={kind}
          disabled={editing !== null}
          onChange={(e) => {
            setKind(e.target.value as CommitmentSummary["kind"] | "");
            setParty("");
          }}
          required
        >
          <option value="">Choose</option>
          <option value="subcontract">Subcontract</option>
          <option value="purchase_order">Purchase order</option>
        </select>
      </label>
      <label>
        Counterparty
        <select
          value={party}
          disabled={editing !== null}
          onChange={(e) => setParty(e.target.value)}
          required
        >
          <option value="">Choose</option>
          {(editing
            ? parties.filter((p) => p.id === editing.counterparty_id)
            : eligible
          ).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </label>
      {editing && (
        <label>
          State
          <select
            value={state}
            onChange={(e) =>
              setState(e.target.value as CommitmentSummary["state"])
            }
          >
            <option value="open">Open</option>
            <option value="cancelled">Cancelled (final)</option>
          </select>
        </label>
      )}
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
        Reference
        <input
          value={reference}
          maxLength={64}
          onChange={(e) => setReference(e.target.value)}
        />
      </label>
      <label>
        Note
        <input
          value={note}
          maxLength={1000}
          onChange={(e) => setNote(e.target.value)}
        />
      </label>
      {rows.map((row, index) => (
        <div
          key={row.key}
          className="construction-line"
          role="group"
          aria-label={`Commitment line ${index + 1}`}
        >
          <label>
            {`Commitment line ${index + 1} budget line`}
            <select
              value={row.line}
              onChange={(e) => change(index, "line", e.target.value)}
              required
            >
              <option value="">Choose</option>
              {lines.map((l) => (
                <option
                  key={lineKey(l.change_order, l.position)}
                  value={lineKey(l.change_order, l.position)}
                >
                  {lineLabel(l)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {`Commitment line ${index + 1} amount`}
            <input
              value={row.amount}
              inputMode="decimal"
              onChange={(e) => change(index, "amount", e.target.value)}
              required
            />
          </label>
          {rows.length > 1 && (
            <button
              type="button"
              onClick={() =>
                setRows((list) => list.filter((_, i) => i !== index))
              }
            >
              {`Remove commitment line ${index + 1}`}
            </button>
          )}
        </div>
      ))}
      <div className="mgmt-form-actions">
        {rows.length < 200 && (
          <button
            type="button"
            onClick={() => setRows((list) => [...list, blankRow()])}
          >
            Add a commitment line
          </button>
        )}
        {editing && (
          <button type="button" onClick={onCancel}>
            New commitment instead
          </button>
        )}
        <button type="submit" disabled={busy}>
          Save commitment
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
