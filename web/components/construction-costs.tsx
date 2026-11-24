"use client";

import React, { useEffect, useId, useState } from "react";
import {
  fetchCostLinks,
  linkCost,
  refusal,
  reverseCost,
  type CostBody,
  type CostFact,
} from "../lib/construction-api";
import {
  costKindSchema,
  type Budget,
  type CostKind,
  type CostLink,
  type Project,
} from "../lib/construction-contracts";
import { formatMinor, toMinor } from "../lib/construction-rules";
import { lineKey, lineLabel, lineName } from "./construction-budget";
import { COST_NAMES, CostSource } from "./construction-cost-sources";

function sourceLabel(link: CostLink) {
  switch (link.kind) {
    case "stock_write_off":
      return `Stock write-off ${link.stock_document_id?.slice(-8)}, line ${link.stock_line_no}`;
    case "payable":
      return `Payable ${link.document_id?.slice(-8)}, revision ${link.document_revision}, line ${link.line_id?.slice(-8)}`;
    case "time_entry":
      return `Time entry ${link.time_entry_id?.slice(-8)}, revision ${link.time_entry_revision}`;
  }
}

export function ConstructionCosts({
  business,
  project,
  budget,
  places,
  onChanged,
}: {
  business: string;
  project: Project;
  budget: Budget;
  places: number;
  onChanged: (message: string) => Promise<void>;
}) {
  const heading = useId();
  const id = project.project_id;
  const [items, setItems] = useState<CostLink[] | null>(null);
  const [error, setError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [needsReload, setNeedsReload] = useState(false);
  const [adding, setAdding] = useState(false);
  const [reversing, setReversing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    fetchCostLinks(business, id)
      .then((result) => {
        if (live) {
          setItems(result.items);
          setNeedsReload(false);
        }
      })
      .catch((failure: unknown) => {
        if (live) setError(refusal(failure));
      });
    return () => {
      live = false;
    };
  }, [business, id, loadAttempt]);

  async function save(action: () => Promise<CostLink>, message: string) {
    if (busy || needsReload) return;
    setBusy(true);
    setError("");
    try {
      const result = await action();
      setItems((current) =>
        [
          ...(current ?? []).filter((item) => item.number !== result.number),
          result,
        ].sort((left, right) => left.number - right.number),
      );
      setAdding(false);
      setReversing(null);
      setNeedsReload(true);
      await Promise.all([
        fetchCostLinks(business, id)
          .then((latest) => {
            setItems(latest.items);
            setNeedsReload(false);
          })
          .catch((failure: unknown) => {
            setError(
              `Cost saved. Actual cost history could not be refreshed. ${refusal(failure)}`,
            );
          }),
        onChanged(message),
      ]);
    } catch (failure) {
      setError(refusal(failure));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={heading}>
      <h3 id={heading}>Actual costs</h3>
      {error && <p role="alert">{error}</p>}
      {(items === null || needsReload) &&
        (error ? (
          <button
            type="button"
            onClick={() => {
              setError("");
              setLoadAttempt((n) => n + 1);
            }}
          >
            Retry actual costs
          </button>
        ) : (
          <p role="status">Loading actual costs…</p>
        ))}
      {items?.length === 0 && <p>No actual costs linked yet.</p>}
      {items && items.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Actual costs table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Actual cost history">
            <thead>
              <tr>
                <th scope="col">Link</th>
                <th scope="col">Budget line</th>
                <th scope="col">Source</th>
                <th scope="col">Amount</th>
                <th scope="col">Status</th>
                <th scope="col">Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.number}>
                  <th scope="row">{item.number}</th>
                  <td>{lineName(item.change_order, item.position)}</td>
                  <td>
                    {sourceLabel(item)}
                    {item.note && <div>{item.note}</div>}
                  </td>
                  <td>
                    {formatMinor(item.amount_minor, places)} {item.currency}
                  </td>
                  <td>
                    {item.reversal
                      ? `Reversed · ${item.reversal.reason}`
                      : "Linked"}
                  </td>
                  <td>
                    {!item.reversal && (
                      <button
                        type="button"
                        disabled={busy || needsReload}
                        onClick={() => {
                          setAdding(false);
                          setError("");
                          setReversing(item.number);
                        }}
                      >
                        Reverse cost {item.number}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {items && budget.lines.length > 0 && !adding && reversing === null && (
        <button
          type="button"
          disabled={busy || needsReload}
          onClick={() => {
            setError("");
            setAdding(true);
          }}
        >
          Link actual cost
        </button>
      )}
      {adding && (
        <LinkForm
          business={business}
          project={project}
          budget={budget}
          places={places}
          busy={busy}
          onCancel={() => {
            setError("");
            setAdding(false);
          }}
          onLink={(body) =>
            void save(() => linkCost(business, id, body), "Cost linked.")
          }
        />
      )}
      {reversing !== null && (
        <form
          key={reversing}
          className="mgmt-form"
          aria-label="Reverse actual cost"
          onSubmit={(event) => {
            event.preventDefault();
            const reason = String(
              new FormData(event.currentTarget).get("reason") ?? "",
            ).trim();
            if (!reason) {
              setError("Enter a reason for reversing this cost.");
              return;
            }
            void save(
              () => reverseCost(business, id, reversing, reason),
              "Cost reversed.",
            );
          }}
        >
          <fieldset disabled={busy}>
            <legend>Reverse cost {reversing}</legend>
            <label>
              Reversal reason{" "}
              <textarea name="reason" maxLength={500} required />
            </label>
            <button type="submit">Confirm reversal</button>
            <button
              type="button"
              onClick={() => {
                setError("");
                setReversing(null);
              }}
            >
              Cancel reversal
            </button>
          </fieldset>
        </form>
      )}
    </section>
  );
}

function LinkForm({
  business,
  project,
  budget,
  places,
  busy,
  onCancel,
  onLink,
}: {
  business: string;
  project: Project;
  budget: Budget;
  places: number;
  busy: boolean;
  onCancel: () => void;
  onLink: (body: CostBody) => void;
}) {
  const kindId = useId();
  const lineId = useId();
  const [kind, setKind] = useState<CostKind>("stock_write_off");
  const [fact, setFact] = useState<CostFact>();
  const [error, setError] = useState("");

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const line = budget.lines.find(
      (item) =>
        lineKey(item.change_order, item.position) === values.get("line"),
    );
    if (!fact || !line) {
      setError("Select a source and a budget line.");
      return;
    }
    const terms = {
      schema_version: 1 as const,
      change_order: line.change_order,
      position: line.position,
      note: String(values.get("note") ?? "").trim() || null,
    };
    if (fact.kind === "time_entry") {
      const rate = toMinor(String(values.get("rate") ?? ""), places);
      if (!rate || rate > 1_000_000_000) {
        setError("Enter a valid positive hourly rate.");
        return;
      }
      setError("");
      onLink({ ...terms, ...fact, rate_per_hour_minor: rate });
    } else {
      setError("");
      onLink({ ...terms, ...fact });
    }
  }
  return (
    <form className="mgmt-form" aria-label="Link actual cost" onSubmit={submit}>
      <fieldset disabled={busy}>
        <legend>New cost link</legend>
        <label htmlFor={lineId}>Budget line</label>
        <select id={lineId} name="line" required defaultValue="">
          <option value="">Select a budget line</option>
          {budget.lines.map((item) => {
            const key = lineKey(item.change_order, item.position);
            return (
              <option key={key} value={key}>
                {lineLabel(item)}
              </option>
            );
          })}
        </select>
        <label htmlFor={kindId}>Cost source</label>
        <select
          id={kindId}
          value={kind}
          onChange={(event) => {
            const selected = costKindSchema.safeParse(
              event.currentTarget.value,
            );
            if (selected.success) {
              setKind(selected.data);
              setFact(undefined);
              setError("");
            }
          }}
        >
          {Object.entries(COST_NAMES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <CostSource
          kind={kind}
          business={business}
          project={project}
          onPick={setFact}
        />
        {kind === "time_entry" && (
          <label>
            Hourly rate ({project.currency}){" "}
            <input name="rate" inputMode="decimal" required />
          </label>
        )}
        <label>
          Cost note <textarea name="note" maxLength={500} />
        </label>
        {error && <p role="alert">{error}</p>}
        <button type="submit" disabled={!fact}>
          Save cost link
        </button>
        <button type="button" onClick={onCancel}>
          Cancel cost link
        </button>
      </fieldset>
    </form>
  );
}
