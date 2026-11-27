import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service — AMARKAL Platform",
  description:
    "Terms of Service and regulated-industry disclosures for US operation.",
  robots: { index: true, follow: true },
};

export default function TermsOfServicePage() {
  return (
    <div className="management-shell">
      <header className="mgmt-header">
        <div className="mgmt-brand-area">
          <Link href="/" className="mgmt-brand">
            AMARKAL <span>Platform</span>
          </Link>
        </div>
        <div className="mgmt-header-actions">
          <Link href="/" className="mgmt-nav-link">
            Home
          </Link>
          <Link href="/legal/privacy/" className="mgmt-nav-link">
            Privacy Policy
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
          <Link href="/legal/privacy/" className="legal-inline-link">
            Privacy Policy
          </Link>
        </p>
        <h1>AMARKAL Platform Terms of Service (United States)</h1>
        <p>
          <strong>Effective date:</strong> November 26, 2026
          <br />
          <strong>Operator:</strong> Alexey AAA logistics LLC (doing business as{" "}
          <strong>AMARKAL Platform</strong>)
          <br />
          <strong>Support:</strong>{" "}
          <a
            href="mailto:support@amarkal-platform.com"
            className="legal-inline-link"
          >
            support@amarkal-platform.com
          </a>
          {" · "}
          <strong>Legal:</strong>{" "}
          <a
            href="mailto:legal@amarkal-platform.com"
            className="legal-inline-link"
          >
            legal@amarkal-platform.com
          </a>
        </p>

        <h2>1. Platform Scope and Independent Tenants</h2>
        <p>
          AMARKAL Platform provides multi-tenant business management software
          covering scheduling, counterparties, internal financial documents,
          inventory, workforce operations, and industry-specific operational
          modules. Each registered company operates as an independent tenant
          responsible for its own customer relationships, pricing, taxes,
          contracts, and statutory obligations.
        </p>

        <h2>2. Storefronts and Marketplaces (Non-Custodial)</h2>
        <p>
          AMARKAL Platform does not act as a merchant of record, escrow agent,
          money transmitter, or broker for transactions between tenants and
          their customers. Payment processing is provided solely by third-party
          payment processors (such as Stripe) under the tenant&apos;s direct
          agreement with that processor.
        </p>

        <h2>
          3. Regulated-Industry Disclosures (No Unverified Compliance Claims)
        </h2>
        <ul>
          <li>
            <strong>Healthcare, Veterinary, and Social Care:</strong> Unless and
            until AMARKAL Platform executes a written Business Associate
            Agreement (BAA) and completes independent HIPAA compliance
            verification, tenants MUST NOT store Protected Health Information
            (PHI) regulated under HIPAA on the platform.
          </li>
          <li>
            <strong>Financial, Legal, Tax, and Public Administration:</strong>{" "}
            AMARKAL Platform internal ledgers, invoices, and case workflows are
            operational records and do not constitute certified tax filing,
            statutory accounting, legal advice, or FedRAMP/StateRAMP-authorized
            government systems.
          </li>
          <li>
            <strong>Module Readiness:</strong> Only modules marked technically
            verified and explicitly enabled by a business owner are active.
            Unverified modules remain disabled.
          </li>
        </ul>

        <h2>4. Acceptable Use, Security, and Account Responsibility</h2>
        <p>
          Tenants must maintain accurate staff access grants, promptly revoke
          departed staff memberships, and refrain from attempting cross-tenant
          access, automated abuse, or unlawful data processing.
        </p>

        <h2>5. Governing Law</h2>
        <p>
          These Terms are governed by applicable United States federal law and
          the laws of the State of Delaware, without regard to conflict-of-laws
          principles.
        </p>
      </main>
      <footer className="mgmt-footer">
        <span>© 2026 Alexey AAA logistics LLC — AMARKAL Platform</span>
        <Link href="/onboarding/">Register business</Link>
        <Link href="/legal/terms/">Terms of Service</Link>
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </footer>
    </div>
  );
}
