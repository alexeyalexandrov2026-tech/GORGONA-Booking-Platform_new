import type { Metadata } from "next";
import { Suspense } from "react";
import { CustomerChangePage } from "./change";
import "../proposal.css";

export const metadata: Metadata = { title: "Construction change order" };

export default function Page() {
  return (
    <main className="customer-proposal">
      <h1>Construction change order</h1>
      <Suspense fallback={<p role="status">Loading change order…</p>}>
        <CustomerChangePage />
      </Suspense>
    </main>
  );
}
