import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { AppHubTabs } from "../components/landing/app-hub-tabs";
import { ArchitectFlow } from "../components/landing/architect-flow";
import { CommissionCalculator } from "../components/landing/commission-calculator";
import { IndustryExplorer } from "../components/landing/industry-explorer";
import { INDUSTRIES } from "../components/landing/industries";
import "./landing.css";

export const metadata: Metadata = {
  title:
    "AMARKAL Platform — US Business OS across 39 industries, 0% commission",
  description:
    "Run any US business on AMARKAL Platform: operations, scheduling, clients, staff, finance, and AI automation for 39 NAICS industries. 0% commission.",
};

const NAV = [
  { href: "#industries", label: "Industries" },
  { href: "#manifesto", label: "0% commission" },
  { href: "#architect", label: "AI Business Architect" },
  { href: "#app-hub", label: "App Hub" },
] as const;

const WINDOW_NAV = [
  "Overview",
  "Calendar",
  "Orders",
  "Clients",
  "Finance",
  "App Hub",
] as const;

const TRUST = [
  {
    title: "Built for the United States",
    text: "USD, US time zones and the NAICS industry system. Nothing to translate or convert.",
  },
  {
    title: "Your data stays yours",
    text: "Every business is isolated from every other one at the database level.",
  },
  {
    title: "AI that asks first",
    text: "The AI drafts and suggests. Nothing changes until a person approves it.",
  },
  {
    title: "Open by design",
    text: "Scoped API keys, signed webhooks and a native MCP server come with every workspace.",
  },
] as const;

const PRINCIPLES = [
  "Your customers stay yours. They interact on your portal, under your brand.",
  "We never take a percentage of your orders, services, or sales.",
  "No bidding for visibility. Your client portal and customer list belong to you.",
  "Export or automate whenever you like. API keys, webhooks and MCP are in the box.",
] as const;

const ARCHITECT_POINTS = [
  "Works from plain English or a photo of your price list",
  "Picks your industry profile and your US time zone",
  "Drafts services, prices, resources and opening hours",
  "Publishes nothing until you approve every part",
] as const;

const CONNECTORS = [
  "Native MCP server",
  "Zapier, Make and n8n",
  "QuickBooks Online",
  "Google Calendar and Outlook",
  "Reserve with Google",
  "Twilio SMS and voice",
  "WhatsApp and Instagram DM",
  "Stripe",
] as const;

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="lp-icon"
      viewBox="0 0 24 24"
      width="26"
      height="26"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

const FEATURES: readonly { title: string; text: string; icon: ReactNode }[] = [
  {
    title: "Scheduling & operations",
    text: "Services, specialists and resources with one shared view of availability, plus a branded portal for your customers.",
    icon: (
      <Icon>
        <rect x="3" y="4.5" width="18" height="16" rx="2.5" />
        <path d="M3 9.5h18M8 3v3M16 3v3" />
      </Icon>
    ),
  },
  {
    title: "Clients and documents",
    text: "Customer and vendor cards, contracts and files together, with every change kept in a history.",
    icon: (
      <Icon>
        <circle cx="9" cy="8" r="3.2" />
        <path d="M3.5 19.5c.4-3.4 2.7-5.2 5.5-5.2s5.1 1.8 5.5 5.2" />
        <path d="M16.5 5.3a3.2 3.2 0 0 1 0 5.4M18.2 14.6c1.6.7 2.6 2.3 2.8 4.9" />
      </Icon>
    ),
  },
  {
    title: "Staff and shifts",
    text: "Weekly schedules, shift swaps with approval and timesheets for the people who run your day.",
    icon: (
      <Icon>
        <circle cx="12" cy="12" r="8.5" />
        <path d="M12 7.5V12l3 2" />
      </Icon>
    ),
  },
  {
    title: "Finance in USD",
    text: "A double-entry ledger, invoices and payment records that your accountant can follow.",
    icon: (
      <Icon>
        <path d="M12 3v18M16 7.5c-.9-1-2.2-1.5-4-1.5-2.3 0-4 1.1-4 3s1.7 2.6 4 3 4 1.1 4 3-1.7 3-4 3c-1.8 0-3.2-.5-4.2-1.6" />
      </Icon>
    ),
  },
  {
    title: "Industry modules",
    text: "Transport, construction, rental, property, restaurant, supply chain, projects and more switch on for your profile.",
    icon: (
      <Icon>
        <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
        <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
        <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
        <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
      </Icon>
    ),
  },
  {
    title: "AMARKAL AI Assistant",
    text: "Helps customers choose a service and a time on your client portal through the same verified workflow.",
    icon: (
      <Icon>
        <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3zM18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z" />
      </Icon>
    ),
  },
];

export default function HomePage() {
  return (
    <div className="lp">
      <a className="skip" href="#main-content">
        Skip to content
      </a>

      <div className="lp-top lp-dark">
        <header className="lp-header lp-container">
          <Link href="/" className="lp-brand">
            <span className="lp-brand-mark" aria-hidden="true" />
            <span>
              AMARKAL <span className="lp-brand-sub">Platform</span>
            </span>
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
            <Link href="/overview/" className="lp-link-quiet">
              Sign in
            </Link>
            <Link
              href="/onboarding/"
              className="lp-btn lp-btn--primary lp-btn--sm"
            >
              Create your business
            </Link>
          </div>
        </header>

        <section
          className="lp-container lp-hero"
          aria-labelledby="lp-hero-title"
        >
          <div className="lp-hero-copy">
            <p className="lp-eyebrow">AMARKAL Platform · US Business OS</p>
            <h1 id="lp-hero-title">Run any US business on one platform.</h1>
            <p className="lp-lead">
              Operations, scheduling, clients, staff, documents and finance in
              one workspace that adapts to {INDUSTRIES.length} US industries,
              with an AI Assistant for your customers. Describe your business,
              approve the AI’s draft and launch. 0% commission, always.
            </p>
            <div className="lp-cta-row">
              <Link
                href="/onboarding/"
                className="lp-btn lp-btn--primary lp-btn--lg"
              >
                Create your business
              </Link>
              <Link href="/book/" className="lp-btn lp-btn--ghost lp-btn--lg">
                Open client portal
              </Link>
            </div>
            <ul className="lp-facts">
              <li>
                <strong>{INDUSTRIES.length}</strong> NAICS industries
              </li>
              <li>
                <strong>0%</strong> commission
              </li>
              <li>
                <strong>USD</strong> and US time zones
              </li>
            </ul>
          </div>

          <div className="lp-window" aria-hidden="true">
            <div className="lp-window-bar">
              <span />
              <span />
              <span />
            </div>
            <div className="lp-window-body">
              <ul className="lp-window-nav">
                {WINDOW_NAV.map((label, index) => (
                  <li
                    key={label}
                    data-active={index === 0 ? "true" : undefined}
                  >
                    {label}
                  </li>
                ))}
              </ul>
              <div className="lp-window-main">
                <div className="lp-skeleton lp-skeleton--title" />
                <div className="lp-window-cards">
                  <div className="lp-skeleton lp-skeleton--card" />
                  <div className="lp-skeleton lp-skeleton--card" />
                  <div className="lp-skeleton lp-skeleton--card" />
                </div>
                <div className="lp-skeleton lp-skeleton--row" />
                <div className="lp-skeleton lp-skeleton--row" />
                <div className="lp-skeleton lp-skeleton--row lp-skeleton--short" />
              </div>
            </div>
          </div>
        </section>
      </div>

      <main id="main-content">
        <section className="lp-trust" aria-label="Why AMARKAL Platform">
          <ul className="lp-container lp-trust-grid">
            {TRUST.map((item) => (
              <li key={item.title}>
                <strong>{item.title}</strong>
                <span>{item.text}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="lp-section" aria-labelledby="lp-features-title">
          <div className="lp-container">
            <p className="lp-eyebrow">One workspace</p>
            <h2 id="lp-features-title">Everything a business runs on</h2>
            <p className="lp-section-lead">
              Start with the core and add only what your industry needs. Your
              menu adapts to the modules you use.
            </p>
            <ul className="lp-feature-grid">
              {FEATURES.map((feature) => (
                <li key={feature.title} className="lp-card lp-feature">
                  {feature.icon}
                  <h3>{feature.title}</h3>
                  <p>{feature.text}</p>
                </li>
              ))}
            </ul>
            <p className="lp-fineprint">
              Industry workflows are switched on only after they are verified.
              The product shows the status of every module before you enable it.
            </p>
          </div>
        </section>

        <section
          id="industries"
          className="lp-section lp-section--tint"
          aria-labelledby="industries-title"
        >
          <div className="lp-container">
            <p className="lp-eyebrow">{INDUSTRIES.length} industries</p>
            <h2 id="industries-title">
              {INDUSTRIES.length} US industries. One platform.
            </h2>
            <p className="lp-section-lead">
              Choose your industry, or combine several. AMARKAL Platform maps
              every direction to NAICS sectors, so you start with the right
              modules instead of a blank screen.
            </p>
            <IndustryExplorer />
          </div>
        </section>

        <section
          id="manifesto"
          className="lp-section lp-dark"
          aria-labelledby="manifesto-title"
        >
          <div className="lp-container lp-manifesto">
            <div className="lp-manifesto-copy">
              <p className="lp-zero" aria-hidden="true">
                0%
              </p>
              <h2 id="manifesto-title">
                <span className="sr-only">0% </span>commission on every
                transaction. Always.
              </h2>
              <p className="lp-section-lead">
                You built the business. You keep what it earns. AMARKAL Platform
                is software for your business, not a toll booth between you and
                your customers.
              </p>
              <ul className="lp-principles">
                {PRINCIPLES.map((principle) => (
                  <li key={principle}>{principle}</li>
                ))}
              </ul>
            </div>
            <CommissionCalculator />
          </div>
        </section>

        <section
          id="architect"
          className="lp-section"
          aria-labelledby="architect-title"
        >
          <div className="lp-container lp-split">
            <div>
              <p className="lp-eyebrow">AI Business Architect</p>
              <h2 id="architect-title">
                Describe your business. Approve the setup.
              </h2>
              <p className="lp-section-lead">
                The AI Business Architect turns a few plain sentences, or a
                photo of your price list, into a setup you can review: services,
                prices, resources and opening hours. You approve every line
                before anything goes live.
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

        <section
          id="app-hub"
          className="lp-section lp-dark"
          aria-labelledby="app-hub-title"
        >
          <div className="lp-container lp-split lp-split--reverse">
            <div>
              <p className="lp-eyebrow">App Hub and MCP</p>
              <h2 id="app-hub-title">Connect what you need. Nothing else.</h2>
              <p className="lp-section-lead">
                The core stays focused on running your business. Messengers,
                chat and telephony are not built in: they connect through the
                AMARKAL App Hub with your own accounts, when you want them.
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

        <section className="lp-final" aria-labelledby="final-title">
          <div className="lp-container lp-final-inner">
            <h2 id="final-title">Open your business in minutes.</h2>
            <p className="lp-section-lead">
              Create a workspace, let the AI Business Architect draft your
              setup, and approve it when it looks right.
            </p>
            <div className="lp-cta-row">
              <Link
                href="/onboarding/"
                className="lp-btn lp-btn--primary lp-btn--lg"
              >
                Create your business
              </Link>
              <Link href="/book/" className="lp-btn lp-btn--outline lp-btn--lg">
                Open client portal
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer">
        <div className="lp-container lp-footer-inner">
          <p className="lp-footer-brand">AMARKAL Platform</p>
          <nav aria-label="Footer">
            <ul>
              <li>
                <Link href="/onboarding/">Create your business</Link>
              </li>
              <li>
                <Link href="/book/">Client portal</Link>
              </li>
              <li>
                <Link href="/overview/">Sign in</Link>
              </li>
              <li>
                <Link href="/integrations/">App Hub</Link>
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
