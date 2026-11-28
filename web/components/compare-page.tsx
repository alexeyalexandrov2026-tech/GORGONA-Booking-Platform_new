import Link from "next/link";
import { AmarkalLogo } from "./amarkal-logo";
import { B2bDemoRequestForm } from "./b2b-demo-request-form";
import {
  ALL_COMPETITOR_SLUGS,
  COMPETITORS,
  type CompetitorSpec,
} from "./landing/competitors";
import "../app/landing.css";
import "../app/us-release-v2.css";

export function ComparePageTemplate({ spec }: { spec: CompetitorSpec }) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebPage",
        name: spec.seoTitle,
        url: `https://www.amarkal-platform.com/compare/${spec.slug}/`,
        description: spec.seoDescription,
      },
      {
        "@type": "FAQPage",
        mainEntity: spec.faq.map((item) => ({
          "@type": "Question",
          name: item.q,
          acceptedAnswer: {
            "@type": "Answer",
            text: item.a,
          },
        })),
      },
    ],
  };

  return (
    <div className="lp">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <a className="skip" href="#main-content">
        Skip to content
      </a>

      <header className="lp-header-shell">
        <div className="lp-header lp-container">
          <Link href="/" className="lp-brand" aria-label="AMARKAL Platform">
            <AmarkalLogo variant="light" height={22} />
          </Link>
          <nav className="lp-nav" aria-label="Comparison navigation">
            <ul>
              <li>
                <Link href="/#platform">Platform</Link>
              </li>
              <li>
                <Link href="/security/">Trust &amp; Security</Link>
              </li>
              <li>
                <Link href="/shop/?demo=1">B2C Shop Demo</Link>
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
              Create your business
            </Link>
          </div>
        </div>
      </header>

      <main id="main-content">
        <section className="lp-section">
          <div className="lp-container">
            <p className="lp-mono">
              AMARKAL Platform vs {spec.name} · 0% Commission US Business OS
            </p>
            <h1 style={{ maxWidth: 880, marginTop: 8 }}>{spec.headline}</h1>
            <p className="lp-section-lead" style={{ maxWidth: 760 }}>
              {spec.subheadline}
            </p>
            <div className="usr-inline" style={{ marginTop: 24 }}>
              <Link href="/onboarding/" className="lp-btn lp-btn--primary">
                Launch Workspace &amp; Import CSV →
              </Link>
              <Link href="/shop/?demo=1" className="lp-btn lp-btn--outline">
                Try Live B2C Shop Demo
              </Link>
              <Link href="/security/" className="lp-btn lp-btn--link">
                Review Security Architecture ›
              </Link>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section--tint">
          <div className="lp-container">
            <p className="lp-mono">Why US Operators Switch</p>
            <h2>Key advantages over {spec.name}</h2>
            <ul className="lp-checks" style={{ marginTop: 18 }}>
              {spec.whySwitch.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          </div>
        </section>

        <section className="lp-section">
          <div className="lp-container">
            <p className="lp-mono">Capability Comparison</p>
            <h2>AMARKAL Platform vs {spec.name} side by side</h2>
            <div
              style={{ overflowX: "auto", marginTop: 20 }}
              tabIndex={0}
              role="region"
              aria-label={`AMARKAL Platform vs ${spec.name} comparison table`}
            >
              <table className="usr-table">
                <thead>
                  <tr>
                    <th scope="col">Capability</th>
                    <th scope="col">AMARKAL Platform</th>
                    <th scope="col">{spec.name}</th>
                  </tr>
                </thead>
                <tbody>
                  {spec.rows.map((row) => (
                    <tr key={row.capability}>
                      <td>
                        <strong>{row.capability}</strong>
                      </td>
                      <td>{row.amarkal}</td>
                      <td>{row.competitor}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div style={{ marginTop: 40 }}>
              <h2>Frequently Asked Questions</h2>
              <div className="usr-stack" style={{ marginTop: 16 }}>
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

            <div style={{ marginTop: 40 }}>
              <p className="lp-mono" style={{ marginBottom: 10 }}>
                Explore Other Comparisons
              </p>
              <div className="usr-inline">
                {ALL_COMPETITOR_SLUGS.filter((s) => s !== spec.slug).map(
                  (slug) => (
                    <Link
                      key={slug}
                      href={`/compare/${slug}/`}
                      className="lp-btn lp-btn--outline lp-btn--sm"
                    >
                      AMARKAL vs {COMPETITORS[slug].name} →
                    </Link>
                  ),
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section--tint" id="demo-request">
          <div className="lp-container">
            <B2bDemoRequestForm sourcePath={`/compare/${spec.slug}/`} />
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
                <Link href="/">Home</Link>
              </li>
              <li>
                <Link href="/security/">Trust &amp; Security</Link>
              </li>
              <li>
                <Link href="/shop/?demo=1">B2C Shop Demo</Link>
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
