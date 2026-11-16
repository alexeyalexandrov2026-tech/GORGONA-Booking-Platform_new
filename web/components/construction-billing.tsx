"use client";

import React, { useEffect, useId, useState } from "react";
import {
  createPayApplication,
  fetchPayApplication,
  fetchPayApplications,
  fetchRetainageRate,
  refusal,
  saveRetainageRate,
  type PayApplicationBody,
} from "../lib/construction-api";
import type {
  PayApplication,
  PayApplicationList,
  Project,
  RetainageRate,
} from "../lib/construction-contracts";
import { formatMinor, quantityText, toMinor } from "../lib/construction-rules";
import { lineKey, lineName } from "./construction-budget";
import { PayApplicationForm } from "./construction-pay-application-form";

export function ConstructionBilling({
  business,
  project,
  companyWide,
  places,
}: {
  business: string;
  project: Project;
  companyWide: boolean;
  places: number;
}) {
  const heading = useId();
  const id = project.project_id;
  const [view, setView] = useState<{
    rate: RetainageRate;
    list: PayApplicationList | null;
  } | null>(null);
  const [detail, setDetail] = useState<PayApplication>();
  const [mode, setMode] = useState<"rate" | "application" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [readError, setReadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let current = true;
    Promise.all([
      fetchRetainageRate(business, id),
      companyWide ? fetchPayApplications(business, project) : null,
    ])
      .then(([rate, list]) => {
        if (current) setView({ rate, list });
      })
      .catch((failure: unknown) => {
        if (current) setReadError(refusal(failure));
      });
    return () => {
      current = false;
    };
  }, [attempt, business, companyWide, id, project]);

  function reload() {
    setView(null);
    setMode(null);
    setReadError("");
    setActionError("");
    setAttempt((current) => current + 1);
  }

  function open(next: typeof mode) {
    setActionError("");
    setStatus("");
    setMode(next);
  }

  async function saveRate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !view) return;
    const raw = String(new FormData(event.currentTarget).get("rate") ?? "");
    const rate = toMinor(raw, 2);
    if (rate === null || rate > 5000) {
      setActionError(
        "Enter a percentage from 0 to 50 with up to two decimal places.",
      );
      return;
    }
    setBusy(true);
    setActionError("");
    try {
      await saveRetainageRate(business, id, view.rate.revision, rate);
      setStatus("Retainage rate saved.");
      reload();
    } catch (failure) {
      setActionError(refusal(failure));
    } finally {
      setBusy(false);
    }
  }

  async function create(body: PayApplicationBody) {
    if (busy || !view?.list) return;
    setBusy(true);
    setActionError("");
    try {
      const application = await createPayApplication(business, project, body);
      setDetail(application);
      setStatus(`Pay application ${application.number} saved.`);
      reload();
    } catch (failure) {
      setActionError(refusal(failure));
    } finally {
      setBusy(false);
    }
  }

  async function show(number: number) {
    if (busy) return;
    open(null);
    setBusy(true);
    try {
      setDetail(await fetchPayApplication(business, project, number));
    } catch (failure) {
      setActionError(refusal(failure));
    } finally {
      setBusy(false);
    }
  }

  const money = (minor: number) =>
    `${formatMinor(minor, places)} ${project.currency}`;
  const list = view?.list;

  return (
    <section className="construction-section" aria-labelledby={heading}>
      <h3 id={heading}>Pay applications</h3>
      {status && <p role="status">{status}</p>}
      {(readError || actionError) && (
        <p role="alert">{readError || actionError}</p>
      )}
      {!view && !readError && <p role="status">Loading pay applications…</p>}
      {(readError || actionError) && (
        <button type="button" onClick={reload} disabled={busy}>
          Reload pay applications
        </button>
      )}
      {view && (
        <>
          <p>Current retainage rate {formatMinor(view.rate.rate_bp, 2)}%</p>
          {list ? (
            <p>
              Contract {money(list.contract_minor)} · Billed{" "}
              {money(list.billed_to_date_minor)} · Retained at billing{" "}
              {money(list.retained_minor)} · Invoiced amount{" "}
              {money(list.due_minor)} · Remaining to bill{" "}
              {money(list.remaining_minor)}
            </p>
          ) : (
            <p>
              Pay application history and draft creation require company-wide
              Finance access.
            </p>
          )}
          {list?.items.length === 0 && <p>No pay applications yet.</p>}
          {list && list.items.length > 0 && (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Billing periods"
              tabIndex={0}
            >
              <table className="mgmt-table" aria-label="Billing periods">
                <thead>
                  <tr>
                    <th scope="col">Application</th>
                    <th scope="col">Period end</th>
                    <th scope="col">This period</th>
                    <th scope="col">Billed to date</th>
                    <th scope="col">Retained</th>
                    <th scope="col">Invoice amount</th>
                    <th scope="col">Invoice</th>
                    <th scope="col">Retainage document</th>
                  </tr>
                </thead>
                <tbody>
                  {list.items.map((item) => (
                    <tr key={item.number}>
                      <th scope="row">
                        <button
                          type="button"
                          disabled={busy || mode !== null}
                          onClick={() => void show(item.number)}
                        >
                          Application {item.number}
                        </button>
                      </th>
                      <td>{item.period_end}</td>
                      <td>{money(item.this_period_minor)}</td>
                      <td>{money(item.billed_to_date_minor)}</td>
                      <td>{money(item.retained_minor)}</td>
                      <td>{money(item.due_minor)}</td>
                      <td>{item.invoice_state}</td>
                      <td>{item.retainage_state ?? "None"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!mode && (
            <div className="mgmt-form-actions">
              <button
                type="button"
                onClick={() => open("rate")}
                disabled={busy}
              >
                Edit retainage rate
              </button>
              {list && (
                <button
                  type="button"
                  onClick={() => open("application")}
                  disabled={busy}
                >
                  New pay application
                </button>
              )}
            </div>
          )}
          {mode === "rate" && (
            <form
              className="mgmt-form"
              aria-label="Edit retainage rate"
              onSubmit={(event) => void saveRate(event)}
            >
              <fieldset disabled={busy}>
                <legend>Retainage rate</legend>
                <label>
                  Retainage percent{" "}
                  <input
                    inputMode="decimal"
                    name="rate"
                    required
                    defaultValue={formatMinor(view.rate.rate_bp, 2)}
                  />
                </label>
                <button type="submit">Save retainage rate</button>
                <button type="button" onClick={() => open(null)}>
                  Cancel
                </button>
              </fieldset>
            </form>
          )}
          {list && mode === "application" && (
            <PayApplicationForm
              business={business}
              project={project}
              lastPeriod={list.items.at(-1)?.period_end}
              busy={busy}
              onCreate={(body) => void create(body)}
              onCancel={() => open(null)}
            />
          )}
        </>
      )}
      {detail && (
        <ApplicationDetail
          detail={detail}
          places={places}
          onClose={() => setDetail(undefined)}
        />
      )}
    </section>
  );
}

function ApplicationDetail({
  detail,
  places,
  onClose,
}: {
  detail: PayApplication;
  places: number;
  onClose: () => void;
}) {
  const heading = useId();
  const document = detail.invoice;
  const held = detail.retainage;
  return (
    <section className="construction-section" aria-labelledby={heading}>
      <h4 id={heading}>Application {detail.number} detail</h4>
      <button type="button" onClick={onClose}>
        Close application detail
      </button>
      <p>
        Period end {detail.period_end} · Retainage rate{" "}
        {formatMinor(detail.rate_bp, 2)}%
      </p>
      <dl>
        <dt>Invoice</dt>
        <dd>
          {document.number} · {document.state} · {document.total}{" "}
          {document.currency}
        </dd>
        {held && (
          <>
            <dt>Retainage accrual</dt>
            <dd>
              {held.number} · {held.state} · {held.total} {held.currency}
            </dd>
          </>
        )}
      </dl>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Billed quantities and values"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Billed quantities and values">
          <thead>
            <tr>
              <th scope="col">Contract line</th>
              <th scope="col">Completed</th>
              <th scope="col">Value to date ({detail.currency})</th>
              <th scope="col">Previously billed ({detail.currency})</th>
              <th scope="col">This period ({detail.currency})</th>
            </tr>
          </thead>
          <tbody>
            {detail.lines.map((line) => (
              <tr key={lineKey(line.change_order, line.position)}>
                <th scope="row">
                  {lineName(line.change_order, line.position)} ·{" "}
                  {line.description}
                </th>
                <td>
                  {quantityText(line.completed)} {line.unit}
                </td>
                <td>{formatMinor(line.value_to_date_minor, places)}</td>
                <td>{formatMinor(line.previous_minor, places)}</td>
                <td>{formatMinor(line.this_period_minor, places)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
