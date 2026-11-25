import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms of Service — GORGONA Platform",
  description:
    "Terms of Service and regulated-industry disclosures for US operation.",
};

export default function TermsOfServicePage() {
  return (
    <main
      className="mgmt-main"
      style={{ maxWidth: "820px", margin: "2rem auto" }}
    >
      <p>
        <Link href="/">← Back to GORGONA</Link> ·{" "}
        <Link href="/legal/privacy/">Privacy Policy</Link>
      </p>
      <h1>GORGONA Platform Terms of Service (United States)</h1>
      <p>
        <strong>Effective date:</strong> Pending Commercial Launch (Pre-Launch
        Draft for Legal Counsel Review)
      </p>

      <h2>1. Platform Scope and Independent Tenants</h2>
      <p>
        GORGONA provides multi-tenant business management software covering
        scheduling, counterparties, internal financial documents, inventory,
        workforce operations, and industry-specific operational modules. Each
        registered company operates as an independent tenant responsible for its
        own customer relationships, pricing, taxes, contracts, and statutory
        obligations.
      </p>

      <h2>2. Storefronts and Marketplaces (Non-Custodial)</h2>
      <p>
        GORGONA does not act as a merchant of record, escrow agent, money
        transmitter, or broker for transactions between tenants and their
        customers. Payment processing is provided solely by third-party payment
        processors (such as Stripe Connect) under the tenant&apos;s direct
        agreement with that processor.
      </p>

      <h2>
        3. Regulated-Industry Disclosures (No Unverified Compliance Claims)
      </h2>
      <ul>
        <li>
          <strong>Healthcare, Veterinary, and Social Care:</strong> Unless and
          until GORGONA executes a written Business Associate Agreement (BAA)
          and completes independent HIPAA compliance verification, tenants MUST
          NOT store Protected Health Information (PHI) regulated under HIPAA on
          the platform.
        </li>
        <li>
          <strong>Financial, Legal, Tax, and Public Administration:</strong>{" "}
          GORGONA internal ledgers, invoices, and case workflows are operational
          records and do not constitute certified tax filing, statutory
          accounting, legal advice, or FedRAMP/StateRAMP-authorized government
          systems.
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
        These Terms are governed by applicable United States federal law and the
        laws of the State of Delaware (subject to final corporate entity
        registration prior to commercial launch).
      </p>
    </main>
  );
}
