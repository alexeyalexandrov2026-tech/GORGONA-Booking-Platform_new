import type { Metadata } from "next";
import Link from "next/link";
import { AmarkalLogo } from "../../components/amarkal-logo";
import { PartnerNetworkDirectory } from "../../components/partner-network-directory";
import "../landing.css";
import "../us-release-v2.css";

export const metadata: Metadata = {
  title: "Certified Partner & Integrator Network | AMARKAL Platform",
  description:
    "Find AMARKAL certified US ERP implementers, CPA holding consolidation advisors, Industrial MRP II / IoT integrators, and amarkal-plugin.json ISV developers — or apply to join the Partner Network.",
  alternates: { canonical: "https://www.amarkal-platform.com/partners/" },
  openGraph: {
    title: "Certified Partner & Integrator Network | AMARKAL Platform",
    description:
      "Turnkey US implementation practices, 3-tier partner certification, multi-client Agency Console, and 0% commission on partner retainers.",
    url: "https://www.amarkal-platform.com/partners/",
    siteName: "AMARKAL Platform",
    type: "website",
  },
  robots: { index: true, follow: true },
};

export default function PartnersPage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "AMARKAL Platform Certified Partner & Integrator Network",
    url: "https://www.amarkal-platform.com/partners/",
    publisher: {
      "@type": "Organization",
      name: "Alexey AAA Logistics LLC",
      url: "https://www.amarkal-platform.com/",
    },
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
          <nav className="lp-nav" aria-label="Partner Network navigation">
            <ul>
              <li>
                <Link href="/security/">Trust &amp; Security</Link>
              </li>
              <li>
                <Link href="/compare/netsuite/">vs NetSuite</Link>
              </li>
              <li>
                <Link href="/compare/odoo/">vs Odoo</Link>
              </li>
              <li>
                <Link href="/partners/">Partners</Link>
              </li>
            </ul>
          </nav>
          <div className="lp-header-actions">
            <Link href="/auth/signin/" className="lp-btn lp-btn--ghost">
              Sign in
            </Link>
            <Link href="/onboarding/" className="lp-btn lp-btn--primary">
              Create business
            </Link>
          </div>
        </div>
      </header>

      <main id="main-content">
        <section className="lp-section lp-section--tint">
          <div className="lp-container">
            <div className="usr-inline" style={{ marginBottom: "12px" }}>
              <span className="usr-badge usr-badge-ai">
                AMARKAL ECOSYSTEM · 39 NAICS US INDUSTRIES
              </span>
              <span className="usr-badge">MULTI-CLIENT AGENCY CONSOLE</span>
              <span className="usr-badge">0% RETAINER COMMISSION</span>
            </div>
            <h1 style={{ marginTop: 0, marginBottom: "12px" }}>
              Certified Partner &amp; Integrator Network
            </h1>
            <p
              className="lp-section-lead"
              style={{ marginTop: 0, maxWidth: "760px" }}
            >
              Launch AMARKAL yourself in minutes with AI Business Architect — or
              work with certified US ERP consultants, CPA consolidation firms,
              and systems integrators for turnkey NetSuite/Odoo/QuickBooks
              migrations and bespoke <code>amarkal-plugin.json</code>{" "}
              extensions.
            </p>
            <div className="usr-inline" style={{ marginTop: "16px" }}>
              <a href="#partner-apply" className="button usr-small-btn">
                Apply as a Partner / Integrator
              </a>
              <Link
                href="/onboarding/"
                className="button secondary usr-small-btn"
              >
                Self-Deploy in Minutes →
              </Link>
            </div>
          </div>
        </section>

        <section className="lp-section">
          <div className="lp-container">
            <PartnerNetworkDirectory />
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
                <Link href="/compare/netsuite/">vs NetSuite</Link>
              </li>
              <li>
                <Link href="/compare/odoo/">vs Odoo</Link>
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
