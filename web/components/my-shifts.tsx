"use client";
import { useCallback, useEffect, useState } from "react";
import {
  fetchChangeHistory,
  fetchChanges,
  fetchColleagueShifts,
  fetchColleagues,
  fetchShifts,
} from "../lib/workforce-api";
import type {
  Change,
  ChangeKind,
  Colleague,
  Shift,
  WorkforceCommand,
} from "../lib/workforce-contracts";
import {
  ClosedNotice,
  CommandNotices,
  Panel,
  dayWindow,
  explain,
  moment,
  placeOf,
  span,
  useDesk,
  useWorkforceCommands,
  zoneOf,
} from "./workforce-shared";

const DAYS = 28;
export const CHANGE_KIND: Record<ChangeKind, string> = {
  handover: "Handover",
  swap: "Swap",
  pickup: "Open shift request",
};
export const CHANGE_STATUS: Record<Change["status"], string> = {
  proposed: "Waiting for the colleague",
  accepted: "Accepted, waiting for a manager",
  approved: "Approved and applied",
  declined: "Declined",
  withdrawn: "Withdrawn",
};
/** What happened at one step of a request, as opposed to where it stands now. */
export const CHANGE_STEP: Record<Change["status"], string> = {
  proposed: "Proposed",
  accepted: "Accepted by the colleague",
  approved: "Approved by a manager and applied",
  declined: "Declined",
  withdrawn: "Withdrawn",
};
const latest = (items: Change[]) =>
  [...items].sort(
    (a, b) => Date.parse(b.event_created_at) - Date.parse(a.event_created_at),
  );
const soonest = (items: Shift[]) =>
  [...items].sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at));

/** Own shifts, open shifts of the home location and requests to change them. */
export function MyShifts({
  businessId,
  actorId,
}: {
  businessId: string;
  actorId: string;
}) {
  const { desk, workspace, failed, reload } = useDesk(businessId);
  const [from, setFrom] = useState(() => new Date().toISOString().slice(0, 10));
  const [shifts, setShifts] = useState<Shift[] | null>(null);
  const [free, setFree] = useState<Shift[]>([]);
  const [changes, setChanges] = useState<Change[]>([]);
  const [colleagues, setColleagues] = useState<Colleague[]>([]);
  const [known, setKnown] = useState<Map<string, Shift>>(new Map());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [proposing, setProposing] = useState<{
    shift: Shift;
    kind: "handover" | "swap";
    colleague: string;
    theirs: Shift[] | null;
    other: string;
  } | null>(null);
  const [history, setHistory] = useState<{
    change: Change;
    items: Change[] | null;
  } | null>(null);

  const profileId = desk?.profile?.profile_id ?? null;
  const load = useCallback(async () => {
    const window = dayWindow(from, DAYS);
    const [own, vacant, requests, team] = await Promise.all([
      fetchShifts(businessId, "my-shifts", window.starts, window.ends),
      fetchShifts(businessId, "open-shifts", window.starts, window.ends),
      fetchChanges(businessId, true),
      fetchColleagues(businessId),
    ]);
    const map = new Map<string, Shift>();
    for (const item of [...own.items, ...vacant.items])
      map.set(item.shift_id, item);
    // A request names a colleague's shift only by its id; read those shifts too.
    const others = new Set<string>();
    for (const request of requests.items)
      for (const side of [request.from_profile_id, request.target_profile_id])
        if (side && team.items.some((item) => item.profile_id === side))
          others.add(side);
    const theirs = await Promise.allSettled(
      [...others]
        .slice(0, 10)
        .map((side) =>
          fetchColleagueShifts(businessId, side, window.starts, window.ends),
        ),
    );
    for (const part of theirs)
      if (part.status === "fulfilled")
        for (const item of part.value.items)
          if (!map.has(item.shift_id)) map.set(item.shift_id, item);
    setShifts(soonest(own.items.filter((item) => item.status === "published")));
    setFree(soonest(vacant.items));
    setChanges(latest(requests.items));
    setColleagues(team.items);
    setKnown(map);
    setLoadError(null);
  }, [businessId, from]);
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

  const open = desk?.writes === "open";
  const others = colleagues.filter((item) => item.profile_id !== profileId);
  const person = (profile: string | null) =>
    profile === null
      ? "nobody"
      : profile === profileId
        ? "you"
        : (colleagues.find((item) => item.profile_id === profile)
            ?.display_name ?? "a colleague of another location");
  const describe = (shift: Shift) =>
    `${shift.position} · ${span(shift.starts_at, shift.ends_at, zoneOf(workspace?.locations, shift.location_id))} · ${placeOf(workspace?.locations, shift.location_id)}`;
  const named = (shift: string | null) => {
    if (shift === null) return "";
    const found = known.get(shift);
    return found ? describe(found) : "a shift outside the dates shown";
  };

  async function chooseColleague(colleague: string) {
    if (!proposing) return;
    const next = { ...proposing, colleague, theirs: null, other: "" };
    setProposing(next);
    if (proposing.kind !== "swap" || !colleague) return;
    try {
      const window = dayWindow(from, DAYS);
      const listed = await fetchColleagueShifts(
        businessId,
        colleague,
        window.starts,
        window.ends,
      );
      setProposing({ ...next, theirs: soonest(listed.items) });
    } catch (error) {
      setProposing({ ...next, theirs: [] });
      center.report(explain(error));
    }
  }
  const propose = (
    kind: ChangeKind,
    shift: Shift,
    target: string,
    other: Shift | null,
    done: string,
  ) =>
    center.run(
      {
        operation: "change.propose",
        key: crypto.randomUUID(),
        subject: crypto.randomUUID(),
        body: {
          schema_version: 1,
          kind,
          shift_id: shift.shift_id,
          expected_shift_revision: shift.revision,
          target_profile_id: target,
          other_shift_id: other?.shift_id ?? null,
          expected_other_shift_revision: other?.revision ?? null,
        },
      },
      done,
    );
  function submitProposal(event: React.FormEvent) {
    event.preventDefault();
    if (!proposing?.colleague) return;
    const other =
      proposing.theirs?.find((item) => item.shift_id === proposing.other) ??
      null;
    if (proposing.kind === "swap" && !other) return;
    void propose(
      proposing.kind,
      proposing.shift,
      proposing.colleague,
      other,
      `Request sent to ${person(proposing.colleague)}. It takes effect only after they accept and a manager approves.`,
    ).then((sent) => {
      if (sent) setProposing(null);
    });
  }
  const answer = (
    change: Change,
    action: "accept" | "decline" | "withdraw",
    done: string,
  ) => {
    const command: WorkforceCommand = {
      operation: "change.event",
      key: crypto.randomUUID(),
      subject: change.request_id,
      body: {
        schema_version: 1,
        expected_revision: change.revision,
        action,
      },
    };
    return center.run(command, done).then((result) => {
      if (result && history) setHistory(null);
    });
  };
  async function showHistory(change: Change) {
    setHistory({ change, items: null });
    try {
      const items = await fetchChangeHistory(
        businessId,
        change.request_id,
        true,
      );
      setHistory({ change, items });
    } catch (error) {
      setHistory(null);
      center.report(explain(error));
    }
  }

  const summary = (change: Change) =>
    `${CHANGE_KIND[change.kind]}: ${named(change.shift_id)}${change.other_shift_id ? ` for ${named(change.other_shift_id)}` : ""}`;
  return (
    <section aria-label="My shifts" className="workforce">
      <h1>My shifts</h1>
      <p>
        Your shifts for four weeks. A handover, a swap or an open shift takes
        effect only after the colleague accepts and a manager approves.
      </p>
      {desk && <ClosedNotice writes={desk.writes} />}
      {(failed ?? loadError) && (
        <p role="alert" className="error">
          {failed ?? loadError}
        </p>
      )}
      <CommandNotices center={center} />
      {!desk || shifts === null ? (
        !(failed ?? loadError) && <p aria-live="polite">Loading your shifts…</p>
      ) : !profileId ? (
        <p>
          You are not on the staff schedule yet. Ask a manager to add you, then
          your shifts appear here.
        </p>
      ) : (
        <>
          <label>
            Show four weeks from
            <input
              type="date"
              required
              value={from}
              onChange={(event) => {
                if (event.target.value) setFrom(event.target.value);
              }}
            />
          </label>
          <section aria-label="Assigned to me" className="workforce-card">
            <h2>Assigned to me</h2>
            {shifts.length === 0 && <p>No shifts in these four weeks.</p>}
            <ul className="cp-list">
              {shifts.map((shift) => (
                <li key={shift.shift_id} className="workforce-item">
                  <h3>{describe(shift)}</h3>
                  <div className="workforce-actions">
                    {(["handover", "swap"] as const).map((kind) => (
                      <button
                        key={kind}
                        className="secondary"
                        disabled={
                          center.blocked || !open || others.length === 0
                        }
                        aria-label={`${kind === "handover" ? "Hand over" : "Swap"} ${describe(shift)}`}
                        onClick={() =>
                          setProposing({
                            shift,
                            kind,
                            colleague: "",
                            theirs: null,
                            other: "",
                          })
                        }
                      >
                        {kind === "handover" ? "Hand over" : "Swap"}
                      </button>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
            {others.length === 0 && shifts.length > 0 && (
              <p>There are no colleagues in your location to ask.</p>
            )}
          </section>
          {proposing && (
            <Panel
              label={`${proposing.kind === "handover" ? "Hand over" : "Swap"} ${describe(proposing.shift)}`}
              onClose={() => setProposing(null)}
            >
              <form onSubmit={submitProposal}>
                <fieldset disabled={center.blocked}>
                  <label>
                    Colleague
                    <select
                      required
                      value={proposing.colleague}
                      onChange={(event) =>
                        void chooseColleague(event.target.value)
                      }
                    >
                      <option value="">Choose a colleague</option>
                      {others.map((item) => (
                        <option key={item.profile_id} value={item.profile_id}>
                          {item.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                  {proposing.kind === "swap" && proposing.colleague && (
                    <label>
                      Their shift
                      <select
                        required
                        value={proposing.other}
                        disabled={proposing.theirs === null}
                        onChange={(event) =>
                          setProposing({
                            ...proposing,
                            other: event.target.value,
                          })
                        }
                      >
                        <option value="">
                          {proposing.theirs === null
                            ? "Loading their shifts…"
                            : proposing.theirs.length
                              ? "Choose their shift"
                              : "They have no shifts in these dates"}
                        </option>
                        {proposing.theirs?.map((item) => (
                          <option key={item.shift_id} value={item.shift_id}>
                            {describe(item)}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <button
                    type="submit"
                    disabled={
                      !proposing.colleague ||
                      (proposing.kind === "swap" && !proposing.other)
                    }
                  >
                    Send request
                  </button>
                </fieldset>
              </form>
            </Panel>
          )}
          <section aria-label="Open shifts" className="workforce-card">
            <h2>Open shifts</h2>
            {free.length === 0 && (
              <p>No open shifts in your location for these dates.</p>
            )}
            <ul className="cp-list">
              {free.map((shift) => (
                <li key={shift.shift_id} className="workforce-item">
                  <h3>{describe(shift)}</h3>
                  <button
                    className="secondary"
                    disabled={center.blocked || !open}
                    aria-label={`Ask for ${describe(shift)}`}
                    onClick={() =>
                      void propose(
                        "pickup",
                        shift,
                        profileId,
                        null,
                        "Request saved. Confirm it below; then a manager decides.",
                      )
                    }
                  >
                    Ask for this shift
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section aria-label="My requests" className="workforce-card">
            <h2>My requests</h2>
            {changes.length === 0 && <p>You have no requests.</p>}
            <ul className="cp-list">
              {changes.map((change) => {
                const mine = change.proposed_by === actorId;
                const asked = change.recipient_user_id === actorId;
                const label = summary(change);
                return (
                  <li key={change.request_id} className="workforce-item">
                    <h3>{label}</h3>
                    <p>
                      From {person(change.from_profile_id)} to{" "}
                      {person(change.target_profile_id)} ·{" "}
                      <span
                        className={`workforce-badge workforce-${change.status}`}
                      >
                        {CHANGE_STATUS[change.status]}
                      </span>{" "}
                      ·{" "}
                      {moment(
                        change.event_created_at,
                        zoneOf(workspace?.locations, change.location_id),
                      )}
                    </p>
                    <div className="workforce-actions">
                      {change.status === "proposed" && asked && (
                        <button
                          disabled={center.blocked || !open}
                          aria-label={`${mine ? "Confirm" : "Accept"} ${label}`}
                          onClick={() =>
                            void answer(
                              change,
                              "accept",
                              "Accepted. A manager decides next.",
                            )
                          }
                        >
                          {mine ? "Confirm my request" : "Accept"}
                        </button>
                      )}
                      {change.status === "proposed" && asked && !mine && (
                        <button
                          className="secondary"
                          disabled={center.blocked || !open}
                          aria-label={`Decline ${label}`}
                          onClick={() =>
                            void answer(change, "decline", "Request declined.")
                          }
                        >
                          Decline
                        </button>
                      )}
                      {["proposed", "accepted"].includes(change.status) &&
                        mine && (
                          <button
                            className="secondary"
                            disabled={center.blocked || !open}
                            aria-label={`Withdraw ${label}`}
                            onClick={() =>
                              void answer(
                                change,
                                "withdraw",
                                "Request withdrawn. Nothing changed.",
                              )
                            }
                          >
                            Withdraw
                          </button>
                        )}
                      <button
                        className="secondary"
                        aria-label={`History of ${label}`}
                        onClick={() => void showHistory(change)}
                      >
                        History
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
          {history && (
            <Panel
              label={`History of ${summary(history.change)}`}
              onClose={() => setHistory(null)}
            >
              {history.items === null ? (
                <p aria-live="polite">Loading every step…</p>
              ) : (
                <ol className="cp-list">
                  {history.items.map((item) => (
                    <li key={item.revision}>
                      <strong>
                        Step {item.revision}: {CHANGE_STEP[item.status]}
                      </strong>{" "}
                      by{" "}
                      {item.event_created_by === actorId
                        ? "you"
                        : "another person"}{" "}
                      on{" "}
                      {moment(
                        item.event_created_at,
                        zoneOf(workspace?.locations, item.location_id),
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
          )}
        </>
      )}
    </section>
  );
}
