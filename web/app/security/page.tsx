import type { Metadata } from "next";
import Link from "next/link";
import { AmarkalLogo } from "../../components/amarkal-logo";
import { B2bDemoRequestForm } from "../../components/b2b-demo-request-form";
import "../landing.css";
import "../us-release-v2.css";

export const metadata: Metadata = {
  title: "Trust & Security Center | AMARKAL Platform",
  description:
    "How AMARKAL Platform protects US business data: PostgreSQL 18 FORCE Row-Level Security, AES-256-GCM BYOK Vaults, zero AI model training on customer data, and strict Human-in-the-Loop financial guardrails.",
  alternates: { canonical: "https://www.amarkal-platform.com/security/" },
  openGraph: {
    title: "Trust & Security Center | AMARKAL Platform",
    description:
      "Enterprise tenant isolation, AES-256-GCM BYOK secret vault, zero AI training on tenant data, and verifiable audit trails.",
    url: "https://www.amarkal-platform.com/security/",
    siteName: "AMARKAL Platform",
    type: "website",
  },
  robots: { index: true, follow: true },
};

const PILLARS = [
  {
    code: "01 · DATABASE ISOLATION",
    title: "PostgreSQL 18 ENABLE + FORCE Row-Level Security",
    detail:
      "Every tenant table carries mandatory PostgreSQL 18 FORCE RLS policies executed under the least-privilege gba_runtime role (zero SECURITY DEFINER bypasses). Cross-company queries are statically rejected by automated CI guards before code ever ships.",
  },
  {
    code: "02 · SECRET VAULT & BYOK AI",
    title: "Per-Tenant AES-256-GCM Vault & Zero AI Training",
    detail:
      "Optional Anthropic, Google Gemini, OpenAI, and Microsoft 365 credentials are encrypted at rest per tenant using authenticated AES-256-GCM. Your operational records are never used to train foundation models.",
  },
  {
    code: "03 · HYBRID AI GOVERNANCE",
    title: "Hard $0.00 Human-in-the-Loop Financial Guardrail",
    detail:
      "Hybrid Smart Autonomy lets safe, reversible routine tasks run automatically, while every payment, refund, Purchase Order approval, US payroll export, and contract signature permanently requires explicit human sign-off.",
  },
  {
    code: "04 · NETWORK & WEBHOOK DEFENSE",
    title: "SSRF Protection, HMAC-SHA256 & Malware Scanning",
    detail:
      "All outbound webhooks enforce HTTPS-only public DNS resolution (blocking localhost, private ranges, and cloud metadata IPs), sign payloads with HMAC-SHA256, and uploaded files are scanned via an isolated malware-scanner service.",
  },
  {
    code: "05 · IMMUTABLE AUDITABILITY",
    title: "Double-Entry Ledger & Versioned Contracts",
    detail:
      "Financial documents follow strict double-entry accounting (DR = CR), agreements and counterparties preserve immutable revision histories, and every autonomous or human-approved AI action is logged with rollback support.",
  },
  {
    code: "06 · ZERO VENDOR LOCK-IN",
    title: "1-Click Data Portability & 0% Commission",
    detail:
      "Export your records to JSON or RFC-4180 CSV (with spreadsheet formula-injection neutralization) anytime. Payments settle directly through your own Stripe US account with 0% AMARKAL take-rate.",
  },
] as const;

const CONTROLS = [
  {
    domain: "Multi-Tenant Isolation",
    control: "PostgreSQL 18 ENABLE + FORCE RLS on every tenant table",
    verification: "Automated RLS & cross-tenant SQL suite on every commit",
  },
  {
    domain: "Encryption in Transit & Rest",
    control:
      "TLS 1.3 via Google Cloud Load Balancer + AES-256-GCM Secret Vault",
    verification: "Zero plaintext secret storage; masked UI key prefixes",
  },
  {
    domain: "Authentication & RBAC",
    control:
      "OIDC / Google Identity Federation + Branch-Scoped Role Permissions",
    verification: "Server-side permission checks inside authorized_tenant TX",
  },
  {
    domain: "AI Safety & Privacy",
    control:
      "Read-only grounded Copilot + Hard $0.00 Human Financial Guardrail",
    verification: "Zero LLM calls inside DB transactions; optional BYOK keys",
  },
  {
    domain: "US & Global Compliance",
    control:
      "CCPA/CPRA & GDPR DPA readiness, FLSA/CA §510 Payroll Prep, EU/UK VAT",
    verification:
      "Published Terms, Privacy Policy & live /status/ uptime probe",
  },
  {
    domain: "Inbound & Outbound Integrations",
    control: "SHA-256 hashed IoT/Inbox tokens, Scoped 11-tool MCP, SSRF Guard",
    verification:
      "One-time token display with instant key rotation & rate limits",
  },
] as const;

export default function SecurityTrustCenterPage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "AMARKAL Platform Trust & Security Center",
    url: "https://www.amarkal-platform.com/security/",
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
          <nav className="lp-nav" aria-label="Trust Center navigation">
            <ul>
              <li>
                <Link href="/#platform">Platform</Link>
              </li>
              <li>
                <Link href="/compare/zoho-one/">Compare</Link>
              </li>
              <li>
                <Link href="/status/">Live Status</Link>
              </li>
              <li>
                <Link href="/legal/privacy/">Privacy</Link>
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
            <p className="lp-mono">Enterprise Trust &amp; Security Center</p>
            <h1 style={{ maxWidth: 860, marginTop: 8 }}>
              Engineered for isolation, auditable AI, and zero vendor lock-in.
            </h1>
            <p className="lp-section-lead" style={{ maxWidth: 740 }}>
              AMARKAL Platform is operated by Alexey AAA Logistics LLC on Google
              Cloud Platform (US regions). Security is enforced at the database
              engine level — never left to UI conventions.
            </p>
            <div className="usr-inline" style={{ marginTop: 24 }}>
              <Link href="/status/" className="lp-btn lp-btn--primary">
                Inspect Live System Status →
              </Link>
              <Link href="/onboarding/" className="lp-btn lp-btn--outline">
                Launch Isolated Workspace
              </Link>
              <Link href="/legal/privacy/" className="lp-btn lp-btn--link">
                Read Privacy Policy ›
              </Link>
            </div>
          </div>
        </section>

        <section className="lp-section lp-section--tint">
          <div className="lp-container">
            <p className="lp-mono">Six Security Foundations</p>
            <h2>Verifiable controls across database, AI, and payments</h2>
            <div className="usr-connector-grid" style={{ marginTop: 24 }}>
              {PILLARS.map((item) => (
                <article key={item.code} className="usr-connector">
                  <span className="lp-mono">{item.code}</span>
                  <h3 style={{ marginTop: 6 }}>{item.title}</h3>
                  <p className="usr-muted">{item.detail}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="lp-section">
          <div className="lp-container">
            <p className="lp-mono">Security &amp; Compliance Matrix</p>
            <h2>Built for enterprise procurement and IT review</h2>
            <div
              style={{ overflowX: "auto", marginTop: 20 }}
              tabIndex={0}
              role="region"
              aria-label="Security controls matrix"
            >
              <table className="usr-table">
                <thead>
                  <tr>
                    <th scope="col">Security Domain</th>
                    <th scope="col">Implemented Architecture</th>
                    <th scope="col">Continuous Verification</th>
                  </tr>
                </thead>
                <tbody>
                  {CONTROLS.map((row) => (
                    <tr key={row.domain}>
                      <td>
                        <strong>{row.domain}</strong>
                      </td>
                      <td>{row.control}</td>
                      <td>{row.verification}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="usr-muted" style={{ marginTop: 16 }}>
              Need a security questionnaire review, DPA, or architecture
              briefing for your IT/legal team? Contact{" "}
              <a href="mailto:support@amarkal-platform.com">
                support@amarkal-platform.com
              </a>{" "}
              or request a guided walkthrough below.
            </p>
          </div>
        </section>

        <section className="lp-section lp-section--tint" id="demo-request">
          <div className="lp-container">
            <B2bDemoRequestForm sourcePath="/security/" />
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
                <Link href="/status/">System Status</Link>
              </li>
              <li>
                <Link href="/compare/zoho-one/">Compare Competitors</Link>
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
