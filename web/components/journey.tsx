"use client";
import Image from "next/image";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { api, ApiError, errorMessage, money, newCapability } from "../lib/api";
import {
  bookingSchema,
  type Booking,
  type Bootstrap,
  type Details,
  type Quote,
  type Slot,
} from "../lib/contracts";
import {
  addOnOffered,
  MAX_EXTRA_LINES,
  selectionOf,
  servicesOffered,
  servingAll,
  type Line,
} from "../lib/visit";
import {
  Summary,
  Times,
  HoldNotice,
  Appointment,
  DetailsForm,
} from "./booking-parts";
type Step = "service" | "time" | "details" | "review" | "confirmed";
const steps: Step[] = ["service", "time", "details", "review"];

export function Journey({ salon }: { salon: Bootstrap }) {
  const [step, setStep] = useState<Step>("service");
  const [locationId, setLocationId] = useState(salon.locations[0]!.id);
  // L7c: the visit's services in order, each with its own add-ons (decision 48).
  const [lines, setLines] = useState<Line[]>([
    { variant_id: "", add_on_ids: [] },
  ]);
  const [artistId, setArtistId] = useState("");
  const [day, setDay] = useState(salon.locations[0]!.today);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [details, setDetails] = useState<Details | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const holdAttempt = useRef<{
    signature: string;
    token: string;
    key: string;
  } | null>(null);
  const confirmAttempt = useRef<{ signature: string; key: string } | null>(
    null,
  );
  const heading = useRef<HTMLHeadingElement>(null);
  const focusLine = useRef<number | null>(null);
  const location = salon.locations.find((l) => l.id === locationId)!;
  const variant = salon.variants.find((v) => v.id === lines[0]!.variant_id);
  const complete = lines.every((line) => line.variant_id);
  const serviceIds = Array.from(
    new Set(
      lines.flatMap((line) =>
        salon.variants
          .filter((v) => v.id === line.variant_id)
          .map((v) => v.service_id),
      ),
    ),
  );
  const selection = selectionOf(locationId, lines, artistId || null);
  useEffect(() => {
    heading.current?.focus();
  }, [step]);
  useEffect(() => {
    // Keyboard users land on the service select a line change concerns.
    if (focusLine.current === null) return;
    document.getElementById(`visit-line-${focusLine.current}`)?.focus();
    focusLine.current = null;
  }, [lines]);
  // Any change of the visit invalidates its quote; a change of services also the specialist.
  function changeLines(next: Line[], services: boolean) {
    setLines(next);
    setQuote(null);
    setSlot(null);
    if (services) setArtistId("");
  }
  function serviceOptions(index: number) {
    const offered = servicesOffered(salon, lines, index);
    return Array.from(new Set(offered.map((v) => v.service_name))).map(
      (name) => (
        <optgroup key={name} label={name}>
          {offered
            .filter((v) => v.service_name === name)
            .map((v) => (
              <option key={v.id} value={v.id}>
                {v.name} · {v.duration_minutes} min
              </option>
            ))}
        </optgroup>
      ),
    );
  }
  function addOns(index: number) {
    const line = lines[index]!;
    return (
      <fieldset className="addons">
        <legend>
          {index === 0 ? "Make it yours" : `Add-ons for service ${index + 1}`}{" "}
          <span>Optional add-ons</span>
        </legend>
        {salon.add_ons.map((a) => {
          const checked = line.add_on_ids.includes(a.id);
          const offered = addOnOffered(salon, lines, index, a.id);
          return (
            <label key={a.id} className="check">
              <input
                type="checkbox"
                disabled={!offered && !checked}
                checked={checked}
                onChange={(e) =>
                  changeLines(
                    lines.map((l, i) =>
                      i !== index
                        ? l
                        : {
                            ...l,
                            add_on_ids: e.target.checked
                              ? [...l.add_on_ids, a.id]
                              : l.add_on_ids.filter((id) => id !== a.id),
                          },
                    ),
                    false,
                  )
                }
              />
              <span>
                {a.name}
                <small>
                  {offered
                    ? `${money(a.price_cents, a.currency)} · +${a.duration_minutes} min`
                    : "Not available with this visit"}
                </small>
              </span>
            </label>
          );
        })}
      </fieldset>
    );
  }
  useEffect(() => {
    if (!booking?.hold_expires_at || booking.status !== "HOLD") return;
    const expiry = booking.hold_expires_at;
    const timer = window.setInterval(
      () =>
        setRemaining(
          Math.max(0, Math.ceil((Date.parse(expiry) - Date.now()) / 1000)),
        ),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [booking]);
  function move(next: Step) {
    setError("");
    setStep(next);
  }
  async function reserve() {
    if (!slot) return;
    const body = {
      ...selection,
      resource_id: slot.resource_id,
      start_at: slot.start_at,
    };
    const signature = JSON.stringify(body);
    if (holdAttempt.current?.signature !== signature)
      holdAttempt.current = {
        signature,
        token: newCapability(),
        key: crypto.randomUUID(),
      };
    const attempt = holdAttempt.current;
    setBusy(true);
    setError("");
    try {
      const held = await api("holds", bookingSchema, body, {
        "Booking-Token": attempt.token,
        "Idempotency-Key": attempt.key,
      });
      if (
        held.status !== "HOLD" ||
        !held.hold_expires_at ||
        Date.parse(held.hold_expires_at) <= Date.now()
      )
        throw new ApiError(
          "HOLD_EXPIRED",
          "The hold expired. Please choose another time.",
        );
      setBooking(held);
      setQuote(held.quote);
      setRemaining(
        Math.ceil((Date.parse(held.hold_expires_at) - Date.now()) / 1000),
      );
      move("details");
    } catch (e) {
      setError(errorMessage(e));
      if (
        e instanceof ApiError &&
        ["SLOT_CONFLICT", "HOLD_EXPIRED"].includes(e.code)
      ) {
        holdAttempt.current = null;
        setSlot(null);
        setStep("time");
      }
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    if (!booking || !details || !holdAttempt.current) return;
    const signature = JSON.stringify(details);
    if (confirmAttempt.current?.signature !== signature)
      confirmAttempt.current = { signature, key: crypto.randomUUID() };
    setBusy(true);
    setError("");
    try {
      const confirmed = await api(
        `bookings/${booking.booking_id}/confirm`,
        bookingSchema,
        details,
        {
          "Booking-Token": holdAttempt.current.token,
          "Idempotency-Key": confirmAttempt.current.key,
        },
      );
      if (confirmed.status !== "CONFIRMED")
        throw new ApiError(
          "INVALID_RESPONSE",
          "Please retry to check your confirmation.",
        );
      setBooking(confirmed);
      move("confirmed");
    } catch (e) {
      setError(errorMessage(e));
      if (
        e instanceof ApiError &&
        ["SLOT_CONFLICT", "HOLD_EXPIRED"].includes(e.code)
      ) {
        holdAttempt.current = null;
        setBooking(null);
        setSlot(null);
        setStep("time");
      }
    } finally {
      setBusy(false);
    }
  }
  const style = salon.branding.accent
    ? ({ "--accent": salon.branding.accent } as CSSProperties)
    : undefined;
  return (
    <div className="studio" style={style}>
      <a className="skip" href="#booking">
        Skip to booking
      </a>
      <header className="masthead">
        {salon.branding.logo_url && (
          <Image
            src={salon.branding.logo_url}
            alt={`${salon.name} logo`}
            width={88}
            height={88}
            unoptimized
          />
        )}
        <span className="studio-name">{salon.name}</span>
        <span className="masthead-note">A moment, just for you</span>
      </header>
      <main id="booking">
        <div className="intro">
          <p className="eyebrow">Reserve your visit</p>
          <h1>
            Your appointment,
            <br />
            thoughtfully arranged.
          </h1>
          <p>Choose what feels right. We’ll take care of the details.</p>
        </div>
        {step !== "confirmed" && (
          <ol className="progress" aria-label="Booking progress">
            {steps.map((s, i) => (
              <li key={s} aria-current={s === step ? "step" : undefined}>
                <span>{String(i + 1).padStart(2, "0")}</span>
                {["Service", "Your time", "Details", "Review"][i]}
              </li>
            ))}
          </ol>
        )}
        <div className="booking-grid">
          <section className="panel" aria-busy={busy}>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            {step === "service" && (
              <>
                <h2 ref={heading} tabIndex={-1}>
                  Begin with a little care.
                </h2>
                <p className="muted">Select your service and finish.</p>
                <label>
                  Location
                  <select
                    aria-label="Location"
                    value={locationId}
                    onChange={(e) => {
                      setLocationId(e.target.value);
                      setArtistId("");
                      setDay(
                        salon.locations.find((l) => l.id === e.target.value)!
                          .today,
                      );
                    }}
                  >
                    {salon.locations.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Service and variant
                  <select
                    id="visit-line-0"
                    aria-label="Service and variant"
                    value={lines[0]!.variant_id}
                    onChange={(e) =>
                      changeLines(
                        lines.map((l, i) =>
                          i === 0
                            ? { variant_id: e.target.value, add_on_ids: [] }
                            : l,
                        ),
                        true,
                      )
                    }
                  >
                    <option value="">Choose a service</option>
                    {serviceOptions(0)}
                  </select>
                </label>
                {variant && (
                  <>
                    <p className="service-price">
                      {money(variant.price_cents, variant.currency)}{" "}
                      <span> / {variant.duration_minutes} min</span>
                    </p>
                    {addOns(0)}
                  </>
                )}
                {lines.slice(1).map((line, k) => {
                  const index = k + 1;
                  const name = `Service ${index + 1}`;
                  return (
                    <div className="visit-line" key={index}>
                      <label>
                        {name}
                        <select
                          id={`visit-line-${index}`}
                          aria-label={name}
                          value={line.variant_id}
                          onChange={(e) =>
                            changeLines(
                              lines.map((l, i) =>
                                i === index
                                  ? {
                                      variant_id: e.target.value,
                                      add_on_ids: [],
                                    }
                                  : l,
                              ),
                              true,
                            )
                          }
                        >
                          <option value="">Choose a service</option>
                          {serviceOptions(index)}
                        </select>
                      </label>
                      {line.variant_id && addOns(index)}
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => {
                          focusLine.current = index - 1;
                          changeLines(
                            lines.filter((_, i) => i !== index),
                            true,
                          );
                        }}
                      >
                        Remove service {index + 1}
                      </button>
                    </div>
                  );
                })}
                {variant && lines.length <= MAX_EXTRA_LINES && (
                  <p>
                    <button
                      type="button"
                      className="secondary"
                      disabled={!complete}
                      onClick={() => {
                        focusLine.current = lines.length;
                        changeLines(
                          [...lines, { variant_id: "", add_on_ids: [] }],
                          true,
                        );
                      }}
                    >
                      Add another service
                    </button>
                  </p>
                )}
                <button
                  disabled={!variant || !complete}
                  onClick={() => move("time")}
                >
                  Continue to times
                </button>
              </>
            )}
            {step === "time" && (
              <>
                <h2 ref={heading} tabIndex={-1}>
                  A time just for you.
                </h2>
                <p className="muted">
                  All times are shown in {location.timezone}.
                </p>
                <label>
                  Artist
                  <select
                    aria-label="Artist"
                    value={artistId}
                    disabled={busy}
                    onChange={(e) => {
                      setArtistId(e.target.value);
                      setSlot(null);
                    }}
                  >
                    <option value="">Any available artist</option>
                    {/* L7c: one specialist serves every service of the visit. */}
                    {servingAll(salon.artists, locationId, serviceIds).map(
                      (a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ),
                    )}
                  </select>
                </label>
                <label>
                  Date
                  <input
                    type="date"
                    value={day}
                    min={location.today}
                    max={location.last_day}
                    disabled={busy}
                    onChange={(e) => {
                      setDay(e.target.value);
                      setSlot(null);
                    }}
                  />
                </label>
                <Times
                  selection={selection}
                  day={day}
                  salon={salon}
                  slot={slot}
                  disabled={busy}
                  refresh={error}
                  onSelect={setSlot}
                  onQuote={setQuote}
                />
                <div className="actions">
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => move("service")}
                  >
                    Back
                  </button>
                  <button
                    disabled={!slot || busy}
                    onClick={() => void reserve()}
                  >
                    {busy ? "Reserving…" : "Continue to details"}
                  </button>
                </div>
              </>
            )}
            {step === "details" && (
              <>
                <h2 ref={heading} tabIndex={-1}>
                  A few personal details.
                </h2>
                <HoldNotice remaining={remaining} />
                <DetailsForm
                  initial={details}
                  cancellation={salon.cancellation.summary}
                  onSubmit={(data) => {
                    setDetails(data);
                    move("review");
                  }}
                />
                <button className="secondary" onClick={() => move("time")}>
                  Choose another time
                </button>
              </>
            )}
            {step === "review" && booking && details && (
              <>
                <h2 ref={heading} tabIndex={-1}>
                  One last look.
                </h2>
                <HoldNotice remaining={remaining} />
                <Appointment
                  booking={booking}
                  salon={salon}
                  timezone={location.timezone}
                />
                <dl className="review-details">
                  <dt>Guest</dt>
                  <dd>{details.name}</dd>
                  <dt>Email</dt>
                  <dd>{details.email}</dd>
                  <dt>Phone</dt>
                  <dd>{details.phone}</dd>
                </dl>
                <p className="fine">{salon.cancellation.summary}</p>
                <div className="actions">
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => move("details")}
                  >
                    Edit details
                  </button>
                  <button disabled={busy} onClick={() => void confirm()}>
                    {busy ? "Confirming…" : "Confirm booking"}
                  </button>
                </div>
                {remaining === 0 && (
                  <button
                    className="secondary"
                    onClick={() => {
                      holdAttempt.current = null;
                      setBooking(null);
                      setSlot(null);
                      move("time");
                    }}
                  >
                    Choose a new time
                  </button>
                )}
              </>
            )}
            {step === "confirmed" && booking && (
              <>
                <p className="eyebrow">Appointment confirmed</p>
                <h2 ref={heading} tabIndex={-1}>
                  You’re booked.
                </h2>
                <p>We look forward to welcoming you.</p>
                <Appointment
                  booking={booking}
                  salon={salon}
                  timezone={location.timezone}
                />
                <p className="fine">
                  Keep this booking reference for the studio.
                </p>
                <p className="reference" data-testid="booking-reference">
                  {booking.booking_id}
                </p>
                <p className="fine">{salon.cancellation.summary}</p>
              </>
            )}
          </section>
          <Summary quote={quote} />
        </div>
      </main>
      <footer>Time well spent. Care thoughtfully given.</footer>
    </div>
  );
}
