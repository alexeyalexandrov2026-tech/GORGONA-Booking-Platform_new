"use client";

import React, { useEffect, useId, useState } from "react";
import { businessToday } from "../lib/business-time";
import type {
  Acceptance,
  AcceptanceBody,
  AcceptanceList,
  AcceptanceReleaseBody,
} from "../lib/construction-acceptance-contracts";
import {
  fetchAcceptances,
  recordAcceptance,
  refusal,
  releaseAcceptanceRetainage,
} from "../lib/construction-api";
import type { Project } from "../lib/construction-contracts";
import { formatMinor } from "../lib/construction-rules";
import { ManagementApiError } from "../lib/management-api";

type Recording = { scope: "phase"; phase: string } | { scope: "final" };
type Action = Recording | { scope: "release"; record: Acceptance };

function label(record: Acceptance) {
  return record.phase ?? "Final acceptance";
}

export function ConstructionAcceptance({
  business,
  project,
  places,
  projectRevision,
  onFinalRecorded,
}: {
  business: string;
  project: Project;
  places: number;
  projectRevision: number;
  onFinalRecorded: () => void;
}) {
  const heading = useId();
  const id = project.project_id;
  const [list, setList] = useState<AcceptanceList | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [readError, setReadError] = useState("");
  const [writeError, setWriteError] = useState<{
    message: string;
    conflict: boolean;
  } | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    fetchAcceptances(business, project)
      .then((result) => {
        if (!active) return;
        setList(result);
        setReadError("");
        if (result.final) onFinalRecorded();
      })
      .catch((failure: unknown) => {
        if (active) setReadError(refusal(failure));
      });
    return () => {
      active = false;
    };
  }, [business, project, projectRevision, attempt, onFinalRecorded]);

  function reload() {
    setList(null);
    setReadError("");
    setWriteError(null);
    setAction(null);
    setAttempt((n) => n + 1);
  }

  function open(next: Action | null) {
    setWriteError(null);
    setNotice("");
    setAction(next);
  }

  async function save(write: () => Promise<Acceptance>, message: string) {
    if (busy || !list || readError) return;
    setBusy(true);
    setWriteError(null);
    try {
      const result = await write();
      if (result.scope === "final") onFinalRecorded();
      setNotice(message);
      reload();
    } catch (failure) {
      setWriteError({
        message: refusal(failure),
        conflict:
          failure instanceof ManagementApiError && failure.status === 409,
      });
    } finally {
      setBusy(false);
    }
  }

  function canRelease(record: Acceptance, value: AcceptanceList) {
    if (record.release || value.final?.release || value.held_minor <= 0)
      return false;
    if (record.scope === "final") return true;
    const phase = value.phases.find(
      (item) => item.acceptance === record.number,
    );
    return !!phase?.billed_in_full && phase.retained_minor > 0;
  }

  const money = (amount: number) =>
    `${formatMinor(amount, places)} ${project.currency}`;
  const locked = busy || !!readError;
  const today = businessToday(project.time_zone);

  return (
    <section className="construction-section" aria-labelledby={heading}>
      <h3 id={heading}>Acceptance and retainage releases</h3>
      {notice && <p role="status">{notice}</p>}
      {readError && <p role="alert">{readError}</p>}
      {writeError && <p role="alert">{writeError.message}</p>}
      {(readError || writeError?.conflict) && (
        <button type="button" disabled={busy} onClick={reload}>
          Reload acceptance records
        </button>
      )}
      {!list && !readError && <p role="status">Loading acceptance records…</p>}
      {list && (
        <>
          <p>
            Retained {money(list.retained_minor)} · Released{" "}
            {money(list.released_minor)} · Still held {money(list.held_minor)}
          </p>
          {list.phases.length > 0 && (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Acceptance by phase"
              tabIndex={0}
            >
              <table className="mgmt-table" aria-label="Acceptance by phase">
                <thead>
                  <tr>
                    <th scope="col">Phase</th>
                    <th scope="col">Work</th>
                    <th scope="col">Blocking items</th>
                    <th scope="col">Billing</th>
                    <th scope="col">Retained</th>
                    <th scope="col">Acceptance</th>
                  </tr>
                </thead>
                <tbody>
                  {list.phases.map((phase) => (
                    <tr key={phase.phase}>
                      <th scope="row">{phase.phase}</th>
                      <td>{phase.finished ? "Finished" : "In progress"}</td>
                      <td>{phase.open_items}</td>
                      <td>
                        {phase.billed_in_full
                          ? "Billed in full"
                          : "Billing incomplete"}
                      </td>
                      <td>{money(phase.retained_minor)}</td>
                      <td>
                        {phase.acceptance !== null ? (
                          `Accepted · ${phase.acceptance}`
                        ) : list.final ? (
                          "Covered by final acceptance"
                        ) : phase.finished && phase.open_items === 0 ? (
                          <button
                            type="button"
                            disabled={locked || action !== null}
                            onClick={() =>
                              open({ scope: "phase", phase: phase.phase })
                            }
                          >
                            Record acceptance for {phase.phase}
                          </button>
                        ) : (
                          "Pending"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!list.final && (
            <button
              type="button"
              disabled={locked || action !== null}
              onClick={() => open({ scope: "final" })}
            >
              Record final acceptance
            </button>
          )}
          {list.items.length === 0 ? (
            <p>No acceptance records yet.</p>
          ) : (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Acceptance records"
              tabIndex={0}
            >
              <table className="mgmt-table" aria-label="Acceptance records">
                <thead>
                  <tr>
                    <th scope="col">Record</th>
                    <th scope="col">Scope</th>
                    <th scope="col">Accepted on</th>
                    <th scope="col">Signatory and source</th>
                    <th scope="col">Warranty</th>
                    <th scope="col">Retainage release</th>
                  </tr>
                </thead>
                <tbody>
                  {list.items.map((record) => (
                    <tr key={record.number}>
                      <th scope="row">{record.number}</th>
                      <td>
                        {label(record)}
                        {record.note && <p>{record.note}</p>}
                      </td>
                      <td>{record.accepted_on}</td>
                      <td>
                        {record.signatory} · {record.source}
                      </td>
                      <td>
                        {record.warranty_ends_on
                          ? `${record.warranty_starts_on} to ${record.warranty_ends_on}`
                          : "—"}
                      </td>
                      <td>
                        {record.release ? (
                          <>
                            {money(record.release.amount_minor)} on{" "}
                            {record.release.released_on}
                            {record.release.note && (
                              <p>{record.release.note}</p>
                            )}
                          </>
                        ) : canRelease(record, list) ? (
                          <button
                            type="button"
                            disabled={locked || action !== null}
                            onClick={() => open({ scope: "release", record })}
                          >
                            Release retainage for record {record.number}
                          </button>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {action?.scope === "release" && (
            <ReleaseForm
              key={action.record.number}
              record={action.record}
              today={today}
              busy={locked}
              onCancel={() => open(null)}
              onSave={(body) =>
                void save(
                  () =>
                    releaseAcceptanceRetainage(
                      business,
                      id,
                      action.record.number,
                      body,
                    ),
                  "Retainage released.",
                )
              }
            />
          )}
          {action && action.scope !== "release" && (
            <AcceptanceForm
              key={action.scope === "final" ? "final" : action.phase}
              action={action}
              today={today}
              busy={locked}
              onCancel={() => open(null)}
              onSave={(body) =>
                void save(
                  () => recordAcceptance(business, id, body),
                  "Acceptance recorded.",
                )
              }
            />
          )}
        </>
      )}
    </section>
  );
}

function AcceptanceForm({
  action,
  today,
  busy,
  onCancel,
  onSave,
}: {
  action: Recording;
  today: string;
  busy: boolean;
  onCancel: () => void;
  onSave: (body: AcceptanceBody) => void;
}) {
  const sourceId = useId();
  const [date, setDate] = useState("");
  const [error, setError] = useState("");
  const title =
    action.scope === "phase" ? `Accept ${action.phase}` : "Final acceptance";
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const signatory = String(fields.get("signatory") ?? "").trim();
    const source = fields.get("source");
    const warranty = String(fields.get("warranty") ?? "");
    if (!signatory || (source !== "paper" && source !== "email")) {
      setError(
        "Enter the customer signatory and the source of their acceptance.",
      );
      return;
    }
    if (
      !today ||
      !date ||
      date > today ||
      (action.scope === "final" && warranty <= date)
    ) {
      setError(
        "Enter a valid site date and, for final acceptance, a later warranty end date.",
      );
      return;
    }
    setError("");
    const base: Omit<AcceptanceBody, "scope" | "phase" | "warranty_ends_on"> = {
      schema_version: 1,
      accepted_on: date,
      signatory,
      source,
      note: String(fields.get("note") ?? "").trim() || null,
    };
    onSave(
      action.scope === "phase"
        ? { ...base, ...action, warranty_ends_on: null }
        : { ...base, scope: "final", phase: null, warranty_ends_on: warranty },
    );
  }
  return (
    <form className="mgmt-form" aria-label={title} onSubmit={submit}>
      <fieldset disabled={busy}>
        <legend>{title}</legend>
        {action.scope === "final" && (
          <p>
            Final acceptance closes measurements, approvals and billing for the
            project.
          </p>
        )}
        <label>
          Acceptance date{" "}
          <input
            type="date"
            min="2000-01-01"
            max={today || undefined}
            value={date}
            onChange={(event) => setDate(event.target.value)}
            required
          />
        </label>
        <label>
          Customer signatory <input name="signatory" maxLength={200} required />
        </label>
        <label htmlFor={sourceId}>Acceptance source</label>
        <select id={sourceId} name="source" required defaultValue="">
          <option value="">Choose a source</option>
          <option value="paper">Paper</option>
          <option value="email">Email</option>
        </select>
        {action.scope === "final" && (
          <label>
            Warranty end date{" "}
            <input
              type="date"
              name="warranty"
              min={date || undefined}
              max="2100-12-31"
              required
            />
          </label>
        )}
        <label>
          Acceptance note <textarea name="note" maxLength={1000} />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit">Save acceptance</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </fieldset>
    </form>
  );
}

function ReleaseForm({
  record,
  today,
  busy,
  onCancel,
  onSave,
}: {
  record: Acceptance;
  today: string;
  busy: boolean;
  onCancel: () => void;
  onSave: (body: AcceptanceReleaseBody) => void;
}) {
  const [error, setError] = useState("");
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const date = String(fields.get("date") ?? "");
    if (!date || !today || date > today || date < record.accepted_on) {
      setError(
        "Enter a site date on or after acceptance and no later than today.",
      );
      return;
    }
    setError("");
    onSave({
      schema_version: 1,
      released_on: date,
      note: String(fields.get("note") ?? "").trim() || null,
    });
  }
  return (
    <form
      className="mgmt-form"
      aria-label={`Release retainage for record ${record.number}`}
      onSubmit={submit}
    >
      <fieldset disabled={busy}>
        <legend>Release retainage for {label(record)}</legend>
        <label>
          Release date{" "}
          <input
            name="date"
            type="date"
            min={record.accepted_on}
            max={today || undefined}
            required
          />
        </label>
        <label>
          Release note <textarea name="note" maxLength={1000} />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit">Confirm release</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </fieldset>
    </form>
  );
}
