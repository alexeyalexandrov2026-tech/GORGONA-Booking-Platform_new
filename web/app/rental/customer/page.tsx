import type { Metadata } from "next";
import { Suspense } from "react";
import { RentalProposalPage } from "./proposal";
import "../../construction/customer/proposal.css";

export const metadata: Metadata = { title: "Rental proposal" };

export default function Page() {
  return (
    <main className="customer-proposal">
      <h1>Rental proposal</h1>
      <Suspense fallback={<p role="status">Loading proposal…</p>}>
        <RentalProposalPage />
      </Suspense>
    </main>
  );
}
