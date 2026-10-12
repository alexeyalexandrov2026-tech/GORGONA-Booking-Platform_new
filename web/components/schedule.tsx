"use client";
import { useCallback, useEffect, useState } from "react";
import { businessDateTime, shiftDate } from "../lib/business-time";
import {
  fetchChangeHistory,
  fetchChanges,
  fetchDirectory,
  fetchLocationSetting,
  fetchShift,
  fetchShifts,
  fetchSkillHistory,
  fetchSkills,
} from "../lib/workforce-api";
import type {
  Change,
  DirectoryEntry,
  LocationSetting,
  Shift,
  ShiftStatus,
  Skill,
  StaffSkill,
  WorkforceCommand,
} from "../lib/workforce-contracts";
import { LocationFilter } from "./location-filter";
import { CHANGE_KIND, CHANGE_STATUS, CHANGE_STEP } from "./my-shifts";
import {
  ClosedNotice,
  CommandNotices,
  MomentFields,
  Panel,
  dayWindow,
  explain,
  moment,
  placeOf,
  span,
  toFields,
  toInstant,
  today,
  useDesk,
  useWorkforceCommands,
  zoneOf,
  type Moment,
} from "./workforce-shared";

const DAYS = 7;
const SHIFT_STATUS: Record<ShiftStatus, string> = {
  draft: "Draft",
  published: "Published",
  cancelled: "Cancelled",
};
const ROLE: Record<DirectoryEntry["role"], string> = {
  owner: "Owner",
  manager: "Manager",
  front_desk: "Front desk",
  artist: "Staff",
};
type Tab = "shifts" | "staff" | "requests" | "privacy";
const TABS: [Tab, string][] = [
  ["shifts", "Shifts"],
  ["staff", "Staff and skills"],
  ["requests", "Change requests"],
  ["privacy", "Privacy"],
];
interface ShiftForm {
  shift: Shift | null;
  start: Moment;
  end: Moment;
  position: string;
  skills: string[];
  status: ShiftStatus;
  assignee: string;
}
interface SkillForm {
  skill: Skill | null;
  code: string;
  name: string;
  archived: boolean;
}

/** Schedule of one location: shifts, staff with skills and change requests. */
export function Schedule({
  businessId,
  actorId,
  companyWide,
}: {
  businessId: string;
  actorId: string;
  companyWide: boolean;
}) {
  const { desk, workspace, failed, reload } = useDesk(businessId);
  const [tab, setTab] = useState<Tab>("shifts");
  const [chosen, setChosen] = useState("");
  const [picked, setPicked] = useState("");
  const [shifts, setShifts] = useState<Shift[] | null>(null);
  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [changes, setChanges] = useState<Change[]>([]);
  const [known, setKnown] = useState<Map<string, Shift>>(new Map());
  const [cut, setCut] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState<ShiftForm | null>(null);
  const [versions, setVersions] = useState<{
    shift: Shift;
    items: Shift[] | null;
  } | null>(null);
  const [person, setPerson] = useState<{
    entry: DirectoryEntry;
    grants: Map<string, StaffSkill[]> | null;
    from: Moment;
  } | null>(null);
  const [skillForm, setSkillForm] = useState<SkillForm | null>(null);
  const [waiting, setWaiting] = useState(true);
  const [steps, setSteps] = useState<{
    change: Change;
    items: Change[] | null;
  } | null>(null);

  const [privacy, setPrivacy] = useState<LocationSetting | null>(null);
  const [privacyError, setPrivacyError] = useState<string | null>(null);
  // An unsaved choice belongs to the location it was made for.
  const [choice, setChoice] = useState<{
    location: string;
    visible: boolean;
  } | null>(null);

  const locations = workspace?.locations;
  const selected =
    chosen || workspace?.location_id || workspace?.locations[0]?.id || "";
  // Until a date is chosen the week starts today in the location's own time.
  const from = picked || today(zoneOf(locations, selected));
  const loadPrivacy = useCallback(async () => {
    if (!selected) return;
    try {
      setPrivacy(await fetchLocationSetting(businessId, selected));
      setPrivacyError(null);
    } catch (error) {
      setPrivacy(null);
      setPrivacyError(explain(error));
    }
  }, [businessId, selected]);
  const load = useCallback(async () => {
    const window = dayWindow(from, DAYS);
    const [listed, people, catalogue, requests] = await Promise.all([
      fetchShifts(businessId, "shifts", window.starts, window.ends),
      fetchDirectory(businessId),
      fetchSkills(businessId),
      fetchChanges(businessId, false),
    ]);
    const map = new Map(listed.items.map((item) => [item.shift_id, item]));
    // A request names shifts by id; read the ones outside the week shown.
    const missing = new Set<string>();
    for (const request of requests.items)
      for (const shift of [request.shift_id, request.other_shift_id])
        if (shift && !map.has(shift)) missing.add(shift);
    const extra = await Promise.allSettled(
      [...missing].slice(0, 40).map((shift) => fetchShift(businessId, shift)),
    );
    for (const part of extra)
      if (part.status === "fulfilled") map.set(part.value.shift_id, part.value);
    setShifts(
      [...listed.items].sort(
        (a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at),
      ),
    );
    setDirectory(people.items);
    setSkills(catalogue.items);
    setChanges(
      [...requests.items].sort(
        (a, b) =>
          Date.parse(b.event_created_at) - Date.parse(a.event_created_at),
      ),
    );
    setKnown(map);
    setCut(listed.more || people.more || requests.more);
    setLoadError(null);
  }, [businessId, from]);
  const refresh = useCallback(async () => {
    await reload();
    await load();
    await loadPrivacy();
  }, [reload, load, loadPrivacy]);
  const center = useWorkforceCommands(businessId, actorId, refresh);
  useEffect(() => {
    void Promise.resolve().then(loadPrivacy);
  }, [loadPrivacy]);
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
  const staff = directory.filter((entry) => entry.profile_id !== null);
  const nameOf = (profile: string | null) =>
    profile === null
      ? "nobody"
      : (directory.find((entry) => entry.profile_id === profile)
          ?.display_name ?? "a person outside your area");
  const skillNames = (ids: string[]) =>
    ids
      .map(
        (id) =>
          skills.find((skill) => skill.skill_id === id)?.name ?? "a skill",
      )
      .join(", ");
  const describe = (shift: Shift) =>
    `${shift.position} · ${span(shift.starts_at, shift.ends_at, zoneOf(locations, shift.location_id))}`;
  const named = (shift: string | null) => {
    if (shift === null) return "";
    const found = known.get(shift);
    return found
      ? `${describe(found)} · ${placeOf(locations, found.location_id)}`
      : "a shift outside your area";
  };
  const until = shiftDate(from, DAYS);
  const week = shifts?.filter((shift) => {
    if (shift.location_id !== selected) return false;
    const zone = zoneOf(locations, shift.location_id);
    return (
      businessDateTime(shift.starts_at, zone).date < until &&
      businessDateTime(shift.ends_at, zone).date >= from
    );
  });

  async function act(command: WorkforceCommand, done: string) {
    const result = await center.run(command, done);
    return result !== null;
  }
  // A setting read for another location is never shown for this one.
  const current = privacy?.location_id === selected ? privacy : null;
  const visible =
    (choice?.location === selected ? choice.visible : null) ??
    current?.colleague_shifts_visible ??
    true;
  const changer =
    current?.changed_by === actorId
      ? "you"
      : (directory.find((entry) => entry.user_id === current?.changed_by)
          ?.display_name ?? "another manager");
  function savePrivacy(event: React.FormEvent) {
    event.preventDefault();
    if (!current || visible === current.colleague_shifts_visible) return;
    void act(
      {
        operation: "location_setting",
        key: crypto.randomUUID(),
        subject: current.location_id,
        body: {
          schema_version: 1,
          expected_revision: current.revision,
          colleague_shifts_visible: visible,
        },
      },
      visible
        ? "Saved. Staff of this location now see colleagues’ published shifts."
        : "Saved. Staff of this location now see only their own shifts and open shifts.",
    ).then((saved) => {
      if (saved) setChoice(null);
    });
  }
  function openShift(shift: Shift | null) {
    const zone = zoneOf(locations, shift?.location_id ?? selected);
    setVersions(null);
    setEditing(
      shift
        ? {
            shift,
            start: toFields(shift.starts_at, zone),
            end: toFields(shift.ends_at, zone),
            position: shift.position,
            skills: [...shift.required_skill_ids],
            status: shift.status,
            assignee: shift.staff_profile_id ?? "",
          }
        : {
            shift: null,
            start: { date: from, time: "09:00" },
            end: { date: from, time: "17:00" },
            position: "",
            skills: [],
            status: "draft",
            assignee: "",
          },
    );
  }
  function saveShift(event: React.FormEvent) {
    event.preventDefault();
    if (!editing) return;
    const location = editing.shift?.location_id ?? selected;
    const zone = zoneOf(locations, location);
    let starts: string;
    let ends: string;
    try {
      starts = toInstant(editing.start, zone);
      ends = toInstant(editing.end, zone);
    } catch (error) {
      center.report(explain(error));
      return;
    }
    if (Date.parse(ends) <= Date.parse(starts)) {
      center.report("The end must follow the start.");
      return;
    }
    const assignee =
      editing.status === "published" && editing.assignee
        ? editing.assignee
        : null;
    void act(
      {
        operation: "shift",
        key: crypto.randomUUID(),
        subject: editing.shift?.shift_id ?? crypto.randomUUID(),
        body: {
          schema_version: 1,
          expected_revision: editing.shift?.revision ?? 0,
          location_id: location,
          position: editing.position.trim(),
          starts_at: starts,
          ends_at: ends,
          required_skill_ids: editing.skills,
          status: editing.status,
          staff_profile_id: assignee,
        },
      },
      editing.status === "cancelled"
        ? "Shift cancelled. Its history is kept."
        : editing.status === "draft"
          ? "Draft saved."
          : assignee
            ? `Published and assigned to ${nameOf(assignee)}.`
            : "Published as an open shift.",
    ).then((saved) => {
      if (saved) setEditing(null);
    });
  }
  async function showVersions(shift: Shift) {
    setEditing(null);
    setVersions({ shift, items: null });
    try {
      const count = Math.min(shift.revision, 20);
      const items = await Promise.all(
        Array.from({ length: count }, (_, index) =>
          fetchShift(businessId, shift.shift_id, shift.revision - index),
        ),
      );
      setVersions({ shift, items });
    } catch (error) {
      setVersions(null);
      center.report(explain(error));
    }
  }
  async function openPerson(entry: DirectoryEntry) {
    const profile = entry.profile_id;
    if (!profile) return;
    const zone = zoneOf(locations, entry.home_location_id ?? "");
    const base = {
      entry,
      grants: null,
      from: toFields(new Date().toISOString(), zone),
    };
    setPerson(base);
    try {
      const lists = await Promise.all(
        skills.map((skill) =>
          fetchSkillHistory(businessId, profile, skill.skill_id),
        ),
      );
      setPerson({
        ...base,
        grants: new Map(
          skills.map((skill, index) => [skill.skill_id, lists[index] ?? []]),
        ),
      });
    } catch (error) {
      setPerson(null);
      center.report(explain(error));
    }
  }
  function grant(skill: Skill, granted: boolean) {
    const profile = person?.entry.profile_id;
    if (!person || !profile) return;
    const entry = person.entry;
    let effective: string;
    try {
      effective = toInstant(
        person.from,
        zoneOf(locations, entry.home_location_id ?? ""),
      );
    } catch (error) {
      center.report(explain(error));
      return;
    }
    const events = person.grants?.get(skill.skill_id) ?? [];
    void act(
      {
        operation: "staff_skill",
        key: crypto.randomUUID(),
        subject: profile,
        skill: skill.skill_id,
        body: {
          schema_version: 1,
          expected_revision: events[events.length - 1]?.revision ?? 0,
          effective_at: effective,
          granted,
        },
      },
      `${skill.name} ${granted ? "granted to" : "revoked from"} ${entry.display_name ?? "this person"}.`,
    ).then((saved) => {
      if (saved) void openPerson(entry);
    });
  }
  function saveSkill(event: React.FormEvent) {
    event.preventDefault();
    if (!skillForm) return;
    void act(
      {
        operation: "skill",
        key: crypto.randomUUID(),
        subject: skillForm.skill?.skill_id ?? crypto.randomUUID(),
        body: {
          schema_version: 1,
          expected_revision: skillForm.skill?.revision ?? 0,
          code: skillForm.code,
          name: skillForm.name.trim(),
          archived: skillForm.archived,
        },
      },
      "Skill saved.",
    ).then((saved) => {
      if (saved) setSkillForm(null);
    });
  }
  const addProfile = (entry: DirectoryEntry) =>
    act(
      {
        operation: "profile",
        key: crypto.randomUUID(),
        subject: crypto.randomUUID(),
        body: {
          schema_version: 1,
          membership_id: entry.membership_id,
          location_id: entry.location_id ?? selected,
        },
      },
      `${entry.display_name ?? "This person"} is now on the schedule of ${placeOf(locations, entry.location_id ?? selected)}.`,
    );
  const decide = (change: Change, action: "approve" | "decline") =>
    act(
      {
        operation: "change.event",
        key: crypto.randomUUID(),
        subject: change.request_id,
        body: {
          schema_version: 1,
          expected_revision: change.revision,
          action,
        },
      },
      action === "approve"
        ? "Approved and applied. Skills and overlaps were checked again."
        : "Request declined. Nothing changed.",
    ).then((saved) => {
      if (saved) setSteps(null);
    });
  async function showSteps(change: Change) {
    setSteps({ change, items: null });
    try {
      const items = await fetchChangeHistory(
        businessId,
        change.request_id,
        false,
      );
      setSteps({ change, items });
    } catch (error) {
      setSteps(null);
      center.report(explain(error));
    }
  }

  const summary = (change: Change) =>
    `${CHANGE_KIND[change.kind]}: ${named(change.shift_id)}${change.other_shift_id ? ` for ${named(change.other_shift_id)}` : ""}`;
  const requests = changes.filter(
    (change) => !waiting || change.status === "accepted",
  );
  const loading = !desk || shifts === null;
  return (
    <section aria-label="Schedule" className="workforce">
      <h1>Schedule</h1>
      <p>
        Plan shifts for one location. One person cannot hold two overlapping
        shifts, and a required skill must be in effect when the shift starts.
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
          Only the first 1000 records of each list are shown. Narrow the dates
          to see the rest.
        </p>
      )}
      <div
        role="group"
        aria-label="Schedule sections"
        className="workforce-tabs"
      >
        {TABS.map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? undefined : "secondary"}
            aria-pressed={tab === id}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      {loading && !(failed ?? loadError) && (
        <p aria-live="polite">Loading the schedule…</p>
      )}
      {!loading && tab === "shifts" && (
        <section aria-label="Shifts" className="workforce-card">
          <h2>Shifts</h2>
          {workspace && workspace.location_id === null && (
            <LocationFilter
              locations={workspace.locations}
              value={selected}
              onChange={(value) => {
                setChosen(value);
                setEditing(null);
                setVersions(null);
              }}
            />
          )}
          <label>
            Week from
            <input
              type="date"
              required
              value={from}
              onChange={(event) => {
                if (event.target.value) setPicked(event.target.value);
              }}
            />
          </label>
          <button
            disabled={center.blocked || !open || !selected}
            onClick={() => openShift(null)}
          >
            New shift
          </button>
          {week && week.length === 0 && (
            <p>No shifts in this location for these seven days.</p>
          )}
          <ul className="cp-list">
            {week?.map((shift) => (
              <li key={shift.shift_id} className="workforce-item">
                <h3>{describe(shift)}</h3>
                <p>
                  <span className={`workforce-badge workforce-${shift.status}`}>
                    {SHIFT_STATUS[shift.status]}
                  </span>{" "}
                  ·{" "}
                  {shift.status === "published"
                    ? shift.staff_profile_id
                      ? `Assigned to ${nameOf(shift.staff_profile_id)}`
                      : "Open: nobody is assigned"
                    : "Not assigned"}
                  {shift.required_skill_ids.length > 0 &&
                    ` · requires ${skillNames(shift.required_skill_ids)}`}{" "}
                  · version {shift.revision}
                </p>
                <div className="workforce-actions">
                  {shift.status !== "cancelled" && (
                    <button
                      className="secondary"
                      disabled={center.blocked || !open}
                      aria-label={`Edit ${describe(shift)}`}
                      onClick={() => openShift(shift)}
                    >
                      Edit
                    </button>
                  )}
                  <button
                    className="secondary"
                    aria-label={`Versions of ${describe(shift)}`}
                    onClick={() => void showVersions(shift)}
                  >
                    Versions
                  </button>
                </div>
              </li>
            ))}
          </ul>
          {editing && (
            <Panel
              label={
                editing.shift ? `Edit ${describe(editing.shift)}` : "New shift"
              }
              onClose={() => setEditing(null)}
            >
              <form onSubmit={saveShift}>
                <fieldset disabled={center.blocked}>
                  <legend>
                    {placeOf(locations, editing.shift?.location_id ?? selected)}{" "}
                    ·{" "}
                    {zoneOf(locations, editing.shift?.location_id ?? selected)}
                  </legend>
                  <label>
                    Position
                    <input
                      required
                      maxLength={200}
                      value={editing.position}
                      onChange={(event) =>
                        setEditing({ ...editing, position: event.target.value })
                      }
                    />
                  </label>
                  <MomentFields
                    legend="Start"
                    value={editing.start}
                    onChange={(start) => setEditing({ ...editing, start })}
                  />
                  <MomentFields
                    legend="End"
                    value={editing.end}
                    onChange={(end) => setEditing({ ...editing, end })}
                  />
                  <fieldset>
                    <legend>Required skills</legend>
                    {skills.filter(
                      (skill) =>
                        !skill.archived ||
                        editing.skills.includes(skill.skill_id),
                    ).length === 0 && <p>The skills catalogue is empty.</p>}
                    {skills
                      .filter(
                        (skill) =>
                          !skill.archived ||
                          editing.skills.includes(skill.skill_id),
                      )
                      .map((skill) => (
                        <label key={skill.skill_id} className="workforce-check">
                          <input
                            type="checkbox"
                            checked={editing.skills.includes(skill.skill_id)}
                            onChange={(event) =>
                              setEditing({
                                ...editing,
                                skills: event.target.checked
                                  ? [...editing.skills, skill.skill_id]
                                  : editing.skills.filter(
                                      (id) => id !== skill.skill_id,
                                    ),
                              })
                            }
                          />
                          {skill.name}
                        </label>
                      ))}
                  </fieldset>
                  <label>
                    Status
                    <select
                      value={editing.status}
                      onChange={(event) =>
                        setEditing({
                          ...editing,
                          status: event.target.value as ShiftStatus,
                        })
                      }
                    >
                      {/* A published or cancelled shift cannot go back to a draft. */}
                      {(!editing.shift || editing.shift.status === "draft") && (
                        <option value="draft">Draft</option>
                      )}
                      <option value="published">Published</option>
                      {editing.shift && (
                        <option value="cancelled">Cancelled</option>
                      )}
                    </select>
                  </label>
                  <label>
                    Assigned to
                    <select
                      value={
                        editing.status === "published" ? editing.assignee : ""
                      }
                      disabled={editing.status !== "published"}
                      onChange={(event) =>
                        setEditing({ ...editing, assignee: event.target.value })
                      }
                    >
                      <option value="">Nobody (open shift)</option>
                      {staff.map((entry) => (
                        <option
                          key={entry.membership_id}
                          value={entry.profile_id ?? ""}
                        >
                          {entry.display_name ?? "Team member"}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="submit" disabled={!editing.position.trim()}>
                    Save shift
                  </button>
                </fieldset>
              </form>
            </Panel>
          )}
          {versions && (
            <Panel
              label={`Versions of ${describe(versions.shift)}`}
              onClose={() => setVersions(null)}
            >
              {versions.items === null ? (
                <p aria-live="polite">Loading every version…</p>
              ) : (
                <ol className="cp-list" reversed>
                  {versions.items.map((item) => (
                    <li key={item.revision}>
                      <strong>
                        Version {item.revision}: {SHIFT_STATUS[item.status]}
                      </strong>{" "}
                      · {describe(item)} ·{" "}
                      {item.staff_profile_id
                        ? `assigned to ${nameOf(item.staff_profile_id)}`
                        : "nobody assigned"}
                      {item.required_skill_ids.length > 0 &&
                        ` · requires ${skillNames(item.required_skill_ids)}`}
                    </li>
                  ))}
                </ol>
              )}
              {versions.shift.revision > 20 && (
                <p>Only the latest 20 versions are listed.</p>
              )}
            </Panel>
          )}
        </section>
      )}
      {!loading && tab === "staff" && (
        <>
          <section aria-label="Staff" className="workforce-card">
            <h2>Staff</h2>
            {workspace && workspace.location_id === null && (
              <>
                <LocationFilter
                  locations={workspace.locations}
                  value={selected}
                  onChange={(value) => {
                    setChosen(value);
                    setChoice(null);
                  }}
                />
                <p>
                  A person with access to the whole company is added to the
                  schedule of the location chosen here. A home location cannot
                  be changed later.
                </p>
              </>
            )}
            {directory.length === 0 && <p>No members in your area.</p>}
            <ul className="cp-list">
              {directory.map((entry) => {
                const name = entry.display_name ?? "Team member";
                return (
                  <li key={entry.membership_id} className="workforce-item">
                    <h3>{name}</h3>
                    <p>
                      {ROLE[entry.role]} ·{" "}
                      {entry.home_location_id
                        ? `on the schedule of ${placeOf(locations, entry.home_location_id)}`
                        : "not on the schedule"}
                    </p>
                    <div className="workforce-actions">
                      {entry.profile_id ? (
                        <button
                          className="secondary"
                          aria-label={`Skills of ${name}`}
                          onClick={() => void openPerson(entry)}
                        >
                          Skills
                        </button>
                      ) : (
                        <button
                          className="secondary"
                          disabled={center.blocked || !open || !selected}
                          aria-label={`Add ${name} to the schedule of ${placeOf(locations, entry.location_id ?? selected)}`}
                          onClick={() => void addProfile(entry)}
                        >
                          Add to the schedule of{" "}
                          {placeOf(locations, entry.location_id ?? selected)}
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
          {person && (
            <Panel
              label={`Skills of ${person.entry.display_name ?? "Team member"}`}
              onClose={() => setPerson(null)}
            >
              {person.grants === null ? (
                <p aria-live="polite">Loading skills…</p>
              ) : (
                <>
                  <MomentFields
                    legend="Effective from"
                    value={person.from}
                    onChange={(value) => setPerson({ ...person, from: value })}
                  />
                  {skills.length === 0 && <p>The skills catalogue is empty.</p>}
                  <ul className="cp-list">
                    {skills.map((skill) => {
                      const events = person.grants?.get(skill.skill_id) ?? [];
                      const last = events[events.length - 1];
                      const zone = zoneOf(
                        locations,
                        person.entry.home_location_id ?? "",
                      );
                      return (
                        <li key={skill.skill_id} className="workforce-item">
                          <h4>
                            {skill.name}
                            {skill.archived && " (archived)"}
                          </h4>
                          <p>
                            {last
                              ? `${last.granted ? "Granted" : "Revoked"} from ${moment(last.effective_at, zone)}`
                              : "Never granted"}
                          </p>
                          {events.length > 0 && (
                            <ol>
                              {events.map((item) => (
                                <li key={item.revision}>
                                  Step {item.revision}:{" "}
                                  {item.granted ? "granted" : "revoked"} from{" "}
                                  {moment(item.effective_at, zone)}
                                </li>
                              ))}
                            </ol>
                          )}
                          <button
                            className="secondary"
                            disabled={center.blocked || !open}
                            aria-label={`${last?.granted ? "Revoke" : "Grant"} ${skill.name}`}
                            onClick={() => grant(skill, !last?.granted)}
                          >
                            {last?.granted ? "Revoke" : "Grant"}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </>
              )}
            </Panel>
          )}
          <section aria-label="Skills catalogue" className="workforce-card">
            <h2>Skills catalogue</h2>
            {!companyWide && (
              <p>
                Skills belong to the whole company. Changing them requires
                company-wide access.
              </p>
            )}
            {skills.length === 0 && <p>No skills yet.</p>}
            <ul className="cp-list">
              {skills.map((skill) => (
                <li key={skill.skill_id} className="workforce-item">
                  <h3>
                    {skill.name}
                    {skill.archived && " (archived)"}
                  </h3>
                  <p>
                    Code {skill.code} · version {skill.revision}
                  </p>
                  {companyWide && (
                    <button
                      className="secondary"
                      disabled={center.blocked || !open}
                      aria-label={`Edit skill ${skill.name}`}
                      onClick={() =>
                        setSkillForm({
                          skill,
                          code: skill.code,
                          name: skill.name,
                          archived: skill.archived,
                        })
                      }
                    >
                      Edit
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {companyWide && (
              <button
                disabled={center.blocked || !open}
                onClick={() =>
                  setSkillForm({
                    skill: null,
                    code: "",
                    name: "",
                    archived: false,
                  })
                }
              >
                New skill
              </button>
            )}
            {skillForm && (
              <Panel
                label={
                  skillForm.skill
                    ? `Edit skill ${skillForm.skill.name}`
                    : "New skill"
                }
                onClose={() => setSkillForm(null)}
              >
                <form onSubmit={saveSkill}>
                  <fieldset disabled={center.blocked}>
                    <label>
                      Code (capital letters, digits and underscores)
                      <input
                        required
                        pattern="[A-Z][A-Z0-9_]{0,63}"
                        maxLength={64}
                        value={skillForm.code}
                        disabled={skillForm.skill !== null}
                        onChange={(event) =>
                          setSkillForm({
                            ...skillForm,
                            code: event.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      Name
                      <input
                        required
                        maxLength={200}
                        value={skillForm.name}
                        onChange={(event) =>
                          setSkillForm({
                            ...skillForm,
                            name: event.target.value,
                          })
                        }
                      />
                    </label>
                    {skillForm.skill && (
                      <label className="workforce-check">
                        <input
                          type="checkbox"
                          checked={skillForm.archived}
                          onChange={(event) =>
                            setSkillForm({
                              ...skillForm,
                              archived: event.target.checked,
                            })
                          }
                        />
                        Archived: no longer offered for new shifts
                      </label>
                    )}
                    <button
                      type="submit"
                      disabled={!skillForm.name.trim() || !skillForm.code}
                    >
                      Save skill
                    </button>
                  </fieldset>
                </form>
              </Panel>
            )}
          </section>
        </>
      )}
      {!loading && tab === "privacy" && (
        <section aria-label="Privacy" className="workforce-card">
          <h2>Privacy</h2>
          {workspace && workspace.location_id === null && (
            <LocationFilter
              locations={workspace.locations}
              value={selected}
              onChange={(value) => {
                setChosen(value);
                setChoice(null);
              }}
            />
          )}
          {privacyError && (
            <p role="alert" className="error">
              {privacyError}
            </p>
          )}
          {!current ? (
            !privacyError && <p aria-live="polite">Loading the setting…</p>
          ) : (
            <form onSubmit={savePrivacy}>
              <fieldset disabled={center.blocked || !open}>
                <legend>
                  Colleagues’ shifts in {placeOf(locations, selected)}
                </legend>
                <label className="workforce-check">
                  <input
                    type="radio"
                    name="colleague-shifts"
                    checked={visible}
                    onChange={() =>
                      setChoice({ location: selected, visible: true })
                    }
                  />
                  Staff see the published shifts of colleagues in this location
                </label>
                <label className="workforce-check">
                  <input
                    type="radio"
                    name="colleague-shifts"
                    checked={!visible}
                    onChange={() =>
                      setChoice({ location: selected, visible: false })
                    }
                  />
                  Staff see only their own shifts and open shifts
                </label>
                <p>
                  While colleagues’ shifts are hidden, a swap cannot be chosen
                  in “My shifts”. A handover, a request for an open shift and
                  the requests a person already takes part in still work.
                </p>
                <button
                  type="submit"
                  disabled={visible === current.colleague_shifts_visible}
                >
                  Save privacy
                </button>
              </fieldset>
              <p>
                {current.revision === 0 || !current.changed_at
                  ? "Never changed: colleagues’ shifts are visible by default."
                  : `Version ${current.revision}: last changed by ${changer} on ${moment(current.changed_at, zoneOf(locations, selected))}.`}
              </p>
            </form>
          )}
        </section>
      )}
      {!loading && tab === "requests" && (
        <section aria-label="Change requests" className="workforce-card">
          <h2>Change requests</h2>
          <label className="workforce-check">
            <input
              type="checkbox"
              checked={waiting}
              onChange={(event) => setWaiting(event.target.checked)}
            />
            Only requests waiting for a manager
          </label>
          {requests.length === 0 && (
            <p>
              {waiting
                ? "No requests are waiting for a manager."
                : "There are no change requests in your area."}
            </p>
          )}
          <ul className="cp-list">
            {requests.map((change) => {
              const label = summary(change);
              return (
                <li key={change.request_id} className="workforce-item">
                  <h3>{label}</h3>
                  <p>
                    From {nameOf(change.from_profile_id)} to{" "}
                    {nameOf(change.target_profile_id)} ·{" "}
                    <span
                      className={`workforce-badge workforce-${change.status}`}
                    >
                      {CHANGE_STATUS[change.status]}
                    </span>{" "}
                    ·{" "}
                    {moment(
                      change.event_created_at,
                      zoneOf(locations, change.location_id),
                    )}
                  </p>
                  {change.applied_shifts.length > 0 && (
                    <p>
                      Applied:{" "}
                      {change.applied_shifts
                        .map(
                          (applied) =>
                            `${named(applied.shift_id)} is now version ${applied.revision}`,
                        )
                        .join("; ")}
                      .
                    </p>
                  )}
                  <div className="workforce-actions">
                    {change.status === "accepted" && (
                      <button
                        disabled={center.blocked || !open}
                        aria-label={`Approve ${label}`}
                        onClick={() => void decide(change, "approve")}
                      >
                        Approve
                      </button>
                    )}
                    {["proposed", "accepted"].includes(change.status) && (
                      <button
                        className="secondary"
                        disabled={center.blocked || !open}
                        aria-label={`Decline ${label}`}
                        onClick={() => void decide(change, "decline")}
                      >
                        Decline
                      </button>
                    )}
                    <button
                      className="secondary"
                      aria-label={`History of ${label}`}
                      onClick={() => void showSteps(change)}
                    >
                      History
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          {steps && (
            <Panel
              label={`History of ${summary(steps.change)}`}
              onClose={() => setSteps(null)}
            >
              {steps.items === null ? (
                <p aria-live="polite">Loading every step…</p>
              ) : (
                <ol className="cp-list">
                  {steps.items.map((item) => (
                    <li key={item.revision}>
                      <strong>
                        Step {item.revision}: {CHANGE_STEP[item.status]}
                      </strong>{" "}
                      by{" "}
                      {item.event_created_by === actorId
                        ? "you"
                        : (directory.find(
                            (entry) => entry.user_id === item.event_created_by,
                          )?.display_name ?? "another person")}{" "}
                      on{" "}
                      {moment(
                        item.event_created_at,
                        zoneOf(locations, item.location_id),
                      )}
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
          )}
        </section>
      )}
    </section>
  );
}
