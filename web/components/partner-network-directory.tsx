"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type PartnerTrack =
  | "all"
  | "implementation_migration"
  | "cpa_finance_holding"
  | "industrial_mrp_iot"
  | "isv_plugin_mcp";

interface PracticeListing {
  readonly slug: string;
  readonly practiceName: string;
  readonly partnerTier: string;
  readonly track: Exclude<PartnerTrack, "all">;
  readonly regionLabel: string;
  readonly statesCovered: readonly string[];
  readonly naicsSpecialties: readonly string[];
  readonly erpMigrations: readonly string[];
  readonly deliverables: readonly string[];
  readonly availability: string;
}

const PRACTICE_LISTINGS: readonly PracticeListing[] = [
  {
    slug: "amarkal-direct-midwest-freight",
    practiceName:
      "AMARKAL Direct Implementation Desk — Freight, 3PL & Logistics",
    partnerTier: "Official AMARKAL Solutions Architecture",
    track: "implementation_migration",
    regionLabel: "Midwest & Nationwide US",
    statesCovered: ["IL", "OH", "MI", "IN", "WI", "Nationwide"],
    naicsSpecialties: [
      "484 Freight Trucking",
      "488 Freight Brokerage",
      "493 Warehousing",
    ],
    erpMigrations: ["QuickBooks", "Odoo", "NetSuite", "Excel / TMS CSV"],
    deliverables: [
      "Turnkey 48-hour CSV & OFX data migration",
      "US Payroll (FLSA/CA/Union) + Stripe 0% fee checkout setup",
      "Predictive EAM fleet telemetry & preventive work orders",
    ],
    availability: "Accepting US Mid-Market Implementations",
  },
  {
    slug: "amarkal-finance-holding-practice",
    practiceName: "Multi-Entity Holding, US GAAP & CPA Consolidation Practice",
    partnerTier: "Certified ERP & CPA Advisory Track",
    track: "cpa_finance_holding",
    regionLabel: "Northeast & Cross-Border (US / CA / EU)",
    statesCovered: ["NY", "NJ", "DE", "MA", "TX", "Cross-Border"],
    naicsSpecialties: [
      "All 39 NAICS",
      "5412 CPA & Advisory",
      "Multi-Entity Holdings",
    ],
    erpMigrations: [
      "NetSuite OneWorld",
      "QuickBooks Online",
      "Zoho Books",
      "Xero",
    ],
    deliverables: [
      "Double-entry FIN-03 chart of accounts & audit setup",
      "US Bank Feeds (Plaid BYOK / OFX) & Human-in-the-Loop reconciliation",
      "Holding consolidation, Due To/Due From eliminations & NCI reporting",
    ],
    availability: "Founding CPA Partner Slots Open",
  },
  {
    slug: "amarkal-industrial-mrp-iot-pod",
    practiceName:
      "Industrial MRP II, Construction & Equipment Fleet Integrators",
    partnerTier: "Vertical Systems Integrator Track",
    track: "industrial_mrp_iot",
    regionLabel: "South, Gulf & West Coast US",
    statesCovered: ["TX", "CA", "FL", "GA", "AZ", "WA"],
    naicsSpecialties: [
      "31-33 Manufacturing",
      "23 Construction",
      "532 Equipment Rental",
    ],
    erpMigrations: [
      "Odoo Manufacturing",
      "Monday.com",
      "Procore",
      "Legacy On-Prem ERP",
    ],
    deliverables: [
      "Multi-level BOM explosion & atomic raw-material reservations",
      "IoT sensor webhook & Samsara/Motive ELD maintenance rules",
      "Executive BI Gantt timelines & Board Pack reporting",
    ],
    availability: "Accepting Q4/Q1 Deployment Scoping",
  },
  {
    slug: "amarkal-isv-sdk-mcp-engineering",
    practiceName:
      "Custom Plugin SDK (amarkal-plugin.json) & Remote MCP Engineering",
    partnerTier: "Verified ISV & Developer Partner Track",
    track: "isv_plugin_mcp",
    regionLabel: "Remote US & Global Engineering",
    statesCovered: ["CA", "NY", "WA", "TX", "IL", "Global Remote"],
    naicsSpecialties: [
      "488 Customs & EDI",
      "62 Healthcare FHIR",
      "44-45 Omnichannel Retail",
    ],
    erpMigrations: [
      "Custom API Bridges",
      "X12 EDI 850/810",
      "HL7 FHIR",
      "Remote MCP Agents",
    ],
    deliverables: [
      "Custom amarkal-plugin.json manifest design & SSRF security audit",
      "HMAC-SHA256 webhook bridges & AES-256-GCM BYOK vault integration",
      "Autonomous MCP tool workflows with strict $0.00 HITL guardrails",
    ],
    availability: "Open to Agencies & ISV Teams",
  },
];

const CERTIFICATION_TIERS = [
  {
    code: "TIER 01 · ASSOCIATE",
    title: "AMARKAL Certified Implementation Specialist",
    audience: "Independent ERP consultants, bookkeepers & operations agencies",
    curriculum: [
      "39 NAICS Blueprint activation & No-Code Workspace Studio",
      "1-Click CSV Migration Wizard & Sample Enterprise Sandbox workflows",
      "US Bank Feeds (OFX/QFX/CSV/Plaid BYOK) & Executive BI dashboards",
    ],
    benefits: [
      "Multi-client Agency Workspace Switcher via native Delegations",
      "Listed in the public AMARKAL Certified Partner Directory",
      "Direct engineering escalation channel for client launches",
    ],
  },
  {
    code: "TIER 02 · FINANCE & HOLDING",
    title: "Certified Multi-Entity & CPA Advisory Partner",
    audience: "US CPA firms, fractional CFO practices & NetSuite migrators",
    curriculum: [
      "Double-Entry FIN-03 Ledger, 3-Way PO Match & Stripe 0% reconciliation",
      "Holding Multi-Entity Consolidation, Due To/Due From eliminations & NCI",
      "US Payroll Compliance (FLSA, CA §510, Union CBA) & Multi-Currency FX",
    ],
    benefits: [
      "Scoped client delegation without sharing business owner passwords",
      "1-click Board Pack CSV & consolidated US GAAP / IFRS exports",
      "Co-marketing placement on US vertical & migration comparison pages",
    ],
  },
  {
    code: "TIER 03 · ISV & ARCHITECT",
    title: "AMARKAL Plugin SDK & MCP Systems Integrator",
    audience: "Systems integrators, EDI/IoT consultancies & vertical ISVs",
    curriculum: [
      "PostgreSQL 18 FORCE RLS security model & Clean Core plugin boundaries",
      "Building & publishing verified amarkal-plugin.json Marketplace extensions",
      "Industrial MRP II, Predictive EAM IoT webhooks & 11-tool Native MCP",
    ],
    benefits: [
      "Verified Publisher badge inside AMARKAL Plugin Marketplace",
      "0% revenue-share toll booth on agency retainers and implementations",
      "Early access to upcoming SDK scopes & enterprise webhook schemas",
    ],
  },
] as const;

const TRACK_LABELS: readonly { id: PartnerTrack; label: string }[] = [
  { id: "all", label: "All Tracks" },
  { id: "implementation_migration", label: "ERP Implementation & Migration" },
  { id: "cpa_finance_holding", label: "CPA & Multi-Entity Holding" },
  { id: "industrial_mrp_iot", label: "Industrial MRP II & IoT" },
  { id: "isv_plugin_mcp", label: "ISV Plugin SDK & MCP" },
];

export function PartnerNetworkDirectory() {
  const [trackFilter, setTrackFilter] = useState<PartnerTrack>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Partner application form state
  const [companyName, setCompanyName] = useState("");
  const [contactName, setContactName] = useState("");
  const [workEmail, setWorkEmail] = useState("");
  const [usState, setUsState] = useState("IL");
  const [partnerTrack, setPartnerTrack] = useState<
    Exclude<PartnerTrack, "all">
  >("implementation_migration");
  const [naicsFocus, setNaicsFocus] = useState("");
  const [teamSize, setTeamSize] = useState("5-25");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [experienceSummary, setExperienceSummary] = useState("");
  const [honeypot, setHoneypot] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<{
    referenceId: string;
    message: string;
  } | null>(null);

  const filteredListings = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return PRACTICE_LISTINGS.filter((item) => {
      if (trackFilter !== "all" && item.track !== trackFilter) return false;
      if (!q) return true;
      const blob = [
        item.practiceName,
        item.partnerTier,
        item.regionLabel,
        ...item.statesCovered,
        ...item.naicsSpecialties,
        ...item.erpMigrations,
        ...item.deliverables,
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }, [trackFilter, searchQuery]);

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      const res = await fetch("/v1/public/partners/apply", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          company_name: companyName.trim(),
          contact_name: contactName.trim(),
          work_email: workEmail.trim(),
          us_state: usState.trim(),
          partner_track: partnerTrack,
          naics_focus: naicsFocus.trim(),
          team_size: teamSize,
          website_url: websiteUrl.trim(),
          experience_summary: experienceSummary.trim(),
          website: honeypot,
        }),
      });
      const payload = (await res.json().catch(() => null)) as {
        reference_id?: string;
        message?: string;
        detail?: string;
      } | null;
      if (!res.ok) {
        setSubmitError(
          payload?.detail ??
            `Unable to submit application (HTTP ${res.status}).`,
        );
        return;
      }
      setSubmitSuccess({
        referenceId: payload?.reference_id ?? "PARTNER-OK",
        message:
          payload?.message ??
          "Application received by AMARKAL Partner Enablement Desk.",
      });
      setCompanyName("");
      setContactName("");
      setWorkEmail("");
      setNaicsFocus("");
      setWebsiteUrl("");
      setExperienceSummary("");
    } catch {
      setSubmitError(
        "Network error while submitting application. Please retry.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="usr-stack">
      <section className="usr-card" aria-labelledby="partner-dir-h">
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "12px",
            marginBottom: "16px",
          }}
        >
          <div>
            <h2 id="partner-dir-h" style={{ marginBottom: "4px" }}>
              US Implementation Practices &amp; Certified Tracks
            </h2>
            <p className="usr-muted" style={{ margin: 0 }}>
              Filter by US state, NAICS vertical, or legacy ERP migration path
              (NetSuite, Odoo, QuickBooks, Zoho, Monday).
            </p>
          </div>
          <label style={{ margin: 0, flex: "1 1 260px", maxWidth: "360px" }}>
            <span className="sr-only">
              Search partner directory by state, NAICS, or ERP
            </span>
            <input
              type="search"
              aria-label="Search partner directory by state, NAICS, or ERP"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search IL, TX, NetSuite, CPA, 484, EDI..."
            />
          </label>
        </div>

        <div
          className="usr-inline"
          role="group"
          aria-label="Filter partner directory by practice track"
          style={{ marginBottom: "20px" }}
        >
          {TRACK_LABELS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              aria-pressed={trackFilter === tab.id}
              className="usr-small-btn"
              style={{
                borderRadius: "999px",
                border: "1px solid var(--line)",
                background: trackFilter === tab.id ? "#111318" : "#f4f5f8",
                color: trackFilter === tab.id ? "#ffffff" : "#2f3440",
                cursor: "pointer",
              }}
              onClick={() => setTrackFilter(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {filteredListings.length === 0 ? (
          <p className="usr-muted" style={{ margin: 0 }}>
            No practices match that filter. Clear the search query or apply
            below to launch a certified practice in your region.
          </p>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(440px, 100%), 1fr))",
              gap: "16px",
            }}
          >
            {filteredListings.map((item) => (
              <article
                key={item.slug}
                style={{
                  border: "1px solid var(--line)",
                  borderRadius: "14px",
                  padding: "20px",
                  background: "#fafbfc",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: "12px",
                }}
              >
                <div>
                  <div className="usr-inline" style={{ marginBottom: "8px" }}>
                    <span className="usr-badge usr-badge-ai">
                      {item.partnerTier}
                    </span>
                    <span className="usr-badge">{item.regionLabel}</span>
                  </div>
                  <h3 style={{ margin: "0 0 8px", fontSize: "1.1rem" }}>
                    {item.practiceName}
                  </h3>
                  <div
                    className="usr-inline"
                    style={{ gap: "6px", marginBottom: "10px" }}
                  >
                    {item.naicsSpecialties.map((tag) => (
                      <span key={tag} className="usr-badge">
                        {tag}
                      </span>
                    ))}
                  </div>
                  <ul
                    style={{
                      margin: "0 0 10px",
                      paddingLeft: "18px",
                      fontSize: "0.88rem",
                      color: "#2f3440",
                    }}
                  >
                    {item.deliverables.map((d) => (
                      <li key={d} style={{ marginBottom: "4px" }}>
                        {d}
                      </li>
                    ))}
                  </ul>
                  <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
                    Migrations: {item.erpMigrations.join(" · ")}
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "8px",
                    paddingTop: "10px",
                    borderTop: "1px solid var(--line)",
                  }}
                >
                  <span className="usr-muted" style={{ fontSize: "0.8rem" }}>
                    {item.availability}
                  </span>
                  <a
                    href="#partner-apply"
                    className="button secondary usr-small-btn"
                  >
                    Request Scoping →
                  </a>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="usr-card" aria-labelledby="partner-cert-h">
        <h2 id="partner-cert-h" style={{ marginBottom: "6px" }}>
          3-Tier AMARKAL Partner Certification &amp; Agency Console
        </h2>
        <p className="usr-muted" style={{ marginTop: 0 }}>
          Built for US ERP integrators, CPA firms, and ISV engineering teams.
          AMARKAL natively includes a Multi-Client Workspace Switcher and
          time-bounded scoped Delegations so agencies can operate dozens of
          client environments securely under PostgreSQL 18 FORCE RLS — with 0%
          commission taken from partner retainers.
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(auto-fit, minmax(min(280px, 100%), 1fr))",
            gap: "16px",
            marginBottom: "16px",
          }}
        >
          {CERTIFICATION_TIERS.map((tier) => (
            <article
              key={tier.code}
              style={{
                border: "1px solid var(--line)",
                borderRadius: "14px",
                padding: "20px",
                background: "#ffffff",
              }}
            >
              <span className="usr-badge usr-badge-ai">{tier.code}</span>
              <h3 style={{ margin: "10px 0 4px", fontSize: "1.08rem" }}>
                {tier.title}
              </h3>
              <p
                className="usr-muted"
                style={{ margin: "0 0 10px", fontSize: "0.84rem" }}
              >
                {tier.audience}
              </p>
              <strong style={{ fontSize: "0.85rem" }}>Core Curriculum</strong>
              <ul
                style={{
                  margin: "6px 0 12px",
                  paddingLeft: "18px",
                  fontSize: "0.85rem",
                }}
              >
                {tier.curriculum.map((c) => (
                  <li key={c} style={{ marginBottom: "4px" }}>
                    {c}
                  </li>
                ))}
              </ul>
              <strong style={{ fontSize: "0.85rem" }}>Partner Benefits</strong>
              <ul
                style={{
                  margin: "6px 0 0",
                  paddingLeft: "18px",
                  fontSize: "0.85rem",
                }}
              >
                {tier.benefits.map((b) => (
                  <li key={b} style={{ marginBottom: "4px" }}>
                    {b}
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>

        <div className="usr-inline">
          <Link href="/overview/" className="button secondary usr-small-btn">
            Open Agency Workspace Switcher
          </Link>
          <Link
            href="/app-marketplace/"
            className="button secondary usr-small-btn"
          >
            Inspect Plugin SDK (amarkal-plugin.json)
          </Link>
          <Link href="/security/" className="button secondary usr-small-btn">
            Review PG18 FORCE RLS Trust Center
          </Link>
        </div>
      </section>

      <section
        id="partner-apply"
        className="usr-card"
        aria-labelledby="partner-apply-h"
      >
        <div className="usr-inline" style={{ marginBottom: "8px" }}>
          <span className="usr-badge usr-badge-ai">
            FOUNDING PARTNER COHORT OPEN
          </span>
          <span className="usr-badge">0% RETAINER COMMISSION</span>
        </div>
        <h2 id="partner-apply-h" style={{ marginBottom: "6px" }}>
          Apply to Join the AMARKAL Partner &amp; Integrator Network
        </h2>
        <p className="usr-muted" style={{ marginTop: 0 }}>
          Whether you are an independent ERP consultant, US CPA practice, or
          vertical systems integrator — submit your profile to receive sandbox
          access, certification materials, and Founding Partner directory
          placement.
        </p>

        {submitError ? (
          <div className="usr-errors" role="alert">
            {submitError}
          </div>
        ) : null}

        {submitSuccess ? (
          <div
            role="status"
            style={{
              padding: "16px 20px",
              borderRadius: "12px",
              border: "1px solid #a9dbb9",
              background: "#e9f6ee",
              color: "#165430",
              marginBottom: "16px",
            }}
          >
            <strong>Reference {submitSuccess.referenceId}:</strong>{" "}
            {submitSuccess.message}
          </div>
        ) : null}

        <form onSubmit={handleApply} className="usr-stack">
          <div className="usr-grid">
            <label>
              Agency / CPA Firm / Integrator Name
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                required
                minLength={2}
                placeholder="Midwest ERP Advisory LLC"
              />
            </label>
            <label>
              Primary Contact Name
              <input
                type="text"
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
                required
                minLength={2}
                placeholder="Dana Mercer"
              />
            </label>
            <label>
              Work Email
              <input
                type="email"
                value={workEmail}
                onChange={(e) => setWorkEmail(e.target.value)}
                required
                placeholder="partners@yourfirm.com"
              />
            </label>
            <label>
              US State / Region
              <input
                type="text"
                value={usState}
                onChange={(e) => setUsState(e.target.value)}
                required
                minLength={2}
                placeholder="IL / TX / NY / Nationwide"
              />
            </label>
            <label>
              Partner Track
              <select
                value={partnerTrack}
                onChange={(e) =>
                  setPartnerTrack(
                    e.target.value as Exclude<PartnerTrack, "all">,
                  )
                }
              >
                <option value="implementation_migration">
                  ERP Implementation &amp; Migration
                </option>
                <option value="cpa_finance_holding">
                  CPA, Double-Entry &amp; Multi-Entity Holding
                </option>
                <option value="industrial_mrp_iot">
                  Industrial MRP II, Construction &amp; IoT
                </option>
                <option value="isv_plugin_mcp">
                  ISV Plugin SDK (amarkal-plugin.json) &amp; MCP
                </option>
              </select>
            </label>
            <label>
              Target NAICS Industries
              <input
                type="text"
                value={naicsFocus}
                onChange={(e) => setNaicsFocus(e.target.value)}
                required
                minLength={2}
                placeholder="484 Trucking, 23 Construction, 5412 CPA..."
              />
            </label>
            <label>
              Consulting / Engineering Team Size
              <select
                value={teamSize}
                onChange={(e) => setTeamSize(e.target.value)}
              >
                <option value="1-4">1–4 (Boutique / Solo Specialist)</option>
                <option value="5-25">5–25 (Regional Firm / Agency)</option>
                <option value="26-100">26–100 (Mid-Market Integrator)</option>
                <option value="100+">100+ (National Practice)</option>
              </select>
            </label>
            <label>
              Firm Website (Optional)
              <input
                type="url"
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
                placeholder="https://yourfirm.com"
              />
            </label>
          </div>

          <label>
            ERP Migration &amp; Systems Integration Experience
            <textarea
              className="usr-textarea"
              rows={4}
              value={experienceSummary}
              onChange={(e) => setExperienceSummary(e.target.value)}
              placeholder="Share your NetSuite, Odoo, Zoho, QuickBooks, EDI, or custom API implementation background..."
            />
          </label>

          {/* Anti-spam honeypot field hidden from screen readers and sighted users */}
          <div aria-hidden="true" style={{ display: "none" }}>
            <label>
              Leave blank
              <input
                type="text"
                tabIndex={-1}
                autoComplete="off"
                value={honeypot}
                onChange={(e) => setHoneypot(e.target.value)}
              />
            </label>
          </div>

          <div>
            <button
              type="submit"
              className="button usr-small-btn"
              disabled={submitting}
            >
              {submitting
                ? "Submitting Application..."
                : "Submit Partner Application"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
