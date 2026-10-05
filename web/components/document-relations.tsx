"use client";
import { useState } from "react";
import { fetchCounterparties } from "../lib/counterparty-api";
import { fetchDocument, fetchDocumentHistory } from "../lib/document-api";
import type { CounterpartyPage } from "../lib/counterparty-contracts";
import type {
  Document,
  DocumentCommand,
  DocumentHistory,
  DocumentLinks,
} from "../lib/document-contracts";
import { FileSummary, categories } from "./document-editor";

const label = (value: string) =>
  categories.find(([key]) => key === value)?.[1] ?? value;

export function DocumentRelations({
  businessId,
  selected,
  history,
  setHistory,
  historical,
  setHistorical,
  links,
  linksEnabled,
  locked,
  readLocked,
  onRead,
  onCommand,
  onDownload,
}: {
  businessId: string;
  selected: Document;
  history: DocumentHistory | null;
  setHistory: (history: DocumentHistory) => void;
  historical: Document | null;
  setHistorical: (document: Document | null) => void;
  links: DocumentLinks | null;
  linksEnabled: boolean;
  locked: boolean;
  readLocked: boolean;
  onRead: (action: () => Promise<void>) => void;
  onCommand: (command: DocumentCommand) => void;
  onDownload: (document: Document) => void;
}) {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<CounterpartyPage["items"] | null>(null);
  const subject = selected.document_id;
  const linked = new Set(links?.current.map((c) => c.counterparty_id));
  return (
    <>
      <section aria-label="Document versions" className="mgmt-card">
        <h2>Saved versions</h2>
        <p>Saved versions never change. Each save adds a new version.</p>
        <ul className="cp-list">
          {history?.items.map((item) => (
            <li key={item.revision}>
              <button
                className="secondary"
                disabled={readLocked}
                onClick={() =>
                  onRead(async () =>
                    setHistorical(
                      await fetchDocument(businessId, subject, item.revision),
                    ),
                  )
                }
              >
                Read version {item.revision}
              </button>{" "}
              <span>
                {item.title} · {item.archived ? "archived" : "current"} ·{" "}
                {item.file_id ? "with file" : "no file"}
              </span>
            </li>
          ))}
        </ul>
        {history?.next_cursor && (
          <button
            disabled={readLocked}
            onClick={() =>
              onRead(async () => {
                const older = await fetchDocumentHistory(
                  businessId,
                  subject,
                  history.next_cursor ?? undefined,
                );
                setHistory({
                  ...older,
                  items: [...history.items, ...older.items],
                });
              })
            }
          >
            Load older versions
          </button>
        )}
      </section>
      {historical && (
        <section aria-label="Saved document version" className="mgmt-card">
          <h2>Version {historical.revision}</h2>
          <p>
            {historical.title} · {label(historical.category)} ·{" "}
            {historical.archived ? "archived" : "current"}
          </p>
          <p>
            Valid from {historical.valid_from ?? "not set"} · valid until{" "}
            {historical.valid_until ?? "not set"}
          </p>
          <FileSummary file={historical.file} />
          {historical.file && (
            <button
              disabled={readLocked}
              onClick={() => onDownload(historical)}
            >
              Download file of version {historical.revision}
            </button>
          )}
          <button
            className="secondary"
            disabled={readLocked}
            onClick={() => setHistorical(null)}
          >
            Close version {historical.revision}
          </button>
        </section>
      )}
      <section aria-label="Linked counterparties" className="mgmt-card">
        <h2>Linked counterparties</h2>
        <p>
          Links are recorded one by one and kept in history. A merged card shows
          the documents of the cards merged into it.
        </p>
        {!linksEnabled && (
          <p className="warning">
            Linking needs both Documents and Counterparties turned on. Existing
            links remain readable.
          </p>
        )}
        {links && links.current.length === 0 && (
          <p>No linked counterparties.</p>
        )}
        <ul className="cp-list">
          {links?.current.map((card) => (
            <li key={card.counterparty_id}>
              <strong>{card.display_name}</strong> · {card.state}{" "}
              <button
                className="secondary"
                disabled={locked || !linksEnabled}
                onClick={() =>
                  onCommand({
                    type: "link",
                    id: subject,
                    key: crypto.randomUUID(),
                    body: {
                      schema_version: 1,
                      action: "unlink",
                      counterparty_id: card.counterparty_id,
                      expected_sequence: card.sequence,
                    },
                  })
                }
              >
                Unlink {card.display_name}
              </button>
            </li>
          ))}
        </ul>
        <form
          className="mgmt-filter-bar"
          onSubmit={(e) => {
            e.preventDefault();
            onRead(async () =>
              setFound(
                (await fetchCounterparties(businessId, query.trim(), "active"))
                  .items,
              ),
            );
          }}
        >
          <label>
            Find a counterparty to link
            <input
              value={query}
              maxLength={200}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <button disabled={readLocked || !linksEnabled}>
            Search counterparties
          </button>
        </form>
        {found && found.length === 0 && <p>No active cards match.</p>}
        <ul className="cp-list">
          {found
            ?.filter((card) => !linked.has(card.counterparty_id))
            .map((card) => (
              <li key={card.counterparty_id}>
                {card.display_name} · {card.kind}{" "}
                <button
                  disabled={locked || !linksEnabled || selected.archived}
                  onClick={() =>
                    onCommand({
                      type: "link",
                      id: subject,
                      key: crypto.randomUUID(),
                      body: {
                        schema_version: 1,
                        action: "link",
                        counterparty_id: card.counterparty_id,
                      },
                    })
                  }
                >
                  Link {card.display_name}
                </button>
              </li>
            ))}
        </ul>
        {links && links.history.length > 0 && (
          <>
            <h3>Link history</h3>
            <ul className="cp-list">
              {links.history.map((event) => (
                <li key={event.link_id}>
                  {event.action} · step {event.sequence} ·{" "}
                  {new Date(event.decided_at).toLocaleString()}
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </>
  );
}
