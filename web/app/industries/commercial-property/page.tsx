import type { Metadata } from "next";
import { IndustryLandingTemplate } from "../../../components/industry-landing-template";

export const metadata: Metadata = {
  title:
    "Commercial & Residential Property Management OS (NAICS 53) | AMARKAL Platform",
  description:
    "Manage property portfolios, leases, recurring rent schedules, contractor maintenance work orders, and USD ledger accounting with 0% commission.",
};

export default function CommercialPropertyPage() {
  return (
    <IndustryLandingTemplate
      spec={{
        slug: "commercial-property",
        naicsLabel: "NAICS 53 · Property & Real Estate Operations",
        defaultIndustryOption: "Commercial & Residential Property (NAICS 53)",
        headline:
          "Portfolio Leases, Maintenance Dispatch & Recurring Billing Unified.",
        subheadline:
          "Run commercial and residential property portfolios on one Business OS: units, showings, lease terms, contractor work orders, monthly recurring billing schedules, and AR/AP aging.",
        workflows: [
          {
            title: "Units, Listings & Showings",
            detail:
              "Track property portfolios, available units, lease lifecycles, and scheduled prospect showings without per-unit marketplace surcharges.",
          },
          {
            title: "Contractor Work Orders & Vendor POs",
            detail:
              "Assign maintenance requests to vetted contractors, issue purchase orders with approval thresholds, and verify vendor invoices via 3-way match.",
          },
          {
            title: "Recurring Lease & CAM Billing",
            detail:
              "Automate monthly or quarterly rent and CAM schedules, email tenants secure portal links, and collect USD ACH directly into your bank.",
          },
          {
            title: "Owner-Ready AR/AP Aging & Double-Entry Ledger",
            detail:
              "Monitor overdue balances by aging bucket (Current through 90+ days) and hand clean CSV schedules to your CPA or property owners.",
          },
        ],
        replaces: [
          "Legacy property fee-heavy portals",
          "Spreadsheet maintenance trackers",
          "Manual monthly CAM invoicing",
          "Disconnected owner accounting",
        ],
        faq: [
          {
            q: "Does AMARKAL support multi-entity property holdings?",
            a: "Yes. Manage multiple legal entities and locations under one roof with strict tenant isolation and enterprise group reporting.",
          },
          {
            q: "Can external maintenance contractors access only their assigned jobs?",
            a: "Yes. Scoped contractor workflows and tokenized vendor links expose strictly the assigned job or PO — never tenant financials.",
          },
        ],
      }}
    />
  );
}
