"use client";

import React, { useEffect, useId, useState } from "react";
import {
  assignWarrantyRepair,
  fetchCostLinks,
  fetchWarrantyClaim,
  moveWarrantyClaim,
  refusal,
} from "../lib/construction-api";
import type { CostLink, Project } from "../lib/construction-contracts";
import { formatMinor } from "../lib/construction-rules";
import {
  warrantyMoves,
  warrantyStateSchema,
  type WarrantyClaim,
  type WarrantyEventBody,
  type WarrantyState,
} from "../lib/construction-warranty-contracts";
import { lineName } from "./construction-budget";
import { COST_NAMES } from "./construction-cost-sources";
import { siteTime } from "./construction-estimates";

const moveLabels: Record<WarrantyState, string> = {
  open: "Reopen",
  repaired: "Mark repaired",
  closed: "Close",
  rejected: "Reject",
};

export function WarrantyClaimDetail({
  business,
  project,
  number,
  places,
  projectRevision,
  onChanged,
}: {
  business: string;
  project: Project;
  number: number;
  places: number;
  projectRevision: number;
  onChanged: () => void;
}) {
  const heading = useId();
  const id = project.project_id;
  const [claim, setClaim] = useState<WarrantyClaim>();
  const [editor, setEditor] = useState<"event" | "repair" | null>(null);
  const [readError, setReadError] = useState("");
  const [writeError, setWriteError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    fetchWarrantyClaim(business, id, number)
      .then((result) => {
        if (!active) return;
        setClaim(result);
        setReadError("");
      })
      .catch((failure: unknown) => {
        if (active) setReadError(refusal(failure));
      });
    return () => {
      active = false;
    };
  }, [attempt, business, id, number, projectRevision]);

  function open(next: typeof editor) {
    setWriteError("");
    setNotice("");
    setEditor(next);
  }

  async function save(command: () => Promise<WarrantyClaim>, message: string) {
    if (busy || readError) return;
    setBusy(true);
    setWriteError("");
    try {
      setClaim(await command());
      setEditor(null);
      setNotice(message);
      onChanged();
    } catch (failure) {
      setWriteError(refusal(failure));
    } finally {
      setBusy(false);
    }
  }

  const canEdit = claim && warrantyMoves[claim.state].length > 0;
  const money = (minor: number) =>
    `${formatMinor(minor, places)} ${project.currency}`;
  return (
    <section className="construction-section" aria-labelledby={heading}>
      <h4 id={heading}>Warranty claim {number}</h4>
      {notice && <p role="status">{notice}</p>}
      {readError && <p role="alert">{readError}</p>}
      {writeError && <p role="alert">{writeError}</p>}
      {!claim && !readError && <p role="status">Loading warranty claim…</p>}
      {(claim || readError) && (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            setClaim(undefined);
            setReadError("");
            open(null);
            setAttempt((n) => n + 1);
          }}
        >
          Refresh claim
        </button>
      )}
      {claim && (
        <>
          <p>
            {claim.title} · Status {claim.state}
          </p>
          <p>
            Reported by {claim.reported_by} on {claim.raised_on}
            {claim.location && ` · ${claim.location}`}
          </p>
          {claim.description && <p>{claim.description}</p>}
          {claim.events.length > 0 && (
            <ol aria-label="Claim history">
              {claim.events.map((event) => (
                <li key={event.sequence}>
                  {moveLabels[event.state]}
                  {" · "}
                  <time dateTime={event.recorded_at}>
                    {siteTime(event.recorded_at, project.time_zone)}
                  </time>
                  {event.note && ` · ${event.note}`}
                </li>
              ))}
            </ol>
          )}
          <p>Active repair costs {money(claim.repair_minor)}</p>
          {claim.repairs.length > 0 && (
            <ul aria-label="Assigned repair costs">
              {claim.repairs.map((repair) => (
                <li key={repair.cost_link}>
                  Cost link {repair.cost_link} · {money(repair.amount_minor)}
                  {repair.reversed && " · Reversed"}
                </li>
              ))}
            </ul>
          )}
          {canEdit && !editor && (
            <div className="mgmt-form-actions">
              <button
                type="button"
                disabled={!!readError}
                onClick={() => open("event")}
              >
                Update claim status
              </button>
              <button
                type="button"
                disabled={!!readError}
                onClick={() => open("repair")}
              >
                Assign repair cost
              </button>
            </div>
          )}
          {canEdit && editor === "event" && (
            <EventForm
              key={claim.events.at(-1)?.sequence ?? 0}
              claim={claim}
              busy={busy || !!readError}
              onCancel={() => open(null)}
              onSave={(body) =>
                void save(
                  () => moveWarrantyClaim(business, id, number, body),
                  "Claim status updated.",
                )
              }
            />
          )}
          {canEdit && editor === "repair" && (
            <RepairForm
              business={business}
              project={project}
              claim={claim}
              places={places}
              projectRevision={projectRevision}
              busy={busy || !!readError}
              onCancel={() => open(null)}
              onSave={(cost) =>
                void save(
                  () => assignWarrantyRepair(business, id, number, cost),
                  "Repair cost assigned.",
                )
              }
            />
          )}
        </>
      )}
    </section>
  );
}

function EventForm({
  claim,
  busy,
  onSave,
  onCancel,
}: {
  claim: WarrantyClaim;
  busy: boolean;
  onSave: (body: WarrantyEventBody) => void;
  onCancel: () => void;
}) {
  const stateId = useId();
  const [state, setState] = useState("");
  const [error, setError] = useState("");
  const targets = warrantyMoves[claim.state];
  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const target = warrantyStateSchema.safeParse(state);
    if (!target.success || !targets.includes(target.data)) return;
    const note =
      String(new FormData(event.currentTarget).get("note") ?? "").trim() ||
      null;
    if ((target.data === "open" || target.data === "rejected") && !note) {
      setError("Enter the reason to reopen or reject this claim.");
      return;
    }
    if (note && Array.from(note).length > 1000) {
      setError("Use up to 1000 characters for the status note.");
      return;
    }
    setError("");
    onSave({
      schema_version: 1,
      expected_sequence: claim.events.at(-1)?.sequence ?? 0,
      state: target.data,
      note,
    });
  }
  return (
    <form
      className="mgmt-form"
      aria-label="Update warranty claim status"
      onSubmit={submit}
    >
      <fieldset disabled={busy}>
        <legend>Update claim status</legend>
        <label htmlFor={stateId}>Claim transition</label>
        <select
          id={stateId}
          value={state}
          onChange={(event) => setState(event.target.value)}
          required
        >
          <option value="">Choose a transition</option>
          {targets.map((item) => (
            <option key={item} value={item}>
              {moveLabels[item]}
            </option>
          ))}
        </select>
        <label>
          Status note{" "}
          <textarea
            name="note"
            maxLength={2000}
            required={state === "open" || state === "rejected"}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit">Save claim status</button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </fieldset>
    </form>
  );
}

function RepairForm({
  business,
  project,
  claim,
  places,
  projectRevision,
  busy,
  onSave,
  onCancel,
}: {
  business: string;
  project: Project;
  claim: WarrantyClaim;
  places: number;
  projectRevision: number;
  busy: boolean;
  onSave: (number: number) => void;
  onCancel: () => void;
}) {
  const id = useId();
  const [links, setLinks] = useState<CostLink[]>();
  const [choice, setChoice] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const projectId = project.project_id;
  useEffect(() => {
    let active = true;
    fetchCostLinks(business, projectId)
      .then((result) => {
        if (!active) return;
        setLinks(result.items);
        setError("");
      })
      .catch((failure: unknown) => {
        if (active) setError(refusal(failure));
      });
    return () => {
      active = false;
    };
  }, [attempt, business, projectId, projectRevision]);

  const options = links?.filter(
    (link) =>
      !link.reversal &&
      !claim.repairs.some((repair) => repair.cost_link === link.number),
  );
  return (
    <form
      className="mgmt-form"
      aria-label="Assign repair cost"
      onSubmit={(event) => {
        event.preventDefault();
        if (busy || error) return;
        const link = options?.find((item) => String(item.number) === choice);
        if (link) onSave(link.number);
      }}
    >
      <fieldset disabled={busy}>
        <legend>Assign existing repair cost</legend>
        <label htmlFor={id}>Project cost link</label>
        <select
          id={id}
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
          required
          disabled={!!error || !options?.length}
        >
          <option value="">Choose a cost link</option>
          {options?.map((link) => (
            <option key={link.number} value={link.number}>
              {link.number} · {lineName(link.change_order, link.position)} ·{" "}
              {COST_NAMES[link.kind]} · {formatMinor(link.amount_minor, places)}{" "}
              {link.currency}
            </option>
          ))}
        </select>
        {!links && !error && <p role="status">Loading project cost links…</p>}
        {options?.length === 0 && (
          <p>Link a repair expense in Actual costs first.</p>
        )}
        {error && (
          <>
            <p role="alert">{error}</p>
            <button
              type="button"
              onClick={() => {
                setError("");
                setLinks(undefined);
                setAttempt((n) => n + 1);
              }}
            >
              Reload cost links
            </button>
          </>
        )}
        <button
          type="submit"
          disabled={
            !!error || !options?.some((item) => String(item.number) === choice)
          }
        >
          Save repair cost
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </fieldset>
    </form>
  );
}
