"use client";

import React, { useEffect, useId, useState } from "react";
import { businessToday } from "../lib/business-time";
import {
  createWarrantyClaim,
  fetchWarrantyClaims,
  refusal,
} from "../lib/construction-api";
import type { Project } from "../lib/construction-contracts";
import type {
  WarrantyClaimBody,
  WarrantyList,
} from "../lib/construction-warranty-contracts";
import { formatMinor } from "../lib/construction-rules";
import { WarrantyClaimDetail } from "./construction-warranty-detail";

export function ConstructionWarranty({
  business,
  project,
  places,
  projectRevision,
  phases,
  onChanged,
}: {
  business: string;
  project: Project;
  places: number;
  projectRevision: number;
  phases: string[];
  onChanged: () => void;
}) {
  const titleId = useId();
  const [list, setList] = useState<WarrantyList | null>(null);
  const [selection, setSelection] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [readError, setReadError] = useState("");
  const [writeError, setWriteError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    fetchWarrantyClaims(business, project)
      .then((result) => {
        if (!active) return;
        setList(result);
        setReadError("");
      })
      .catch((failure: unknown) => {
        if (active) setReadError(refusal(failure));
      });
    return () => {
      active = false;
    };
  }, [attempt, business, project, projectRevision]);

  async function create(body: WarrantyClaimBody) {
    if (busy || readError) return;
    setBusy(true);
    setWriteError("");
    try {
      const saved = await createWarrantyClaim(
        business,
        project.project_id,
        body,
      );
      setNotice(`Warranty claim ${saved.number} recorded.`);
      setAdding(false);
      setSelection(saved.number);
      onChanged();
    } catch (failure) {
      setWriteError(refusal(failure));
    } finally {
      setBusy(false);
    }
  }

  const money = (minor: number) =>
    `${formatMinor(minor, places)} ${project.currency}`;
  const start = list?.warranty_starts_on;
  const end = list?.warranty_ends_on;
  const today = businessToday(project.time_zone);
  const maxDate = today && end ? (today < end ? today : end) : "";

  return (
    <section className="construction-section" aria-labelledby={titleId}>
      <h3 id={titleId}>Warranty claims</h3>
      {notice && <p role="status">{notice}</p>}
      {readError && (
        <>
          <p role="alert">{readError}</p>
          <button
            type="button"
            onClick={() => {
              setReadError("");
              setAttempt((n) => n + 1);
            }}
          >
            Reload warranty claims
          </button>
        </>
      )}
      {writeError && <p role="alert">{writeError}</p>}
      {!list && !readError && <p role="status">Loading warranty claims…</p>}
      {list && start && end && (
        <>
          <p>
            Warranty {start} to {end} · Active repair costs{" "}
            {money(list.repair_minor)}
          </p>
          {!adding && (
            <button
              type="button"
              disabled={!!readError || !maxDate || maxDate < start}
              onClick={() => {
                setNotice("");
                setSelection(null);
                setAdding(true);
              }}
            >
              New warranty claim
            </button>
          )}
          {list.items.length === 0 ? (
            <p>No warranty claims recorded.</p>
          ) : (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Warranty claim register"
              tabIndex={0}
            >
              <table
                className="mgmt-table"
                aria-label="Warranty claim register"
              >
                <thead>
                  <tr>
                    <th scope="col">Claim</th>
                    <th scope="col">Phase</th>
                    <th scope="col">Reported on</th>
                    <th scope="col">Status</th>
                    <th scope="col">Repair costs</th>
                  </tr>
                </thead>
                <tbody>
                  {list.items.map((item) => (
                    <tr key={item.number}>
                      <th scope="row">
                        <button
                          type="button"
                          disabled={adding}
                          aria-expanded={selection === item.number}
                          onClick={() =>
                            setSelection((current) =>
                              current === item.number ? null : item.number,
                            )
                          }
                        >
                          {item.number}. {item.title}
                        </button>
                      </th>
                      <td>{item.phase ?? "—"}</td>
                      <td>{item.raised_on}</td>
                      <td>{item.state}</td>
                      <td>{money(item.repair_minor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {adding && (
            <NewClaimForm
              minDate={start}
              maxDate={maxDate}
              phases={phases}
              busy={busy || !!readError}
              onSave={(body) => void create(body)}
              onCancel={() => {
                setAdding(false);
                setWriteError("");
              }}
            />
          )}
        </>
      )}
      {list && !start && (
        <p>Record final acceptance to open the warranty period.</p>
      )}
      {selection !== null && (
        <WarrantyClaimDetail
          key={selection}
          business={business}
          project={project}
          number={selection}
          places={places}
          projectRevision={projectRevision}
          onChanged={onChanged}
        />
      )}
    </section>
  );
}

function NewClaimForm({
  minDate,
  maxDate,
  phases,
  busy,
  onSave,
  onCancel,
}: {
  minDate: string;
  maxDate: string;
  phases: string[];
  busy: boolean;
  onSave: (body: WarrantyClaimBody) => void;
  onCancel: () => void;
}) {
  const phaseId = useId();
  const [error, setError] = useState("");
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const read = (key: string) => String(fields.get(key) ?? "").trim();
    const title = read("title");
    const reporter = read("reported_by");
    const date = read("date");
    const phase = String(fields.get("phase") ?? "");
    const description = read("description");
    const location = read("location");
    if (
      !title ||
      !reporter ||
      !date ||
      date < minDate ||
      date > maxDate ||
      (phase && !phases.includes(phase))
    ) {
      setError(
        "Enter the title, reporter and a site date inside the warranty period.",
      );
      return;
    }
    if (
      Array.from(title).length > 120 ||
      Array.from(reporter).length > 200 ||
      Array.from(location).length > 200 ||
      Array.from(description).length > 4000
    ) {
      setError(
        "Use up to 120 characters for the title, 200 for the reporter or location, and 4000 for the description.",
      );
      return;
    }
    setError("");
    onSave({
      schema_version: 1,
      title,
      reported_by: reporter,
      raised_on: date,
      phase: phase || null,
      location: location || null,
      description: description || null,
    });
  }
  return (
    <form
      className="mgmt-form"
      aria-label="New warranty claim"
      onSubmit={submit}
    >
      <fieldset disabled={busy}>
        <legend>New warranty claim</legend>
        <label>
          Claim title <input name="title" maxLength={240} required />
        </label>
        <label>
          Reported by <input name="reported_by" maxLength={400} required />
        </label>
        <label>
          Reported on{" "}
          <input name="date" type="date" min={minDate} max={maxDate} required />
        </label>
        <label htmlFor={phaseId}>Claim phase</label>
        <select id={phaseId} name="phase" defaultValue="">
          <option value="">No phase</option>
          {phases.map((phase) => (
            <option key={phase} value={phase}>
              {phase}
            </option>
          ))}
        </select>
        <label>
          Claim location <input name="location" maxLength={400} />
        </label>
        <label>
          Claim description <textarea name="description" maxLength={8000} />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit">Record warranty claim</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </fieldset>
    </form>
  );
}
