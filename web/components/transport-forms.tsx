"use client";

// M6b (package M): planning and fleet forms for owners and managers. An order or trip form keeps its
// record id until the save succeeds; stop windows are entered in each stop's own time zone, and every
// refusal from the server is shown in words with the form left as entered.
import React, { useId, useState } from "react";
import { stopWindowFields, stopWindowInstants } from "../lib/transport-rules";
import { ManagementApiError, type LocationItem } from "../lib/management-api";
import {
  saveDriver,
  saveOrder,
  saveTrip,
  saveVehicle,
  type LoadBody,
} from "../lib/transport-api";
import type { Driver, Order, Trip, Vehicle } from "../lib/transport-contracts";

export type Customer = { id: string; name: string };
type Notify = (text: string) => void;

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

type LoadRow = {
  load_id: string;
  description: string;
  quantity: string;
  unit: string;
};
const blankLoad = (): LoadRow => ({
  load_id: crypto.randomUUID(),
  description: "",
  quantity: "",
  unit: "",
});

export function OrdersPanel({
  businessId,
  orders,
  customers,
  onSaved,
  notify,
  onMoney,
}: {
  businessId: string;
  orders: Order[];
  customers: Customer[];
  onSaved: (order: Order) => void;
  notify: Notify;
  onMoney?: (order: Order) => void;
}) {
  const headingId = useId();
  const [orderId, setOrderId] = useState(() => crypto.randomUUID());
  const [revision, setRevision] = useState(0);
  const [customer, setCustomer] = useState("");
  const [reference, setReference] = useState("");
  const [loads, setLoads] = useState<LoadRow[]>([blankLoad()]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const customerName = (id: string) =>
    customers.find((c) => c.id === id)?.name ?? "Unknown customer";

  function reset() {
    setOrderId(crypto.randomUUID());
    setRevision(0);
    setCustomer("");
    setReference("");
    setLoads([blankLoad()]);
  }
  function edit(order: Order) {
    setError(null);
    setOrderId(order.order_id);
    setRevision(order.revision);
    setCustomer(order.customer_id);
    setReference(order.reference);
    setLoads(
      order.loads.map((l) => ({
        load_id: l.load_id,
        description: l.description,
        quantity: String(l.quantity),
        unit: l.unit,
      })),
    );
  }
  const change = (index: number, field: keyof LoadRow, value: string) =>
    setLoads((rows) =>
      rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    );

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    setBusy(true);
    try {
      const body: LoadBody[] = loads.map((l) => ({
        load_id: l.load_id,
        description: l.description.trim(),
        quantity: Number(l.quantity),
        unit: l.unit.trim(),
      }));
      const saved = await saveOrder(businessId, orderId, {
        schema_version: 1,
        expected_revision: revision,
        customer_id: customer,
        reference: reference.trim(),
        loads: body,
      });
      onSaved(saved);
      reset();
      notify("Order saved.");
    } catch (failure) {
      setError(`The order was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="transport-orders" aria-labelledby={headingId}>
      <h2 id={headingId}>Orders</h2>
      {orders.length === 0 ? (
        <p className="muted">No orders yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Orders table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Orders">
            <thead>
              <tr>
                <th scope="col">Reference</th>
                <th scope="col">Customer</th>
                <th scope="col">Loads (planned of total)</th>
                <th scope="col">Change</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.order_id}>
                  <th scope="row">{order.reference}</th>
                  <td>{customerName(order.customer_id)}</td>
                  <td>
                    {order.loads
                      .map(
                        (l) =>
                          `${l.description}: ${l.planned} of ${l.quantity} ${l.unit}`,
                      )
                      .join("; ")}
                  </td>
                  <td>
                    <button
                      type="button"
                      aria-label={`Edit ${order.reference}`}
                      onClick={() => edit(order)}
                    >
                      Edit
                    </button>
                    {onMoney && (
                      <button
                        type="button"
                        aria-label={`Money for ${order.reference}`}
                        onClick={() => onMoney(order)}
                      >
                        Money
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form aria-label="Order" onSubmit={submit}>
        <h3>{revision ? `Edit order ${reference}` : "New order"}</h3>
        <label>
          Customer
          <select
            value={customer}
            onChange={(e) => setCustomer(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reference
          <input
            value={reference}
            maxLength={64}
            onChange={(e) => setReference(e.target.value)}
            required
          />
        </label>
        {loads.map((row, index) => (
          <fieldset key={row.load_id}>
            <legend>Load {index + 1}</legend>
            <label>
              Description
              <input
                value={row.description}
                maxLength={500}
                onChange={(e) => change(index, "description", e.target.value)}
                required
              />
            </label>
            <label>
              Quantity
              <input
                type="number"
                min={1}
                value={row.quantity}
                onChange={(e) => change(index, "quantity", e.target.value)}
                required
              />
            </label>
            <label>
              Unit
              <input
                value={row.unit}
                maxLength={32}
                onChange={(e) => change(index, "unit", e.target.value)}
                required
              />
            </label>
            {loads.length > 1 && (
              <button
                type="button"
                onClick={() =>
                  setLoads((rows) => rows.filter((_, i) => i !== index))
                }
              >
                Remove load {index + 1}
              </button>
            )}
          </fieldset>
        ))}
        <div className="mgmt-form-actions">
          {loads.length < 50 && (
            <button
              type="button"
              onClick={() => setLoads((rows) => [...rows, blankLoad()])}
            >
              Add a load
            </button>
          )}
          {revision > 0 && (
            <button type="button" onClick={reset}>
              New order instead
            </button>
          )}
          <button type="submit" disabled={busy}>
            Save order
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

type StopRow = {
  key: string;
  kind: "pickup" | "delivery";
  place: string;
  zone: string;
  date: string;
  from: string;
  endDate: string;
  to: string;
};
type LegRow = {
  key: string;
  load: string;
  quantity: string;
  pickup: string;
  delivery: string;
};
const blankStop = (kind: StopRow["kind"]): StopRow => ({
  key: crypto.randomUUID(),
  kind,
  place: "",
  zone: "",
  date: "",
  from: "",
  endDate: "",
  to: "",
});
const blankLeg = (): LegRow => ({
  key: crypto.randomUUID(),
  load: "",
  quantity: "",
  pickup: "1",
  delivery: "2",
});

export function TripForm({
  businessId,
  orders,
  locations,
  editing,
  onSaved,
  onDone,
  notify,
}: {
  businessId: string;
  orders: Order[];
  locations: LocationItem[];
  editing: Trip | null;
  onSaved: (trip: Trip) => void;
  onDone: () => void;
  notify: Notify;
}) {
  const headingId = useId();
  const [tripId, setTripId] = useState(
    () => editing?.trip_id ?? crypto.randomUUID(),
  );
  const [revision, setRevision] = useState(editing?.revision ?? 0);
  const [location, setLocation] = useState(editing?.location_id ?? "");
  const [reference, setReference] = useState(editing?.reference ?? "");
  const [stops, setStops] = useState<StopRow[]>(() =>
    editing
      ? editing.stops.map((s) => ({
          key: crypto.randomUUID(),
          kind: s.kind,
          place: s.place,
          zone: s.time_zone,
          ...stopWindowFields(s.window_start, s.window_end, s.time_zone),
        }))
      : [blankStop("pickup"), blankStop("delivery")],
  );
  const [legs, setLegs] = useState<LegRow[]>(() =>
    editing
      ? editing.legs.map((l) => ({
          key: crypto.randomUUID(),
          load: l.load_id,
          quantity: String(l.quantity),
          pickup: String(l.pickup_stop),
          delivery: String(l.delivery_stop),
        }))
      : [blankLeg()],
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const loads = orders.flatMap((o) =>
    o.loads.map((l) => ({ order: o, load: l })),
  );
  const stopChange = (index: number, patch: Partial<StopRow>) =>
    setStops((rows) =>
      rows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  const legChange = (index: number, patch: Partial<LegRow>) =>
    setLegs((rows) =>
      rows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  const stopName = (index: number) =>
    `${index + 1} · ${stops[index]?.place || (stops[index]?.kind === "pickup" ? "Pickup" : "Delivery")}`;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    let body;
    try {
      body = {
        schema_version: 1 as const,
        expected_revision: revision,
        location_id: location,
        reference: reference.trim(),
        stops: stops.map((s) => {
          const zone = s.zone.trim();
          // Review R-04: an explicit end date keeps long, empty and DST-crossing windows exact.
          const { start, end } = stopWindowInstants(
            s.date,
            s.from,
            s.endDate,
            s.to,
            zone,
          );
          return {
            kind: s.kind,
            place: s.place.trim(),
            time_zone: zone,
            window_start: start,
            window_end: end,
          };
        }),
        legs: legs.map((l) => ({
          load_id: l.load,
          quantity: Number(l.quantity),
          pickup_stop: Number(l.pickup),
          delivery_stop: Number(l.delivery),
        })),
      };
    } catch (failure) {
      setError(`The trip was not saved: ${refusal(failure)}`);
      return;
    }
    setBusy(true);
    try {
      const saved = await saveTrip(businessId, tripId, body);
      onSaved(saved);
      notify("Trip saved.");
      if (editing) onDone();
      else {
        setTripId(crypto.randomUUID());
        setRevision(0);
        setReference("");
        setStops([blankStop("pickup"), blankStop("delivery")]);
        setLegs([blankLeg()]);
      }
    } catch (failure) {
      setError(`The trip was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="transport-plan" aria-labelledby={headingId}>
      <h2 id={headingId}>
        {editing ? `Edit trip ${editing.reference}` : "Plan a trip"}
      </h2>
      <form aria-label="Trip" onSubmit={submit}>
        <label>
          Location
          <select
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reference
          <input
            value={reference}
            maxLength={64}
            onChange={(e) => setReference(e.target.value)}
            required
          />
        </label>
        {stops.map((stop, index) => (
          <fieldset key={stop.key}>
            <legend>Stop {index + 1}</legend>
            <label>
              Kind
              <select
                value={stop.kind}
                onChange={(e) =>
                  stopChange(index, {
                    kind: e.target.value as StopRow["kind"],
                  })
                }
              >
                <option value="pickup">Pickup</option>
                <option value="delivery">Delivery</option>
              </select>
            </label>
            <label>
              Place
              <input
                value={stop.place}
                maxLength={300}
                onChange={(e) => stopChange(index, { place: e.target.value })}
                required
              />
            </label>
            <label>
              Time zone
              <input
                value={stop.zone}
                maxLength={64}
                placeholder="America/Chicago"
                onChange={(e) => stopChange(index, { zone: e.target.value })}
                required
              />
            </label>
            <label>
              Date
              <input
                type="date"
                value={stop.date}
                onChange={(e) => stopChange(index, { date: e.target.value })}
                required
              />
            </label>
            <label>
              From
              <input
                type="time"
                value={stop.from}
                onChange={(e) => stopChange(index, { from: e.target.value })}
                required
              />
            </label>
            <label>
              Ends on (if another day)
              <input
                type="date"
                value={stop.endDate}
                onChange={(e) => stopChange(index, { endDate: e.target.value })}
              />
            </label>
            <label>
              To
              <input
                type="time"
                value={stop.to}
                onChange={(e) => stopChange(index, { to: e.target.value })}
                required
              />
            </label>
            {stops.length > 2 && (
              <button
                type="button"
                onClick={() =>
                  setStops((rows) => rows.filter((_, i) => i !== index))
                }
              >
                Remove stop {index + 1}
              </button>
            )}
          </fieldset>
        ))}
        <p className="muted">
          Each window is entered in its stop&apos;s own time zone.
        </p>
        {legs.map((leg, index) => {
          const chosen = loads.find((x) => x.load.load_id === leg.load);
          return (
            <fieldset key={leg.key}>
              <legend>Leg {index + 1}</legend>
              <label>
                Load
                <select
                  value={leg.load}
                  onChange={(e) => legChange(index, { load: e.target.value })}
                  required
                >
                  <option value="">Choose</option>
                  {loads.map(({ order, load }) => (
                    <option key={load.load_id} value={load.load_id}>
                      {`${order.reference} · ${load.description}`}
                    </option>
                  ))}
                </select>
              </label>
              {chosen && (
                <p className="muted">
                  {chosen.load.planned} of {chosen.load.quantity}{" "}
                  {chosen.load.unit} already planned on trips.
                </p>
              )}
              <label>
                Quantity
                <input
                  type="number"
                  min={1}
                  value={leg.quantity}
                  onChange={(e) =>
                    legChange(index, { quantity: e.target.value })
                  }
                  required
                />
              </label>
              <label>
                Pickup stop
                <select
                  value={leg.pickup}
                  onChange={(e) => legChange(index, { pickup: e.target.value })}
                >
                  {stops.map((s, i) => (
                    <option key={s.key} value={String(i + 1)}>
                      {stopName(i)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Delivery stop
                <select
                  value={leg.delivery}
                  onChange={(e) =>
                    legChange(index, { delivery: e.target.value })
                  }
                >
                  {stops.map((s, i) => (
                    <option key={s.key} value={String(i + 1)}>
                      {stopName(i)}
                    </option>
                  ))}
                </select>
              </label>
              {legs.length > 1 && (
                <button
                  type="button"
                  onClick={() =>
                    setLegs((rows) => rows.filter((_, i) => i !== index))
                  }
                >
                  Remove leg {index + 1}
                </button>
              )}
            </fieldset>
          );
        })}
        <div className="mgmt-form-actions">
          {stops.length < 50 && (
            <button
              type="button"
              onClick={() =>
                setStops((rows) => [...rows, blankStop("delivery")])
              }
            >
              Add a stop
            </button>
          )}
          {legs.length < 100 && (
            <button
              type="button"
              onClick={() => setLegs((rows) => [...rows, blankLeg()])}
            >
              Add a leg
            </button>
          )}
          {editing && (
            <button type="button" onClick={onDone}>
              Cancel the change
            </button>
          )}
          <button type="submit" disabled={busy}>
            Save trip
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

export function FleetPanel({
  businessId,
  drivers,
  vehicles,
  locations,
  onDriver,
  onVehicle,
  notify,
}: {
  businessId: string;
  drivers: Driver[];
  vehicles: Vehicle[];
  locations: LocationItem[];
  onDriver: (driver: Driver) => void;
  onVehicle: (vehicle: Vehicle) => void;
  notify: Notify;
}) {
  const headingId = useId();
  const [driverId, setDriverId] = useState(() => crypto.randomUUID());
  const [driverName, setDriverName] = useState("");
  const [driverPlace, setDriverPlace] = useState("");
  const [vehicleId, setVehicleId] = useState(() => crypto.randomUUID());
  const [kind, setKind] = useState<"truck" | "trailer">("truck");
  const [unit, setUnit] = useState("");
  const [vehiclePlace, setVehiclePlace] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const placeName = (id: string) =>
    locations.find((l) => l.id === id)?.name ?? "Unknown location";

  async function submitDriver(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    setBusy(true);
    try {
      onDriver(
        await saveDriver(businessId, driverId, {
          schema_version: 1,
          location_id: driverPlace,
          display_name: driverName.trim(),
        }),
      );
      setDriverId(crypto.randomUUID());
      setDriverName("");
      setDriverPlace("");
      notify("Driver saved.");
    } catch (failure) {
      setError(`The driver was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }
  async function submitVehicle(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    setBusy(true);
    try {
      onVehicle(
        await saveVehicle(businessId, vehicleId, {
          schema_version: 1,
          location_id: vehiclePlace,
          kind,
          unit_number: unit.trim(),
        }),
      );
      setVehicleId(crypto.randomUUID());
      setUnit("");
      setVehiclePlace("");
      notify("Vehicle saved.");
    } catch (failure) {
      setError(`The vehicle was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="transport-fleet" aria-labelledby={headingId}>
      <h2 id={headingId}>Fleet</h2>
      <p className="muted">
        Drivers and vehicles are registered here once, with fixed details; a
        carrier&apos;s dispatcher assigns them but never registers them.
      </p>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Drivers table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Drivers">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Location</th>
            </tr>
          </thead>
          <tbody>
            {drivers.length === 0 ? (
              <tr>
                <td colSpan={2}>No drivers yet.</td>
              </tr>
            ) : (
              drivers.map((d) => (
                <tr key={d.driver_id}>
                  <th scope="row">{d.display_name}</th>
                  <td>{placeName(d.location_id)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <form aria-label="Driver" onSubmit={submitDriver}>
        <h3>Driver</h3>
        <label>
          Name
          <input
            value={driverName}
            maxLength={200}
            onChange={(e) => setDriverName(e.target.value)}
            required
          />
        </label>
        <label>
          Location
          <select
            value={driverPlace}
            onChange={(e) => setDriverPlace(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Save driver
          </button>
        </div>
      </form>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Vehicles table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Vehicles">
          <thead>
            <tr>
              <th scope="col">Unit</th>
              <th scope="col">Kind</th>
              <th scope="col">Location</th>
            </tr>
          </thead>
          <tbody>
            {vehicles.length === 0 ? (
              <tr>
                <td colSpan={3}>No vehicles yet.</td>
              </tr>
            ) : (
              vehicles.map((v) => (
                <tr key={v.vehicle_id}>
                  <th scope="row">{v.unit_number}</th>
                  <td>{v.kind === "truck" ? "Truck" : "Trailer"}</td>
                  <td>{placeName(v.location_id)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <form aria-label="Vehicle" onSubmit={submitVehicle}>
        <h3>Vehicle</h3>
        <label>
          Kind
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as "truck" | "trailer")}
          >
            <option value="truck">Truck</option>
            <option value="trailer">Trailer</option>
          </select>
        </label>
        <label>
          Unit number
          <input
            value={unit}
            maxLength={32}
            onChange={(e) => setUnit(e.target.value)}
            required
          />
        </label>
        <label>
          Location
          <select
            value={vehiclePlace}
            onChange={(e) => setVehiclePlace(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Save vehicle
          </button>
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
