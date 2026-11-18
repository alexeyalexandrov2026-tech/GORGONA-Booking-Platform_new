import type { Metadata } from "next";
import { Suspense } from "react";
import { RentalChangePage } from "./offer";
import "../../../construction/customer/proposal.css";

export const metadata: Metadata = { title: "Rental agreement change" };

export default function Page() {
  return (
    <main className="customer-proposal">
      <h1>Rental agreement change</h1>
      <Suspense fallback={<p role="status">Loading rental change…</p>}>
        <RentalChangePage />
      </Suspense>
    </main>
  );
}
