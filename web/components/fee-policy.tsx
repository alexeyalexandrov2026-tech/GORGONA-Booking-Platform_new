"use client";

// L9a (package L): the published fee policy for late cancellations and no-shows. A visit is
// billed by the version in force when it was booked; publishing adds a version, never edits one.
import React, { useEffect, useId, useState } from "react";
import {
  type FeePolicyView,
  type FeeRule,
  fetchFeePolicy,
  ManagementApiError,
  publishFeePolicy,
} from "../lib/management-api";

type Kind = "none" | "percent" | "amount";

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function describe(rule: FeeRule | null): string {
  if (rule === null) return "none";
  return "percent" in rule ? `${rule.percent} % of the visit` : rule.amount;
}

function kindOf(rule: FeeRule | null): Kind {
  if (rule === null) return "none";
  return "percent" in rule ? "percent" : "amount";
}

function valueOf(rule: FeeRule | null): string {
  if (rule === null) return "";
  return "percent" in rule ? rule.percent : rule.amount;
}

function ruleOf(kind: Kind, value: string): FeeRule | null {
  if (kind === "none") return null;
  return kind === "percent" ? { percent: value } : { amount: value };
}

function FeeFields({
  label,
  kind,
  value,
  onKind,
  onValue,
}: {
  label: string;
  kind: Kind;
  value: string;
  onKind: (kind: Kind) => void;
  onValue: (value: string) => void;
}) {
  return (
    <fieldset className="fee-rule">
      <legend>{label}</legend>
      <label>
        Kind
        <select
          aria-label={`${label} kind`}
          value={kind}
          onChange={(e) => onKind(e.target.value as Kind)}
        >
          <option value="none">No fee</option>
          <option value="percent">Percentage of the visit</option>
          <option value="amount">Fixed amount</option>
        </select>
      </label>
      {kind !== "none" && (
        <label>
          {kind === "percent" ? "Percentage" : "Amount"}
          <input
            aria-label={`${label} ${kind === "percent" ? "percentage" : "amount"}`}
            inputMode="decimal"
            pattern="[0-9]+\.[0-9]{2}"
            placeholder="0.00"
            value={value}
            onChange={(e) => onValue(e.target.value)}
            required
          />
        </label>
      )}
    </fieldset>
  );
}

export function FeePolicySection({ salonId }: { salonId: string }) {
  const headingId = useId();
  const [versions, setVersions] = useState<FeePolicyView[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [hours, setHours] = useState("24");
  const [lateKind, setLateKind] = useState<Kind>("none");
  const [lateValue, setLateValue] = useState("");
  const [missedKind, setMissedKind] = useState<Kind>("none");
  const [missedValue, setMissedValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function show(list: FeePolicyView[]) {
    setVersions(list);
    const current = list[0];
    if (!current) return;
    setHours(String(current.free_cancellation_minutes / 60));
    setLateKind(kindOf(current.late_cancellation_fee));
    setLateValue(valueOf(current.late_cancellation_fee));
    setMissedKind(kindOf(current.no_show_fee));
    setMissedValue(valueOf(current.no_show_fee));
  }

  useEffect(() => {
    let live = true;
    fetchFeePolicy(salonId)
      .then((list) => {
        if (live) show(list);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The fee policy could not be read: ${refusal(failure)}`);
      })
      .finally(() => {
        if (live) setLoaded(true);
      });
    return () => {
      live = false;
    };
  }, [salonId]);

  async function publish(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const published = await publishFeePolicy(salonId, {
        expected_version: versions[0]?.version ?? 0,
        free_cancellation_minutes: Math.round(Number(hours) * 60),
        late_cancellation_fee: ruleOf(lateKind, lateValue),
        no_show_fee: ruleOf(missedKind, missedValue),
      });
      show([published, ...versions]);
      setNotice(`Fee policy version ${published.version} published.`);
    } catch (failure) {
      setError(`The fee policy was not published: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const current = versions[0] ?? null;
  return (
    <section aria-labelledby={headingId} className="fee-policy">
      <h3 id={headingId}>Cancellation and no-show fees</h3>
      {!loaded && (
        <p className="muted" role="status">
          Loading the fee policy…
        </p>
      )}
      {loaded && current === null && (
        <p className="muted">No fee policy is published yet.</p>
      )}
      {current !== null && (
        <p>
          Version {current.version}: free cancellation up to{" "}
          {current.free_cancellation_minutes / 60} hours before the start; late
          cancellation fee {describe(current.late_cancellation_fee)}; no-show
          fee {describe(current.no_show_fee)}. A visit keeps the version in
          force when it was booked.
        </p>
      )}
      <form onSubmit={publish} aria-label="Publish a fee policy">
        <label>
          Free cancellation (hours before the start)
          <input
            type="number"
            min={0}
            max={8760}
            step={1}
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            required
          />
        </label>
        <FeeFields
          label="Late cancellation fee"
          kind={lateKind}
          value={lateValue}
          onKind={setLateKind}
          onValue={setLateValue}
        />
        <FeeFields
          label="No-show fee"
          kind={missedKind}
          value={missedValue}
          onKind={setMissedKind}
          onValue={setMissedValue}
        />
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy || !loaded}>
            {busy ? "Publishing…" : "Publish a new version"}
          </button>
        </div>
      </form>
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
    </section>
  );
}
