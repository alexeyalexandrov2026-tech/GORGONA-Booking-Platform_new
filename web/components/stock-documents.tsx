"use client";
import { useCallback, useEffect, useState } from "react";
import { fetchLedger } from "../lib/ledger-api";
import {
  fetchBalances,
  fetchDocument,
  fetchDocuments,
  fetchItems,
  fetchPlaces,
} from "../lib/inventory-api";
import {
  DOCUMENT_KINDS,
  DOCUMENT_REASONS,
  amountFits,
  quantityFits,
  type DocumentBody,
  type DocumentKind,
  type DocumentSummary,
  type Item,
  type Place,
  type StockDocument,
} from "../lib/inventory-contracts";
import {
  InventoryNotices,
  explain,
  useInventoryCommands,
  type CommandCenter,
} from "./inventory-commands";

const NO_AMOUNTS =
  "Amounts are shown only to finance managers of the whole company.";
const TEXT = /^[^\u0000-\u001f\u007f-\u009f]+$/;
const DAY = /^\d{4}-\d{2}-\d{2}$/;
/** An owner of stock; `scale` is the minor units of its book, null without a book. */
type Owner = { id: string; label: string; scale: number | null };
type Names = {
  item: (id: string) => string;
  place: (id: string) => string;
  owner: (id: string) => string;
  kind: (kind: string) => string;
  reason: (kind: DocumentKind, reason: string) => string;
};

const kindLabel = (kind: string) =>
  DOCUMENT_KINDS.find(([value]) => value === kind)?.[1] ?? kind;
const reasonLabel = (kind: DocumentKind, reason: string) =>
  (DOCUMENT_REASONS[kind] as readonly (readonly string[])[]).find(
    ([value]) => value === reason,
  )?.[1] ?? reason;

export function StockDocuments({
  actorId,
  businessId,
  finance,
}: {
  actorId: string;
  businessId: string;
  /** A company-wide owner or manager: posts every kind and reads amounts. */
  finance: boolean;
}) {
  const [items, setItems] = useState<Item[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [owners, setOwners] = useState<Owner[]>([]);
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [opened, setOpened] = useState<StockDocument | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const read = useCallback(async () => {
    const [itemList, placeList, documentList, balances, ledger] =
      await Promise.all([
        fetchItems(businessId),
        fetchPlaces(businessId),
        fetchDocuments(businessId, filter || undefined),
        finance ? null : fetchBalances(businessId),
        finance ? fetchLedger(businessId) : null,
      ]);
    return { itemList, placeList, documentList, balances, ledger };
  }, [businessId, filter, finance]);
  const show = useCallback((data: Awaited<ReturnType<typeof read>>) => {
    setItems(data.itemList.items);
    setPlaces(data.placeList.items);
    setDocuments(data.documentList.items);
    setCursor(data.documentList.next_cursor);
    if (data.ledger)
      // Documents with amounts post to the owner's book: only owners with a book.
      setOwners(
        data.ledger.items.flatMap((x) =>
          x.book
            ? [
                {
                  id: x.legal_entity_id,
                  label: `${x.code} · ${x.legal_name}`,
                  scale: x.book.minor_units,
                },
              ]
            : [],
        ),
      );
    else {
      // A branch manager reads no company names: owners are known by their stock.
      const ids = [
        ...new Set([
          ...(data.balances?.items ?? []).map((x) => x.legal_entity_id),
          ...data.documentList.items.map((x) => x.legal_entity_id),
        ]),
      ];
      setOwners(
        ids.map((id, n) => ({
          id,
          label: ids.length === 1 ? "Company" : `Company owner ${n + 1}`,
          scale: null,
        })),
      );
    }
  }, []);
  const load = useCallback(async () => show(await read()), [read, show]);
  useEffect(() => {
    let active = true;
    read().then(
      (data) => {
        if (!active) return;
        show(data);
        setFailed(null);
      },
      (error: unknown) => {
        if (active) setFailed(explain(error));
      },
    );
    return () => {
      active = false;
    };
  }, [read, show]);
  const center = useInventoryCommands(businessId, actorId, load);
  const names: Names = {
    item: (id) => {
      const item = items.find((x) => x.item_id === id);
      return item ? `${item.code} · ${item.name}` : "A material";
    },
    place: (id) => {
      const place = places.find((x) => x.place_id === id);
      return place ? `${place.code} · ${place.name}` : "Another branch";
    },
    owner: (id) => owners.find((x) => x.id === id)?.label ?? "Company",
    kind: kindLabel,
    reason: reasonLabel,
  };
  async function more() {
    if (!cursor) return;
    try {
      const page = await fetchDocuments(
        businessId,
        filter || undefined,
        cursor,
      );
      setDocuments((current) => [...current, ...page.items]);
      setCursor(page.next_cursor);
    } catch (error) {
      setFailed(explain(error));
    }
  }
  async function open(id: string) {
    try {
      setOpened(await fetchDocument(businessId, id));
      setFailed(null);
    } catch (error) {
      setFailed(explain(error));
    }
  }

  return (
    <div className="inventory-screen stock-documents">
      <h1>Stock documents</h1>
      {failed && (
        <p role="alert" className="error">
          {failed}
        </p>
      )}
      <InventoryNotices
        center={center}
        label="Stock document recovery"
        withError={false}
      />
      <section aria-label="Document list">
        <h2>Posted documents</h2>
        <label>
          Place
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All places</option>
            {places.map((place) => (
              <option key={place.place_id} value={place.place_id}>
                {place.code} · {place.name}
              </option>
            ))}
          </select>
        </label>
        {documents.length === 0 ? (
          <p>No documents yet.</p>
        ) : (
          <div className="table-scroll">
            <table className="wide">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Kind</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Place</th>
                  <th scope="col">Destination</th>
                  <th scope="col">Lines</th>
                  <th scope="col">
                    <span className="visually-hidden">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {documents.map((row) => (
                  <tr key={row.document_id}>
                    <td>{row.document_date}</td>
                    <td>{kindLabel(row.kind)}</td>
                    <td>{reasonLabel(row.kind, row.reason)}</td>
                    <td>{names.place(row.place_id)}</td>
                    <td>
                      {row.to_place_id ? names.place(row.to_place_id) : "—"}
                    </td>
                    <td>{row.line_count}</td>
                    <td>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => void open(row.document_id)}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {cursor && (
          <button
            type="button"
            className="secondary"
            onClick={() => void more()}
          >
            Show more documents
          </button>
        )}
      </section>
      {opened && (
        <DocumentView
          document={opened}
          documents={documents}
          names={names}
          close={() => setOpened(null)}
        />
      )}
      <DocumentForm
        key={center.generation}
        businessId={businessId}
        finance={finance}
        items={items}
        places={places}
        owners={owners}
        documents={documents}
        center={center}
      />
    </div>
  );
}

function DocumentView({
  document,
  documents,
  names,
  close,
}: {
  document: StockDocument;
  documents: DocumentSummary[];
  names: Names;
  close: () => void;
}) {
  const source = documents.find(
    (x) => x.document_id === document.source_document_id,
  );
  const returns = document.kind === "return";
  return (
    <section aria-label="Document">
      <h2>
        {names.kind(document.kind)} of {document.document_date}
      </h2>
      <dl>
        <dt>Owner</dt>
        <dd>{names.owner(document.legal_entity_id)}</dd>
        <dt>Reason</dt>
        <dd>{names.reason(document.kind, document.reason)}</dd>
        <dt>Place</dt>
        <dd>{names.place(document.place_id)}</dd>
        {document.to_place_id && (
          <>
            <dt>Destination</dt>
            <dd>{names.place(document.to_place_id)}</dd>
          </>
        )}
        {document.source_document_id && (
          <>
            <dt>Returns</dt>
            <dd>
              {source
                ? `${names.kind(source.kind)} of ${source.document_date}`
                : "An earlier document"}
            </dd>
          </>
        )}
        {document.supplier_document && (
          <>
            <dt>Supplier document</dt>
            <dd>{document.supplier_document}</dd>
          </>
        )}
      </dl>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Line</th>
              <th scope="col">Material</th>
              <th scope="col">Quantity</th>
              {document.money && <th scope="col">Amount</th>}
              {returns && <th scope="col">Returns line</th>}
            </tr>
          </thead>
          <tbody>
            {document.lines.map((line) => (
              <tr key={line.line_no}>
                <td>{line.line_no}</td>
                <td>{names.item(line.item_id)}</td>
                <td>{line.quantity}</td>
                {document.money && <td>{line.amount}</td>}
                {returns && <td>{line.source_line_no}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {document.money ? (
        <p>
          Total {document.money.total} {document.money.currency}
        </p>
      ) : (
        document.kind !== "transfer" && <p>{NO_AMOUNTS}</p>
      )}
      <button type="button" className="secondary" onClick={close}>
        Close document
      </button>
    </section>
  );
}

type Line = { item: string; quantity: string; amount: string };
const EMPTY: Line = { item: "", quantity: "", amount: "" };

function DocumentForm({
  businessId,
  finance,
  items,
  places,
  owners,
  documents,
  center,
}: {
  businessId: string;
  finance: boolean;
  items: Item[];
  places: Place[];
  owners: Owner[];
  documents: DocumentSummary[];
  center: CommandCenter;
}) {
  const kinds = finance
    ? DOCUMENT_KINDS
    : DOCUMENT_KINDS.filter(([kind]) => kind === "transfer");
  const [kind, setKind] = useState<DocumentKind>(kinds[0]![0]);
  const [chosenOwner, setOwner] = useState("");
  const [place, setPlace] = useState("");
  const [toPlace, setToPlace] = useState("");
  const [date, setDate] = useState(() =>
    new Date().toLocaleDateString("en-CA"),
  );
  const [reason, setReason] = useState<string>(
    DOCUMENT_REASONS[kinds[0]![0]][0][0],
  );
  const [supplierDocument, setSupplierDocument] = useState("");
  const [lines, setLines] = useState<Line[]>([EMPTY]);
  const [source, setSource] = useState<StockDocument | null>(null);
  const [returned, setReturned] = useState<Record<number, string>>({});
  const owner = owners.find((x) => x.id === chosenOwner) ?? owners[0];
  const open = places.filter((x) => !x.archived);
  const usable = items.filter((x) => !x.archived);
  const scale = (id: string) =>
    items.find((x) => x.item_id === id)?.quantity_scale;
  const sources = documents.filter(
    (x) =>
      (x.kind === "receipt" || x.kind === "write_off") &&
      x.legal_entity_id === owner?.id,
  );
  const named =
    (kind === "receipt" && reason === "purchase") ||
    (kind === "return" && reason === "supplier_return");

  function choose(next: DocumentKind) {
    setKind(next);
    setReason(DOCUMENT_REASONS[next][0][0]);
    setLines([EMPTY]);
    setSource(null);
    setReturned({});
    setSupplierDocument("");
  }
  function change(n: number, patch: Partial<Line>) {
    setLines(lines.map((line, i) => (i === n ? { ...line, ...patch } : line)));
  }
  async function pick(id: string) {
    setReturned({});
    if (!id) return setSource(null);
    try {
      const document = await fetchDocument(businessId, id);
      setSource(document);
      // A return defaults to the place of the document it returns.
      setPlace(document.place_id);
    } catch {
      setSource(null);
    }
  }

  const quantities = lines.every(
    (line) =>
      line.item !== "" && quantityFits(line.quantity, scale(line.item) ?? 0),
  );
  const amounts =
    kind !== "receipt" ||
    lines.every((line) => amountFits(line.amount, owner?.scale ?? 2));
  const back = Object.entries(returned).filter(([, value]) => value !== "");
  const valid =
    owner !== undefined &&
    place !== "" &&
    DAY.test(date) &&
    (!named ||
      supplierDocument.trim() === "" ||
      (TEXT.test(supplierDocument.trim()) &&
        supplierDocument.trim().length <= 64)) &&
    (kind === "return"
      ? source !== null &&
        back.length > 0 &&
        back.every(([no, value]) => {
          const line = source.lines.find((x) => x.line_no === Number(no));
          return (
            line !== undefined && quantityFits(value, scale(line.item_id) ?? 0)
          );
        })
      : quantities &&
        amounts &&
        (kind !== "transfer" || (toPlace !== "" && toPlace !== place)));

  function body(): DocumentBody | null {
    if (!owner) return null;
    const common = {
      schema_version: 1 as const,
      legal_entity_id: owner.id,
      place_id: place,
      document_date: date,
    };
    const supplier =
      named && supplierDocument.trim() ? supplierDocument.trim() : null;
    const moved = lines.map((line) => ({
      item_id: line.item,
      quantity: line.quantity,
    }));
    if (kind === "receipt")
      return {
        ...common,
        kind,
        reason,
        supplier_id: null,
        supplier_document: supplier,
        lines: lines.map((line) => ({
          item_id: line.item,
          quantity: line.quantity,
          amount: line.amount,
        })),
      };
    if (kind === "write_off") return { ...common, kind, reason, lines: moved };
    if (kind === "transfer")
      return { ...common, kind, to_place_id: toPlace, lines: moved };
    if (!source) return null;
    return {
      ...common,
      kind,
      reason,
      source_document_id: source.document_id,
      supplier_id: null,
      supplier_document: supplier,
      lines: back.map(([no, quantity]) => ({
        source_line_no: Number(no),
        quantity,
      })),
    };
  }

  return (
    <form
      aria-label="New stock document"
      onSubmit={(event) => {
        event.preventDefault();
        const document = body();
        if (!valid || !document) return;
        void center.run(
          {
            type: "document",
            id: crypto.randomUUID(),
            key: crypto.randomUUID(),
            body: document,
          },
          "Stock document posted.",
        );
      }}
    >
      <h2>New stock document</h2>
      <label>
        Document kind
        <select
          value={kind}
          onChange={(e) => choose(e.target.value as DocumentKind)}
        >
          {kinds.map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </label>
      <label>
        Owner
        <select
          value={owner?.id ?? ""}
          onChange={(e) => {
            setOwner(e.target.value);
            setSource(null);
            setReturned({});
          }}
        >
          {owners.map((x) => (
            <option key={x.id} value={x.id}>
              {x.label}
            </option>
          ))}
        </select>
      </label>
      {kind !== "transfer" && (
        <label>
          Reason
          <select value={reason} onChange={(e) => setReason(e.target.value)}>
            {DOCUMENT_REASONS[kind].map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
      )}
      {kind === "return" && (
        <label>
          Source document
          <select
            value={source?.document_id ?? ""}
            onChange={(e) => void pick(e.target.value)}
          >
            <option value="">Choose a receipt or a write-off</option>
            {sources.map((x) => (
              <option key={x.document_id} value={x.document_id}>
                {`${kindLabel(x.kind)} of ${x.document_date} at ${
                  places.find((p) => p.place_id === x.place_id)?.code ??
                  "another branch"
                } · ${x.line_count} ${x.line_count === 1 ? "line" : "lines"}`}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Place
        <select value={place} onChange={(e) => setPlace(e.target.value)}>
          <option value="">Choose a place</option>
          {open.map((x) => (
            <option key={x.place_id} value={x.place_id}>
              {x.code} · {x.name}
            </option>
          ))}
        </select>
      </label>
      {kind === "transfer" && (
        <label>
          To place
          <select value={toPlace} onChange={(e) => setToPlace(e.target.value)}>
            <option value="">Choose a place</option>
            {open
              .filter((x) => x.place_id !== place)
              .map((x) => (
                <option key={x.place_id} value={x.place_id}>
                  {x.code} · {x.name}
                </option>
              ))}
          </select>
        </label>
      )}
      <label>
        Document date
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </label>
      {named && (
        <label>
          Supplier document number (optional)
          <input
            value={supplierDocument}
            maxLength={64}
            onChange={(e) => setSupplierDocument(e.target.value)}
          />
        </label>
      )}
      {kind === "return" ? (
        source && (
          <fieldset>
            <legend>Quantities to return</legend>
            {source.lines.map((line) => (
              <div className="stock-line" key={line.line_no}>
                <label>
                  Quantity to return, line {line.line_no}
                  <input
                    inputMode="decimal"
                    value={returned[line.line_no] ?? ""}
                    onChange={(e) =>
                      setReturned({
                        ...returned,
                        [line.line_no]: e.target.value,
                      })
                    }
                  />
                </label>
                <p>
                  {items.find((x) => x.item_id === line.item_id)?.code ??
                    "A material"}
                  : {line.quantity} in the source document
                </p>
              </div>
            ))}
          </fieldset>
        )
      ) : (
        <fieldset>
          <legend>Lines</legend>
          {lines.map((line, n) => (
            <div className="stock-line" key={n}>
              <label>
                Material {n + 1}
                <select
                  value={line.item}
                  onChange={(e) => change(n, { item: e.target.value })}
                >
                  <option value="">Choose a material</option>
                  {usable.map((x) => (
                    <option key={x.item_id} value={x.item_id}>
                      {x.code} · {x.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Quantity {n + 1}
                <input
                  inputMode="decimal"
                  value={line.quantity}
                  onChange={(e) => change(n, { quantity: e.target.value })}
                />
              </label>
              {kind === "receipt" && (
                <label>
                  Amount {n + 1}
                  <input
                    inputMode="decimal"
                    value={line.amount}
                    onChange={(e) => change(n, { amount: e.target.value })}
                  />
                </label>
              )}
              {lines.length > 1 && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setLines(lines.filter((_, i) => i !== n))}
                >
                  Remove line {n + 1}
                </button>
              )}
            </div>
          ))}
          {lines.length < 100 && (
            <button
              type="button"
              className="secondary"
              onClick={() => setLines([...lines, EMPTY])}
            >
              Add line
            </button>
          )}
        </fieldset>
      )}
      {center.error && (
        <p role="alert" className="error">
          {center.error}
        </p>
      )}
      <button type="submit" disabled={!valid || center.blocked}>
        Post document
      </button>
    </form>
  );
}
