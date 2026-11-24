import type { Metadata } from "next";
import { Suspense } from "react";
import { ContractorWorkPage } from "./contractor-work";
import "../../construction/customer/proposal.css";

export const metadata: Metadata = { title: "Contractor work order" };

export default function Page() {
  return (
    <main className="customer-proposal">
      <h1>Contractor work order</h1>
      <Suspense fallback={<p role="status">Loading work order…</p>}>
        <ContractorWorkPage />
      </Suspense>
    </main>
  );
}
