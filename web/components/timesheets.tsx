"use client";
import { useCallback, useEffect, useState } from "react";
import {
  fetchDirectory,
  fetchShifts,
  fetchTimeEntries,
  fetchTimeHistory,
} from "../lib/workforce-api";
import type {
  Shift,
  TimeEntry,
  WorkforceCommand,
} from "../lib/workforce-contracts";
import {
  ClosedNotice,
  CommandNotices,
  MomentFields,
  Panel,
  explain,
  moment,
  span,
  toFields,
  toInstant,
  useDesk,
  useWorkforceCommands,
  worked,
  zoneOf,
  type Moment,
} from "./workforce-shared";

const STATUS: Record<TimeEntry["status"], string> = {
  open: "Open",
  proposed: "Waiting for a decision",
  approved: "Approved",
  declined: "Declined",
};
const ACTION: Record<TimeEntry["action"], string> = {
  clock_in: "Clocked in",
  break_start: "Break started",
  break_end: "Break ended",
  clock_out: "Clocked out",
  correct: "Correction proposed",
  approve: "Approved",
  decline: "Declined",
};
interface Period {
  start: Moment;
  end: Moment;
}
interface Correction extends Period {
  entry: TimeEntry;
  breaks: Period[];
  reason: string;
}
const given = (entry: TimeEntry) =>
  entry.reason_source === "human" ? entry.reason : null;
const newest = (items: TimeEntry[]) =>
  [...items].sort((a, b) => Date.parse(b.starts_at) - Date.parse(a.starts_at));

/** Own clock and time records for everyone; decisions for owners and managers. */
export function Timesheets({
  businessId,
  actorId,
  role,
}: {
  businessId: string;
  actorId: string;
  role: string;
}) {
  const manages = role === "owner" || role === "manager";
  const { desk, workspace, failed, reload } = useDesk(businessId);
  const [mine, setMine] = useState<TimeEntry[] | null>(null);
  const [team, setTeam] = useState<TimeEntry[] | null>(null);
  const [people, setPeople] = useState<Map<string, string>>(new Map());
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [linked, setLinked] = useState("");
  const [cut, setCut] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(true);
  const [history, setHistory] = useState<{
    entry: TimeEntry;
    own: boolean;
    items: TimeEntry[] | null;
  } | null>(null);
  const [correcting, setCorrecting] = useState<Correction | null>(null);
  const [declining, setDeclining] = useState<{
    entry: TimeEntry;
    reason: string;
  } | null>(null);

  const load = useCallback(async () => {
    const now = Date.now();
    const [own, near] = await Promise.all([
      fetchTimeEntries(businessId, true),
      fetchShifts(
        businessId,
        "my-shifts",
        new Date(now - 18 * 3_600_000).toISOString(),
        new Date(now + 30 * 3_600_000).toISOString(),
      ),
    ]);
    let all: Awaited<ReturnType<typeof fetchTimeEntries>> | null = null;
    const names = new Map<string, string>();
    if (manages) {
      const [entries, directory] = await Promise.all([
        fetchTimeEntries(businessId, false),
        fetchDirectory(businessId),
      ]);
      all = entries;
      for (const person of directory.items)
        names.set(person.user_id, person.display_name ?? "Team member");
    }
    setMine(newest(own.items));
    setShifts(near.items.filter((item) => item.status === "published"));
    setTeam(all ? newest(all.items) : null);
    setPeople(names);
    setCut(own.more || Boolean(all?.more));
    setLoadError(null);
  }, [businessId, manages]);
  const refresh = useCallback(async () => {
    await reload();
    await load();
  }, [reload, load]);
  const center = useWorkforceCommands(businessId, actorId, refresh);
  useEffect(() => {
    let active = true;
    void Promise.resolve()
      .then(load)
      .catch((error: unknown) => {
        if (active) setLoadError(explain(error));
      });
    return () => {
      active = false;
    };
  }, [load]);

  const profile = desk?.profile ?? null;
  const open = desk?.writes === "open";
  const zone = (entry: { location_id: string }) =>
    zoneOf(workspace?.locations, entry.location_id);
  const who = (user: string) =>
    user === actorId ? "you" : (people.get(user) ?? "a manager");
  const current = mine?.find((entry) => entry.status === "open") ?? null;

  async function showHistory(entry: TimeEntry, own: boolean) {
    setHistory({ entry, own, items: null });
    try {
      const items = await fetchTimeHistory(businessId, entry.entry_id, own);
      setHistory({ entry, own, items });
    } catch (error) {
      setHistory(null);
      center.report(explain(error));
    }
  }
  async function act(command: WorkforceCommand, done: string) {
    const result = await center.run(command, done);
    if (result && history) void showHistory(history.entry, history.own);
    return result !== null;
  }
  const clock = (
    entry: TimeEntry,
    action: "break_start" | "break_end" | "clock_out",
    done: string,
  ) =>
    act(
      {
        operation: "time.event",
        key: crypto.randomUUID(),
        subject: entry.entry_id,
        body: {
          schema_version: 1,
          expected_revision: entry.revision,
          action,
          at: new Date().toISOString(),
        },
      },
      done,
    );
  function clockIn() {
    if (!profile) return;
    const shift = shifts.find((item) => item.shift_id === linked);
    void act(
      {
        operation: "time.clock_in",
        key: crypto.randomUUID(),
        subject: crypto.randomUUID(),
        body: {
          schema_version: 1,
          expected_revision: 0,
          staff_profile_id: profile.profile_id,
          starts_at: new Date().toISOString(),
          shift_id: shift?.shift_id ?? null,
          expected_shift_revision: shift?.revision ?? null,
        },
      },
      "You are clocked in.",
    );
  }
  function startCorrection(entry: TimeEntry) {
    // A declined proposal is not the basis of the next one; the approved version is.
    const source =
      entry.status === "declined" && entry.effective ? entry.effective : entry;
    const place = zone(entry);
    setDeclining(null);
    setCorrecting({
      entry,
      start: toFields(source.starts_at, place),
      end: toFields(source.ends_at ?? source.starts_at, place),
      breaks: source.breaks.map((period) => ({
        start: toFields(period.starts_at, place),
        end: toFields(period.ends_at, place),
      })),
      reason: "",
    });
  }
  function submitCorrection(event: React.FormEvent) {
    event.preventDefault();
    if (!correcting) return;
    const place = zone(correcting.entry);
    let starts: string;
    let ends: string;
    let breaks: { schema_version: 1; starts_at: string; ends_at: string }[];
    try {
      starts = toInstant(correcting.start, place);
      ends = toInstant(correcting.end, place);
      breaks = correcting.breaks.map((period) => ({
        schema_version: 1 as const,
        starts_at: toInstant(period.start, place),
        ends_at: toInstant(period.end, place),
      }));
    } catch (error) {
      center.report(explain(error));
      return;
    }
    if (Date.parse(ends) <= Date.parse(starts)) {
      center.report("The end must follow the start.");
      return;
    }
    let prior = Date.parse(starts);
    for (const period of breaks) {
      if (
        Date.parse(period.ends_at) <= Date.parse(period.starts_at) ||
        Date.parse(period.starts_at) < prior ||
        Date.parse(period.ends_at) > Date.parse(ends)
      ) {
        center.report(
          "Each break must end after it starts, follow the previous one and stay inside the worked time.",
        );
        return;
      }
      prior = Date.parse(period.ends_at);
    }
    void act(
      {
        operation: "time.event",
        key: crypto.randomUUID(),
        subject: correcting.entry.entry_id,
        body: {
          schema_version: 1,
          expected_revision: correcting.entry.revision,
          action: "correct",
          starts_at: starts,
          ends_at: ends,
          breaks,
          reason: correcting.reason.trim(),
        },
      },
      "Correction sent. The approved version stays in effect until a manager decides.",
    ).then((sent) => {
      if (sent) setCorrecting(null);
    });
  }
  const decide = (entry: TimeEntry, reason: string | null) =>
    act(
      {
        operation: "time.event",
        key: crypto.randomUUID(),
        subject: entry.entry_id,
        body: {
          schema_version: 1,
          expected_revision: entry.revision,
          action: reason === null ? "approve" : "decline",
          reason,
        },
      },
      reason === null
        ? entry.user_id === actorId
          ? "Approved. This is recorded as an approval of your own time."
          : "Approved. This version is now in effect."
        : "Declined. The earlier approved version, if any, stays in effect.",
    );

  const title = (entry: TimeEntry, own: boolean) =>
    `${own ? "My record" : (people.get(entry.user_id) ?? "Team member")} · ${moment(entry.starts_at, zone(entry))}`;
  const record = (entry: TimeEntry, own: boolean) => {
    const place = zone(entry);
    const name = title(entry, own);
    const ownTime = entry.user_id === actorId;
    return (
      <li key={entry.entry_id} className="workforce-item">
        <h3>{name}</h3>
        <p>
          {entry.ends_at
            ? span(entry.starts_at, entry.ends_at, place)
            : `Started ${moment(entry.starts_at, place)}`}
          {entry.worked_microseconds !== null &&
            ` · worked ${worked(entry.worked_microseconds)}`}
          {entry.breaks.length > 0 &&
            ` · ${entry.breaks.length} break${entry.breaks.length > 1 ? "s" : ""}`}
        </p>
        <p className="workforce-badges">
          <span className={`workforce-badge workforce-${entry.status}`}>
            {STATUS[entry.status]}
          </span>
          {/* The mark follows the time that counts, not a pending or declined version. */}
          {(entry.effective?.out_of_schedule ?? entry.out_of_schedule) && (
            <span className="workforce-badge">Outside the schedule</span>
          )}
          {(entry.effective?.self_approved ||
            (entry.status === "approved" && entry.self_approved)) && (
            <span className="workforce-badge workforce-flag">
              Approved by the owner for their own time
            </span>
          )}
        </p>
        {entry.effective && entry.effective.revision !== entry.revision && (
          <p className="workforce-effective">
            In effect: approved version {entry.effective.revision},{" "}
            {span(entry.effective.starts_at, entry.effective.ends_at, place)} ·
            worked {worked(entry.effective.worked_microseconds)}.{" "}
            {entry.status === "proposed"
              ? `Version ${entry.revision} is a pending correction and does not count until a manager approves it.`
              : `Version ${entry.revision} was declined and does not count.`}
            {entry.status === "proposed" &&
              entry.out_of_schedule !== entry.effective.out_of_schedule &&
              ` The pending correction starts ${entry.out_of_schedule ? "outside" : "inside"} the schedule.`}
          </p>
        )}
        {!entry.effective && entry.status === "proposed" && (
          <p className="workforce-effective">
            Nothing is in effect yet: this record waits for a manager.
          </p>
        )}
        {!entry.effective && entry.status === "declined" && (
          <p className="workforce-effective">
            Nothing is in effect: this record was declined and does not count.
          </p>
        )}
        {given(entry) && <p>Reason given: {given(entry)}</p>}
        <div className="workforce-actions">
          {own && entry.status !== "open" && (
            <button
              className="secondary"
              disabled={center.blocked || !open}
              aria-label={`Correct ${name}`}
              onClick={() => startCorrection(entry)}
            >
              Correct
            </button>
          )}
          {!own && entry.status === "proposed" && !ownTime && (
            <>
              <button
                disabled={center.blocked || !open}
                aria-label={`Approve ${name}`}
                onClick={() => void decide(entry, null)}
              >
                Approve
              </button>
              <button
                className="secondary"
                disabled={center.blocked || !open}
                aria-label={`Decline ${name}`}
                onClick={() => {
                  setCorrecting(null);
                  setDeclining({ entry, reason: "" });
                }}
              >
                Decline
              </button>
            </>
          )}
          {!own &&
            entry.status === "proposed" &&
            ownTime &&
            (role === "owner" ? (
              <button
                disabled={center.blocked || !open}
                aria-label={`Approve my own time ${name}`}
                onClick={() => void decide(entry, null)}
              >
                Approve my own time
              </button>
            ) : (
              <span>Another manager decides your own time.</span>
            ))}
          <button
            className="secondary"
            aria-label={`History of ${name}`}
            onClick={() => void showHistory(entry, own)}
          >
            History
          </button>
        </div>
      </li>
    );
  };

  const shown = team?.filter(
    (entry) => !waiting || entry.status === "proposed",
  );
  return (
    <section aria-label="Timesheets" className="workforce">
      <h1>Timesheets</h1>
      <p>
        Clock in and out and take breaks. A correction never rewrites a record:
        it adds a version, and the last approved version stays in effect.
      </p>
      {desk && <ClosedNotice writes={desk.writes} />}
      {(failed ?? loadError) && (
        <p role="alert" className="error">
          {failed ?? loadError}
        </p>
      )}
      <CommandNotices center={center} />
      {cut && (
        <p role="note">
          Only the first 1000 records are shown. Older ones stay stored.
        </p>
      )}
      <section aria-label="My time" className="workforce-card">
        <h2>My time</h2>
        {!desk || mine === null ? (
          <p aria-live="polite">Loading your time records…</p>
        ) : !profile ? (
          <p>
            You are not on the staff schedule yet, so there is nothing to clock.
            Ask a manager to add you.
          </p>
        ) : current ? (
          <>
            <p>
              Clocked in since {moment(current.starts_at, zone(current))}
              {current.break_started_at &&
                `, on a break since ${moment(current.break_started_at, zone(current))}`}
              .
            </p>
            <div className="workforce-actions">
              {current.break_started_at ? (
                <button
                  disabled={center.blocked || !open}
                  onClick={() =>
                    void clock(current, "break_end", "Break ended.")
                  }
                >
                  End break
                </button>
              ) : (
                <button
                  disabled={center.blocked || !open}
                  onClick={() =>
                    void clock(current, "break_start", "Break started.")
                  }
                >
                  Start break
                </button>
              )}
              <button
                disabled={center.blocked}
                onClick={() =>
                  void clock(
                    current,
                    "clock_out",
                    "You are clocked out. The record waits for a manager.",
                  )
                }
              >
                Clock out
              </button>
            </div>
          </>
        ) : (
          <>
            <label>
              Shift
              <select
                value={linked}
                onChange={(event) => setLinked(event.target.value)}
              >
                <option value="">Without a shift</option>
                {shifts.map((item) => (
                  <option key={item.shift_id} value={item.shift_id}>
                    {item.position} ·{" "}
                    {span(item.starts_at, item.ends_at, zone(item))}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={center.blocked || !open} onClick={clockIn}>
              Clock in
            </button>
          </>
        )}
      </section>
      {correcting && (
        <Panel
          label={`Correct ${title(correcting.entry, true)}`}
          onClose={() => setCorrecting(null)}
        >
          <form onSubmit={submitCorrection}>
            <fieldset disabled={center.blocked}>
              <legend>
                Times of {zone(correcting.entry)}. The earlier versions stay
                readable.
              </legend>
              <MomentFields
                legend="Start"
                value={correcting.start}
                onChange={(start) => setCorrecting({ ...correcting, start })}
              />
              <MomentFields
                legend="End"
                value={correcting.end}
                onChange={(end) => setCorrecting({ ...correcting, end })}
              />
              {correcting.breaks.map((period, index) => (
                <fieldset key={index} className="workforce-break">
                  <legend>Break {index + 1}</legend>
                  <MomentFields
                    legend={`Break ${index + 1} start`}
                    value={period.start}
                    onChange={(start) =>
                      setCorrecting({
                        ...correcting,
                        breaks: correcting.breaks.map((item, at) =>
                          at === index ? { ...item, start } : item,
                        ),
                      })
                    }
                  />
                  <MomentFields
                    legend={`Break ${index + 1} end`}
                    value={period.end}
                    onChange={(end) =>
                      setCorrecting({
                        ...correcting,
                        breaks: correcting.breaks.map((item, at) =>
                          at === index ? { ...item, end } : item,
                        ),
                      })
                    }
                  />
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      setCorrecting({
                        ...correcting,
                        breaks: correcting.breaks.filter(
                          (_, at) => at !== index,
                        ),
                      })
                    }
                  >
                    Remove break {index + 1}
                  </button>
                </fieldset>
              ))}
              <button
                type="button"
                className="secondary"
                disabled={correcting.breaks.length >= 100}
                onClick={() =>
                  setCorrecting({
                    ...correcting,
                    breaks: [
                      ...correcting.breaks,
                      { start: correcting.start, end: correcting.start },
                    ],
                  })
                }
              >
                Add a break
              </button>
              <label>
                Reason for the correction
                <textarea
                  required
                  maxLength={1000}
                  value={correcting.reason}
                  onChange={(event) =>
                    setCorrecting({ ...correcting, reason: event.target.value })
                  }
                />
              </label>
              <button type="submit" disabled={!correcting.reason.trim()}>
                Send correction
              </button>
            </fieldset>
          </form>
        </Panel>
      )}
      <section aria-label="My time records" className="workforce-card">
        <h2>My time records</h2>
        {mine && mine.length === 0 && <p>You have no time records yet.</p>}
        <ul className="cp-list">{mine?.map((entry) => record(entry, true))}</ul>
      </section>
      {manages && (
        <section aria-label="Team time records" className="workforce-card">
          <h2>Team time records</h2>
          <label className="workforce-check">
            <input
              type="checkbox"
              checked={waiting}
              onChange={(event) => setWaiting(event.target.checked)}
            />
            Only records waiting for a decision
          </label>
          {team === null && !loadError && (
            <p aria-live="polite">Loading team records…</p>
          )}
          {shown && shown.length === 0 && (
            <p>
              {waiting
                ? "No records are waiting for a decision."
                : "There are no time records in your area."}
            </p>
          )}
          <ul className="cp-list">
            {shown?.map((entry) => record(entry, false))}
          </ul>
        </section>
      )}
      {declining && (
        <Panel
          label={`Decline ${title(declining.entry, false)}`}
          onClose={() => setDeclining(null)}
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void decide(declining.entry, declining.reason.trim()).then(
                (sent) => {
                  if (sent) setDeclining(null);
                },
              );
            }}
          >
            <fieldset disabled={center.blocked}>
              <label>
                Reason for declining
                <textarea
                  required
                  maxLength={1000}
                  value={declining.reason}
                  onChange={(event) =>
                    setDeclining({ ...declining, reason: event.target.value })
                  }
                />
              </label>
              <button type="submit" disabled={!declining.reason.trim()}>
                Decline this version
              </button>
            </fieldset>
          </form>
        </Panel>
      )}
      {history && (
        <Panel
          label={`History of ${title(history.entry, history.own)}`}
          onClose={() => setHistory(null)}
        >
          {history.items === null ? (
            <p aria-live="polite">Loading every version…</p>
          ) : (
            <ol className="cp-list">
              {history.items.map((item) => (
                <li key={item.revision}>
                  <strong>
                    Version {item.revision}: {ACTION[item.action]}
                  </strong>{" "}
                  by {who(item.created_by)} on{" "}
                  {moment(item.created_at, zone(item))}
                  <br />
                  {item.ends_at
                    ? `${span(item.starts_at, item.ends_at, zone(item))} · worked ${worked(item.worked_microseconds ?? 0)}`
                    : `Started ${moment(item.starts_at, zone(item))}`}
                  {item.breaks.length > 0 &&
                    ` · breaks: ${item.breaks
                      .map((period) =>
                        span(period.starts_at, period.ends_at, zone(item)),
                      )
                      .join(", ")}`}
                  {given(item) && ` · reason: ${given(item)}`}
                  {item.action === "approve" &&
                    item.self_approved &&
                    " · approved by the owner for their own time"}
                  {item.effective?.revision === item.revision &&
                    " · in effect from this version"}
                </li>
              ))}
            </ol>
          )}
        </Panel>
      )}
    </section>
  );
}
