import type { Metadata } from "next";
import { Suspense } from "react";
import { CustomerProposalPage } from "./proposal";
import "./proposal.css";

export const metadata: Metadata = { title: "Construction proposal" };

export default function Page() {
  return (
    <main className="customer-proposal">
      <h1>Construction proposal</h1>
      <Suspense fallback={<p role="status">Loading proposal…</p>}>
        <CustomerProposalPage />
      </Suspense>
    </main>
  );
}
