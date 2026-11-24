"use client";

import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { businessDateTime } from "../lib/business-time";
import { refusal, type CostFact } from "../lib/construction-api";
import type { CostKind, Project } from "../lib/construction-contracts";
import { fetchInvoice, fetchInvoices } from "../lib/financial-api";
import {
  fetchAllItems,
  fetchAllPlaces,
  fetchDocument,
  fetchDocuments,
} from "../lib/inventory-api";
import { fetchLedger } from "../lib/ledger-api";
import { fetchDirectory, fetchTimeEntriesPage } from "../lib/workforce-api";

export const COST_NAMES: Record<CostKind, string> = {
  stock_write_off: "Stock write-off",
  payable: "Payable",
  time_entry: "Approved time",
};

type Option<T> = { id: string; label: string; value: T };
type Page<T> = { items: Option<T>[]; next: string | null };
const page = <T,>(items: Option<T>[], next: string | null = null): Page<T> => ({
  items,
  next,
});
const reference = (id: string) => id.slice(-8);

function Choices<T>({
  label,
  load,
  onPick,
}: {
  label: string;
  load: (after?: string) => Promise<Page<T>>;
  onPick: (value: T | undefined) => void;
}) {
  const id = useId();
  const [value, setValue] = useState<Page<T> | null>(null);
  const [error, setError] = useState("");
  const [paging, setPaging] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let current = true;
    load()
      .then((result) => {
        if (current) setValue(result);
      })
      .catch((failure: unknown) => {
        if (current) setError(refusal(failure));
      });
    return () => {
      current = false;
    };
  }, [load, retry]);

  async function more() {
    if (!value?.next || paging) return;
    setPaging(true);
    setError("");
    try {
      const result = await load(value.next);
      if (
        result.next === value.next ||
        result.items.some((item) =>
          value.items.some((previous) => previous.id === item.id),
        )
      ) {
        throw new Error("The source list could not be read safely.");
      }
      setValue(page([...value.items, ...result.items], result.next));
    } catch (failure) {
      setError(refusal(failure));
    } finally {
      setPaging(false);
    }
  }

  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        defaultValue=""
        disabled={!value?.items.length}
        onChange={(event) =>
          onPick(
            value?.items.find((item) => item.id === event.currentTarget.value)
              ?.value,
          )
        }
      >
        <option value="">Select {label.toLowerCase()}</option>
        {value?.items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
      {!value && !error && <p role="status">Loading {label.toLowerCase()}…</p>}
      {value?.items.length === 0 && !value.next && (
        <p>No eligible {label.toLowerCase()} records.</p>
      )}
      {error && <p role="alert">{error}</p>}
      {!value && error && (
        <button
          type="button"
          onClick={() => {
            setError("");
            setRetry((n) => n + 1);
          }}
        >
          Retry {label.toLowerCase()}
        </button>
      )}
      {value?.next && (
        <button type="button" disabled={paging} onClick={() => void more()}>
          More {label.toLowerCase()} records
        </button>
      )}
    </div>
  );
}

type PickerProps = {
  business: string;
  project: Project;
  onPick: (value: CostFact | undefined) => void;
};

function StockSource({ business, project, onPick }: PickerProps) {
  const [place, setPlace] = useState<string>();
  const [document, setDocument] = useState<string>();
  const loadPlaces = useCallback(
    async () =>
      page(
        (await fetchAllPlaces(business)).items
          .filter((item) => item.location_id === project.location_id)
          .map((item) => ({
            id: item.place_id,
            label: `${item.code} · ${item.name}`,
            value: item.place_id,
          })),
      ),
    [business, project.location_id],
  );
  const loadDocuments = useCallback(
    async (after?: string) => {
      const result = await fetchDocuments(business, place, after);
      return page(
        result.items
          .filter(
            (item) =>
              item.kind === "write_off" &&
              item.location_id === project.location_id &&
              item.place_id === place,
          )
          .map((item) => ({
            id: item.document_id,
            label: `${item.document_date} · ${item.reason} · ${reference(item.document_id)}`,
            value: item.document_id,
          })),
        result.next_cursor,
      );
    },
    [business, place, project.location_id],
  );
  const loadLines = useCallback(async () => {
    if (!document) return page<number>([]);
    const [data, materials] = await Promise.all([
      fetchDocument(business, document),
      fetchAllItems(business),
    ]);
    if (
      data.document_id !== document ||
      data.kind !== "write_off" ||
      data.place_id !== place ||
      data.location_id !== project.location_id
    )
      throw new Error("The write-off does not belong to this project branch.");
    if (data.money?.currency !== project.currency || !data.money.entry_id)
      return page<number>([]);
    const names = new Map(
      materials.items.map((item) => [item.item_id, item.name]),
    );
    return page(
      data.lines
        .filter((line) => line.amount !== null && Number(line.amount) > 0)
        .map((line) => ({
          id: String(line.line_no),
          label: `Line ${line.line_no} · ${names.get(line.item_id) ?? "Material"} · ${line.amount} ${project.currency}`,
          value: line.line_no,
        })),
    );
  }, [business, document, place, project.currency, project.location_id]);
  return (
    <>
      <Choices
        label="Stock place"
        load={loadPlaces}
        onPick={(next) => {
          setPlace(next);
          setDocument(undefined);
          onPick(undefined);
        }}
      />
      {place && (
        <Choices
          key={place}
          label="Stock write-off"
          load={loadDocuments}
          onPick={(next) => {
            setDocument(next);
            onPick(undefined);
          }}
        />
      )}
      {document && (
        <Choices
          key={document}
          label="Write-off line"
          load={loadLines}
          onPick={(line) =>
            onPick(
              line === undefined
                ? undefined
                : {
                    kind: "stock_write_off",
                    stock_document_id: document,
                    stock_line_no: line,
                  },
            )
          }
        />
      )}
    </>
  );
}

function PayableSource({ business, project, onPick }: PickerProps) {
  const typeId = useId();
  const [book, setBook] = useState<string>();
  const [kind, setKind] = useState<"invoice" | "manual_accrual">("invoice");
  const [document, setDocument] = useState<string>();
  const loadBooks = useCallback(
    async (after?: string) => {
      const result = await fetchLedger(business, after);
      return page(
        result.items.flatMap((item) =>
          item.book
            ? [
                {
                  id: item.book.book_id,
                  label: `${item.code} · ${item.legal_name}`,
                  value: item.book.book_id,
                },
              ]
            : [],
        ),
        result.next_cursor,
      );
    },
    [business],
  );
  const loadDocuments = useCallback(
    async (after?: string) => {
      if (!book) return page<string>([]);
      const result = await fetchInvoices(business, book, kind, after);
      return page(
        result.items
          .filter(
            (item) =>
              item.state === "issued" &&
              item.direction === "payable" &&
              item.currency === project.currency,
          )
          .map((item) => ({
            id: item.document_id,
            value: item.document_id,
            label: `${item.number} · ${item.title} · ${item.invoice_date}`,
          })),
        result.next_cursor,
      );
    },
    [business, book, kind, project.currency],
  );
  const loadLines = useCallback(async () => {
    if (!book || !document) return page<string>([]);
    const data = await fetchInvoice(business, book, document, kind);
    if (
      data.currency !== project.currency ||
      data.state !== "issued" ||
      data.direction !== "payable"
    )
      return page<string>([]);
    return page(
      data.lines.map((line) => ({
        id: line.line_id,
        value: line.line_id,
        label: `${line.description} · ${line.amount} ${project.currency} · ${reference(line.line_id)}`,
      })),
    );
  }, [business, book, document, kind, project.currency]);
  function clearDocument() {
    setDocument(undefined);
    onPick(undefined);
  }
  return (
    <>
      <Choices
        label="Ledger book"
        load={loadBooks}
        onPick={(next) => {
          setBook(next);
          clearDocument();
        }}
      />
      {book && (
        <>
          <label htmlFor={typeId}>Payable type</label>
          <select
            id={typeId}
            value={kind}
            onChange={(event) => {
              setKind(
                event.currentTarget.value === "invoice"
                  ? "invoice"
                  : "manual_accrual",
              );
              clearDocument();
            }}
          >
            <option value="invoice">Invoice</option>
            <option value="manual_accrual">Manual accrual</option>
          </select>
          <Choices
            key={`${book}:${kind}`}
            label="Issued payable"
            load={loadDocuments}
            onPick={(next) => {
              setDocument(next);
              onPick(undefined);
            }}
          />
          {document && (
            <Choices
              key={document}
              label="Payable line"
              load={loadLines}
              onPick={(line) =>
                onPick(
                  line
                    ? {
                        kind: "payable",
                        book_id: book,
                        document_id: document,
                        line_id: line,
                      }
                    : undefined,
                )
              }
            />
          )}
        </>
      )}
    </>
  );
}

function TimeSource({ business, project, onPick }: PickerProps) {
  const people = useRef<ReturnType<typeof fetchDirectory> | null>(null);
  const load = useCallback(
    async (after?: string) => {
      people.current ??= fetchDirectory(business);
      const [entries, directory] = await Promise.all([
        fetchTimeEntriesPage(business, false, after),
        people.current.catch(() => {
          people.current = null;
          return { items: [] };
        }),
      ]);
      const names = new Map(
        directory.items.map((person) => [person.user_id, person.display_name]),
      );
      return page(
        entries.items.flatMap((entry) => {
          const time = entry.effective;
          if (
            entry.location_id !== project.location_id ||
            !time ||
            !time.worked_microseconds
          )
            return [];
          const date = businessDateTime(time.starts_at, project.time_zone);
          return [
            {
              id: entry.entry_id,
              value: entry.entry_id,
              label: `${date} · ${names.get(entry.user_id) ?? "Team member"} · rev ${time.revision} · ${reference(entry.entry_id)}`,
            },
          ];
        }),
        entries.next_cursor,
      );
    },
    [business, project.location_id, project.time_zone],
  );
  return (
    <Choices
      label="Approved time entry"
      load={load}
      onPick={(entry) =>
        onPick(entry ? { kind: "time_entry", time_entry_id: entry } : undefined)
      }
    />
  );
}

export function CostSource({
  kind,
  ...props
}: PickerProps & { kind: CostKind }) {
  switch (kind) {
    case "stock_write_off":
      return <StockSource {...props} />;
    case "payable":
      return <PayableSource {...props} />;
    case "time_entry":
      return <TimeSource {...props} />;
  }
}
