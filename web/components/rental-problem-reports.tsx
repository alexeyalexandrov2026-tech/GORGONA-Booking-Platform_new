"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  businessDateTime,
  businessTimeToInstant,
  businessToday,
} from "../lib/business-time";
import { ManagementApiError } from "../lib/management-api";
import {
  fetchProblemReports,
  recordProblemReport,
  refusal,
  type StaffProblemBody,
} from "../lib/rental-api";
import {
  problemKinds,
  type Booking,
  type ProblemKind,
  type ProblemReport,
} from "../lib/rental-contracts";

// R-09 (RENT-01): problem reports on a booking. The customer company reports through its live grant
// on the customer page; here the business reads every report and records the ones that came by
// phone, email or paper. A retry after a lost answer resends the same body with the same key.
export const problemKindLabels: Record<ProblemKind, string> = {
  breakdown: "Breakdown",
  damage: "Damage",
  accident: "Accident",
  other: "Other",
};

const SOURCES = [
  ["phone", "Phone"],
  ["email", "Email"],
  ["paper", "Paper"],
] as const;
type Source = StaffProblemBody["source"];

/** A wall-clock minute in a zone as an instant that has already happened, or a reason. */
export function pastInstant(date: string, time: string, zone: string): string {
  const instant = businessTimeToInstant(date, time, zone);
  if (Date.parse(instant) > Date.now())
    throw new Error(
      "Enter when the problem happened; it cannot be in the future.",
    );
  return instant;
}

function wallTime(instant: string, zone: string) {
  try {
    const local = businessDateTime(instant, zone);
    return `${local.date} ${local.time}`;
  } catch {
    return instant;
  }
}

function reporter(report: ProblemReport) {
  if (report.source === "platform") return "Customer company on the platform";
  const way = report.source === "paper" ? "on paper" : `by ${report.source}`;
  return `${report.reported_by ?? ""} ${way}`;
}

export function RentalProblemReports({
  business,
  booking,
  zone,
}: {
  business: string;
  booking: Booking;
  zone: string;
}) {
  const heading = useId();
  const bookingId = booking.booking_id;
  const [reports, setReports] = useState<ProblemReport[] | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    fetchProblemReports(business, bookingId).then(
      (list) => {
        if (live) setReports(list.items);
      },
      (failure: unknown) => {
        if (live)
          setError(
            `The problem reports could not be read: ${refusal(failure)}`,
          );
      },
    );
    return () => {
      live = false;
    };
  }, [business, bookingId, attempt]);

  function reload() {
    setReports(null);
    setError("");
    setAttempt((value) => value + 1);
  }

  function recorded(report: ProblemReport) {
    setReports((current) =>
      [
        ...(current ?? []).filter((item) => item.number !== report.number),
        report,
      ].sort((a, b) => a.number - b.number),
    );
  }

  return (
    <section aria-labelledby={heading}>
      <h3 id={heading}>Problem reports</h3>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {reports === null && !error && (
        <p className="muted" role="status">
          Loading problem reports…
        </p>
      )}
      {reports?.length === 0 && (
        <p className="muted">No problem reports yet.</p>
      )}
      {reports && reports.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Problem reports table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Problem reports">
            <thead>
              <tr>
                <th scope="col">No.</th>
                <th scope="col">Kind</th>
                <th scope="col">Happened</th>
                <th scope="col">Reported</th>
                <th scope="col">What happened</th>
                <th scope="col">Recorded</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr key={report.number}>
                  <th scope="row">{report.number}</th>
                  <td>{problemKindLabels[report.kind]}</td>
                  <td>{wallTime(report.occurred_at, zone)}</td>
                  <td>{reporter(report)}</td>
                  <td>{report.description}</td>
                  <td>{wallTime(report.recorded_at, zone)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button type="button" className="secondary" onClick={reload}>
        Reload problem reports
      </button>
      {booking.cancellation ? (
        <p className="muted">
          The booking is cancelled, so no new problem can be recorded.
        </p>
      ) : (
        <ProblemForm
          business={business}
          bookingId={bookingId}
          zone={zone}
          onRecorded={recorded}
        />
      )}
    </section>
  );
}

function ProblemForm({
  business,
  bookingId,
  zone,
  onRecorded,
}: {
  business: string;
  bookingId: string;
  zone: string;
  onRecorded: (report: ProblemReport) => void;
}) {
  const [kind, setKind] = useState<ProblemKind | "">("");
  const [description, setDescription] = useState("");
  const [date, setDate] = useState(() => businessToday(zone));
  const [time, setTime] = useState("");
  const [source, setSource] = useState<Source | "">("");
  const [name, setName] = useState("");
  const [pending, setPending] = useState<StaffProblemBody | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const inFlight = useRef(false);
  const locked = busy || pending !== null;

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    setError("");
    setNotice("");
    let body = pending;
    if (!body) {
      if (!kind || !source) {
        setError("Choose the kind of problem and how it was reported.");
        return;
      }
      try {
        body = {
          schema_version: 1,
          kind,
          description: description.trim(),
          occurred_at: pastInstant(date, time, zone),
          source,
          reported_by: name.trim(),
        };
      } catch (failure) {
        setError(refusal(failure));
        return;
      }
    }
    inFlight.current = true;
    setPending(body);
    setBusy(true);
    try {
      const report = await recordProblemReport(business, bookingId, body);
      onRecorded(report);
      setPending(null);
      setKind("");
      setDescription("");
      setTime("");
      setSource("");
      setName("");
      setNotice(`Problem report ${report.number} recorded.`);
    } catch (failure) {
      const refused =
        failure instanceof ManagementApiError &&
        failure.status !== undefined &&
        failure.status >= 400 &&
        failure.status < 500;
      if (refused) {
        setPending(null);
        setError(`The problem report was not recorded: ${refusal(failure)}`);
      } else {
        setError(
          `The answer was lost (${refusal(failure)}). Retry to check whether the report was saved.`,
        );
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form
      aria-label="Record a problem report"
      onSubmit={(event) => void record(event)}
    >
      <label>
        Kind
        <select
          value={kind}
          required
          disabled={locked}
          onChange={(event) =>
            setKind(
              problemKinds.find((item) => item === event.target.value) ?? "",
            )
          }
        >
          <option value="">Choose a kind</option>
          {problemKinds.map((item) => (
            <option key={item} value={item}>
              {problemKindLabels[item]}
            </option>
          ))}
        </select>
      </label>
      <label>
        What happened
        <textarea
          value={description}
          required
          maxLength={2000}
          disabled={locked}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <label>
        Date
        <input
          type="date"
          value={date}
          required
          disabled={locked}
          onChange={(event) => setDate(event.target.value)}
        />
      </label>
      <label>
        Time
        <input
          type="time"
          value={time}
          required
          disabled={locked}
          onChange={(event) => setTime(event.target.value)}
        />
      </label>
      <p className="muted">
        Branch time{zone ? ` (${zone})` : ""}; the moment must have passed.
      </p>
      <label>
        How it was reported
        <select
          value={source}
          required
          disabled={locked}
          onChange={(event) =>
            setSource(
              SOURCES.find(([value]) => value === event.target.value)?.[0] ??
                "",
            )
          }
        >
          <option value="">Choose how</option>
          {SOURCES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Reporter name
        <input
          value={name}
          required
          maxLength={200}
          autoComplete="off"
          disabled={locked}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <div className="mgmt-form-actions">
        <button
          type="submit"
          disabled={busy || (!pending && !description.trim())}
        >
          {busy
            ? "Recording…"
            : pending
              ? "Retry problem report"
              : "Record problem report"}
        </button>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
    </form>
  );
}
