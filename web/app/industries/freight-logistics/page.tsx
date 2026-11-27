import type { Metadata } from "next";
import { IndustryLandingTemplate } from "../../../components/industry-landing-template";

export const metadata: Metadata = {
  title:
    "Freight, Dispatch & Logistics Business OS (NAICS 48-49) | AMARKAL Platform",
  description:
    "Run US freight dispatch, carrier brokerage, BOL documents, B2B quotes, vendor PO 3-way match, and USD double-entry accounting with 0% commission.",
};

export default function FreightLogisticsPage() {
  return (
    <IndustryLandingTemplate
      spec={{
        slug: "freight-logistics",
        naicsLabel: "NAICS 48-49 · Freight & Logistics",
        defaultIndustryOption: "Transport & Logistics (NAICS 48-49)",
        headline:
          "The Business OS for US Freight Carriers, Dispatchers & Brokers.",
        subheadline:
          "Manage loads, trips, driver HOS & assignments, broker carrier tenders, B2B CPQ lane quotes, 3-way vendor fuel/maintenance matching, and direct Stripe ACH settlement — with 0% AMARKAL commission.",
        workflows: [
          {
            title: "Dispatch, Trips & Stop Events",
            detail:
              "Track multi-leg loads, drivers, trucks, HOS compliance, and live stop quantities under strict multi-tenant PostgreSQL 18 isolation.",
          },
          {
            title: "Brokerage Tenders & Rate Confirmations",
            detail:
              "Publish carrier tenders, record carrier rate confirmation answers, and accrue carrier pay cleanly without spreadsheets.",
          },
          {
            title: "Deal-to-Cash CPQ & B2B Portal",
            detail:
              "Send Net-30 freight lane quotes via email, let shippers sign electronically and download PDF on /portal/, and convert to USD Stripe ACH links.",
          },
          {
            title: "PO 3-Way Match & AR/AP Aging",
            detail:
              "Match fleet maintenance and fuel purchase orders against receipts and vendor bills, monitor aging buckets, and export clean CSV for your CPA.",
          },
        ],
        replaces: [
          "Disconnected TMS spreadsheets",
          "Separate quoting & PDF tools",
          "Manual vendor bill reconciliation",
          "High-fee invoice payment portals",
        ],
        faq: [
          {
            q: "Does AMARKAL charge a percentage commission on freight invoices?",
            a: "No. AMARKAL Platform charges 0% transaction commission. Payments settle directly to your US business bank account via Stripe Connect Express (cards, Apple Pay, or US ACH).",
          },
          {
            q: "Can we connect QuickBooks Online or Slack optionally?",
            a: "Yes. QuickBooks Online, Xero, Slack, and custom webhooks are strictly optional connectors inside App Hub — never forced into your core workflow.",
          },
        ],
      }}
    />
  );
}
