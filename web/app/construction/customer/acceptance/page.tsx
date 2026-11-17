import type { Metadata } from "next";
import { Suspense } from "react";
import { CustomerWorkPage } from "./acceptance";
import "../proposal.css";

export const metadata: Metadata = { title: "Construction work acceptance" };

export default function Page() {
  return (
    <main className="customer-proposal">
      <h1>Construction work acceptance</h1>
      <Suspense fallback={<p role="status">Loading work…</p>}>
        <CustomerWorkPage />
      </Suspense>
    </main>
  );
}
