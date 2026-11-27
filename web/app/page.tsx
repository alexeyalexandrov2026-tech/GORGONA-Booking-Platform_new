import type { Metadata } from "next";
import Link from "next/link";
import { AmarkalLogo } from "../components/amarkal-logo";
import { AppHubTabs } from "../components/landing/app-hub-tabs";
import { ArchitectFlow } from "../components/landing/architect-flow";
import { CommissionCalculator } from "../components/landing/commission-calculator";
import { IndustryExplorer } from "../components/landing/industry-explorer";
import { INDUSTRIES } from "../components/landing/industries";
import { MonolithHeroStage } from "../components/landing/monolith-hero-stage";
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
      "Run any US business on one operating system across 39 NAICS industries with 0% commission, 7-tool Native MCP, and AI that asks first.",
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
        "US Business Operating System across 39 NAICS industries covering operations, counterparties, contracts, staff, double-entry USD finance, optional client portals, 7-tool Native MCP, and human-in-the-loop AI.",
    },
  ],
};

const TRUST = [
  {
    title: "Built for the United States",
    text: "USD, US time zones and NAICS 2022. Nothing to translate or convert.",
  },
  {
    title: "Your data stays yours",
    text: "Every business is isolated at the PostgreSQL row level with 1-click JSON export.",
  },
  {
    title: "AI that asks first",
    text: "AI drafts proposals and operational setups. Nothing changes until a person approves.",
  },
  {
    title: "Open by design",
    text: "Scoped API keys, signed webhooks and a 7-tool native MCP server in every workspace.",
  },
] as const;

const PRINCIPLES = [
  "Your customers stay yours. They interact on your portal, under your brand.",
  "We never take a percentage of your orders, services, or sales.",
  "Direct Stripe US payouts (Cards, Apple Pay, Google Pay, ACH) straight to your bank.",
  "Export or automate whenever you like. API keys, webhooks and MCP are included.",
] as const;

const ARCHITECT_POINTS = [
  "Works from plain English or a photo of your price list",
  "Picks your NAICS industry profile and US time zone",
  "Drafts services, prices, resources and opening hours",
  "Publishes nothing until you approve every part",
] as const;

const CONNECTORS = [
  "Native MCP server (7 tools)",
  "Stripe US Live & ACH",
  "Zapier, Make and n8n",
  "QuickBooks Online",
  "Google Calendar and Outlook",
  "Reserve with Google",
  "Twilio SMS and voice",
  "WhatsApp and Instagram DM",
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
                <h3>AI Assistant</h3>
                <p>
                  Drafts workspace setups, operational proposals and live
                  business insights — executing actions only after explicit
                  owner approval.
                </p>
                <div className="lp-tile-ai-pill" aria-hidden="true">
                  <span>●</span> Human-in-the-loop · 0 unapproved writes
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">02</span>
                <h3>Clients &amp; documents</h3>
                <p>
                  Customer and vendor cards, versioned contracts and files with
                  full immutable history.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>Agreement v3</span>
                  <span>Attested</span>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">03</span>
                <h3>Staff &amp; shifts</h3>
                <p>
                  Weekly schedules, shift swaps with manager approval, and
                  verified timesheets.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>Zero conflicts</span>
                  <span>Branch RBAC</span>
                </div>
              </article>

              <article className="lp-tile lp-tile--w2">
                <span className="lp-mono">04</span>
                <h3>Finance in USD</h3>
                <p>
                  Double-entry ledger, FIN-03 invoices, and live Stripe US
                  reconciliation your accountant can follow.
                </p>
                <div className="lp-tile-meta" aria-hidden="true">
                  <span>DR = CR</span>
                  <span>0% take-rate</span>
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
                AMARKAL App Hub and our 7-tool Native MCP server using your own
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
