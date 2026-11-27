import type { Metadata } from "next";
import Link from "next/link";
import { AmarkalLogo } from "../../../components/amarkal-logo";

export const metadata: Metadata = {
  title: "Privacy Policy — AMARKAL Platform",
  description: "Data protection, tenant isolation, and US privacy disclosures.",
  robots: { index: true, follow: true },
};

export default function PrivacyPolicyPage() {
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
          <Link href="/legal/terms/" className="mgmt-nav-link">
            Terms of Service
          </Link>
          <Link href="/auth/signin/" className="mgmt-nav-link">
            Sign in
          </Link>
        </div>
      </header>
      <main
        id="main-content"
        className="mgmt-main"
        style={{ maxWidth: "820px", margin: "2rem auto" }}
      >
        <p style={{ marginTop: 0 }}>
          <Link href="/" className="legal-inline-link">
            ← Back to AMARKAL Platform
          </Link>{" "}
          ·{" "}
          <Link href="/legal/terms/" className="legal-inline-link">
            Terms of Service
          </Link>
        </p>
        <h1>AMARKAL Platform Privacy Policy (United States)</h1>
        <p>
          <strong>Effective date:</strong> November 26, 2026
          <br />
          <strong>Operator:</strong> Alexey AAA Logistics LLC (doing business as{" "}
          <strong>AMARKAL Platform</strong>)
          <br />
          <strong>Privacy &amp; legal contact:</strong>{" "}
          <a
            href="mailto:legal@amarkal-platform.com"
            className="legal-inline-link"
          >
            legal@amarkal-platform.com
          </a>
          {" · "}
          <strong>Support:</strong>{" "}
          <a
            href="mailto:support@amarkal-platform.com"
            className="legal-inline-link"
          >
            support@amarkal-platform.com
          </a>
        </p>

        <h2>1. Data We Process</h2>
        <p>
          We process business account records, staff identity links (Google
          Cloud Identity / OpenID Connect issuer and subject identifiers),
          operational records created by tenants, payment session references
          processed via Stripe, and customer contact details entered during
          service or order workflows.
        </p>

        <h2>2. Strict Multi-Tenant Isolation</h2>
        <p>
          Tenant data is isolated in PostgreSQL using enforced Row-Level
          Security (FORCE ROW LEVEL SECURITY) scoped per transaction. Access
          tokens are held in browser memory only and never persisted in
          localStorage.
        </p>

        <h2>3. AI Learning Plane &amp; Contact Data Redaction</h2>
        <p>
          Non-production data never enters AI training pipelines. Evidence
          envelopes are tenant-isolated, require explicit learning scope and
          provenance, and automatically reject or redact direct contact fields
          (email addresses and phone numbers).
        </p>

        <h2>4. US State Privacy Rights (CCPA/CPRA and Similar Laws)</h2>
        <p>
          AMARKAL Platform acts as a service provider / processor for customer
          data controlled by each tenant business. Requests to access, correct,
          or delete personal data should be directed to the relevant business
          tenant or to our privacy contact at{" "}
          <a
            href="mailto:legal@amarkal-platform.com"
            className="legal-inline-link"
          >
            legal@amarkal-platform.com
          </a>
          . We do not sell personal information.
        </p>

        <h2>5. Security &amp; Retention</h2>
        <p>
          All production traffic uses TLS 1.2+ behind Google Cloud Global HTTPS
          Load Balancer with Cloud Armor WAF, private Cloud SQL PostgreSQL 18,
          and Google Secret Manager. Audit logs record access and administrative
          mutations while excluding secrets and raw credentials.
        </p>
      </main>
      <footer className="mgmt-footer">
        <span>© 2026 Alexey AAA Logistics LLC — AMARKAL Platform</span>
        <Link href="/onboarding/">Register business</Link>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}
