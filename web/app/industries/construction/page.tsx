import type { Metadata } from "next";
import { IndustryLandingTemplate } from "../../../components/industry-landing-template";

export const metadata: Metadata = {
  title:
    "Construction & Field Services Business OS (NAICS 23) | AMARKAL Platform",
  description:
    "Estimates, change orders, subcontractor commitments, 3-way PO matching, progress billing, and FIN-03 accounting for US contractors.",
};

export default function ConstructionIndustryPage() {
  return (
    <IndustryLandingTemplate
      spec={{
        slug: "construction",
        naicsLabel: "NAICS 23 · Construction & Field Services",
        defaultIndustryOption: "Construction & Field Services (NAICS 23)",
        headline:
          "Estimates, Change Orders, Job Costing & 3-Way Match in One OS.",
        subheadline:
          "Give general contractors and trade teams one authoritative system from client proposal and change-order sign-off to subcontractor POs, daily site logs, and USD progress billing.",
        workflows: [
          {
            title: "Estimates & Client Change Orders",
            detail:
              "Versioned project estimates, customer-facing change order approvals, and formal work acceptance receipts with zero internal cost leakage.",
          },
          {
            title: "Subcontractor POs & 3-Way Match",
            detail:
              "Issue purchase orders to material suppliers and subcontractors, record site deliveries, and automatically flag vendor bill variances.",
          },
          {
            title: "Workforce Shifts & Timesheets",
            detail:
              "Coordinate field crews across locations, track approved timesheets, and tie labor and material consumption directly to project margins.",
          },
          {
            title: "Direct US ACH & FIN-03 Ledger",
            detail:
              "Collect large milestone draws via US Bank ACH with 0% AMARKAL fee, backed by double-entry FIN-03 accounting and CPA CSV exports.",
          },
        ],
        replaces: [
          "Disconnected estimating spreadsheets",
          "Paper change-order approvals",
          "Manual subcontractor bill checking",
          "Separate timesheet & billing apps",
        ],
        faq: [
          {
            q: "Can clients approve proposals and change orders without creating an account?",
            a: "Yes. Both construction customer links and the B2B /portal/ use cryptographically hashed one-time tokens under PostgreSQL FORCE RLS.",
          },
          {
            q: "Are approval thresholds configurable for large material POs?",
            a: "Yes. Configure USD approval policies separately for Sales Quotes and Purchase Orders in Commercial & Procurement.",
          },
        ],
      }}
    />
  );
}
