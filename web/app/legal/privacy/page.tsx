import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Privacy Policy — AMARKAL Platform",
  description: "Data protection, tenant isolation, and US privacy disclosures.",
};

export default function PrivacyPolicyPage() {
  return (
    <main
      className="mgmt-main"
      style={{ maxWidth: "820px", margin: "2rem auto" }}
    >
      <p>
        <Link href="/">← Back to AMARKAL Platform</Link> ·{" "}
        <Link href="/legal/terms/">Terms of Service</Link>
      </p>
      <h1>AMARKAL Platform Privacy Policy (United States)</h1>
      <p>
        <strong>Effective date:</strong> Pending Commercial Launch (Pre-Launch
        Draft for Legal Counsel Review)
      </p>

      <h2>1. Data We Process</h2>
      <p>
        We process business account records, staff identity links (OpenID
        Connect issuer/subject identifiers), operational records created by
        tenants, and customer contact details entered during service or order
        workflows.
      </p>

      <h2>2. Strict Multi-Tenant Isolation</h2>
      <p>
        Tenant data is isolated in PostgreSQL using enforced Row-Level Security
        (FORCE ROW LEVEL SECURITY) scoped per transaction. Access tokens are
        held in browser memory only and never persisted in localStorage.
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
        data controlled by each tenant business. Requests to access, correct, or
        delete personal data should be directed to the relevant business tenant
        or to the platform privacy contact listed prior to commercial launch. We
        do not sell personal information.
      </p>

      <h2>5. Security &amp; Retention</h2>
      <p>
        All production and staging traffic uses TLS 1.2+ behind Google Cloud
        Global HTTPS Load Balancer with Cloud Armor WAF, private Cloud SQL
        PostgreSQL 18, and Google Secret Manager. Audit logs record access and
        administrative mutations while excluding secrets and raw credentials.
      </p>
    </main>
  );
}
