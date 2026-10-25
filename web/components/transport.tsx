"use client";

// M6a (package M): the dispatch board and the trip page. Every time is shown in its stop's own time
// zone; a replacement moment is entered in the first stop's zone. A stop event keeps its source event
// id until it is recorded, so retrying after a lost answer records it once (ADR-0030).
// M6b: owners and managers also plan and register the fleet; a carrier's dispatcher sees only the
// forms its grant allows (ADR-0031).
import React, { useCallback, useEffect, useId, useMemo, useState } from "react";
import { businessDateTime, businessTimeToInstant } from "../lib/business-time";
import { fetchCounterparties } from "../lib/counterparty-api";
import {
  ManagementApiError,
  fetchWorkspace,
  type LocationItem,
} from "../lib/management-api";
import {
  assign,
  fetchAllDrivers,
  fetchAllOrders,
  fetchAllTrips,
  fetchAllVehicles,
  fetchClearance,
  fetchTrip,
  recordEvent,
} from "../lib/transport-api";
import {
  FleetPanel,
  OrdersPanel,
  TripForm,
  type Customer,
} from "./transport-forms";
import type {
  Assignment,
  Clearance,
  Driver,
  Order,
  Stop,
  Trip,
  Vehicle,
} from "../lib/transport-contracts";

type Role = Assignment["role"];
const ROLES: Role[] = ["driver", "truck", "trailer"];
const ROLE_LABEL: Record<Role, string> = {
  driver: "Driver",
  truck: "Truck",
  trailer: "Trailer",
};
const STATUS_LABEL: Record<Trip["status"], string> = {
  planned: "Planned",
  in_transit: "In transit",
};
const EVENTS = [
  ["arrived", "Arrived"],
  ["departed", "Departed"],
  ["loaded", "Loaded"],
  ["delivered", "Delivered"],
  ["refused", "Refused"],
  ["damaged", "Damaged"],
  ["exception", "Exception"],
] as const;
const QUANTITY_KINDS = new Set(["loaded", "delivered", "refused", "damaged"]);
const OUTCOME: Record<Clearance["status"], string> = {
  cleared: "Cleared",
  not_cleared: "Not cleared",
  unknown: "Unknown",
};
const REASON: Record<string, string> = {
  unassigned: "not assigned",
  no_hos_profile: "no hours-of-service profile",
  no_duty_data: "no duty records",
  stale_duty_data: "duty records are stale",
  incomplete_duty_data: "duty records have a gap",
  no_telematics: "no telematics",
  stale_telematics: "telematics are stale",
  driving_limit: "driving limit reached",
  window_limit: "on-duty window exceeded",
  cycle_limit: "cycle limit reached",
};

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function local(instant: string, zone: string): string {
  const { date, time } = businessDateTime(instant, zone);
  return `${date} ${time} (${zone})`;
}

function stopWindow(stop: Stop): string {
  const start = businessDateTime(stop.window_start, stop.time_zone);
  const end = businessDateTime(stop.window_end, stop.time_zone);
  const tail = start.date === end.date ? end.time : `${end.date} ${end.time}`;
  return `${start.date} ${start.time}–${tail} (${stop.time_zone})`;
}

function stopLabel(stop: Stop): string {
  return `${stop.position} · ${stop.kind === "pickup" ? "Pickup" : "Delivery"} · ${stop.place}`;
}

const current = (trip: Trip, role: Role) =>
  trip.assignments.find((a) => a.role === role && a.ends_at === null);

/** What the signed-in person may do: everything for an owner or manager, the granted actions for a delegate. */
export type TransportRights = {
  plan: boolean;
  assign: boolean;
  events: boolean;
  fleet: boolean;
};

async function allCustomers(businessId: string): Promise<Customer[]> {
  const customers: Customer[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchCounterparties(businessId, "", "active", after);
    for (const c of page.items)
      if (c.roles.includes("customer"))
        customers.push({ id: c.counterparty_id, name: c.display_name });
    if (!page.next_cursor) return customers;
    after = page.next_cursor;
  }
}

function upsert<T>(list: T[], item: T, same: (x: T) => boolean): T[] {
  return list.some(same)
    ? list.map((x) => (same(x) ? item : x))
    : [...list, item];
}

export function TransportScreen({
  businessId,
  rights,
}: {
  businessId: string;
  rights: TransportRights;
}) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [editing, setEditing] = useState<Trip | null>(null);
  const [notice, setNotice] = useState("");
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<Trip | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const owner = rights.plan || rights.fleet;
    Promise.all([
      fetchAllTrips(businessId),
      fetchAllDrivers(businessId),
      fetchAllVehicles(businessId),
      rights.plan ? fetchAllOrders(businessId) : Promise.resolve([]),
      // Without the counterparties module there is no customer to choose; the board still works.
      rights.plan
        ? allCustomers(businessId).catch(() => [] as Customer[])
        : Promise.resolve([]),
      owner
        ? fetchWorkspace(businessId).then((w) => w.locations)
        : Promise.resolve([]),
    ])
      .then(
        ([tripList, driverList, vehicleList, orderList, people, places]) => {
          if (!live) return;
          setTrips(tripList);
          setDrivers(driverList);
          setVehicles(vehicleList);
          setOrders(orderList);
          setCustomers(people);
          setLocations(places);
          setLoaded(true);
        },
      )
      .catch((failure: unknown) => {
        if (live) setError(`The trips could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId, rights.plan, rights.fleet]);

  const names = useMemo(() => {
    const map = new Map<string, string>();
    for (const d of drivers) map.set(d.resource_id, d.display_name);
    for (const v of vehicles) map.set(v.resource_id, v.unit_number);
    return map;
  }, [drivers, vehicles]);
  const nameOf = useCallback(
    (resource: string | undefined) =>
      resource ? (names.get(resource) ?? "Unknown") : "—",
    [names],
  );

  const changed = useCallback((trip: Trip) => {
    setSelected(trip);
    setTrips((list) => upsert(list, trip, (x) => x.trip_id === trip.trip_id));
  }, []);
  const notify = useCallback((text: string) => setNotice(text), []);
  const planned = useCallback(
    (trip: Trip) => {
      changed(trip);
      // A saved trip changes how much of each load is planned.
      fetchAllOrders(businessId)
        .then(setOrders)
        .catch((failure: unknown) =>
          setError(`The orders could not be read: ${refusal(failure)}`),
        );
    },
    [businessId, changed],
  );

  async function open(trip: Trip) {
    setError(null);
    try {
      changed(await fetchTrip(businessId, trip.trip_id));
    } catch (failure) {
      setError(`The trip could not be read: ${refusal(failure)}`);
    }
  }

  return (
    <div className="transport-screen">
      <h1>Transport</h1>
      <p className="muted">
        Every trip with its stops in their own time zones, its crew and what
        happened at each stop.
      </p>
      <p className="transport-status" role="status">
        {notice}
      </p>
      {!loaded && !error && (
        <p className="muted" role="status">
          Loading the trips…
        </p>
      )}
      {loaded &&
        (trips.length === 0 ? (
          <p className="muted">No trips yet.</p>
        ) : (
          <div
            className="mgmt-table-container"
            role="region"
            aria-label="Trips table"
            tabIndex={0}
          >
            <table className="mgmt-table" aria-label="Trips">
              <thead>
                <tr>
                  <th scope="col">Reference</th>
                  <th scope="col">Status</th>
                  <th scope="col">First window</th>
                  <th scope="col">Last window</th>
                  <th scope="col">Driver</th>
                  <th scope="col">Truck</th>
                </tr>
              </thead>
              <tbody>
                {trips.map((trip) => {
                  const first = trip.stops[0];
                  const last = trip.stops[trip.stops.length - 1];
                  return (
                    <tr key={trip.trip_id}>
                      <th scope="row">
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => void open(trip)}
                        >
                          {trip.reference}
                        </button>
                      </th>
                      <td>{STATUS_LABEL[trip.status]}</td>
                      <td>
                        {first
                          ? local(first.window_start, first.time_zone)
                          : "—"}
                      </td>
                      <td>
                        {last ? local(last.window_end, last.time_zone) : "—"}
                      </td>
                      <td>{nameOf(current(trip, "driver")?.resource_id)}</td>
                      <td>{nameOf(current(trip, "truck")?.resource_id)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {selected && (
        <TripPage
          key={selected.trip_id}
          businessId={businessId}
          trip={selected}
          drivers={drivers}
          vehicles={vehicles}
          nameOf={nameOf}
          onChange={changed}
          rights={rights}
          onEdit={rights.plan ? setEditing : undefined}
        />
      )}
      {loaded && rights.plan && (
        <>
          <OrdersPanel
            businessId={businessId}
            orders={orders}
            customers={customers}
            onSaved={(order) =>
              setOrders((list) =>
                upsert(list, order, (x) => x.order_id === order.order_id),
              )
            }
            notify={notify}
          />
          <TripForm
            key={
              editing ? `edit-${editing.trip_id}-${editing.revision}` : "new"
            }
            businessId={businessId}
            orders={orders}
            locations={locations}
            editing={editing}
            onSaved={planned}
            onDone={() => setEditing(null)}
            notify={notify}
          />
        </>
      )}
      {loaded && rights.fleet && (
        <FleetPanel
          businessId={businessId}
          drivers={drivers}
          vehicles={vehicles}
          locations={locations}
          onDriver={(driver) =>
            setDrivers((list) =>
              upsert(list, driver, (x) => x.driver_id === driver.driver_id),
            )
          }
          onVehicle={(vehicle) =>
            setVehicles((list) =>
              upsert(list, vehicle, (x) => x.vehicle_id === vehicle.vehicle_id),
            )
          }
          notify={notify}
        />
      )}
    </div>
  );
}

function TripPage({
  businessId,
  trip,
  drivers,
  vehicles,
  nameOf,
  onChange,
  rights,
  onEdit,
}: {
  businessId: string;
  trip: Trip;
  drivers: Driver[];
  vehicles: Vehicle[];
  nameOf: (resource: string | undefined) => string;
  onChange: (trip: Trip) => void;
  rights: TransportRights;
  onEdit?: (trip: Trip) => void;
}) {
  const headingId = useId();
  const assignId = useId();
  const eventId = useId();
  const zone = trip.stops[0]?.time_zone ?? "UTC";
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [clearance, setClearance] = useState<Clearance | null>(null);
  // Assign or replace.
  const [role, setRole] = useState<Role>("driver");
  const [assignee, setAssignee] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [fromTime, setFromTime] = useState("");
  const [assignment, setAssignment] = useState(() => crypto.randomUUID());
  // Record a stop event.
  const [stopPosition, setStopPosition] = useState(
    trip.stops[0]?.position ?? 1,
  );
  const [kind, setKind] = useState<(typeof EVENTS)[number][0]>("arrived");
  const [quantities, setQuantities] = useState<Record<number, string>>({});
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [note, setNote] = useState("");
  const [sourceId, setSourceId] = useState(() => crypto.randomUUID());

  const choices =
    role === "driver"
      ? drivers.map((d) => ({ id: d.resource_id, label: d.display_name }))
      : vehicles
          .filter((v) => v.kind === role)
          .map((v) => ({ id: v.resource_id, label: v.unit_number }));
  const stop = trip.stops.find((s) => s.position === stopPosition);
  const legs = QUANTITY_KINDS.has(kind)
    ? trip.legs.filter((l) =>
        kind === "loaded"
          ? l.pickup_stop === stopPosition
          : l.delivery_stop === stopPosition,
      )
    : [];
  const stopOf = (position: number) =>
    trip.stops.find((s) => s.position === position);

  async function submitAssignment(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const open = current(trip, role);
    let startsAt: string | undefined;
    try {
      if (fromDate || fromTime)
        startsAt = businessTimeToInstant(fromDate, fromTime, zone);
      else if (open)
        throw new Error("Enter when the new assignment takes over.");
    } catch (failure) {
      setError(refusal(failure));
      return;
    }
    setBusy(true);
    try {
      const saved = await assign(businessId, trip.trip_id, assignment, {
        schema_version: 1,
        role,
        resource_id: assignee,
        ...(startsAt ? { starts_at: startsAt } : {}),
        replaces: open?.assignment_id ?? null,
      });
      onChange(saved);
      setAssignment(crypto.randomUUID());
      setAssignee("");
      setFromDate("");
      setFromTime("");
    } catch (failure) {
      setError(`The assignment was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function submitEvent(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    let occurredAt: string;
    try {
      occurredAt = businessTimeToInstant(date, time, stop?.time_zone ?? zone);
    } catch (failure) {
      setError(refusal(failure));
      return;
    }
    setBusy(true);
    try {
      const saved = await recordEvent(businessId, trip.trip_id, {
        schema_version: 1,
        source: "dispatcher",
        source_event_id: sourceId,
        stop_position: stopPosition,
        kind,
        occurred_at: occurredAt,
        note: note.trim() || null,
        quantities: legs
          .map((l) => ({
            leg_position: l.position,
            quantity: Number(quantities[l.position] ?? "0"),
          }))
          .filter((q) => q.quantity > 0),
      });
      onChange(saved);
      setSourceId(crypto.randomUUID());
      setQuantities({});
      setNote("");
    } catch (failure) {
      setError(`The event was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function check() {
    setError(null);
    try {
      setClearance(await fetchClearance(businessId, trip.trip_id));
    } catch (failure) {
      setError(`Clearance could not be checked: ${refusal(failure)}`);
    }
  }

  return (
    <section className="transport-trip" aria-labelledby={headingId}>
      <h2 id={headingId}>Trip {trip.reference}</h2>
      <p>Status: {STATUS_LABEL[trip.status]}</p>
      {onEdit && trip.status === "planned" && trip.assignments.length === 0 && (
        <button type="button" onClick={() => onEdit(trip)}>
          Edit trip
        </button>
      )}
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Stops table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Stops">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Kind</th>
              <th scope="col">Place</th>
              <th scope="col">Window</th>
            </tr>
          </thead>
          <tbody>
            {trip.stops.map((s) => (
              <tr key={s.position}>
                <th scope="row">{s.position}</th>
                <td>{s.kind === "pickup" ? "Pickup" : "Delivery"}</td>
                <td>{s.place}</td>
                <td>{stopWindow(s)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Legs table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Legs">
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Load</th>
              <th scope="col">Planned</th>
              <th scope="col">Loaded</th>
              <th scope="col">Delivered</th>
              <th scope="col">Refused</th>
              <th scope="col">Damaged</th>
              <th scope="col">Open</th>
            </tr>
          </thead>
          <tbody>
            {trip.legs.map((l) => (
              <tr key={l.position}>
                <th scope="row">{l.position}</th>
                <td>
                  {stopOf(l.pickup_stop)?.place ?? "—"} →{" "}
                  {stopOf(l.delivery_stop)?.place ?? "—"}
                </td>
                <td>{l.quantity}</td>
                <td>{l.loaded}</td>
                <td>{l.delivered}</td>
                <td>{l.refused}</td>
                <td>{l.damaged}</td>
                <td>{l.quantity - l.delivered - l.refused - l.damaged}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Assignments table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Assignments">
          <thead>
            <tr>
              <th scope="col">Role</th>
              <th scope="col">Assigned</th>
              <th scope="col">From</th>
              <th scope="col">Until</th>
            </tr>
          </thead>
          <tbody>
            {trip.assignments.length === 0 ? (
              <tr>
                <td colSpan={4}>No one is assigned yet.</td>
              </tr>
            ) : (
              trip.assignments.map((a) => (
                <tr key={a.assignment_id}>
                  <th scope="row">{ROLE_LABEL[a.role]}</th>
                  <td>{nameOf(a.resource_id)}</td>
                  <td>{local(a.starts_at, zone)}</td>
                  <td>{a.ends_at ? local(a.ends_at, zone) : "open"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {rights.assign && (
        <form onSubmit={submitAssignment} aria-labelledby={assignId}>
          <h3 id={assignId}>Assign or replace</h3>
          <label>
            Role
            <select
              value={role}
              onChange={(e) => {
                setRole(e.target.value as Role);
                setAssignee("");
              }}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Assignee
            <select
              value={assignee}
              onChange={(e) => setAssignee(e.target.value)}
              required
            >
              <option value="">Choose</option>
              {choices.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            From date
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
            />
          </label>
          <label>
            From time
            <input
              type="time"
              value={fromTime}
              onChange={(e) => setFromTime(e.target.value)}
            />
          </label>
          <p className="muted">
            Times are in {zone}. Leave them empty to assign from the trip&apos;s
            start; a replacement needs the moment it takes over.
          </p>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Assign
            </button>
          </div>
        </form>
      )}

      {rights.events && (
        <form onSubmit={submitEvent} aria-labelledby={eventId}>
          <h3 id={eventId}>Record a stop event</h3>
          <label>
            Stop
            <select
              value={stopPosition}
              onChange={(e) => {
                setStopPosition(Number(e.target.value));
                setQuantities({});
              }}
            >
              {trip.stops.map((s) => (
                <option key={s.position} value={s.position}>
                  {stopLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Event
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value as (typeof EVENTS)[number][0]);
                setQuantities({});
              }}
            >
              {EVENTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {legs.map((l) => (
            <label key={l.position}>
              Leg {l.position} quantity
              <input
                type="number"
                min={0}
                max={l.quantity}
                value={quantities[l.position] ?? ""}
                onChange={(e) =>
                  setQuantities((q) => ({ ...q, [l.position]: e.target.value }))
                }
              />
            </label>
          ))}
          <label>
            Date
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              required
            />
          </label>
          <label>
            Time
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              required
            />
          </label>
          <p className="muted">Times are in {stop?.time_zone ?? zone}.</p>
          <label>
            Note
            <input
              type="text"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Record
            </button>
          </div>
        </form>
      )}

      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Event log table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Event log">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Stop</th>
              <th scope="col">Event</th>
              <th scope="col">Quantities</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            {trip.events.map((e) => {
              const at = stopOf(e.stop_position);
              return (
                <tr key={e.event_id}>
                  <th scope="row">
                    {local(e.occurred_at, at?.time_zone ?? zone)}
                  </th>
                  <td>{at ? stopLabel(at) : e.stop_position}</td>
                  <td>
                    {EVENTS.find(([value]) => value === e.kind)?.[1] ?? e.kind}
                  </td>
                  <td>
                    {e.quantities
                      .map((q) => `Leg ${q.leg_position}: ${q.quantity}`)
                      .join(", ") || "—"}
                  </td>
                  <td>{e.note ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="transport-clearance">
        <button type="button" onClick={() => void check()}>
          Check clearance
        </button>
        {clearance && (
          <div role="status">
            <p>Clearance: {OUTCOME[clearance.status]}</p>
            <ul>
              {clearance.roles.map((r) => (
                <li key={r.role}>
                  {ROLE_LABEL[r.role]}: {OUTCOME[r.status]}
                  {r.reasons.length
                    ? ` — ${r.reasons.map((x) => REASON[x] ?? x).join(", ")}`
                    : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
