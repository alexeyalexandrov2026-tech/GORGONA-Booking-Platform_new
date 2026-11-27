"use client";

import { useId, useState } from "react";
import {
  createRecurringSchedule,
  runRecurringScheduleNow,
  toggleRecurringSchedule,
  type BillingCadence,
  type PaymentTerms,
  type RecurringScheduleView,
} from "../lib/commercial-api";

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(cents / 100);
}

const TERMS: PaymentTerms[] = [
  "Due on receipt",
  "Net 15",
  "Net 30",
  "Net 45",
  "Net 60",
];

export function CommercialRecurringTab({
  businessId,
  schedules,
  busy,
  setBusy,
  setError,
  setNotice,
  onReload,
}: {
  businessId: string;
  schedules: RecurringScheduleView[];
  busy: boolean;
  setBusy: (b: boolean) => void;
  setError: (e: string | null) => void;
  setNotice: (n: string | null) => void;
  onReload: () => void;
}) {
  const titleId = useId();
  const clientId = useId();
  const emailId = useId();
  const amtId = useId();
  const cadenceId = useId();
  const termsId = useId();
  const dateId = useId();
  const emailCheckId = useId();

  const [title, setTitle] = useState("");
  const [clientName, setClientName] = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [amountUsd, setAmountUsd] = useState("2500.00");
  const [cadence, setCadence] = useState<BillingCadence>("monthly");
  const [terms, setTerms] = useState<PaymentTerms>("Net 30");
  const [nextRunDate, setNextRunDate] = useState("2026-12-01");
  const [autoEmail, setAutoEmail] = useState(true);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const cents = Math.round((Number(amountUsd) || 0) * 100);
    if (cents < 50) {
      setError("Enter a recurring USD amount of at least $0.50.");
      return;
    }
    setBusy(true);
    try {
      const created = await createRecurringSchedule(businessId, {
        title: title.trim(),
        counterparty_name: clientName.trim(),
        counterparty_email: clientEmail.trim() || null,
        amount_cents: cents,
        cadence,
        payment_terms: terms,
        next_run_date: nextRunDate,
        auto_email_client: autoEmail,
      });
      setTitle("");
      setClientName("");
      setClientEmail("");
      setNotice(
        `Created recurring schedule ${created.schedule_code} (${created.cadence}).`,
      );
      onReload();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not create recurring schedule.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="usr-card" aria-labelledby="new-recurring-heading">
        <h2 id="new-recurring-heading">
          Create Recurring B2B Retainer / Billing Schedule
        </h2>
        <p className="usr-muted">
          Automate recurring logistics retainers, commercial leases, equipment
          contracts, or monthly B2B service agreements with zero platform fee.
        </p>
        <form onSubmit={(e) => void handleCreate(e)} className="usr-stack">
          <div className="usr-grid">
            <label htmlFor={titleId}>
              Contract / Retainer title
              <input
                id={titleId}
                type="text"
                required
                placeholder="Dedicated Fleet Dispatch Retainer"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label htmlFor={clientId}>
              Client name
              <input
                id={clientId}
                type="text"
                required
                placeholder="Great Lakes Industrial Supply"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
              />
            </label>
            <label htmlFor={emailId}>
              Billing email (optional)
              <input
                id={emailId}
                type="email"
                placeholder="ap@greatlakesindustrial.us"
                value={clientEmail}
                onChange={(e) => setClientEmail(e.target.value)}
              />
            </label>
          </div>
          <div className="usr-grid">
            <label htmlFor={amtId}>
              Recurring amount (USD)
              <input
                id={amtId}
                type="number"
                min="0.50"
                step="0.01"
                required
                value={amountUsd}
                onChange={(e) => setAmountUsd(e.target.value)}
              />
            </label>
            <label htmlFor={cadenceId}>
              Billing cadence
              <select
                id={cadenceId}
                value={cadence}
                onChange={(e) => setCadence(e.target.value as BillingCadence)}
              >
                <option value="weekly">Weekly</option>
                <option value="biweekly">Bi-weekly</option>
                <option value="monthly">Monthly</option>
                <option value="quarterly">Quarterly</option>
                <option value="annual">Annual</option>
              </select>
            </label>
            <label htmlFor={termsId}>
              Payment terms
              <select
                id={termsId}
                value={terms}
                onChange={(e) => setTerms(e.target.value as PaymentTerms)}
              >
                {TERMS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor={dateId}>
              Next run date
              <input
                id={dateId}
                type="date"
                required
                value={nextRunDate}
                onChange={(e) => setNextRunDate(e.target.value)}
              />
            </label>
          </div>
          <label htmlFor={emailCheckId} className="usr-check">
            <input
              id={emailCheckId}
              type="checkbox"
              checked={autoEmail}
              onChange={(e) => setAutoEmail(e.target.checked)}
            />
            <span>
              Automatically email client with secure B2B portal link on each run
            </span>
          </label>
          <div>
            <button type="submit" disabled={busy}>
              {busy ? "Saving…" : "Create Recurring Schedule"}
            </button>
          </div>
        </form>
      </section>

      <section className="usr-card" aria-labelledby="recurring-list-heading">
        <h2 id="recurring-list-heading">Active &amp; Paused Schedules</h2>
        {schedules.length === 0 ? (
          <p className="usr-muted">
            No recurring retainers or billing schedules created yet.
          </p>
        ) : (
          <div className="usr-table-wrap" tabIndex={0}>
            <table className="usr-table">
              <thead>
                <tr>
                  <th scope="col">Schedule</th>
                  <th scope="col">Client</th>
                  <th scope="col">Amount / Cadence</th>
                  <th scope="col">Next Run</th>
                  <th scope="col">Status</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.schedule_code}</strong> · {s.title}
                      <div className="usr-muted">
                        {s.payment_terms} · {s.runs_count} cycle(s) run
                      </div>
                    </td>
                    <td>
                      {s.counterparty_name}
                      {s.counterparty_email && (
                        <div className="usr-muted">{s.counterparty_email}</div>
                      )}
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <strong>{formatUsd(s.amount_cents)}</strong>
                      <div className="usr-muted">{s.cadence}</div>
                    </td>
                    <td>{s.next_run_date}</td>
                    <td>
                      <span
                        className={
                          "usr-badge " +
                          (s.status === "active"
                            ? "usr-badge-ai"
                            : "usr-badge-off")
                        }
                      >
                        {s.status}
                      </span>
                    </td>
                    <td>
                      <div className="usr-inline">
                        {s.status === "active" && (
                          <button
                            type="button"
                            className="usr-small-btn"
                            disabled={busy}
                            onClick={() => {
                              setBusy(true);
                              setError(null);
                              void runRecurringScheduleNow(businessId, s.id)
                                .then((res) => {
                                  setNotice(
                                    `Generated ${res.generated_quote.quote_number}. Next run: ${res.schedule.next_run_date}.${res.email_status ? ` Email: ${res.email_status}.` : ""}`,
                                  );
                                  onReload();
                                })
                                .catch((e: unknown) =>
                                  setError(
                                    e instanceof Error
                                      ? e.message
                                      : "Could not run billing cycle.",
                                  ),
                                )
                                .finally(() => setBusy(false));
                            }}
                          >
                            Run Cycle Now
                          </button>
                        )}
                        <button
                          type="button"
                          className="secondary usr-small-btn"
                          disabled={busy}
                          onClick={() => {
                            setBusy(true);
                            setError(null);
                            void toggleRecurringSchedule(businessId, s.id)
                              .then((updated) => {
                                setNotice(
                                  `Schedule ${updated.schedule_code} is now ${updated.status}.`,
                                );
                                onReload();
                              })
                              .catch((e: unknown) =>
                                setError(
                                  e instanceof Error
                                    ? e.message
                                    : "Could not toggle schedule.",
                                ),
                              )
                              .finally(() => setBusy(false));
                          }}
                        >
                          {s.status === "active" ? "Pause" : "Resume"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
