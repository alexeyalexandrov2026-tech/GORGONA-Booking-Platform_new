import type { Metadata } from "next";
import Link from "next/link";
import { AmarkalLogo } from "../components/amarkal-logo";
import { AppHubTabs } from "../components/landing/app-hub-tabs";
import { ArchitectFlow } from "../components/landing/architect-flow";
import { CommissionCalculator } from "../components/landing/commission-calculator";
import { IndustryExplorer } from "../components/landing/industry-explorer";
import { INDUSTRIES } from "../components/landing/industries";
import { MonolithHeroStage } from "../components/landing/monolith-hero-stage";
import { B2bDemoRequestForm } from "../components/b2b-demo-request-form";
import "./landing.css";

export const metadata: Metadata = {
  title:
    "AMARKAL Platform — US Business OS across 39 industries, 0% commission",
  description:
    "Run any US business on AMARKAL Platform: operations, counterparties, contracts, staff, double-entry USD finance, optional client portals, and human-approved AI across 39 NAICS industries. 0% commission.",
  alternates: { canonical: "https://www.amarkal-platform.com/" },
  openGraph: {
    title:
      "AMARKAL Platform — US Business OS across 39 industries, 0% commission",
    description:
      "Unified US Business Operating System for 39 NAICS industries: operations, counterparties, contracts, staff, FIN-03 USD finance, optional client portals, and governed AI. 0% platform commission.",
    url: "https://www.amarkal-platform.com/",
    siteName: "AMARKAL Platform",
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "AMARKAL Platform — US Business OS (0% Commission)",
    description:
      "Run any US business on one operating system across 39 NAICS industries with 0% commission, 11-tool Native MCP, Smart Autonomy AI, MRP II, and US Payroll Prep.",
  },
  robots: { index: true, follow: true },
};

const NAV = [
  { href: "#platform", label: "Platform" },
  { href: "#industries", label: "Industries" },
  { href: "#manifesto", label: "0% commission" },
  { href: "#architect", label: "AI Architect" },
  { href: "#app-hub", label: "App Hub" },
] as const;

const STRUCTURED_DATA = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      name: "AMARKAL Platform",
      legalName: "Alexey AAA Logistics LLC",
      url: "https://www.amarkal-platform.com/",
      email: "support@amarkal-platform.com",
      areaServed: "US",
    },
    {
      "@type": "SoftwareApplication",
      name: "AMARKAL Platform",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      url: "https://www.amarkal-platform.com/",
      description:
        "US Business Operating System across 39 NAICS industries covering operations, MRP II & Predictive EAM/IoT, Omnichannel Inbox & Virtual PBX, US Payroll Prep, Multi-Currency FX & VAT, No-Code Studio, 1-Click B2C Shop, 11-tool Native MCP, and Hybrid Smart Autonomy AI.",
    },
  ],
};

const TRUST = [
  {
    title: "Built for the United States",
    text: "USD, US time zones, FLSA/CA payroll compliance and NAICS 2022 — plus multi-currency FX and EU/UK VAT when you expand.",
  },
  {
    title: "Your data stays yours",
    text: "Every business is isolated at the PostgreSQL row level with AES-256-GCM BYOK vaults and 1-click export.",
  },
  {
    title: "Hybrid Smart Autonomy",
    text: "Routine tasks can run automatically while payments, payroll, and contracts strictly require human approval.",
  },
  {
    title: "Open by design",
    text: "Scoped API keys, IoT & inbox webhooks, BYOK AI and an 11-tool native MCP server in every workspace.",
  },
] as const;

const PRINCIPLES = [
  "Your customers stay yours. They interact on your portal or B2C shop, under your brand.",
  "We never take a percentage of your orders, services, or sales.",
  "Direct Stripe US payouts (Cards, Apple Pay, Google Pay, ACH) plus SEPA & UK Faster Payments rails.",
  "Export or automate whenever you like. API keys, webhooks and 11-tool MCP are included.",
] as const;

const ARCHITECT_POINTS = [
  "Works from plain English or a photo of your price list",
  "Picks your NAICS industry profile and US time zone",
  "Drafts services, prices, resources and opening hours",
  "Publishes nothing until you approve every part",
] as const;

const CONNECTORS = [
  "Native MCP server (11 tools)",
  "BYOK AI (Anthropic, Gemini, OpenAI)",
  "Stripe US Live, ACH & SEPA / UK Rails",
  "Microsoft 365 & Google Workspace",
  "Gusto, ADP & QuickBooks Export",
  "Zapier, Make and n8n",
  "Built-In Email, Virtual PBX & SMS",
  "Industrial IoT & Telematics Webhooks",
] as const;

export default function HomePage() {
  return (
    <div className="lp">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(STRUCTURED_DATA) }}
      />
      <a className="skip" href="#main-content">
        Skip to content
      </a>

      <header className="lp-header-shell">
        <div className="lp-header lp-container">
          <Link href="/" className="lp-brand">
            <AmarkalLogo variant="light" height={22} />
          </Link>
          <nav className="lp-nav" aria-label="Page sections">
            <ul>
              {NAV.map((item) => (
                <li key={item.href}>
                  <a href={item.href}>{item.label}</a>
                </li>
              ))}
            </ul>
          </nav>
          <div className="lp-header-actions">
            <Link href="/auth/signin/" className="lp-link-quiet">
              Sign in
            </Link>
            <Link
              href="/onboarding/"
              className="lp-btn lp-btn--primary lp-btn--sm"
            >
              Create your business
            </Link>
          </div>
        </div>
      </header>

      <main id="main-content">
        {/* Hero — Light MONOLITH Apple precision */}
        <section className="lp-hero-section" aria-labelledby="lp-hero-title">
          <div className="lp-container lp-hero">
            <p className="lp-mono lp-hero-eyebrow">
              US Business OS · {INDUSTRIES.length} industries · 0% commission
            </p>
            <h1 id="lp-hero-title">
              <span>
                Run any US business
                <br />
                on one platform.
              </span>
            </h1>
            <p className="lp-lead">
              Operations, counterparties, contracts, staff, documents,
              double-entry USD finance and optional client portals in one
              operating system that adapts to your industry. With an AI
              Assistant that asks first.
            </p>
            <div className="lp-cta-row">
              <Link
                href="/onboarding/"
                className="lp-btn lp-btn--primary lp-btn--lg"
              >
                Create your business
              </Link>
              <Link
                href="/book/?demo=1"
                className="lp-btn lp-btn--link lp-btn--lg"
              >
                Explore industry demos <span aria-hidden="true">›</span>
              </Link>
            </div>
            <MonolithHeroStage />
          </div>
        </section>

        {/* Bento Grid — One workspace */}
        <section
          id="platform"
          className="lp-section"
          aria-labelledby="lp-features-title"
        >
          <div className="lp-container lp-center">
            <p className="lp-mono">One business operating system</p>
            <h2 id="lp-features-title">
              Everything a business runs on.
              <br />
              <span className="lp-h2-muted">Nothing it doesn’t.</span>
            </h2>
            <div className="lp-bento">
              <article className="lp-tile lp-tile--w4">
                <span className="lp-mono">01</span>
                <h3>Operations, dispatch &amp; workflows</h3>
                <p>
                  Orders, projects, fleet dispatch, assets, resources and
                  optional client booking portals in one operational workspace —
                  adapted to your NAICS profile.
                </p>
                <div className="lp-tile-visual" aria-hidden="true">
                  <div className="lp-mini-track">
                    <span>09:00 · Freight dispatch</span>
                    <i className="is-blue" style={{ width: "64%" }} />
                  </div>
                  <div className="lp-mini-track">
                    <span>12:30 · Site work order</span>
                    <i className="is-gold" style={{ width: "48%" }} />
                  </div>
                  <div className="lp-mini-track">
                    <span>15:00 · Fleet allocation</span>
                    <i className="is-blue" style={{ width: "74%" }} />
                  </div>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2 lp-tile--dark">
                <span className="lp-mono lp-mono--gold">AI</span>
                <h3>Smart Autonomy AI</h3>
                <p>
                  Proactive weekly predictive insights, BYOK AI models, and
                  configurable autonomy: safe routines auto-run while money,
                  payroll, and contracts strictly require owner approval.
                </p>
                <div className="lp-tile-ai-pill" aria-hidden="true">
                  <span>●</span> Hybrid Autonomy · 0 unapproved payouts
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">02</span>
                <h3>Clients, Inbox &amp; Virtual PBX</h3>
                <p>
                  Counterparties, versioned contracts, built-in Email, Virtual
                  PBX calls, SMS, and WhatsApp in one unified CRM timeline.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>Built-In PBX</span>
                  <span>Email · SMS · WA</span>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">03</span>
                <h3>Staff, Shifts &amp; US Payroll</h3>
                <p>
                  Branch schedules, FLSA &amp; California §510 overtime, Union
                  CBA compliance, and 1-click Gusto/ADP CSV export.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>FLSA · CA §510</span>
                  <span>Gusto / ADP CSV</span>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">04</span>
                <h3>USD &amp; Multi-Currency FX</h3>
                <p>
                  Double-entry FIN-03 ledger, real-time FX Gain/Loss
                  revaluation, and live Stripe US reconciliation at 0%
                  take-rate.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>DR = CR</span>
                  <span>Auto FX P&amp;L</span>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">05</span>
                <h3>MRP II &amp; Predictive EAM</h3>
                <p>
                  Multi-level BOM explosion, atomic raw-material reservations,
                  1-click Draft POs, and IoT sensor webhooks creating predictive
                  Work Orders.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>Multi-Level BOM</span>
                  <span>IoT Telemetry</span>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">06</span>
                <h3>No-Code Studio &amp; B2C Shop</h3>
                <p>
                  Custom Kanban boards, typed fields, brand themes, and a
                  1-click B2C storefront with promos, cart, and Stripe checkout.
                </p>
                <div className="lp-tile-meta">
                  <Link href="/shop/?demo=1" className="lp-link-quiet">
                    Try live B2C shop demo ›
                  </Link>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">07</span>
                <h3>Global Tax &amp; Local Rails</h3>
                <p>
                  US Sales Tax, EU/UK VAT with 0% B2B Reverse Charge, CA
                  GST/HST, MX IVA, plus SEPA Instant &amp; UK Faster Payments.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>US / EU / UK VAT</span>
                  <span>SEPA · FPS</span>
                </div>
              </article>
            </div>
            <p className="lp-fineprint">
              Industry workflows are switched on only after they are verified.
              The product shows the status of every module before you enable it.
            </p>
          </div>
        </section>

        {/* Monumental 0% Commission + 4 Trust Pillars + Interactive Calculator */}
        <section
          id="manifesto"
          className="lp-section lp-manifesto-section"
          aria-labelledby="manifesto-title"
        >
          <div className="lp-container lp-center">
            <p className="lp-big-zero" aria-hidden="true">
              0%
            </p>
            <h2 id="manifesto-title" className="lp-zero-heading">
              <span className="sr-only">0% </span>commission. Always.
            </h2>
            <p className="lp-section-lead lp-section-lead--center">
              You built the business. You keep what it earns. AMARKAL Platform
              is operating software for your company — never a toll booth
              between you and your customers.
            </p>

            <ul className="lp-trust-grid" aria-label="Why AMARKAL Platform">
              {TRUST.map((item) => (
                <li key={item.title}>
                  <h3>{item.title}</h3>
                  <p>{item.text}</p>
                </li>
              ))}
            </ul>

            <div className="lp-manifesto-calc-wrap">
              <div className="lp-manifesto-principles">
                <p className="lp-mono">No take-rate. No vendor lock-in.</p>
                <h3>Keep 100% of every customer payment.</h3>
                <ul className="lp-principles">
                  {PRINCIPLES.map((principle) => (
                    <li key={principle}>{principle}</li>
                  ))}
                </ul>
              </div>
              <CommissionCalculator />
            </div>
          </div>
        </section>

        {/* Interactive 39-Industry NAICS Explorer */}
        <section
          id="industries"
          className="lp-section lp-section--tint"
          aria-labelledby="industries-title"
        >
          <div className="lp-container">
            <p className="lp-mono">{INDUSTRIES.length} NAICS industries</p>
            <h2 id="industries-title">
              {INDUSTRIES.length} US industries. One platform.
            </h2>
            <p className="lp-section-lead">
              Choose your industry, or combine several. AMARKAL Platform maps
              every direction to NAICS 2022 sectors, so you start with the right
              modules instead of a blank screen.
            </p>
            <IndustryExplorer />
            <div style={{ marginTop: "28px" }}>
              <p className="lp-mono" style={{ marginBottom: "10px" }}>
                Featured US B2B Vertical Guides
              </p>
              <div className="usr-inline">
                <Link
                  href="/industries/freight-logistics/"
                  className="lp-btn lp-btn--ghost"
                >
                  Freight &amp; Logistics →
                </Link>
                <Link
                  href="/industries/construction/"
                  className="lp-btn lp-btn--ghost"
                >
                  Construction &amp; Field →
                </Link>
                <Link
                  href="/industries/commercial-property/"
                  className="lp-btn lp-btn--ghost"
                >
                  Commercial Property →
                </Link>
                <Link
                  href="/industries/equipment-rental/"
                  className="lp-btn lp-btn--ghost"
                >
                  Equipment &amp; Fleet Rental →
                </Link>
              </div>
            </div>
          </div>
        </section>

        {/* Interactive AI Business Architect */}
        <section
          id="architect"
          className="lp-section"
          aria-labelledby="architect-title"
        >
          <div className="lp-container lp-split">
            <div>
              <p className="lp-mono">AI Business Architect</p>
              <h2 id="architect-title">
                Describe your business. Approve the setup.
              </h2>
              <p className="lp-section-lead">
                The AI Business Architect turns a few plain sentences, or a
                photo of your price list, into a structured workspace draft:
                services, prices, resources and opening hours. You approve every
                line before anything goes live.
              </p>
              <ul className="lp-checks">
                {ARCHITECT_POINTS.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <Link href="/onboarding/" className="lp-btn lp-btn--primary">
                Try the AI Business Architect
              </Link>
            </div>
            <ArchitectFlow />
          </div>
        </section>

        {/* App Hub & Native MCP */}
        <section
          id="app-hub"
          className="lp-section lp-section--tint"
          aria-labelledby="app-hub-title"
        >
          <div className="lp-container lp-split lp-split--reverse">
            <div>
              <p className="lp-mono">App Hub &amp; Native MCP</p>
              <h2 id="app-hub-title">Connect what you need. Nothing else.</h2>
              <p className="lp-section-lead">
                The core stays focused on running your business. Messengers,
                telephony, accounting and AI agents connect cleanly through the
                AMARKAL App Hub and our 11-tool Native MCP server using your own
                accounts.
              </p>
              <ul className="lp-connectors" aria-label="Connectors">
                {CONNECTORS.map((name) => (
                  <li key={name}>{name}</li>
                ))}
              </ul>
              <Link href="/integrations/" className="lp-btn lp-btn--primary">
                Open the App Hub
              </Link>
            </div>
            <AppHubTabs />
          </div>
        </section>

        {/* B2B Demo / Founding Partner Pilot Intake */}
        <section
          id="demo-request"
          className="lp-section"
          aria-labelledby="demo-request-heading"
        >
          <div className="lp-container">
            <h2 id="demo-request-heading" className="sr-only">
              Request a B2B Walkthrough
            </h2>
            <B2bDemoRequestForm sourcePath="/" />
          </div>
        </section>

        {/* Monumental Obsidian Closing CTA */}
        <section className="lp-final" aria-labelledby="final-title">
          <div className="lp-container lp-final-inner">
            <p className="lp-mono lp-mono--dark">
              Freight &amp; logistics · Construction · Property · Rentals · +35
            </p>
            <h2 id="final-title">
              Open your business
              <br />
              in minutes.
            </h2>
            <p className="lp-final-lead">
              Launch a Business OS workspace with the AI Business Architect,
              approve your draft, and keep 100% of your revenue.
            </p>
            <div className="lp-cta-row">
              <Link
                href="/onboarding/"
                className="lp-btn lp-btn--white lp-btn--lg"
              >
                Create your business
              </Link>
              <Link
                href="/book/?demo=1"
                className="lp-btn lp-btn--link-dark lp-btn--lg"
              >
                Explore industry demos <span aria-hidden="true">›</span>
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-container lp-footer-inner">
          <div className="lp-footer-left">
            <AmarkalLogo variant="dark" height={18} />
            <span className="lp-footer-copy">
              © 2026 Alexey AAA Logistics LLC
            </span>
          </div>
          <nav aria-label="Footer">
            <ul>
              <li>
                <Link href="/onboarding/">Create your business</Link>
              </li>
              <li>
                <Link href="/book/?demo=1">Industry demos</Link>
              </li>
              <li>
                <Link href="/shop/?demo=1">B2C Shop demo</Link>
              </li>
              <li>
                <Link href="/security/">Trust &amp; Security</Link>
              </li>
              <li>
                <Link href="/partners/">Partner Network</Link>
              </li>
              <li>
                <Link href="/compare/zoho-one/">vs Zoho One</Link>
              </li>
              <li>
                <Link href="/compare/odoo/">vs Odoo</Link>
              </li>
              <li>
                <Link href="/compare/monday/">vs Monday</Link>
              </li>
              <li>
                <Link href="/compare/netsuite/">vs NetSuite</Link>
              </li>
              <li>
                <Link href="/auth/signin/">Sign in</Link>
              </li>
              <li>
                <Link href="/integrations/">App Hub</Link>
              </li>
              <li>
                <a href="mailto:support@amarkal-platform.com">Support</a>
              </li>
              <li>
                <Link href="/legal/terms/">Terms of Service</Link>
              </li>
              <li>
                <Link href="/legal/privacy/">Privacy Policy</Link>
              </li>
            </ul>
          </nav>
        </div>
      </footer>
    </div>
  );
}
