"use client";

// L7b2a (package L): a specialist's commission plan — who is paid and by which rules. A rule of
// one service wins over the rule for all other services; each is a percentage or a fixed amount.
import React, { useCallback, useEffect, useId, useState } from "react";
import {
  type CommissionPlan,
  fetchCommissionPlan,
  ManagementApiError,
  saveCommissionPlan,
  type ServiceView,
  type StaffView,
} from "../lib/management-api";
import { allActiveParties, type Party } from "./visit-billing";

type RuleDraft = {
  service_id: string;
  kind: "percent" | "amount";
  value: string;
};

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function drafts(plan: CommissionPlan | null): RuleDraft[] {
  return (plan?.rules ?? []).map((rule) => ({
    service_id: rule.service_id ?? "",
    kind: rule.percent !== null ? "percent" : "amount",
    value: rule.percent ?? rule.amount ?? "",
  }));
}

export function CommissionPlanDialog({
  salonId,
  member,
  services,
  defaultCurrency,
  onClose,
}: {
  salonId: string;
  member: StaffView;
  services: ServiceView[];
  defaultCurrency: string;
  onClose: () => void;
}) {
  const titleId = useId();
  const [plan, setPlan] = useState<CommissionPlan | null>(null);
  const [parties, setParties] = useState<Party[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [payee, setPayee] = useState("");
  const [currency, setCurrency] = useState("");
  const [rules, setRules] = useState<RuleDraft[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // One option per service, whatever number of variants it has.
  const choices = services.filter(
    (s, index) =>
      services.findIndex((other) => other.service_id === s.service_id) ===
      index,
  );

  const load = useCallback(
    () =>
      Promise.all([
        fetchCommissionPlan(salonId, member.id),
        allActiveParties(salonId),
      ]).then(([found, partyList]) => {
        setPlan(found);
        setParties(partyList);
        setPayee(found?.counterparty_id ?? "");
        setCurrency(found?.currency ?? defaultCurrency);
        setRules(drafts(found));
        setLoaded(true);
      }),
    [salonId, member.id, defaultCurrency],
  );

  useEffect(() => {
    load().catch((failure: unknown) =>
      setError(`The plan could not be read: ${refusal(failure)}`),
    );
  }, [load]);

  function change(index: number, patch: Partial<RuleDraft>) {
    setRules((current) =>
      current.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)),
    );
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveCommissionPlan(salonId, member.id, {
        expected_revision: plan?.revision ?? 0,
        counterparty_id: payee,
        currency: currency.trim().toUpperCase(),
        rules: rules.map((rule) => ({
          service_id: rule.service_id || null,
          percent: rule.kind === "percent" ? rule.value.trim() : null,
          amount: rule.kind === "amount" ? rule.value.trim() : null,
        })),
      });
      setPlan(saved);
      setRules(drafts(saved));
      setNotice("Plan saved.");
    } catch (failure) {
      if (
        failure instanceof ManagementApiError &&
        failure.code === "COMMISSION_PLAN_REVISION_CONFLICT"
      ) {
        await load().catch(() => undefined);
        setError(
          "The plan was changed elsewhere; the saved plan is shown again.",
        );
      } else setError(`The plan was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="mgmt-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div className="mgmt-modal-card commission-plan">
        <h2 id={titleId}>Commission plan: {member.display_name}</h2>
        {!loaded && !error && (
          <p className="muted" role="status">
            Loading the plan…
          </p>
        )}
        {loaded && (
          <form onSubmit={save} aria-label="Commission plan">
            <p className="muted">
              A rule of one service wins over the rule for all other services.
              The commission is accrued from the visit desk once a visit is
              paid.
            </p>
            <label>
              Paid to
              <select
                aria-label="Paid to"
                value={payee}
                onChange={(e) => setPayee(e.target.value)}
                required
              >
                <option value="">Choose who is paid</option>
                {parties.map((p) => (
                  <option key={p.counterparty_id} value={p.counterparty_id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Currency
              <input
                type="text"
                value={currency}
                maxLength={3}
                pattern="[A-Za-z]{3}"
                onChange={(e) => setCurrency(e.target.value)}
                required
              />
            </label>
            {rules.map((rule, index) => (
              <fieldset key={index} className="service-material-row">
                <legend>Rule {index + 1}</legend>
                <label>
                  Service
                  <select
                    aria-label="Service"
                    value={rule.service_id}
                    onChange={(e) =>
                      change(index, { service_id: e.target.value })
                    }
                  >
                    <option value="">All other services</option>
                    {choices.map((s) => (
                      <option key={s.service_id} value={s.service_id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Kind
                  <select
                    aria-label="Kind"
                    value={rule.kind}
                    onChange={(e) =>
                      change(index, {
                        kind: e.target.value as RuleDraft["kind"],
                      })
                    }
                  >
                    <option value="percent">Percentage</option>
                    <option value="amount">Fixed amount</option>
                  </select>
                </label>
                <label>
                  {rule.kind === "percent" ? "Percentage" : "Amount"}
                  <input
                    type="text"
                    inputMode="decimal"
                    value={rule.value}
                    onChange={(e) => change(index, { value: e.target.value })}
                    required
                  />
                </label>
                <button
                  type="button"
                  className="secondary mgmt-btn-small"
                  onClick={() =>
                    setRules((current) => current.filter((_, i) => i !== index))
                  }
                >
                  Remove rule {index + 1}
                </button>
              </fieldset>
            ))}
            <div className="mgmt-form-actions">
              <button
                type="button"
                className="secondary"
                disabled={rules.length >= 50}
                onClick={() =>
                  setRules((current) => [
                    ...current,
                    { service_id: "", kind: "percent", value: "" },
                  ])
                }
              >
                Add rule
              </button>
              <button type="submit" disabled={busy || !payee}>
                {busy ? "Saving…" : "Save plan"}
              </button>
            </div>
          </form>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p className="hold-note" role="status">
            {notice}
          </p>
        )}
        <div className="mgmt-form-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
