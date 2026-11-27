import type { Metadata } from "next";
import { IndustryLandingTemplate } from "../../../components/industry-landing-template";

export const metadata: Metadata = {
  title:
    "Fleet, Equipment & Yacht Rental Business OS (NAICS 532) | AMARKAL Platform",
  description:
    "Serialized unit availability, conflict-free scheduling, B2B corporate quotes, deposits via Stripe US, and 0% commission for US rental operators.",
};

export default function EquipmentRentalPage() {
  return (
    <IndustryLandingTemplate
      spec={{
        slug: "equipment-rental",
        naicsLabel: "NAICS 532 · Equipment, Fleet & Charter Rental",
        defaultIndustryOption: "Equipment, Fleet & Yacht Rental (NAICS 532)",
        headline:
          "Conflict-Free Rental Fleet Operations with 0% Marketplace Tax.",
        subheadline:
          "Control serialized units, fleet classes, damage/problem reports, B2B corporate quotes, recurring equipment retainers, and direct Stripe USD deposits — keeping 100% of every dollar earned.",
        workflows: [
          {
            title: "Asset Classes & Conflict-Free Occupancy",
            detail:
              "PostgreSQL exclusion constraints guarantee zero double-bookings across heavy machinery, vehicles, vessels, and specialized tools.",
          },
          {
            title: "Rental Agreements, Changes & Problem Reports",
            detail:
              "Manage customer proposals, mid-rental extensions, condition reports, and structured settlement directly in one audit-trailed record.",
          },
          {
            title: "Corporate B2B Quotes & Recurring Contracts",
            detail:
              "Send multi-line corporate quotes with Net-30 terms via /portal/, or run monthly long-term equipment lease schedules automatically.",
          },
          {
            title: "Direct Stripe Connect Express Payouts",
            detail:
              "Collect deposits and balances by card, Apple Pay, or US ACH with 0% AMARKAL platform commission and live FIN-03 reconciliation.",
          },
        ],
        replaces: [
          "Commission-taking rental marketplaces",
          "Double-booked fleet calendars",
          "Manual PDF rental quotes",
          "Disconnected deposit tracking",
        ],
        faq: [
          {
            q: "How does AMARKAL prevent double-bookings on high-value units?",
            a: "Occupancy is enforced directly inside PostgreSQL 18 using GiST exclusion constraints — not fragile application-level checks.",
          },
          {
            q: "Can we combine equipment rental with service, transport, or maintenance?",
            a: "Yes. Every workspace can combine verified modules across all 39 NAICS industries in one unified account.",
          },
        ],
      }}
    />
  );
}
