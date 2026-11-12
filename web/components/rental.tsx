"use client";

// R8a (package R): the rental catalogue (classes and units), availability and bookings with their
// unit. Every figure is the server's (availability is never computed here); a command keeps its
// record id and Idempotency-Key until it succeeds (ADR-0030). Times are shown and entered in the
// time zone of the branch they belong to.
import React, { useEffect, useId, useState } from "react";
import { businessDateTime, businessTimeToInstant } from "../lib/business-time";
import { fetchCounterparties } from "../lib/counterparty-api";
import { fetchWorkspace, type LocationItem } from "../lib/management-api";
import {
  assignUnit,
  book,
  cancelBooking,
  fetchAssignments,
  fetchAvailability,
  fetchBookings,
  fetchClasses,
  fetchUnits,
  refusal,
  saveClass,
  saveUnit,
} from "../lib/rental-api";
import type {
  Assignment,
  Availability,
  Booking,
  MeterKind,
  RentalClass,
  Unit,
} from "../lib/rental-contracts";
import { AgreementAndSecurity, RateCardsSection } from "./rental-agreement";

type Customer = { id: string; name: string };

const METERS: [MeterKind, string][] = [
  ["none", "None"],
  ["odometer", "Odometer"],
  ["hours", "Hours"],
];
const meterLabel = (kind: MeterKind) =>
  METERS.find(([value]) => value === kind)?.[1] ?? kind;

async function allCustomers(businessId: string): Promise<Customer[]> {
  const found: Customer[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchCounterparties(businessId, "", "active", after);
    for (const c of page.items)
      if (c.roles.includes("customer"))
        found.push({ id: c.counterparty_id, name: c.display_name });
    if (!page.next_cursor) return found;
    after = page.next_cursor;
  }
}

function replace<T>(list: T[], item: T, same: (a: T) => boolean): T[] {
  return list.some(same)
    ? list.map((x) => (same(x) ? item : x))
    : [...list, item];
}

const classLabel = (c: RentalClass) => `${c.code} ${c.name}`;

function when(instant: string, zone: string) {
  try {
    const local = businessDateTime(instant, zone);
    return `${local.date} ${local.time}`;
  } catch {
    return instant;
  }
}

/** A period entered as dates and times in a branch's zone, or a reason it cannot be read. */
function readPeriod(
  zone: string | undefined,
  fromDate: string,
  fromTime: string,
  toDate: string,
  toTime: string,
): { starts_at: string; ends_at: string } {
  if (!zone) throw new Error("Choose a branch first.");
  return {
    starts_at: businessTimeToInstant(fromDate, fromTime, zone),
    ends_at: businessTimeToInstant(toDate, toTime, zone),
  };
}

function Period({
  values,
  onChange,
}: {
  values: {
    fromDate: string;
    fromTime: string;
    toDate: string;
    toTime: string;
  };
  onChange: (
    key: "fromDate" | "fromTime" | "toDate" | "toTime",
    value: string,
  ) => void;
}) {
  return (
    <>
      <label>
        From date
        <input
          type="date"
          value={values.fromDate}
          onChange={(e) => onChange("fromDate", e.target.value)}
          required
        />
      </label>
      <label>
        From time
        <input
          type="time"
          value={values.fromTime}
          onChange={(e) => onChange("fromTime", e.target.value)}
          required
        />
      </label>
      <label>
        To date
        <input
          type="date"
          value={values.toDate}
          onChange={(e) => onChange("toDate", e.target.value)}
          required
        />
      </label>
      <label>
        To time
        <input
          type="time"
          value={values.toTime}
          onChange={(e) => onChange("toTime", e.target.value)}
          required
        />
      </label>
    </>
  );
}

const EMPTY_PERIOD = { fromDate: "", fromTime: "", toDate: "", toTime: "" };

function Choose<T>({
  label,
  value,
  onChange,
  items,
  option,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  items: T[];
  option: (item: T) => [string, string];
}) {
  return (
    <label>
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} required>
        <option value="">Choose</option>
        {items.map((item) => {
          const [id, text] = option(item);
          return (
            <option key={id} value={id}>
              {text}
            </option>
          );
        })}
      </select>
    </label>
  );
}

export function RentalScreen({ businessId }: { businessId: string }) {
  const [classes, setClasses] = useState<RentalClass[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Booking | null>(null);
  const [editing, setEditing] = useState<RentalClass | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchClasses(businessId),
      fetchUnits(businessId),
      fetchBookings(businessId),
      // Without the counterparties module there is no customer to choose; the lists still work.
      allCustomers(businessId).catch(() => [] as Customer[]),
      fetchWorkspace(businessId).then((w) => w.locations),
    ])
      .then(([kinds, items, booked, people, places]) => {
        if (!live) return;
        setClasses(kinds);
        setUnits(items);
        setBookings(booked);
        setCustomers(people);
        setLocations(places);
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(
            `The rental catalogue could not be read: ${refusal(failure)}`,
          );
      });
    return () => {
      live = false;
    };
  }, [businessId]);

  const branch = (id: string) => locations.find((l) => l.id === id);
  const branchName = (id: string) => branch(id)?.name ?? "Unknown branch";
  const klass = (id: string) => classes.find((c) => c.class_id === id);
  const customerName = (id: string) =>
    customers.find((c) => c.id === id)?.name ?? "Unknown customer";

  function bookingChanged(item: Booking) {
    setBookings((list) =>
      replace(list, item, (x) => x.booking_id === item.booking_id),
    );
    setSelected((current) =>
      current?.booking_id === item.booking_id ? item : current,
    );
  }

  return (
    <div className="rental-screen">
      <h1>Rental</h1>
      <p className="muted">
        Rental classes and units, availability and bookings with the unit that
        serves them.
      </p>
      <p className="rental-status" role="status">
        {notice}
      </p>
      {!loaded && !error && (
        <p className="muted" role="status">
          Loading the rental catalogue…
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loaded && (
        <>
          <ClassesSection classes={classes} onEdit={setEditing} />
          <ClassForm
            key={editing?.class_id ?? "new"}
            businessId={businessId}
            editing={editing}
            onSaved={(saved) => {
              setClasses((list) =>
                replace(list, saved, (x) => x.class_id === saved.class_id),
              );
              setEditing(null);
              setNotice(`Class ${saved.code} saved.`);
            }}
          />
          <UnitsSection
            businessId={businessId}
            classes={classes}
            units={units}
            locations={locations}
            branchName={branchName}
            onSaved={(saved) => {
              setUnits((list) =>
                replace(list, saved, (x) => x.unit_id === saved.unit_id),
              );
              setNotice(`Unit ${saved.identifier} saved.`);
            }}
          />
          <RateCardsSection
            businessId={businessId}
            classes={classes}
            locations={locations}
            notify={setNotice}
          />
          <AvailabilitySection
            businessId={businessId}
            classes={classes}
            locations={locations}
          />
          <BookingsSection
            businessId={businessId}
            classes={classes}
            customers={customers}
            locations={locations}
            bookings={bookings}
            branch={branch}
            klass={klass}
            customerName={customerName}
            onOpen={setSelected}
            onBooked={(saved) => {
              bookingChanged(saved);
              setNotice(`Booking ${saved.number} saved.`);
            }}
          />
          {selected && (
            <BookingPage
              key={selected.booking_id}
              businessId={businessId}
              booking={selected}
              units={units.filter(
                (u) => u.class_id === selected.class_id && u.state === "active",
              )}
              allUnits={units}
              zone={branch(selected.pickup_location_id)?.timezone ?? ""}
              className={klass(selected.class_id)?.code ?? "Unknown class"}
              branchName={branchName}
              customerName={customerName(selected.customer_id)}
              onChange={bookingChanged}
              notify={setNotice}
            />
          )}
        </>
      )}
    </div>
  );
}

function ClassesSection({
  classes,
  onEdit,
}: {
  classes: RentalClass[];
  onEdit: (item: RentalClass) => void;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>Classes</h2>
      {classes.length === 0 ? (
        <p className="muted">No classes yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Classes table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Classes">
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Name</th>
                <th scope="col">Meter</th>
                <th scope="col">Attributes</th>
                <th scope="col">Revision</th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => (
                <tr key={c.class_id}>
                  <th scope="row">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => onEdit(c)}
                    >
                      {c.code}
                    </button>
                  </th>
                  <td>{c.name}</td>
                  <td>{meterLabel(c.meter_kind)}</td>
                  <td>
                    {c.attributes.map((a) => a.label).join(", ") || "None"}
                  </td>
                  <td>{c.revision}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ClassForm({
  businessId,
  editing,
  onSaved,
}: {
  businessId: string;
  editing: RentalClass | null;
  onSaved: (item: RentalClass) => void;
}) {
  const headingId = useId();
  // A new class keeps its id until the save succeeds, so a retry saves it once.
  const [classId, setClassId] = useState(
    () => editing?.class_id ?? crypto.randomUUID(),
  );
  const [code, setCode] = useState(editing?.code ?? "");
  const [name, setName] = useState(editing?.name ?? "");
  const [meter, setMeter] = useState<MeterKind>(editing?.meter_kind ?? "none");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await saveClass(businessId, classId, {
        schema_version: 1,
        expected_revision: editing?.revision ?? 0,
        code: code.trim().toUpperCase(),
        name: name.trim(),
        meter_kind: meter,
        attributes: editing?.attributes ?? [],
      });
      onSaved(saved);
      if (!editing) {
        setClassId(crypto.randomUUID());
        setCode("");
        setName("");
        setMeter("none");
      }
    } catch (failure) {
      setError(`The class was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>
        {editing ? `Edit class ${editing.code}` : "New class"}
      </h2>
      <form aria-label="Class" onSubmit={submit}>
        <label>
          Code
          <input
            value={code}
            maxLength={32}
            pattern="[A-Za-z0-9][A-Za-z0-9_\-]{0,31}"
            onChange={(e) => setCode(e.target.value)}
            required
          />
        </label>
        <label>
          Name
          <input
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label>
          Meter
          <select
            value={meter}
            onChange={(e) => setMeter(e.target.value as MeterKind)}
          >
            {METERS.map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Save class
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

function UnitsSection({
  businessId,
  classes,
  units,
  locations,
  branchName,
  onSaved,
}: {
  businessId: string;
  classes: RentalClass[];
  units: Unit[];
  locations: LocationItem[];
  branchName: (id: string) => string;
  onSaved: (item: Unit) => void;
}) {
  const headingId = useId();
  const [unitId, setUnitId] = useState(() => crypto.randomUUID());
  const [classId, setClassId] = useState("");
  const [identifier, setIdentifier] = useState("");
  const [location, setLocation] = useState("");
  const [state, setState] = useState<Unit["state"]>("active");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const code = (id: string) =>
    classes.find((c) => c.class_id === id)?.code ?? "Unknown class";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await saveUnit(businessId, unitId, {
        schema_version: 1,
        expected_revision: 0,
        class_id: classId,
        identifier: identifier.trim(),
        location_id: location,
        state,
        values: {},
      });
      onSaved(saved);
      setUnitId(crypto.randomUUID());
      setIdentifier("");
    } catch (failure) {
      setError(`The unit was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>Units</h2>
      <form aria-label="Unit" onSubmit={submit}>
        <Choose
          label="Class"
          value={classId}
          onChange={setClassId}
          items={classes}
          option={(c) => [c.class_id, classLabel(c)]}
        />
        <label>
          Identifier
          <input
            value={identifier}
            maxLength={64}
            onChange={(e) => setIdentifier(e.target.value)}
            required
          />
        </label>
        <Choose
          label="Branch"
          value={location}
          onChange={setLocation}
          items={locations}
          option={(l) => [l.id, l.name]}
        />
        <label>
          State
          <select
            value={state}
            onChange={(e) => setState(e.target.value as Unit["state"])}
          >
            <option value="active">Active</option>
            <option value="retired">Retired</option>
          </select>
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Save unit
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
      {units.length === 0 ? (
        <p className="muted">No units yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Units table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Units">
            <thead>
              <tr>
                <th scope="col">Identifier</th>
                <th scope="col">Class</th>
                <th scope="col">Branch</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {units.map((u) => (
                <tr key={u.unit_id}>
                  <th scope="row">{u.identifier}</th>
                  <td>{code(u.class_id)}</td>
                  <td>{branchName(u.location_id)}</td>
                  <td>{u.state === "active" ? "Active" : "Retired"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function AvailabilitySection({
  businessId,
  classes,
  locations,
}: {
  businessId: string;
  classes: RentalClass[];
  locations: LocationItem[];
}) {
  const headingId = useId();
  const [classId, setClassId] = useState("");
  const [location, setLocation] = useState("");
  const [period, setPeriod] = useState(EMPTY_PERIOD);
  const [result, setResult] = useState<Availability | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    try {
      const zone = locations.find((l) => l.id === location)?.timezone;
      const range = readPeriod(
        zone,
        period.fromDate,
        period.fromTime,
        period.toDate,
        period.toTime,
      );
      setResult(
        await fetchAvailability(businessId, {
          class_id: classId,
          location_id: location,
          ...range,
        }),
      );
    } catch (failure) {
      setError(`Availability could not be read: ${refusal(failure)}`);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>Availability</h2>
      <form aria-label="Availability" onSubmit={submit}>
        <Choose
          label="Class"
          value={classId}
          onChange={setClassId}
          items={classes}
          option={(c) => [c.class_id, classLabel(c)]}
        />
        <Choose
          label="Branch"
          value={location}
          onChange={setLocation}
          items={locations}
          option={(l) => [l.id, l.name]}
        />
        <Period
          values={period}
          onChange={(key, value) => setPeriod((p) => ({ ...p, [key]: value }))}
        />
        <div className="mgmt-form-actions">
          <button type="submit">Check availability</button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
      <p role="status">
        {result &&
          `Available: ${result.available} of ${result.units} (booked ${result.booked})`}
      </p>
    </section>
  );
}

function BookingsSection({
  businessId,
  classes,
  customers,
  locations,
  bookings,
  branch,
  klass,
  customerName,
  onOpen,
  onBooked,
}: {
  businessId: string;
  classes: RentalClass[];
  customers: Customer[];
  locations: LocationItem[];
  bookings: Booking[];
  branch: (id: string) => LocationItem | undefined;
  klass: (id: string) => RentalClass | undefined;
  customerName: (id: string) => string;
  onOpen: (item: Booking) => void;
  onBooked: (item: Booking) => void;
}) {
  const headingId = useId();
  const [classId, setClassId] = useState("");
  const [customer, setCustomer] = useState("");
  const [pickup, setPickup] = useState("");
  const [dropoff, setDropoff] = useState("");
  const [period, setPeriod] = useState(EMPTY_PERIOD);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const range = readPeriod(
        branch(pickup)?.timezone,
        period.fromDate,
        period.fromTime,
        period.toDate,
        period.toTime,
      );
      onBooked(
        await book(businessId, {
          schema_version: 1,
          class_id: classId,
          customer_id: customer,
          pickup_location_id: pickup,
          return_location_id: dropoff,
          ...range,
          note: note.trim() || null,
        }),
      );
    } catch (failure) {
      setError(`The booking was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>Bookings</h2>
      <form aria-label="Booking" onSubmit={submit}>
        <Choose
          label="Class"
          value={classId}
          onChange={setClassId}
          items={classes}
          option={(c) => [c.class_id, classLabel(c)]}
        />
        <Choose
          label="Customer"
          value={customer}
          onChange={setCustomer}
          items={customers}
          option={(c) => [c.id, c.name]}
        />
        <Choose
          label="Pickup branch"
          value={pickup}
          onChange={setPickup}
          items={locations}
          option={(l) => [l.id, l.name]}
        />
        <Choose
          label="Return branch"
          value={dropoff}
          onChange={setDropoff}
          items={locations}
          option={(l) => [l.id, l.name]}
        />
        <Period
          values={period}
          onChange={(key, value) => setPeriod((p) => ({ ...p, [key]: value }))}
        />
        <label>
          Note
          <input
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Save booking
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
      {bookings.length === 0 ? (
        <p className="muted">No bookings yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Bookings table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Bookings">
            <thead>
              <tr>
                <th scope="col">Booking</th>
                <th scope="col">Class</th>
                <th scope="col">Customer</th>
                <th scope="col">From</th>
                <th scope="col">To</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((b) => {
                const zone = branch(b.pickup_location_id)?.timezone ?? "";
                return (
                  <tr key={b.booking_id}>
                    <th scope="row">
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => onOpen(b)}
                      >
                        {`Booking ${b.number}`}
                      </button>
                    </th>
                    <td>{klass(b.class_id)?.code ?? "Unknown class"}</td>
                    <td>{customerName(b.customer_id)}</td>
                    <td>{when(b.starts_at, zone)}</td>
                    <td>{when(b.ends_at, zone)}</td>
                    <td>{b.cancellation ? "Cancelled" : "Booked"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function BookingPage({
  businessId,
  booking,
  units,
  allUnits,
  zone,
  className,
  branchName,
  customerName,
  onChange,
  notify,
}: {
  businessId: string;
  booking: Booking;
  units: Unit[];
  allUnits: Unit[];
  zone: string;
  className: string;
  branchName: (id: string) => string;
  customerName: string;
  onChange: (item: Booking) => void;
  notify: (text: string) => void;
}) {
  const headingId = useId();
  const [assignments, setAssignments] = useState<Assignment[] | null>(null);
  const [unit, setUnit] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const identifier = (id: string) =>
    allUnits.find((u) => u.unit_id === id)?.identifier ?? "Unknown unit";

  useEffect(() => {
    let live = true;
    fetchAssignments(businessId, booking.booking_id)
      .then((list) => {
        if (live) setAssignments(list.items);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The assignments could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId, booking.booking_id]);

  async function assign(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await assignUnit(businessId, booking.booking_id, unit);
      setAssignments(
        (await fetchAssignments(businessId, booking.booking_id)).items,
      );
      notify(`Unit ${identifier(unit)} assigned.`);
      setUnit("");
    } catch (failure) {
      setError(`The unit was not assigned: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function cancel(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const saved = await cancelBooking(
        businessId,
        booking.booking_id,
        reason.trim(),
      );
      onChange(saved);
      setAssignments(
        (await fetchAssignments(businessId, booking.booking_id)).items,
      );
      notify(`Booking ${saved.number} cancelled.`);
      setReason("");
    } catch (failure) {
      setError(`The booking was not cancelled: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>{`Booking ${booking.number}`}</h2>
      <p>
        {className} for {customerName}, {when(booking.starts_at, zone)} to{" "}
        {when(booking.ends_at, zone)}, from{" "}
        {branchName(booking.pickup_location_id)} back to{" "}
        {branchName(booking.return_location_id)}.
        {booking.note ? ` Note: ${booking.note}` : ""}
      </p>
      {booking.cancellation && (
        <p>
          Cancelled {when(booking.cancellation.cancelled_at, zone)}:{" "}
          {booking.cancellation.reason}
        </p>
      )}
      {assignments === null ? (
        <p className="muted" role="status">
          Loading the assignments…
        </p>
      ) : assignments.length === 0 ? (
        <p className="muted">No unit assigned yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Assignments table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Assignments">
            <thead>
              <tr>
                <th scope="col">Unit</th>
                <th scope="col">From</th>
                <th scope="col">To</th>
                <th scope="col">State</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((a) => (
                <tr key={a.assignment_id}>
                  <th scope="row">{identifier(a.unit_id)}</th>
                  <td>{when(a.starts_at, zone)}</td>
                  <td>{when(a.ends_at, zone)}</td>
                  <td>
                    {a.release ? `Released (${a.release.reason})` : "Current"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <AgreementAndSecurity
        businessId={businessId}
        booking={booking}
        zone={zone}
        notify={notify}
      />
      {!booking.cancellation && (
        <>
          <form aria-label="Assign a unit" onSubmit={assign}>
            <Choose
              label="Unit"
              value={unit}
              onChange={setUnit}
              items={units}
              option={(u) => [u.unit_id, u.identifier]}
            />
            <div className="mgmt-form-actions">
              <button type="submit" disabled={busy}>
                Assign unit
              </button>
            </div>
          </form>
          <form aria-label="Cancel booking" onSubmit={cancel}>
            <label>
              Reason
              <input
                value={reason}
                maxLength={500}
                onChange={(e) => setReason(e.target.value)}
                required
              />
            </label>
            <div className="mgmt-form-actions">
              <button type="submit" disabled={busy}>
                Cancel booking
              </button>
            </div>
          </form>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
