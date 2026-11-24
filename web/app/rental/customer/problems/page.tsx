import type { Metadata } from "next";
import { Suspense } from "react";
import { RentalProblemsPage } from "./problems";
import "../../../construction/customer/proposal.css";

export const metadata: Metadata = { title: "Rental problem reports" };

export default function Page() {
  return (
    <main className="customer-proposal">
      <h1>Rental problem reports</h1>
      <Suspense fallback={<p role="status">Loading problem reports…</p>}>
        <RentalProblemsPage />
      </Suspense>
    </main>
  );
}
