"use client";
import { useEffect, useState } from "react";
import { fetchCounterpartyDocuments } from "../lib/document-api";
import {
  validityState,
  type CounterpartyDocuments,
} from "../lib/document-contracts";
import { categories } from "./document-editor";

const failure = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to load linked documents.";

/** Documents linked to this card or to a duplicate merged into it (read-only). */
export function CounterpartyDocumentsPanel({
  businessId,
  counterpartyId,
}: {
  businessId: string;
  counterpartyId: string;
}) {
  const [page, setPage] = useState<CounterpartyDocuments | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const today = new Date().toLocaleDateString("en-CA");

  useEffect(() => {
    let active = true;
    fetchCounterpartyDocuments(businessId, counterpartyId)
      .then((result) => {
        if (active) setPage(result);
      })
      .catch((e: unknown) => {
        if (active) setError(failure(e));
      });
    return () => {
      active = false;
    };
  }, [businessId, counterpartyId]);

  async function more(after: string) {
    setBusy(true);
    setError(null);
    try {
      const next = await fetchCounterpartyDocuments(
        businessId,
        counterpartyId,
        after,
      );
      setPage((current) =>
        current ? { ...next, items: [...current.items, ...next.items] } : next,
      );
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Linked documents" className="mgmt-card">
      <h2>Linked documents</h2>
      {error && <p className="error">{error}</p>}
      {page && page.items.length === 0 && <p>No linked documents.</p>}
      <ul className="cp-list">
        {page?.items.map((item) => (
          <li key={`${item.document.document_id}:${item.counterparty_id}`}>
            <strong>{item.document.title}</strong> ·{" "}
            {categories.find(([key]) => key === item.document.category)?.[1]} ·
            version {item.document.revision} ·{" "}
            {validityState(item.document, today).replaceAll("_", " ")}
            {item.counterparty_id !== counterpartyId && " · via merged card"}
          </li>
        ))}
      </ul>
      {page?.next_cursor && (
        <button disabled={busy} onClick={() => void more(page.next_cursor!)}>
          Load more linked documents
        </button>
      )}
    </section>
  );
}
