"use client";
import { useCallback, useEffect, useState } from "react";
import { LocationFilter } from "./location-filter";
import { businessDateTime, businessTimeToInstant } from "../lib/business-time";
import {
  fetchStaff,
  fetchWorkspace,
  ManagementApiError,
  type StaffView,
  type Workspace,
} from "../lib/management-api";
import {
  executeReservationCommand,
  fetchReservations,
} from "../lib/reservation-api";
import type {
  Reservation,
  ReservationCommand,
} from "../lib/reservation-contracts";

const failure = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to complete this action.";
const uncertain = (error: unknown) =>
  !(error instanceof ManagementApiError) ||
  error.status === undefined ||
  error.status >= 500;

/** Staff reservations of resources: shared occupancy with bookings (ADR-0022). */
export function Reservations({ businessId }: { businessId: string }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [staff, setStaff] = useState<StaffView[]>([]);
  const [locationId, setLocationId] = useState("");
  const [day, setDay] = useState("");
  const [items, setItems] = useState<Reservation[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [startTime, setStartTime] = useState("09:00");
  const [endTime, setEndTime] = useState("10:00");
  const [purpose, setPurpose] = useState("");
  const [pending, setPending] = useState<ReservationCommand | null>(null);
  const [refused, setRefused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const location = workspace?.locations.find((item) => item.id === locationId);
  const timezone = location?.timezone ?? "";
  const resources = staff.filter(
    (item) => item.location_id === locationId && item.is_active,
  );
  const names = new Map(staff.map((item) => [item.id, item.display_name]));
  const enabled = Boolean(workspace?.booking_enabled) && !refused;

  useEffect(() => {
    let active = true;
    Promise.all([fetchWorkspace(businessId), fetchStaff(businessId)])
      .then(([loaded, people]) => {
        if (!active) return;
        setWorkspace(loaded);
        setStaff(people);
        const first = loaded.location_id ?? loaded.locations[0]?.id ?? "";
        setLocationId(first);
        const zone = loaded.locations.find((item) => item.id === first);
        if (zone) setDay(businessDateTime(new Date(), zone.timezone).date);
      })
      .catch((e: unknown) => {
        if (active) setError(failure(e));
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  // A wide UTC window around the day, filtered by the branch's calendar day, so a
  // clock change at midnight never breaks the list.
  const dayRange = useCallback(() => {
    if (!locationId || !day || !timezone) return null;
    const midnight = Date.parse(`${day}T00:00:00Z`);
    return {
      starts: new Date(midnight - 15 * 3_600_000).toISOString(),
      ends: new Date(midnight + 39 * 3_600_000).toISOString(),
    };
  }, [locationId, day, timezone]);
  const onDay = useCallback(
    (item: Reservation) =>
      businessDateTime(item.starts_at, timezone).date <= day &&
      businessDateTime(new Date(Date.parse(item.ends_at) - 1), timezone).date >=
        day,
    [day, timezone],
  );

  useEffect(() => {
    let active = true;
    let range: { starts: string; ends: string } | null;
    try {
      range = dayRange();
    } catch (e: unknown) {
      range = null;
      queueMicrotask(() => {
        if (active) setError(failure(e));
      });
    }
    if (range)
      fetchReservations(businessId, range.starts, range.ends, locationId)
        .then((page) => {
          if (active) setItems(page.items.filter(onDay));
        })
        .catch((e: unknown) => {
          if (active) setError(failure(e));
        });
    return () => {
      active = false;
    };
  }, [businessId, locationId, dayRange, onDay]);

  async function refresh() {
    const range = dayRange();
    if (!range) return;
    const page = await fetchReservations(
      businessId,
      range.starts,
      range.ends,
      locationId,
    );
    setItems(page.items.filter(onDay));
  }

  async function run(command: ReservationCommand) {
    if (busy) return;
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await executeReservationCommand(businessId, command);
      setPending(null);
      // Only the server's answer shows a reservation as made or cancelled.
      setMessage(
        command.type === "create"
          ? "Reservation saved."
          : "Reservation cancelled.",
      );
      if (command.type === "create") {
        setChosen([]);
        setPurpose("");
      }
      await refresh();
    } catch (e: unknown) {
      setError(failure(e));
      if (!uncertain(e) && e instanceof ManagementApiError) {
        setPending(null);
        if (e.code === "MODULE_DISABLED") setRefused(true);
      }
    } finally {
      setBusy(false);
    }
  }

  function reserve(event: React.FormEvent) {
    event.preventDefault();
    if (busy || pending || !enabled || !timezone) return;
    let starts: string;
    let ends: string;
    try {
      starts = businessTimeToInstant(day, startTime, timezone);
      ends = businessTimeToInstant(day, endTime, timezone);
    } catch (e: unknown) {
      setError(failure(e));
      return;
    }
    if (Date.parse(ends) <= Date.parse(starts)) {
      setError("The end must follow the start.");
      return;
    }
    void run({
      type: "create",
      id: crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: {
        schema_version: 1,
        location_id: locationId,
        resource_ids: chosen,
        starts_at: starts,
        ends_at: ends,
        purpose: purpose.trim() || null,
      },
    });
  }

  const locked = busy || Boolean(pending);
  // Times on the chosen day; another day is named with its date.
  const clock = (instant: string) => {
    if (!timezone) return instant;
    const local = businessDateTime(instant, timezone);
    return local.date === day ? local.time : `${local.date} ${local.time}`;
  };
  const resourceNames = (item: Reservation) =>
    item.resource_ids.map((r) => names.get(r) ?? r).join(", ") ||
    "resources outside your branch";
  return (
    <section aria-label="Resource reservations" className="mgmt-card">
      <h1>Resource reservations</h1>
      <p>
        Reserve people, chairs or rooms of one branch for internal work. A
        reserved resource cannot be booked, and a booked one cannot be reserved.
      </p>
      {workspace && !enabled && (
        <p className="warning">
          Booking and resources are turned off. Saved reservations stay readable
          and can still be cancelled.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {pending && !busy && (
        <div className="warning">
          <p>
            The result of the last reservation command is uncertain. Retry the
            same command to check it.
          </p>
          <button disabled={busy} onClick={() => void run(pending)}>
            Retry same reservation command
          </button>
        </div>
      )}
      {workspace && workspace.location_id === null && (
        <LocationFilter
          locations={workspace.locations}
          value={locationId}
          onChange={(value) => {
            setLocationId(value);
            setChosen([]);
            setItems(null);
            setError(null);
          }}
        />
      )}
      <label>
        Day
        <input
          type="date"
          value={day}
          onChange={(e) => {
            setDay(e.target.value);
            setItems(null);
            setError(null);
          }}
        />
      </label>
      <h2>Reservations{timezone && ` (${timezone})`}</h2>
      {items && items.length === 0 && <p>No reservations on this day.</p>}
      <ul className="cp-list">
        {items?.map((item) => (
          <li key={item.reservation_id}>
            <span>
              {clock(item.starts_at)}–{clock(item.ends_at)} ·{" "}
              {resourceNames(item)}
              {item.purpose && ` · ${item.purpose}`} · {item.status}
            </span>{" "}
            {item.status === "active" && (
              <button
                className="secondary"
                disabled={locked}
                onClick={() =>
                  void run({
                    type: "cancel",
                    id: item.reservation_id,
                    key: crypto.randomUUID(),
                    body: { schema_version: 1 },
                  })
                }
              >
                Cancel reservation {clock(item.starts_at)} ·{" "}
                {resourceNames(item)}
              </button>
            )}
          </li>
        ))}
      </ul>
      <form onSubmit={reserve}>
        <fieldset disabled={locked || !enabled}>
          <legend>New reservation</legend>
          {resources.length === 0 && <p>No active resources in this branch.</p>}
          {resources.map((item) => (
            <label key={item.id}>
              <input
                type="checkbox"
                checked={chosen.includes(item.id)}
                onChange={(e) =>
                  setChosen(
                    e.target.checked
                      ? [...chosen, item.id]
                      : chosen.filter((id) => id !== item.id),
                  )
                }
              />{" "}
              {item.display_name}
            </label>
          ))}
          <div className="cp-fields">
            <label>
              Starts at
              <input
                type="time"
                required
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
            </label>
            <label>
              Ends at
              <input
                type="time"
                required
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
              />
            </label>
          </div>
          <label>
            Purpose
            <input
              maxLength={200}
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
            />
          </label>
          <button type="submit" disabled={chosen.length === 0}>
            Reserve
          </button>
        </fieldset>
      </form>
    </section>
  );
}
