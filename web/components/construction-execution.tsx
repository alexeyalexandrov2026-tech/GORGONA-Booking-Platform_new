"use client";

// O7b (package O): execution on the site. The schedule (insert-only versions with dependencies; the
// server derives conflicts, the critical phases and the planned finish), daily reports per site date
// (sent with the revision read) and completed quantities (cumulative, capped by the contract on the
// server; a measurement keeps its Idempotency-Key until saved). O4a decisions 1-9.
import React, { useId, useState } from "react";
import {
  fetchDailyReport,
  recordMeasurement,
  refusal,
  saveDailyReport,
  saveSchedule,
  type ScheduleBody,
} from "../lib/construction-api";
import type {
  DailyReportList,
  Measurement,
  Progress,
  Project,
  Schedule,
} from "../lib/construction-contracts";
import { formatMinor, quantityText } from "../lib/construction-rules";
import { lineKey, lineLabel, lineName } from "./construction-budget";
import { siteTime } from "./construction-estimates";

const yes = (value: boolean) => (value ? "Yes" : "No");

type Plan = { start: string; finish: string; after: string[] };

export function SchedulePanel({
  businessId,
  project,
  schedule,
  phases,
  onChanged,
}: {
  businessId: string;
  project: Project;
  schedule: Schedule;
  phases: string[];
  onChanged: (text: string) => Promise<void>;
}) {
  const headingId = useId();
  const [plan, setPlan] = useState<Record<string, Plan>>(() =>
    Object.fromEntries(
      phases.map((name) => {
        const found = schedule.phases.find((p) => p.phase === name);
        return [
          name,
          {
            start: found?.planned_start ?? "",
            finish: found?.planned_finish ?? "",
            after: found?.depends_on ?? [],
          },
        ];
      }),
    ),
  );
  const [note, setNote] = useState(schedule.note ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (name: string, change: Partial<Plan>) =>
    setPlan((all) => ({ ...all, [name]: { ...all[name]!, ...change } }));
  const planned = (name: string) =>
    Boolean(plan[name]?.start && plan[name]?.finish);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const body: ScheduleBody["phases"] = [];
    for (const name of phases) {
      const row = plan[name]!;
      if (!row.start && !row.finish) continue;
      if (!row.start || !row.finish) {
        setError(
          `${name}: give both the planned start and the planned finish.`,
        );
        return;
      }
      body.push({
        phase: name,
        planned_start: row.start,
        planned_finish: row.finish,
        depends_on: row.after.filter(planned),
      });
    }
    if (body.length === 0) {
      setError("Plan at least one phase.");
      return;
    }
    setBusy(true);
    try {
      const saved = await saveSchedule(businessId, project.project_id, {
        schema_version: 1,
        expected_revision: schedule.revision,
        note: note.trim() || null,
        phases: body,
      });
      await onChanged(`Schedule revision ${saved.revision} saved.`);
    } catch (failure) {
      setError(`The schedule was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Schedule</h3>
      {schedule.revision === 0 ? (
        <p className="muted">No schedule yet.</p>
      ) : (
        <>
          <p>
            {`Revision ${schedule.revision}`}
            {schedule.recorded_at &&
              `, saved ${siteTime(schedule.recorded_at, project.time_zone)}`}
          </p>
          {schedule.planned_finish && (
            <p>{`Planned finish: ${schedule.planned_finish}`}</p>
          )}
          <div
            className="mgmt-table-container"
            role="region"
            aria-label="Planned phases table"
            tabIndex={0}
          >
            <table className="mgmt-table" aria-label="Planned phases">
              <thead>
                <tr>
                  <th scope="col">Phase</th>
                  <th scope="col">Start</th>
                  <th scope="col">Finish</th>
                  <th scope="col">Depends on</th>
                  <th scope="col">Conflict</th>
                  <th scope="col">Critical</th>
                  <th scope="col">Done</th>
                </tr>
              </thead>
              <tbody>
                {schedule.phases.map((p) => (
                  <tr key={p.phase}>
                    <th scope="row">{p.phase}</th>
                    <td>{p.planned_start}</td>
                    <td>{p.planned_finish}</td>
                    <td>
                      {p.depends_on.length ? p.depends_on.join(", ") : "—"}
                    </td>
                    <td>{yes(p.conflict)}</td>
                    <td>{yes(p.critical)}</td>
                    <td>{`${p.percent}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {schedule.unscheduled.length > 0 && (
        <p className="muted">{`Not scheduled: ${schedule.unscheduled.join(", ")}`}</p>
      )}
      <form aria-label="Schedule" onSubmit={submit}>
        <p className="muted">
          Site dates in {project.time_zone}. A phase is planned when both dates
          are given.
        </p>
        {phases.map((name) => (
          <div
            key={name}
            className="construction-line"
            role="group"
            aria-label={name}
          >
            <label>
              {`${name} planned start`}
              <input
                type="date"
                value={plan[name]?.start ?? ""}
                onChange={(e) => set(name, { start: e.target.value })}
              />
            </label>
            <label>
              {`${name} planned finish`}
              <input
                type="date"
                value={plan[name]?.finish ?? ""}
                onChange={(e) => set(name, { finish: e.target.value })}
              />
            </label>
            {phases
              .filter((other) => other !== name)
              .map((other) => (
                <label key={other} className="construction-check">
                  <input
                    type="checkbox"
                    checked={plan[name]?.after.includes(other) ?? false}
                    onChange={(e) =>
                      set(name, {
                        after: e.target.checked
                          ? [...(plan[name]?.after ?? []), other]
                          : (plan[name]?.after ?? []).filter(
                              (x) => x !== other,
                            ),
                      })
                    }
                  />
                  {`${name} depends on ${other}`}
                </label>
              ))}
          </div>
        ))}
        <label>
          Schedule note
          <input
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Save schedule
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

type Crew = { key: string; label: string; headcount: string };
const blankCrew = (): Crew => ({
  key: crypto.randomUUID(),
  label: "",
  headcount: "",
});

export function DailyReports({
  businessId,
  project,
  reports,
  onChanged,
}: {
  businessId: string;
  project: Project;
  reports: DailyReportList["items"];
  onChanged: (text: string) => Promise<void>;
}) {
  const headingId = useId();
  const [date, setDate] = useState("");
  const [revision, setRevision] = useState(0);
  const [weather, setWeather] = useState("");
  const [notes, setNotes] = useState("");
  const [crew, setCrew] = useState<Crew[]>(() => [blankCrew()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const change = (index: number, field: "label" | "headcount", value: string) =>
    setCrew((rows) =>
      rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );

  /** A chosen date shows its report, so a change is sent with the revision read. */
  async function choose(value: string) {
    setDate(value);
    setError(null);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return;
    try {
      const found = await fetchDailyReport(
        businessId,
        project.project_id,
        value,
      );
      setRevision(found?.revision ?? 0);
      if (found) {
        setWeather(found.weather ?? "");
        setNotes(found.notes ?? "");
        setCrew(
          found.crew.length
            ? found.crew.map((c) => ({
                key: crypto.randomUUID(),
                label: c.label,
                headcount: String(c.headcount),
              }))
            : [blankCrew()],
        );
      }
    } catch (failure) {
      setError(`The report of ${value} could not be read: ${refusal(failure)}`);
    }
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const people = [];
    for (const [index, row] of crew.entries()) {
      if (!row.label.trim() && !row.headcount.trim()) continue;
      const count = Number(row.headcount);
      if (
        !row.label.trim() ||
        !/^\d{1,4}$/.test(row.headcount) ||
        count < 1 ||
        count > 1000
      ) {
        setError(`Crew ${index + 1}: a label and a headcount from 1 to 1000.`);
        return;
      }
      people.push({
        label: row.label.trim(),
        headcount: count,
        counterparty_id: null,
      });
    }
    setBusy(true);
    try {
      const saved = await saveDailyReport(
        businessId,
        project.project_id,
        date,
        {
          schema_version: 1,
          expected_revision: revision,
          weather: weather.trim() || null,
          notes: notes.trim() || null,
          crew: people,
          photos: [],
        },
      );
      setRevision(saved.revision);
      await onChanged(
        `The report of ${saved.report_date} is saved as revision ${saved.revision}.`,
      );
    } catch (failure) {
      setError(`The report was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Daily reports</h3>
      {reports.length === 0 ? (
        <p className="muted">No daily reports yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Daily reports table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Daily reports">
            <thead>
              <tr>
                <th scope="col">Site date</th>
                <th scope="col">Revision</th>
                <th scope="col">Weather</th>
                <th scope="col">Headcount</th>
                <th scope="col">Photos</th>
                <th scope="col">Saved</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.report_date}>
                  <th scope="row">{r.report_date}</th>
                  <td>{r.revision}</td>
                  <td>{r.weather ?? "—"}</td>
                  <td>{r.headcount}</td>
                  <td>{r.photo_count}</td>
                  <td>{siteTime(r.recorded_at, project.time_zone)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form aria-label="Daily report" onSubmit={submit}>
        <label>
          Report date
          <input
            type="date"
            value={date}
            onChange={(e) => void choose(e.target.value)}
            required
          />
        </label>
        <label>
          Weather
          <input
            value={weather}
            maxLength={200}
            onChange={(e) => setWeather(e.target.value)}
          />
        </label>
        <label>
          Notes
          <input
            value={notes}
            maxLength={4000}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
        {crew.map((row, index) => (
          <div
            key={row.key}
            className="construction-line"
            role="group"
            aria-label={`Crew ${index + 1}`}
          >
            <label>
              {`Crew ${index + 1} label`}
              <input
                value={row.label}
                maxLength={64}
                onChange={(e) => change(index, "label", e.target.value)}
              />
            </label>
            <label>
              {`Crew ${index + 1} headcount`}
              <input
                value={row.headcount}
                inputMode="numeric"
                onChange={(e) => change(index, "headcount", e.target.value)}
              />
            </label>
            {crew.length > 1 && (
              <button
                type="button"
                onClick={() =>
                  setCrew((rows) => rows.filter((_, i) => i !== index))
                }
              >
                {`Remove crew row ${index + 1}`}
              </button>
            )}
          </div>
        ))}
        <div className="mgmt-form-actions">
          {crew.length < 50 && (
            <button
              type="button"
              onClick={() => setCrew((rows) => [...rows, blankCrew()])}
            >
              Add a crew row
            </button>
          )}
          <button type="submit" disabled={busy}>
            Save report
          </button>
        </div>
        {revision > 0 && (
          <p className="muted">{`Editing revision ${revision} of this date.`}</p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

export function ProgressPanel({
  businessId,
  project,
  places,
  progress,
  measurements,
  onChanged,
}: {
  businessId: string;
  project: Project;
  places: number;
  progress: Progress;
  measurements: Measurement[];
  onChanged: (text: string) => Promise<void>;
}) {
  const headingId = useId();
  const lineId = useId();
  const [line, setLine] = useState("");
  const [measured, setMeasured] = useState("");
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const money = (minor: number) => formatMinor(minor, places);
  const unitOf = (changeOrder: number | null, position: number) =>
    progress.lines.find(
      (l) => l.change_order === changeOrder && l.position === position,
    )?.unit ?? "";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const chosen = progress.lines.find(
      (l) => lineKey(l.change_order, l.position) === line,
    );
    if (!chosen) {
      setError("Choose a line.");
      return;
    }
    if (!/^(0|[1-9]\d{0,8})(\.\d{1,4})?$/.test(quantity.trim())) {
      setError(
        "The quantity to date is 0 or more with at most 4 decimal places.",
      );
      return;
    }
    setBusy(true);
    try {
      const saved = await recordMeasurement(businessId, project.project_id, {
        schema_version: 1,
        change_order: chosen.change_order,
        position: chosen.position,
        measured_on: measured,
        quantity_to_date: quantity.trim(),
        note: note.trim() || null,
      });
      setLine("");
      setMeasured("");
      setQuantity("");
      setNote("");
      await onChanged(`Measurement ${saved.number} recorded.`);
    } catch (failure) {
      setError(`The quantity was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="construction-section" aria-labelledby={headingId}>
      <h3 id={headingId}>Completed quantities</h3>
      <p className="muted">
        {`Completed ${money(progress.completed_minor)} of ${money(progress.contract_minor)} ${project.currency} (${progress.percent}%).`}
      </p>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Progress lines table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Progress lines">
          <thead>
            <tr>
              <th scope="col">Line</th>
              <th scope="col">Phase</th>
              <th scope="col">Description</th>
              <th scope="col">Contracted</th>
              <th scope="col">Completed</th>
              <th scope="col">Done</th>
              <th scope="col">Value</th>
              <th scope="col">Completed value</th>
            </tr>
          </thead>
          <tbody>
            {progress.lines.map((l) => (
              <tr key={lineKey(l.change_order, l.position)}>
                <th scope="row">{lineName(l.change_order, l.position)}</th>
                <td>{l.phase}</td>
                <td>{l.description}</td>
                <td>{`${quantityText(l.quantity)} ${l.unit}`}</td>
                <td>{`${quantityText(l.completed)} ${l.unit}`}</td>
                <td>{`${l.percent}%`}</td>
                <td>{money(l.contract_minor)}</td>
                <td>{money(l.completed_minor)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Progress by phase table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Progress by phase">
          <thead>
            <tr>
              <th scope="col">Phase</th>
              <th scope="col">Value</th>
              <th scope="col">Completed value</th>
              <th scope="col">Done</th>
            </tr>
          </thead>
          <tbody>
            {progress.phases.map((p) => (
              <tr key={p.phase}>
                <th scope="row">{p.phase}</th>
                <td>{money(p.contract_minor)}</td>
                <td>{money(p.completed_minor)}</td>
                <td>{`${p.percent}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {measurements.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Measurements table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Measurements">
            <thead>
              <tr>
                <th scope="col">Number</th>
                <th scope="col">Line</th>
                <th scope="col">Site date</th>
                <th scope="col">Quantity to date</th>
                <th scope="col">Note</th>
              </tr>
            </thead>
            <tbody>
              {measurements.map((m) => (
                <tr key={m.number}>
                  <th scope="row">{m.number}</th>
                  <td>{lineName(m.change_order, m.position)}</td>
                  <td>{m.measured_on}</td>
                  <td>{`${quantityText(m.quantity_to_date)} ${unitOf(m.change_order, m.position)}`}</td>
                  <td>{m.note ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form aria-label="Completed quantity" onSubmit={submit}>
        {/* Its own label: a label around a select would take the options into its name. */}
        <label htmlFor={lineId}>Line</label>
        <select
          id={lineId}
          className="construction-select"
          value={line}
          onChange={(e) => setLine(e.target.value)}
          required
        >
          <option value="">Choose</option>
          {progress.lines.map((l) => (
            <option
              key={lineKey(l.change_order, l.position)}
              value={lineKey(l.change_order, l.position)}
            >
              {lineLabel(l)}
            </option>
          ))}
        </select>
        <label>
          Measured on
          <input
            type="date"
            value={measured}
            onChange={(e) => setMeasured(e.target.value)}
            required
          />
        </label>
        <label>
          Quantity to date
          <input
            value={quantity}
            inputMode="decimal"
            onChange={(e) => setQuantity(e.target.value)}
            required
          />
        </label>
        <label>
          Note
          <input
            value={note}
            maxLength={500}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Record quantity
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}
