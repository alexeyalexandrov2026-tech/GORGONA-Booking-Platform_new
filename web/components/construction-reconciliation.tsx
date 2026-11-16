"use client";

import React, { useEffect, useId, useState } from "react";
import { fetchReconciliation, refusal } from "../lib/construction-api";
import type { Project } from "../lib/construction-contracts";
import type { Reconciliation } from "../lib/construction-reconciliation-contracts";
import { formatMinor } from "../lib/construction-rules";

type MoneyField = Exclude<
  keyof Reconciliation,
  "schema_version" | "project_id" | "currency" | "unissued_documents" | "claims"
>;
const moneyGroups: { title: string; rows: [string, MoneyField][] }[] = [
  {
    title: "Contract and progress",
    rows: [
      ["Contract total", "contract_minor"],
      ["Completed value", "completed_minor"],
      ["Billed", "billed_minor"],
      ["Contract less billed", "contract_minus_billed_minor"],
      ["Completed less billed", "completed_minus_billed_minor"],
    ],
  },
  {
    title: "Costs",
    rows: [
      ["Budget", "budget_minor"],
      ["Committed", "committed_minor"],
      ["Actual cost", "actual_minor"],
      ["Warranty repairs included in actual", "warranty_repair_minor"],
      ["Budget less actual", "budget_minus_actual_minor"],
      ["Contract less actual", "contract_minus_actual_minor"],
    ],
  },
  {
    title: "Invoices and settlements",
    rows: [
      ["Invoice amount at billing", "due_minor"],
      ["Invoice paid", "due_paid_minor"],
      ["Invoice credited", "due_credited_minor"],
      ["Billed less paid and credited", "billed_minus_settled_minor"],
    ],
  },
  {
    title: "Retainage",
    rows: [
      ["Retained at billing", "retained_minor"],
      ["Released", "released_minor"],
      ["Still held", "held_minor"],
      ["Retainage paid", "retainage_paid_minor"],
      ["Retainage credited", "retainage_credited_minor"],
      [
        "Settled retainage above the released amount",
        "retainage_settled_before_release_minor",
      ],
    ],
  },
];

export function ConstructionReconciliation({
  business,
  project,
  places,
  projectRevision,
}: {
  business: string;
  project: Project;
  places: number;
  projectRevision: number;
}) {
  const id = useId();
  const [view, setView] = useState<Reconciliation | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    fetchReconciliation(business, project)
      .then((value) => {
        if (!active) return;
        setView(value);
        setError("");
      })
      .catch((failure: unknown) => {
        if (active) setError(refusal(failure));
      });
    return () => {
      active = false;
    };
  }, [business, project, projectRevision, attempt]);

  return (
    <section className="construction-section" aria-labelledby={id}>
      <h3 id={id}>Project reconciliation</h3>
      <button
        type="button"
        disabled={!view && !error}
        onClick={() => {
          setView(null);
          setError("");
          setAttempt((n) => n + 1);
        }}
      >
        Refresh reconciliation
      </button>
      {error && <p role="alert">{error}</p>}
      {!view && !error && <p role="status">Loading project reconciliation…</p>}
      {view && !error && (
        <>
          <p>Unissued documents {view.unissued_documents}</p>
          <p>
            Warranty claims · {view.claims.open} open · {view.claims.repaired}{" "}
            repaired · {view.claims.closed} closed · {view.claims.rejected}{" "}
            rejected
          </p>
          {moneyGroups.map(({ title, rows }) => (
            <table key={title} className="mgmt-table" aria-label={title}>
              <caption>{title}</caption>
              <thead>
                <tr>
                  <th scope="col">Measure</th>
                  <th scope="col">Amount ({view.currency})</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(([label, field]) => (
                  <tr key={field}>
                    <th scope="row">{label}</th>
                    <td>{formatMinor(view[field], places)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ))}
        </>
      )}
    </section>
  );
}
