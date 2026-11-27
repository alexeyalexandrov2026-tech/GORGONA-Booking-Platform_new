"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AmarkalLogo } from "./amarkal-logo";
import { api, ApiError, errorMessage } from "../lib/api";
import { bootstrapSchema, type Bootstrap } from "../lib/contracts";
import { Journey } from "./journey";
import "../app/us-release-v2.css";

interface DemoWorkflowItem {
  readonly id: string;
  readonly name: string;
  readonly detail: string;
  readonly duration: string;
  readonly amount: string;
  readonly terms: string;
}

interface DemoIndustryScenario {
  readonly id: string;
  readonly label: string;
  readonly company: string;
  readonly meta: string;
  readonly headline: string;
  readonly summary: string;
  readonly modules: readonly string[];
  readonly items: readonly DemoWorkflowItem[];
  readonly windows: readonly string[];
  readonly counterpartPlaceholder: string;
  readonly actionLabel: string;
  readonly resultPrefix: string;
}

const DEMO_SCENARIOS: readonly DemoIndustryScenario[] = [
  {
    id: "freight",
    label: "Freight & Logistics",
    company: "Apex Freight LLC",
    meta: "NAICS 48–49 · Dallas Hub · America/Chicago",
    headline: "Dispatch, load orders & FIN-03 billing.",
    summary:
      "Manage carrier fleets, shipper counterparties, rate confirmations, proof of delivery (POD), double-entry USD invoices, and dock scheduling from one Business OS.",
    modules: [
      "Transport & Dispatch",
      "Counterparties",
      "Documents & POD",
      "FIN-03 Ledger",
      "Workforce",
    ],
    items: [
      {
        id: "dal-atl",
        name: "53′ Dry Van · DAL → ATL",
        detail: "Unit #402 · Driver D. Morales",
        duration: "Next-day linehaul",
        amount: "$2,850",
        terms: "Net-15 FIN-03 invoice",
      },
      {
        id: "mia-clt",
        name: "Temp-Controlled Reefer · MIA → CLT",
        detail: "Reefer #09 · Continuous temp log",
        duration: "24h corridor",
        amount: "$3,420",
        terms: "ACH / Wire · 0% fee",
      },
      {
        id: "hou-aus",
        name: "Dedicated Flatbed · HOU → AUS",
        detail: "Flatbed #4 · Permit & tie-down",
        duration: "Same-day",
        amount: "$1,180",
        terms: "Direct Stripe / ACH",
      },
    ],
    windows: [
      "08:00 AM CT Dock",
      "11:30 AM CT Dock",
      "02:00 PM CT Dock",
      "05:00 PM CT Dock",
    ],
    counterpartPlaceholder: "Northstar Manufacturing Inc.",
    actionLabel: "Create sample dispatch request",
    resultPrefix: "Demo dispatch & FIN-03 draft prepared",
  },
  {
    id: "construction",
    label: "Construction & Field",
    company: "Meridian Build & Field LLC",
    meta: "NAICS 23 · Austin, TX · America/Chicago",
    headline: "Estimates, crew work orders & milestone acceptance.",
    summary:
      "Track general and subcontractor work, material cost control, customer change orders, versioned contracts, and milestone pay applications under strict tenant isolation.",
    modules: [
      "Construction & Acceptance",
      "Contracts & Change Orders",
      "Inventory & Materials",
      "FIN-03 Billing",
      "Crew Shifts",
    ],
    items: [
      {
        id: "hvac-comm",
        name: "Commercial HVAC Commissioning",
        detail: "Crew Alpha · 3 certified techs",
        duration: "Full day",
        amount: "$4,600",
        terms: "Milestone 1 acceptance",
      },
      {
        id: "panel-up",
        name: "400A Electrical Panel Upgrade",
        detail: "Master Electrician + Permit pkg",
        duration: "6 hours",
        amount: "$3,250",
        terms: "50% deposit · 0% fee",
      },
      {
        id: "site-audit",
        name: "Structural Site Inspection & Scope",
        detail: "Project Lead · Signed PDF report",
        duration: "2 hours",
        amount: "$450",
        terms: "Direct USD invoice",
      },
    ],
    windows: ["07:30 AM CT", "10:00 AM CT", "01:00 PM CT", "03:30 PM CT"],
    counterpartPlaceholder: "Brazos Retail Holdings LLC",
    actionLabel: "Create sample work order",
    resultPrefix: "Demo work order & estimate logged",
  },
  {
    id: "property",
    label: "Property & Commercial",
    company: "Mercer Commercial Spaces",
    meta: "NAICS 53 · New York, NY · America/New_York",
    headline: "Asset management, leases & maintenance SLA.",
    summary:
      "Operate commercial or residential portfolios with tenant records, attested lease agreements, vendor maintenance tickets, recurring USD billing, and accounting exports.",
    modules: [
      "Property & Leases",
      "Maintenance Tickets",
      "Counterparties",
      "Double-Entry Ledger",
      "Client Portal",
    ],
    items: [
      {
        id: "suite-4a",
        name: "Suite 4A · Commercial Lease Onboarding",
        detail: "2,400 sq ft · Attested agreement v3",
        duration: "12-month term",
        amount: "$4,800",
        terms: "Monthly ACH · 0% fee",
      },
      {
        id: "hvac-sla",
        name: "Preventive Building Maintenance",
        detail: "Verified vendor dispatch · SLA 4h",
        duration: "Half day",
        amount: "$890",
        terms: "Vendor bill + FIN-03",
      },
      {
        id: "boardroom",
        name: "Executive Floor Tenant Walkthrough",
        detail: "Property Manager · Checklist",
        duration: "90 min",
        amount: "$0",
        terms: "Included in portfolio",
      },
    ],
    windows: ["09:00 AM ET", "11:00 AM ET", "02:30 PM ET", "04:30 PM ET"],
    counterpartPlaceholder: "Hudson Advisory Partners",
    actionLabel: "Create sample property ticket",
    resultPrefix: "Demo property operation recorded",
  },
  {
    id: "rental",
    label: "Equipment & Fleet Rental",
    company: "Harbor Fleet & Equipment Co.",
    meta: "NAICS 53 · Miami, FL · America/New_York",
    headline: "Asset availability, contracts & optional booking portal.",
    summary:
      "Coordinate high-value assets, crew shifts, refundable deposits, inspection logs, and an optional customer-facing booking portal on your own brand domain.",
    modules: [
      "Rental & Fleet",
      "Optional Client Portal",
      "Agreements & Deposits",
      "Crew Schedules",
      "Stripe US (0% fee)",
    ],
    items: [
      {
        id: "sunset",
        name: "Aurora 42′ Vessel Charter",
        detail: "Capt. M. Reyes · Crew + safety log",
        duration: "3 hours",
        amount: "$1,450",
        terms: "$435 (30% deposit)",
      },
      {
        id: "halfday",
        name: "Sea Glass Half-Day Rental",
        detail: "Capt. J. Park · Fuel & dockage",
        duration: "4 hours",
        amount: "$1,890",
        terms: "$567 (30% deposit)",
      },
      {
        id: "fullday",
        name: "Nomad 38′ Full-Day Fleet Allocation",
        detail: "Capt. E. Rivera · Full manifest",
        duration: "8 hours",
        amount: "$3,400",
        terms: "$1,020 (30% deposit)",
      },
    ],
    windows: ["10:00 AM ET", "01:30 PM ET", "05:30 PM ET", "06:00 PM ET"],
    counterpartPlaceholder: "Jordan Taylor",
    actionLabel: "Create sample asset reservation",
    resultPrefix: "Demo asset hold & contract draft created",
  },
];

function MultiIndustryDemo() {
  const [scenarioId, setScenarioId] = useState<string>(DEMO_SCENARIOS[0]!.id);
  const scenario =
    DEMO_SCENARIOS.find((s) => s.id === scenarioId) ?? DEMO_SCENARIOS[0]!;
  const [itemId, setItemId] = useState<string>(scenario.items[0]!.id);
  const [windowSlot, setWindowSlot] = useState<string>(scenario.windows[0]!);
  const [counterpart, setCounterpart] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  const selected =
    scenario.items.find((item) => item.id === itemId) ?? scenario.items[0]!;

  const switchScenario = (next: DemoIndustryScenario) => {
    setScenarioId(next.id);
    setItemId(next.items[0]!.id);
    setWindowSlot(next.windows[0]!);
    setCounterpart("");
    setConfirmed(false);
  };

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
        style={{ maxWidth: "920px", margin: "2rem auto" }}
      >
        <p className="hold-note" role="note" style={{ marginTop: 0 }}>
          <strong>Interactive Business OS Demo (4 Sample Industries)</strong> —
          AMARKAL Platform is a complete US Business Operating System across 39
          NAICS industries. Online client booking is just one optional module
          alongside operations, counterparties, contracts, workforce, and
          double-entry USD finance.
        </p>

        <div
          role="tablist"
          aria-label="Choose a demonstration industry"
          className="usr-tablist"
          style={{ marginBottom: "18px" }}
        >
          {DEMO_SCENARIOS.map((sc) => (
            <button
              key={sc.id}
              type="button"
              role="tab"
              className="usr-tab"
              aria-selected={sc.id === scenario.id}
              onClick={() => switchScenario(sc)}
            >
              {sc.label}
            </button>
          ))}
        </div>

        <section className="usr-card" aria-labelledby="demo-portal-title">
          <p className="eyebrow" style={{ marginTop: 0 }}>
            {scenario.company} · {scenario.meta}
          </p>
          <h1
            id="demo-portal-title"
            style={{ fontSize: "clamp(1.75rem, 3.5vw, 2.35rem)", marginTop: 8 }}
          >
            {scenario.headline}
          </h1>
          <p className="usr-muted">{scenario.summary}</p>

          <div
            className="usr-inline"
            style={{ marginBottom: "20px", gap: "8px" }}
            aria-label="Active Business OS modules in this demo"
          >
            {scenario.modules.map((mod) => (
              <span key={mod} className="usr-badge">
                {mod}
              </span>
            ))}
          </div>

          <h2 style={{ marginTop: 20 }}>
            1. Select a sample operation or order
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "12px",
            }}
          >
            {scenario.items.map((item) => {
              const active = item.id === selected.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => {
                    setItemId(item.id);
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
                  <strong style={{ fontSize: "1rem" }}>{item.name}</strong>
                  <span style={{ fontSize: "0.85rem", color: "#5A606E" }}>
                    {item.detail} · {item.duration}
                  </span>
                  <span
                    style={{
                      fontSize: "0.95rem",
                      fontWeight: 700,
                      color: "#0A0A0C",
                    }}
                  >
                    {item.amount} USD{" "}
                    <span
                      style={{
                        fontWeight: 400,
                        fontSize: "0.82rem",
                        color: "#5A606E",
                      }}
                    >
                      · {item.terms}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>

          <h2 style={{ marginTop: 24 }}>2. Choose an operational window</h2>
          <div
            className="usr-inline"
            role="group"
            aria-label="Operational windows"
          >
            {scenario.windows.map((time) => (
              <button
                key={time}
                type="button"
                className={windowSlot === time ? "" : "secondary"}
                aria-pressed={windowSlot === time}
                onClick={() => {
                  setWindowSlot(time);
                  setConfirmed(false);
                }}
              >
                {time}
              </button>
            ))}
          </div>

          <h2 style={{ marginTop: 24 }}>
            3. Preview end-to-end Business OS record
          </h2>
          <div className="usr-grid" style={{ alignItems: "end" }}>
            <label style={{ marginBottom: 0 }}>
              Counterparty / client name (sample)
              <input
                type="text"
                value={counterpart}
                placeholder={scenario.counterpartPlaceholder}
                onChange={(e) => {
                  setCounterpart(e.target.value);
                  setConfirmed(false);
                }}
              />
            </label>
            <button type="button" onClick={() => setConfirmed(true)}>
              {scenario.actionLabel}
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
              <strong>{scenario.resultPrefix}:</strong> {selected.name} (
              {selected.detail}) for {windowSlot} —{" "}
              {counterpart.trim() || scenario.counterpartPlaceholder} ·{" "}
              {selected.amount} USD ({selected.terms}, 0% AMARKAL platform
              commission). Illustrative demo only; no live transaction was
              created.
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
              <strong>Configure AMARKAL for your US organization</strong>
              <p className="usr-muted" style={{ margin: "4px 0 0" }}>
                Draft modules, catalog, resources, and policies across all 39
                NAICS industries with AI Business Architect — no sign-up
                required to preview.
              </p>
            </div>
            <Link href="/onboarding/" className="button">
              Draft your workspace →
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

  if (demoMode) return <MultiIndustryDemo />;

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
