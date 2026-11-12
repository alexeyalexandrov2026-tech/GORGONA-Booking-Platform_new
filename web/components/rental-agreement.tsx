"use client";

// R8b (package R): rate cards, and on a booking the quote, the accepted agreement and the security.
// Every figure is the server's; money is entered in major units and sent in minor units of the
// currency; a command keeps its Idempotency-Key until it succeeds (ADR-0030).
import React, { useCallback, useEffect, useId, useState } from "react";
import { businessDateTime, businessTimeToInstant } from "../lib/business-time";
import {
  currencyPlaces,
  formatMinor,
  toMinor,
} from "../lib/construction-rules";
import type { LocationItem } from "../lib/management-api";
import {
  acceptAgreement,
  fetchAgreement,
  fetchQuote,
  fetchRateCards,
  fetchSecurity,
  recordSecurityEvent,
  refusal,
  requestSecurity,
  saveRateCard,
} from "../lib/rental-api";
import type {
  Agreement,
  Booking,
  Quote,
  RateCard,
  RentalClass,
  Security,
  SecurityKind,
  SecurityMethod,
} from "../lib/rental-contracts";

const places = (currency: string) => currencyPlaces(currency) ?? 2;
const money = (minor: number | null, currency: string) =>
  minor === null ? "—" : formatMinor(minor, places(currency));

function when(instant: string, zone: string) {
  try {
    const local = businessDateTime(instant, zone);
    return `${local.date} ${local.time}`;
  } catch {
    return instant;
  }
}

/** A money field in major units as minor units, or a reason it cannot be read. */
function minorOf(text: string, currency: string, label: string): number {
  const value = toMinor(text, places(currency));
  if (value === null)
    throw new Error(
      `${label} is not an amount in ${currency || "the currency"}.`,
    );
  return value;
}

const RATES = [
  ["hour", "Hour rate"],
  ["day", "Day rate"],
  ["week", "Week rate"],
  ["month", "Month rate"],
] as const;

export function RateCardsSection({
  businessId,
  classes,
  locations,
  notify,
}: {
  businessId: string;
  classes: RentalClass[];
  locations: LocationItem[];
  notify: (text: string) => void;
}) {
  const headingId = useId();
  const [cards, setCards] = useState<RateCard[]>([]);
  const [classId, setClassId] = useState("");
  const [location, setLocation] = useState("");
  const [currency, setCurrency] = useState("");
  const [rates, setRates] = useState({
    hour: "",
    day: "",
    week: "",
    month: "",
  });
  const [allowance, setAllowance] = useState("");
  const [excess, setExcess] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ids = classes.map((c) => c.class_id).join(",");

  const read = useCallback(async () => {
    const lists = await Promise.all(
      ids ? ids.split(",").map((id) => fetchRateCards(businessId, id)) : [],
    );
    return lists.flatMap((l) => l.items);
  }, [businessId, ids]);

  useEffect(() => {
    let live = true;
    read()
      .then((items) => {
        if (live) setCards(items);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The rate cards could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [read]);

  const code = (id: string) =>
    classes.find((c) => c.class_id === id)?.code ?? "Unknown class";
  const branch = (id: string) =>
    locations.find((l) => l.id === id)?.name ?? "Unknown branch";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const unit = currency.trim().toUpperCase();
      const chosen: Record<string, number> = {};
      for (const [key, label] of RATES)
        if (rates[key].trim()) chosen[key] = minorOf(rates[key], unit, label);
      const saved = await saveRateCard(businessId, classId, {
        schema_version: 1,
        location_id: location,
        currency: unit,
        rates: chosen,
        meter_allowance_per_day: allowance.trim() ? Number(allowance) : null,
        excess_rate: excess.trim()
          ? minorOf(excess, unit, "Excess rate")
          : null,
        extras: [],
      });
      setCards(await read());
      notify(
        `Rate card version ${saved.version} for ${code(saved.class_id)} saved.`,
      );
    } catch (failure) {
      setError(`The rate card was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>Rate cards</h2>
      <form aria-label="Rate card" onSubmit={submit}>
        <label>
          Class
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {classes.map((c) => (
              <option key={c.class_id} value={c.class_id}>
                {`${c.code} ${c.name}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Branch
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
          Currency
          <input
            value={currency}
            maxLength={3}
            pattern="[A-Za-z]{3}"
            placeholder="USD"
            onChange={(e) => setCurrency(e.target.value)}
            required
          />
        </label>
        {RATES.map(([key, label]) => (
          <label key={key}>
            {label}
            <input
              value={rates[key]}
              inputMode="decimal"
              onChange={(e) =>
                setRates((r) => ({ ...r, [key]: e.target.value }))
              }
            />
          </label>
        ))}
        <label>
          Meter allowance per day
          <input
            value={allowance}
            inputMode="numeric"
            pattern="\d{0,7}"
            onChange={(e) => setAllowance(e.target.value)}
          />
        </label>
        <label>
          Excess rate
          <input
            value={excess}
            inputMode="decimal"
            onChange={(e) => setExcess(e.target.value)}
          />
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Save rate card
          </button>
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
      {cards.length === 0 ? (
        <p className="muted">No rate cards yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Rate cards table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Rate cards">
            <thead>
              <tr>
                <th scope="col">Class</th>
                <th scope="col">Branch</th>
                <th scope="col">Version</th>
                <th scope="col">Currency</th>
                <th scope="col">Hour</th>
                <th scope="col">Day</th>
                <th scope="col">Week</th>
                <th scope="col">Month</th>
                <th scope="col">Allowance a day</th>
                <th scope="col">Excess rate</th>
              </tr>
            </thead>
            <tbody>
              {cards.map((c) => (
                <tr key={c.rate_card_id}>
                  <th scope="row">{code(c.class_id)}</th>
                  <td>{branch(c.location_id)}</td>
                  <td>{c.version}</td>
                  <td>{c.currency}</td>
                  <td>{money(c.rates.hour, c.currency)}</td>
                  <td>{money(c.rates.day, c.currency)}</td>
                  <td>{money(c.rates.week, c.currency)}</td>
                  <td>{money(c.rates.month, c.currency)}</td>
                  <td>{c.meter_allowance_per_day ?? "—"}</td>
                  <td>{money(c.excess_rate, c.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function AgreementAndSecurity({
  businessId,
  booking,
  zone,
  notify,
}: {
  businessId: string;
  booking: Booking;
  zone: string;
  notify: (text: string) => void;
}) {
  const [agreement, setAgreement] = useState<Agreement | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [security, setSecurity] = useState<Security | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = booking.booking_id;

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchAgreement(businessId, id),
      fetchQuote(businessId, id).catch(() => null),
      fetchSecurity(businessId, id),
    ])
      .then(([agreed, priced, secured]) => {
        if (!live) return;
        setAgreement(agreed);
        setQuote(priced);
        setSecurity(secured);
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The agreement could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId, id]);

  if (error)
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  if (!loaded)
    return (
      <p className="muted" role="status">
        Loading the agreement…
      </p>
    );
  const currency =
    agreement?.versions.at(-1)?.currency ?? quote?.currency ?? "";
  return (
    <>
      <AgreementPanel
        businessId={businessId}
        booking={booking}
        zone={zone}
        agreement={agreement}
        quote={quote}
        onAccepted={(saved) => {
          setAgreement(saved);
          notify("Agreement accepted.");
        }}
      />
      <SecurityPanel
        businessId={businessId}
        booking={booking}
        zone={zone}
        currency={currency}
        security={security}
        onChange={setSecurity}
        notify={notify}
      />
    </>
  );
}

function AgreementPanel({
  businessId,
  booking,
  zone,
  agreement,
  quote,
  onAccepted,
}: {
  businessId: string;
  booking: Booking;
  zone: string;
  agreement: Agreement | null;
  quote: Quote | null;
  onAccepted: (saved: Agreement) => void;
}) {
  const headingId = useId();
  const [source, setSource] = useState<"platform" | "paper" | "email">("paper");
  const [acceptedBy, setAcceptedBy] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (!zone) throw new Error("The pickup branch has no time zone.");
      onAccepted(
        await acceptAgreement(businessId, booking.booking_id, {
          schema_version: 1,
          source,
          accepted_by: acceptedBy.trim(),
          accepted_at: businessTimeToInstant(date, time, zone),
          extras: [],
        }),
      );
    } catch (failure) {
      setError(`The agreement was not accepted: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Agreement</h3>
      {agreement ? (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Agreement versions table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Agreement versions">
            <thead>
              <tr>
                <th scope="col">Version</th>
                <th scope="col">From</th>
                <th scope="col">To</th>
                <th scope="col">Rental</th>
                <th scope="col">Total</th>
                <th scope="col">Source</th>
                <th scope="col">Accepted by</th>
              </tr>
            </thead>
            <tbody>
              {agreement.versions.map((v) => (
                <tr key={v.version}>
                  <th scope="row">{v.version}</th>
                  <td>{when(v.starts_at, zone)}</td>
                  <td>{when(v.ends_at, zone)}</td>
                  <td>{`${money(v.rental, v.currency)} ${v.currency}`}</td>
                  <td>{`${money(v.total, v.currency)} ${v.currency}`}</td>
                  <td>{v.source}</td>
                  <td>{v.accepted_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <p>
            {quote
              ? `Quote: rental ${money(quote.rental, quote.currency)} ${quote.currency} for ` +
                `${quote.rental_days} days, total ${money(quote.total, quote.currency)} ${quote.currency}`
              : "No rate card prices this booking yet."}
          </p>
          {!booking.cancellation && (
            <form aria-label="Accept the agreement" onSubmit={submit}>
              <label>
                Source
                <select
                  value={source}
                  onChange={(e) =>
                    setSource(e.target.value as "platform" | "paper" | "email")
                  }
                >
                  <option value="platform">Platform</option>
                  <option value="paper">Paper</option>
                  <option value="email">Email</option>
                </select>
              </label>
              <label>
                Accepted by
                <input
                  value={acceptedBy}
                  maxLength={200}
                  onChange={(e) => setAcceptedBy(e.target.value)}
                  required
                />
              </label>
              <label>
                Accepted on
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  required
                />
              </label>
              <label>
                Accepted at
                <input
                  type="time"
                  value={time}
                  onChange={(e) => setTime(e.target.value)}
                  required
                />
              </label>
              <div className="mgmt-form-actions">
                <button type="submit" disabled={busy}>
                  Accept agreement
                </button>
              </div>
            </form>
          )}
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

const KINDS: [SecurityKind, string][] = [
  ["held", "Held"],
  ["captured", "Captured"],
  ["released", "Released"],
  ["expired", "Expired"],
];
const METHODS: [SecurityMethod, string][] = [
  ["card_hold", "Card hold"],
  ["cash", "Cash"],
  ["bank_transfer", "Bank transfer"],
  ["other", "Other"],
];

function SecurityPanel({
  businessId,
  booking,
  zone,
  currency,
  security,
  onChange,
  notify,
}: {
  businessId: string;
  booking: Booking;
  zone: string;
  currency: string;
  security: Security | null;
  onChange: (saved: Security) => void;
  notify: (text: string) => void;
}) {
  const headingId = useId();
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<SecurityMethod>("card_hold");
  const [kind, setKind] = useState<SecurityKind>("held");
  const [eventAmount, setEventAmount] = useState("");
  const [reference, setReference] = useState("");
  const [basis, setBasis] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function request(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      onChange(
        await requestSecurity(
          businessId,
          booking.booking_id,
          minorOf(amount, currency, "Amount"),
          method,
        ),
      );
      notify("Security requested.");
    } catch (failure) {
      setError(`The security was not requested: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function record(event: React.FormEvent) {
    event.preventDefault();
    if (!security) return;
    setError(null);
    setBusy(true);
    try {
      onChange(
        await recordSecurityEvent(businessId, booking.booking_id, {
          schema_version: 1,
          kind,
          amount: minorOf(eventAmount, security.currency, "Amount"),
          occurred_at: new Date().toISOString(),
          ...(reference.trim() ? { reference: reference.trim() } : {}),
          ...(basis.trim() ? { basis: basis.trim() } : {}),
        }),
      );
      notify("Security event recorded.");
      setEventAmount("");
    } catch (failure) {
      setError(`The security event was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const label = (value: SecurityKind) =>
    KINDS.find(([k]) => k === value)?.[1] ?? value;
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Security</h3>
      {security ? (
        <>
          <p>
            {`Security: ${security.state}; held ${money(security.held, security.currency)}, ` +
              `captured ${money(security.captured, security.currency)}, released ` +
              `${money(security.released, security.currency)}, expired ` +
              `${money(security.expired, security.currency)}, remaining ` +
              `${money(security.remaining, security.currency)} ${security.currency}`}
          </p>
          {security.events.length > 0 && (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Security events table"
              tabIndex={0}
            >
              <table className="mgmt-table" aria-label="Security events">
                <thead>
                  <tr>
                    <th scope="col">Event</th>
                    <th scope="col">Kind</th>
                    <th scope="col">Amount</th>
                    <th scope="col">Reference</th>
                    <th scope="col">Basis</th>
                    <th scope="col">When</th>
                  </tr>
                </thead>
                <tbody>
                  {security.events.map((e) => (
                    <tr key={e.sequence}>
                      <th scope="row">{e.sequence}</th>
                      <td>{label(e.kind)}</td>
                      <td>{money(e.amount, security.currency)}</td>
                      <td>{e.reference ?? "—"}</td>
                      <td>{e.basis ?? "—"}</td>
                      <td>{when(e.occurred_at, zone)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <form aria-label="Security event" onSubmit={record}>
            <label>
              Kind
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as SecurityKind)}
              >
                {KINDS.map(([value, text]) => (
                  <option key={value} value={value}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Amount
              <input
                value={eventAmount}
                inputMode="decimal"
                onChange={(e) => setEventAmount(e.target.value)}
                required
              />
            </label>
            <label>
              Reference
              <input
                value={reference}
                maxLength={200}
                onChange={(e) => setReference(e.target.value)}
              />
            </label>
            <label>
              Basis
              <input
                value={basis}
                maxLength={500}
                onChange={(e) => setBasis(e.target.value)}
              />
            </label>
            <div className="mgmt-form-actions">
              <button type="submit" disabled={busy}>
                Record event
              </button>
            </div>
          </form>
        </>
      ) : (
        <form aria-label="Request security" onSubmit={request}>
          <label>
            Amount
            <input
              value={amount}
              inputMode="decimal"
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </label>
          <label>
            Method
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value as SecurityMethod)}
            >
              {METHODS.map(([value, text]) => (
                <option key={value} value={value}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Request security
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
