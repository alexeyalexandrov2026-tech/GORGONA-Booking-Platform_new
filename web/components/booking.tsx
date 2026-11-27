"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AmarkalLogo } from "./amarkal-logo";
import { api, ApiError, errorMessage } from "../lib/api";
import { bootstrapSchema, type Bootstrap } from "../lib/contracts";
import { Journey } from "./journey";
import "../app/us-release-v2.css";

interface DemoService {
  readonly id: string;
  readonly name: string;
  readonly vessel: string;
  readonly duration: string;
  readonly price: string;
  readonly deposit: string;
}

const DEMO_SERVICES: readonly DemoService[] = [
  {
    id: "sunset",
    name: "Sunset Yacht Charter",
    vessel: "Aurora 42′ · Capt. M. Reyes",
    duration: "3 hours",
    price: "$1,450",
    deposit: "$435 (30% deposit)",
  },
  {
    id: "halfday",
    name: "Half-Day Bay Cruise",
    vessel: "Sea Glass · Capt. J. Park",
    duration: "4 hours",
    price: "$1,890",
    deposit: "$567 (30% deposit)",
  },
  {
    id: "fullday",
    name: "Full-Day Coastal Charter",
    vessel: "Nomad 38′ · Capt. E. Rivera",
    duration: "8 hours",
    price: "$3,400",
    deposit: "$1,020 (30% deposit)",
  },
];

const DEMO_SLOTS = [
  "10:00 AM EDT",
  "1:30 PM EDT",
  "5:30 PM EDT",
  "6:00 PM EDT",
] as const;

function DemoClientPortal() {
  const [serviceId, setServiceId] = useState<string>(DEMO_SERVICES[0]!.id);
  const [slot, setSlot] = useState<string>(DEMO_SLOTS[3]!);
  const [guestName, setGuestName] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  const selected =
    DEMO_SERVICES.find((item) => item.id === serviceId) ?? DEMO_SERVICES[0]!;

  return (
    <div className="management-shell">
      <header className="mgmt-header">
        <div className="mgmt-brand-area">
          <Link href="/" className="mgmt-brand">
            <AmarkalLogo variant="light" height={20} />
          </Link>
        </div>
        <div className="mgmt-header-actions">
          <Link href="/" className="mgmt-nav-link">
            Home
          </Link>
          <Link href="/auth/signin/" className="mgmt-nav-link">
            Sign in
          </Link>
          <Link href="/onboarding/" className="mgmt-nav-link active">
            Create your business
          </Link>
        </div>
      </header>
      <main
        id="main-content"
        className="mgmt-main"
        style={{ maxWidth: "860px", margin: "2rem auto" }}
      >
        <p className="hold-note" role="note" style={{ marginTop: 0 }}>
          <strong>Interactive Client Portal Demo · Harbor Yacht Co.</strong> —
          Illustrative US booking storefront powered by AMARKAL Platform (0%
          commission, direct Stripe US checkout).
        </p>

        <section className="usr-card" aria-labelledby="demo-portal-title">
          <p className="eyebrow" style={{ marginTop: 0 }}>
            Harbor Yacht Co. · Miami Marina · America/New_York
          </p>
          <h1
            id="demo-portal-title"
            style={{ fontSize: "clamp(1.75rem, 3.5vw, 2.35rem)", marginTop: 8 }}
          >
            Reserve your charter online.
          </h1>
          <p className="usr-muted">
            Every AMARKAL workspace gets a branded, embeddable client portal on
            your own domain with live availability, smart waitlist, AI booking
            assistant, and direct Stripe payouts.
          </p>

          <h2 style={{ marginTop: 24 }}>1. Choose a service</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "12px",
            }}
          >
            {DEMO_SERVICES.map((svc) => {
              const active = svc.id === selected.id;
              return (
                <button
                  key={svc.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    setServiceId(svc.id);
                    setConfirmed(false);
                  }}
                  style={{
                    textAlign: "left",
                    padding: "16px",
                    borderRadius: "14px",
                    border: active
                      ? "2px solid #0B0C10"
                      : "1px solid var(--line, #e6e8ee)",
                    background: active ? "#F4F5F8" : "#FFFFFF",
                    color: "#0A0A0C",
                    display: "grid",
                    gap: "6px",
                    cursor: "pointer",
                  }}
                >
                  <strong style={{ fontSize: "1rem" }}>{svc.name}</strong>
                  <span style={{ fontSize: "0.85rem", color: "#5A606E" }}>
                    {svc.vessel} · {svc.duration}
                  </span>
                  <span
                    style={{
                      fontSize: "0.95rem",
                      fontWeight: 700,
                      color: "#0A0A0C",
                    }}
                  >
                    {svc.price} USD{" "}
                    <span
                      style={{
                        fontWeight: 400,
                        fontSize: "0.82rem",
                        color: "#5A606E",
                      }}
                    >
                      · {svc.deposit}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          <h2 style={{ marginTop: 24 }}>2. Pick a live time slot (Saturday)</h2>
          <div className="usr-inline" role="group" aria-label="Available slots">
            {DEMO_SLOTS.map((time) => (
              <button
                key={time}
                type="button"
                className={slot === time ? "" : "secondary"}
                aria-pressed={slot === time}
                onClick={() => {
                  setSlot(time);
                  setConfirmed(false);
                }}
              >
                {time}
              </button>
            ))}
          </div>

          <h2 style={{ marginTop: 24 }}>3. Preview instant reservation</h2>
          <div className="usr-grid" style={{ alignItems: "end" }}>
            <label style={{ marginBottom: 0 }}>
              Guest name (sample)
              <input
                type="text"
                value={guestName}
                placeholder="Jordan Taylor"
                onChange={(e) => {
                  setGuestName(e.target.value);
                  setConfirmed(false);
                }}
              />
            </label>
            <button type="button" onClick={() => setConfirmed(true)}>
              Reserve demo slot · {slot}
            </button>
          </div>

          {confirmed && (
            <div
              className="hold-note"
              role="status"
              style={{
                marginTop: 18,
                background: "#E9F6EE",
                borderColor: "#93D0AD",
                color: "#144B2B",
              }}
            >
              <strong>Demo hold created:</strong> {selected.name} (
              {selected.vessel}) on Saturday at {slot} for{" "}
              {guestName.trim() || "your guest"} — {selected.price} USD with{" "}
              <strong>0% AMARKAL commission</strong>. No real charge was made.
            </div>
          )}

          <div
            className="usr-inline"
            style={{
              marginTop: 28,
              paddingTop: 20,
              borderTop: "1px solid var(--line, #e6e8ee)",
              justifyContent: "space-between",
            }}
          >
            <div>
              <strong>Want this portal for your US business?</strong>
              <p className="usr-muted" style={{ margin: "4px 0 0" }}>
                Draft services, pricing, resources, and hours in 60 seconds with
                AI Business Architect — no sign-up required to preview.
              </p>
            </div>
            <Link href="/onboarding/" className="button">
              Launch your own portal →
            </Link>
          </div>
        </section>
      </main>
      <footer className="mgmt-footer">
        <span>© 2026 Alexey AAA Logistics LLC — AMARKAL Platform</span>
        <Link href="/">Home</Link>
        <Link href="/onboarding/">Create business</Link>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}

export function BookingEntry() {
  const [demoMode, setDemoMode] = useState(false);
  const [result, setResult] = useState<Bootstrap | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const isDemo =
      typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("demo") === "1";
    if (isDemo || demoMode) {
      void Promise.resolve().then(() => {
        if (!controller.signal.aborted) setDemoMode(true);
      });
      return () => controller.abort();
    }
    api("bootstrap", bootstrapSchema, undefined, undefined, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setResult(data);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted)
          setError(
            e instanceof ApiError
              ? e
              : new ApiError("UNKNOWN", errorMessage(e)),
          );
      });
    return () => controller.abort();
  }, [attempt, demoMode]);

  if (demoMode) return <DemoClientPortal />;

  if (error)
    return (
      <div className="management-shell">
        <header className="mgmt-header">
          <div className="mgmt-brand-area">
            <Link href="/" className="mgmt-brand">
              <AmarkalLogo variant="light" height={20} />
            </Link>
          </div>
          <div className="mgmt-header-actions">
            <Link href="/" className="mgmt-nav-link">
              Home
            </Link>
            <Link href="/onboarding/" className="mgmt-nav-link">
              Create business
            </Link>
          </div>
        </header>
        <main className="welcome" id="main-content">
          <p className="eyebrow">AMARKAL Client Portal</p>
          <h1>
            {error.code === "TENANT_NOT_FOUND"
              ? "Online booking is not available yet."
              : "We can’t arrange an appointment right now."}
          </h1>
          <p>
            {error.code === "TENANT_NOT_FOUND"
              ? "This domain is not linked to an active business storefront yet. Preview a live interactive client portal demo or launch your own US business portal in 60 seconds."
              : error.message}
          </p>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "12px",
              marginTop: "18px",
            }}
          >
            {error.code === "TENANT_NOT_FOUND" ? (
              <>
                <button type="button" onClick={() => setDemoMode(true)}>
                  Preview interactive demo
                </button>
                <Link href="/onboarding/" className="secondary button">
                  Create your business →
                </Link>
              </>
            ) : null}
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setError(null);
                setAttempt((x) => x + 1);
              }}
            >
              Try again
            </button>
          </div>
        </main>
      </div>
    );
  if (!result)
    return (
      <main className="welcome" aria-busy="true">
        <p role="status">Loading booking portal…</p>
      </main>
    );
  if (!result.variants.length || !result.locations.length)
    return (
      <main className="welcome">
        <h1>Appointments are coming soon.</h1>
        <p>This business is still preparing its bookable services.</p>
      </main>
    );
  return <Journey salon={result} />;
}
