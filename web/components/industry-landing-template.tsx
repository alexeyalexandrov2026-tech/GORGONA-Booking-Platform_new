import Link from "next/link";
import { AmarkalLogo } from "./amarkal-logo";
import { B2bDemoRequestForm } from "./b2b-demo-request-form";
import "../app/landing.css";
import "../app/us-release-v2.css";

export interface IndustryPageSpec {
  slug: string;
  naicsLabel: string;
  defaultIndustryOption: string;
  headline: string;
  subheadline: string;
  workflows: ReadonlyArray<{ title: string; detail: string }>;
  replaces: readonly string[];
  faq: ReadonlyArray<{ q: string; a: string }>;
}

export function IndustryLandingTemplate({ spec }: { spec: IndustryPageSpec }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: `AMARKAL Platform for ${spec.naicsLabel}`,
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    url: `https://www.amarkal-platform.com/industries/${spec.slug}/`,
    provider: {
      "@type": "Organization",
      name: "Alexey AAA Logistics LLC",
      url: "https://www.amarkal-platform.com/",
    },
    description: spec.subheadline,
  };

  return (
    <div className="lp">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <header className="lp-header-bar">
        <div className="lp-header lp-container">
          <Link href="/" className="lp-brand" aria-label="AMARKAL Platform">
            <AmarkalLogo variant="light" height={22} />
          </Link>
          <nav className="lp-nav" aria-label="Industry navigation">
            <ul>
              <li>
                <Link href="/#industries">All 39 Industries</Link>
              </li>
              <li>
                <Link href="/portal/?demo=1">B2B Portal</Link>
              </li>
              <li>
                <Link href="/status/">Status</Link>
              </li>
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
              Launch Workspace
            </Link>
          </div>
        </div>
      </header>

      <main id="main-content">
        <section className="lp-section">
          <div className="lp-container">
            <p className="lp-mono">{spec.naicsLabel} · AMARKAL Business OS</p>
            <h1 style={{ maxWidth: "820px", marginTop: "8px" }}>
              {spec.headline}
            </h1>
            <p className="lp-section-lead" style={{ maxWidth: "740px" }}>
              {spec.subheadline}
            </p>
            <div className="usr-inline" style={{ marginTop: "24px" }}>
              <Link href="/onboarding/" className="lp-btn lp-btn--primary">
                Generate Blueprint with AI Architect →
              </Link>
              <Link href="/portal/?demo=1" className="lp-btn lp-btn--ghost">
                Preview B2B Quote Portal
              </Link>
              <Link href="/book/?demo=1" className="lp-btn lp-btn--ghost">
                Interactive Demo
              </Link>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section--tint">
          <div className="lp-container">
            <p className="lp-mono">Production-Verified Capabilities</p>
            <h2>One isolated Business OS — 0% transaction commission</h2>
            <div className="usr-connector-grid" style={{ marginTop: "20px" }}>
              {spec.workflows.map((wf) => (
                <article className="usr-connector" key={wf.title}>
                  <h3>{wf.title}</h3>
                  <p className="usr-muted">{wf.detail}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-section">
          <div className="lp-container">
            <p className="lp-mono">Consolidate Your Stack</p>
            <h2>Built to replace fragmented legacy tools</h2>
            <p className="lp-section-lead">
              Every organization runs under PostgreSQL 18{" "}
              <code>FORCE ROW LEVEL SECURITY</code>, owns its data with 1-click
              JSON/CPA CSV export, and connects external tools strictly
              optionally through App Hub.
            </p>
            <ul
              className="lp-connectors"
              aria-label="Consolidated capabilities"
            >
              {spec.replaces.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>

            <div style={{ marginTop: "40px" }}>
              <h2>Frequently Asked Questions</h2>
              <div className="usr-stack" style={{ marginTop: "16px" }}>
                {spec.faq.map((entry) => (
                  <div className="usr-card" key={entry.q} style={{ margin: 0 }}>
                    <h3 style={{ margin: "0 0 6px" }}>{entry.q}</h3>
                    <p className="usr-muted" style={{ margin: 0 }}>
                      {entry.a}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section--tint" id="demo-request">
          <div className="lp-container">
            <B2bDemoRequestForm
              defaultIndustry={spec.defaultIndustryOption}
              sourcePath={`/industries/${spec.slug}/`}
            />
          </div>
        </section>
      </main>

      <footer className="mgmt-footer">
        <span>AMARKAL Platform · Alexey AAA Logistics LLC</span>
        <Link href="/">Home (All 39 Industries)</Link>
        <Link href="/status/">System Status</Link>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}
