"use client";

// R8c (package R): after the agreement, on a booking: the handover and return inspections, the
// usage, the settlement, damage charges, refunds and the reconciliation. Every figure is the
// server's; money is entered in major units and sent in minor units; a command keeps its
// Idempotency-Key until it succeeds (ADR-0030). FIN-03 documents are issued on its own screens.
import React, { useCallback, useEffect, useId, useState } from "react";
import { businessTimeToInstant } from "../lib/business-time";
import {
  currencyPlaces,
  formatMinor,
  toMinor,
} from "../lib/construction-rules";
import {
  chargeDamage,
  fetchCharges,
  fetchInspections,
  fetchReconciliation,
  fetchSettlement,
  fetchUsage,
  recordInspection,
  recordRefund,
  refusal,
  settle,
  type InvoiceTerms,
  type MarkBody,
} from "../lib/rental-api";
import type {
  Booking,
  Charges,
  Inspection,
  Inspections,
  MeterKind,
  Reconciliation,
  Settlement,
  Severity,
  Usage,
} from "../lib/rental-contracts";
import { BookSelect, useBooks } from "./transport-money";
import { AccountSelect } from "./visit-billing";

const places = (currency: string) => currencyPlaces(currency) ?? 2;
const money = (minor: number | null, currency: string) =>
  minor === null ? "—" : formatMinor(minor, places(currency));

function minorOf(text: string, currency: string, label: string): number {
  const value = toMinor(text, places(currency));
  if (value === null || value <= 0)
    throw new Error(
      `${label} is not an amount in ${currency || "the currency"}.`,
    );
  return value;
}

type Loaded = {
  inspections: Inspections | null;
  usage: Usage | null;
  settlement: Settlement | null;
  charges: Charges | null;
  reconciliation: Reconciliation | null;
};

export function AfterTheAgreement({
  businessId,
  booking,
  zone,
  meterKind,
  notify,
}: {
  businessId: string;
  booking: Booking;
  zone: string;
  meterKind: MeterKind;
  notify: (text: string) => void;
}) {
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const id = booking.booking_id;
  const changed = useCallback(
    (text: string) => {
      notify(text);
      setVersion((v) => v + 1);
    },
    [notify],
  );

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchInspections(businessId, id),
      fetchUsage(businessId, id),
      fetchSettlement(businessId, id),
      fetchCharges(businessId, id),
      fetchReconciliation(businessId, id),
    ])
      .then(([inspections, usage, settlement, charges, reconciliation]) => {
        if (live)
          setData({ inspections, usage, settlement, charges, reconciliation });
      })
      .catch((failure: unknown) => {
        if (live)
          setError(
            `The handover and settlement could not be read: ${refusal(failure)}`,
          );
      });
    return () => {
      live = false;
    };
  }, [businessId, id, version]);

  if (error)
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  if (!data)
    return (
      <p className="muted" role="status">
        Loading the handover and settlement…
      </p>
    );
  const list = data.inspections?.inspections ?? [];
  const currency =
    data.settlement?.currency ??
    data.usage?.currency ??
    data.reconciliation?.currency ??
    "";
  return (
    <>
      <InspectionsPanel
        businessId={businessId}
        booking={booking}
        meterKind={meterKind}
        inspections={list}
        onRecorded={changed}
      />
      <UsagePanel usage={data.usage} />
      <SettlementPanel
        businessId={businessId}
        booking={booking}
        usage={data.usage}
        settlement={data.settlement}
        onSettled={changed}
      />
      {data.settlement && (
        <>
          <ChargesPanel
            businessId={businessId}
            booking={booking}
            currency={currency}
            inspections={list}
            charges={data.charges}
            onCharged={changed}
          />
          <RefundsPanel
            businessId={businessId}
            booking={booking}
            zone={zone}
            currency={currency}
            charges={data.charges}
            reconciliation={data.reconciliation}
            onRefunded={changed}
          />
        </>
      )}
      <ReconciliationPanel reconciliation={data.reconciliation} />
    </>
  );
}

const SEVERITIES: [Severity, string][] = [
  ["minor", "Minor"],
  ["major", "Major"],
];

function InspectionsPanel({
  businessId,
  booking,
  meterKind,
  inspections,
  onRecorded,
}: {
  businessId: string;
  booking: Booking;
  meterKind: MeterKind;
  inspections: Inspection[];
  onRecorded: (text: string) => void;
}) {
  const headingId = useId();
  const [meter, setMeter] = useState("");
  const [level, setLevel] = useState("");
  const [note, setNote] = useState("");
  const [marks, setMarks] = useState<MarkBody[]>([]);
  const [area, setArea] = useState("");
  const [severity, setSeverity] = useState<Severity>("minor");
  const [markNote, setMarkNote] = useState("");
  const [isNew, setIsNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const handedOver = inspections.some((i) => i.kind === "handover");
  const returned = inspections.some((i) => i.kind === "return");
  const kind = handedOver ? "return" : "handover";

  function addMark() {
    setError(null);
    if (!area.trim()) {
      setError("A mark needs its area.");
      return;
    }
    setMarks((all) => [
      ...all,
      {
        area: area.trim(),
        severity,
        ...(markNote.trim() ? { note: markNote.trim() } : {}),
        new: kind === "return" && isNew,
      },
    ]);
    setArea("");
    setMarkNote("");
    setIsNew(false);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const reading = meter.trim() === "" ? null : Number(meter);
      if (reading !== null && !Number.isInteger(reading))
        throw new Error("The meter is a whole number.");
      const percent = level.trim() === "" ? null : Number(level);
      if (percent !== null && !Number.isInteger(percent))
        throw new Error("The level is a whole number of per cent.");
      await recordInspection(businessId, booking.booking_id, {
        schema_version: 1,
        kind,
        ...(meterKind !== "none" && reading !== null ? { meter: reading } : {}),
        ...(percent !== null ? { level: percent } : {}),
        ...(note.trim() ? { note: note.trim() } : {}),
        marks,
      });
      setMeter("");
      setLevel("");
      setNote("");
      setMarks([]);
      onRecorded(
        kind === "handover" ? "Handover recorded." : "Return recorded.",
      );
    } catch (failure) {
      setError(`The ${kind} was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const rows = inspections.flatMap((i) =>
    i.marks.map((m) => ({ kind: i.kind, ...m })),
  );
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Inspections</h3>
      {inspections.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Inspections table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Inspections">
            <thead>
              <tr>
                <th scope="col">Kind</th>
                <th scope="col">Meter</th>
                <th scope="col">Level</th>
                <th scope="col">Note</th>
                <th scope="col">Marks</th>
              </tr>
            </thead>
            <tbody>
              {inspections.map((i) => (
                <tr key={i.inspection_id}>
                  <th scope="row">
                    {i.kind === "handover" ? "Handover" : "Return"}
                  </th>
                  <td>{i.meter ?? "—"}</td>
                  <td>{i.level === null ? "—" : `${i.level}%`}</td>
                  <td>{i.note ?? "—"}</td>
                  <td>{i.marks.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Inspection marks table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Inspection marks">
            <thead>
              <tr>
                <th scope="col">Inspection</th>
                <th scope="col">Mark</th>
                <th scope="col">Area</th>
                <th scope="col">Severity</th>
                <th scope="col">Note</th>
                <th scope="col">New</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={`${m.kind}-${m.position}`}>
                  <th scope="row">
                    {m.kind === "handover" ? "Handover" : "Return"}
                  </th>
                  <td>{m.position}</td>
                  <td>{m.area}</td>
                  <td>{m.severity === "major" ? "Major" : "Minor"}</td>
                  <td>{m.note ?? "—"}</td>
                  <td>{m.new ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!returned && !booking.cancellation && (
        <form aria-label="Inspection" onSubmit={submit}>
          <p>
            {kind === "handover"
              ? "Records the handover."
              : "Records the return."}
          </p>
          {meterKind !== "none" && (
            <label>
              Meter
              <input
                value={meter}
                inputMode="numeric"
                onChange={(e) => setMeter(e.target.value)}
                required
              />
            </label>
          )}
          <label>
            Level (%)
            <input
              value={level}
              inputMode="numeric"
              onChange={(e) => setLevel(e.target.value)}
            />
          </label>
          <label>
            Note
            <input
              value={note}
              maxLength={1000}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <fieldset>
            <legend>Damage marks</legend>
            <label>
              Mark area
              <input
                value={area}
                maxLength={100}
                onChange={(e) => setArea(e.target.value)}
              />
            </label>
            <label>
              Mark severity
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as Severity)}
              >
                {SEVERITIES.map(([value, text]) => (
                  <option key={value} value={value}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Mark note
              <input
                value={markNote}
                maxLength={500}
                onChange={(e) => setMarkNote(e.target.value)}
              />
            </label>
            {kind === "return" && (
              <label>
                <input
                  type="checkbox"
                  checked={isNew}
                  onChange={(e) => setIsNew(e.target.checked)}
                />
                New since the handover
              </label>
            )}
            <div className="mgmt-form-actions">
              <button type="button" onClick={addMark}>
                Add mark
              </button>
            </div>
            {marks.length > 0 && (
              <ul aria-label="Marks to record">
                {marks.map((m, index) => (
                  <li key={`${m.area}-${index}`}>
                    {`${index + 1}. ${m.area} (${m.severity})${m.new ? ", new" : ""}`}{" "}
                    <button
                      type="button"
                      onClick={() =>
                        setMarks((all) => all.filter((_, i) => i !== index))
                      }
                    >
                      Remove mark {index + 1}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              {kind === "handover" ? "Record handover" : "Record return"}
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

const STATES: Record<Usage["state"], string> = {
  not_handed_over: "not handed over",
  out: "out",
  returned: "returned",
};

function UsagePanel({ usage }: { usage: Usage | null }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Usage</h3>
      <p>
        {usage
          ? `Usage: ${STATES[usage.state]}; overdue ${usage.overdue_hours} h; distance ` +
            `${usage.distance ?? "—"}, allowance ${usage.allowance ?? "—"}, excess ` +
            `${usage.excess ?? "—"} (${money(usage.excess_amount, usage.currency)} ${usage.currency})`
          : "No usage before the agreement."}
      </p>
    </section>
  );
}

/** The book, accounts, dates and number of a FIN-03 invoice draft. */
function InvoiceFields({
  businessId,
  onError,
  terms,
  setTerms,
}: {
  businessId: string;
  onError: (text: string) => void;
  terms: InvoiceTerms;
  setTerms: (next: InvoiceTerms) => void;
}) {
  const { books, book, setBook, accounts } = useBooks(businessId, onError);
  return (
    <>
      <BookSelect
        books={books}
        value={book}
        onChange={(value) => {
          setBook(value);
          setTerms({
            ...terms,
            book_id: value,
            receivable_account_id: "",
            revenue_account_id: "",
          });
        }}
      />
      <AccountSelect
        label="Receivable account"
        accounts={accounts}
        types={["asset"]}
        value={terms.receivable_account_id}
        onChange={(value) =>
          setTerms({ ...terms, receivable_account_id: value })
        }
      />
      <AccountSelect
        label="Revenue account"
        accounts={accounts}
        types={["revenue"]}
        value={terms.revenue_account_id}
        onChange={(value) => setTerms({ ...terms, revenue_account_id: value })}
      />
      <label>
        Invoice date
        <input
          type="date"
          value={terms.invoice_date}
          onChange={(e) => setTerms({ ...terms, invoice_date: e.target.value })}
          required
        />
      </label>
      <label>
        Due date
        <input
          type="date"
          value={terms.due_date ?? ""}
          onChange={(e) =>
            setTerms({ ...terms, due_date: e.target.value || undefined })
          }
        />
      </label>
      <label>
        Number
        <input
          value={terms.number}
          maxLength={62}
          onChange={(e) => setTerms({ ...terms, number: e.target.value })}
          required
        />
      </label>
    </>
  );
}

const NO_TERMS: InvoiceTerms = {
  book_id: "",
  receivable_account_id: "",
  revenue_account_id: "",
  invoice_date: "",
  number: "",
};

function SettlementPanel({
  businessId,
  booking,
  usage,
  settlement,
  onSettled,
}: {
  businessId: string;
  booking: Booking;
  usage: Usage | null;
  settlement: Settlement | null;
  onSettled: (text: string) => void;
}) {
  const headingId = useId();
  const [terms, setTerms] = useState<InvoiceTerms>(NO_TERMS);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await settle(businessId, booking.booking_id, {
        ...terms,
        number: terms.number.trim(),
      });
      onSettled("Settlement recorded.");
    } catch (failure) {
      setError(`The booking was not settled: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Settlement</h3>
      {settlement ? (
        <p>
          {`Settlement: rental ${money(settlement.rental_minor, settlement.currency)}, excess ` +
            `${money(settlement.excess_minor, settlement.currency)}, late ` +
            `${money(settlement.late_minor, settlement.currency)}, total ` +
            `${money(settlement.total_minor, settlement.currency)} ${settlement.currency}`}
        </p>
      ) : usage?.state === "returned" && !booking.cancellation ? (
        <form aria-label="Settle" onSubmit={submit}>
          <InvoiceFields
            businessId={businessId}
            onError={setError}
            terms={terms}
            setTerms={setTerms}
          />
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Settle
            </button>
          </div>
        </form>
      ) : (
        <p>The settlement comes after the return.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

function ChargesPanel({
  businessId,
  booking,
  currency,
  inspections,
  charges,
  onCharged,
}: {
  businessId: string;
  booking: Booking;
  currency: string;
  inspections: Inspection[];
  charges: Charges | null;
  onCharged: (text: string) => void;
}) {
  const headingId = useId();
  const [chosen, setChosen] = useState<number[]>([]);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [terms, setTerms] = useState<InvoiceTerms>(NO_TERMS);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const charged = new Set(
    (charges?.damage_charges ?? []).flatMap((c) => c.marks),
  );
  const open = (
    inspections.find((i) => i.kind === "return")?.marks ?? []
  ).filter((m) => m.new && !charged.has(m.position));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (chosen.length === 0) throw new Error("Choose at least one new mark.");
      const saved = await chargeDamage(businessId, booking.booking_id, {
        ...terms,
        number: terms.number.trim(),
        marks: chosen,
        amount: minorOf(amount, currency, "Amount"),
        reason: reason.trim(),
      });
      setChosen([]);
      setAmount("");
      setReason("");
      onCharged(
        `Damage charge ${saved.damage_charges.at(-1)?.number ?? ""} recorded.`,
      );
    } catch (failure) {
      setError(`The damage was not charged: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const list = charges?.damage_charges ?? [];
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Damage charges</h3>
      {list.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Damage charges table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Damage charges">
            <thead>
              <tr>
                <th scope="col">Charge</th>
                <th scope="col">Marks</th>
                <th scope="col">Amount</th>
                <th scope="col">Reason</th>
              </tr>
            </thead>
            <tbody>
              {list.map((c) => (
                <tr key={c.number}>
                  <th scope="row">{c.number}</th>
                  <td>{c.marks.join(", ")}</td>
                  <td>{`${money(c.amount_minor, currency)} ${currency}`}</td>
                  <td>{c.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open.length > 0 ? (
        <form aria-label="Damage charge" onSubmit={submit}>
          <fieldset>
            <legend>New marks of the return</legend>
            {open.map((m) => (
              <label key={m.position}>
                <input
                  type="checkbox"
                  checked={chosen.includes(m.position)}
                  onChange={(e) =>
                    setChosen((all) =>
                      e.target.checked
                        ? [...all, m.position]
                        : all.filter((p) => p !== m.position),
                    )
                  }
                />
                {`Mark ${m.position}: ${m.area} (${m.severity})`}
              </label>
            ))}
          </fieldset>
          <label>
            Amount
            <input
              value={amount}
              inputMode="decimal"
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </label>
          <label>
            Reason
            <input
              value={reason}
              maxLength={500}
              onChange={(e) => setReason(e.target.value)}
              required
            />
          </label>
          <InvoiceFields
            businessId={businessId}
            onError={setError}
            terms={terms}
            setTerms={setTerms}
          />
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Charge
            </button>
          </div>
        </form>
      ) : (
        <p>No new mark of the return is left to charge.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

function RefundsPanel({
  businessId,
  booking,
  zone,
  currency,
  charges,
  reconciliation,
  onRefunded,
}: {
  businessId: string;
  booking: Booking;
  zone: string;
  currency: string;
  charges: Charges | null;
  reconciliation: Reconciliation | null;
  onRefunded: (text: string) => void;
}) {
  const headingId = useId();
  const issued = (reconciliation?.documents ?? []).filter(
    (d) => d.state === "issued",
  );
  const [method, setMethod] = useState<"external" | "credit">("external");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [invoice, setInvoice] = useState("");
  const [number, setNumber] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const common = {
        schema_version: 1 as const,
        amount: minorOf(amount, currency, "Amount"),
        reason: reason.trim(),
      };
      let saved: Charges;
      if (method === "external") {
        if (!zone) throw new Error("The pickup branch has no time zone.");
        saved = await recordRefund(businessId, booking.booking_id, {
          ...common,
          method,
          reference: reference.trim(),
          refunded_at: businessTimeToInstant(date, time, zone),
        });
      } else {
        saved = await recordRefund(businessId, booking.booking_id, {
          ...common,
          method,
          invoice_document_id: invoice,
          credit_date: date,
          number: number.trim(),
        });
      }
      setAmount("");
      setReason("");
      setReference("");
      onRefunded(`Refund ${saved.refunds.at(-1)?.number ?? ""} recorded.`);
    } catch (failure) {
      setError(`The refund was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const list = charges?.refunds ?? [];
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Refunds</h3>
      {list.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Refunds table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Refunds">
            <thead>
              <tr>
                <th scope="col">Refund</th>
                <th scope="col">Method</th>
                <th scope="col">Amount</th>
                <th scope="col">Reason</th>
                <th scope="col">Reference</th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => (
                <tr key={r.number}>
                  <th scope="row">{r.number}</th>
                  <td>
                    {r.method === "external" ? "External" : "Credit note"}
                  </td>
                  <td>{`${money(r.amount_minor, currency)} ${currency}`}</td>
                  <td>{r.reason}</td>
                  <td>{r.reference ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <form aria-label="Refund" onSubmit={submit}>
        <label>
          Method
          <select
            value={method}
            onChange={(e) => setMethod(e.target.value as "external" | "credit")}
          >
            <option value="external">External</option>
            {issued.length > 0 && <option value="credit">Credit note</option>}
          </select>
        </label>
        <label>
          Amount
          <input
            value={amount}
            inputMode="decimal"
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </label>
        <label>
          Reason
          <input
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
            required
          />
        </label>
        {method === "external" ? (
          <>
            <label>
              Reference
              <input
                value={reference}
                maxLength={200}
                onChange={(e) => setReference(e.target.value)}
                required
              />
            </label>
            <label>
              Refunded on
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </label>
            <label>
              Refunded at
              <input
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
                required
              />
            </label>
          </>
        ) : (
          <>
            <label>
              Invoice
              <select
                value={invoice}
                onChange={(e) => setInvoice(e.target.value)}
                required
              >
                <option value="">Choose an issued invoice</option>
                {issued.map((d) => (
                  <option key={d.document_id} value={d.document_id}>
                    {d.kind === "settlement"
                      ? "Settlement"
                      : `Damage charge ${d.number ?? ""}`}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Credit date
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </label>
            <label>
              Number
              <input
                value={number}
                maxLength={62}
                onChange={(e) => setNumber(e.target.value)}
                required
              />
            </label>
          </>
        )}
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Record refund
          </button>
        </div>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

function ReconciliationPanel({
  reconciliation,
}: {
  reconciliation: Reconciliation | null;
}) {
  const headingId = useId();
  if (!reconciliation)
    return (
      <section aria-labelledby={headingId}>
        <h3 id={headingId}>Reconciliation</h3>
        <p>The reconciliation comes with the settlement.</p>
      </section>
    );
  const c = reconciliation.currency;
  const t = reconciliation.totals;
  const s = reconciliation.security;
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>Reconciliation</h3>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Reconciliation documents table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Reconciliation documents">
          <thead>
            <tr>
              <th scope="col">Document</th>
              <th scope="col">Amount</th>
              <th scope="col">State</th>
              <th scope="col">Principal</th>
              <th scope="col">Paid</th>
              <th scope="col">Credited</th>
              <th scope="col">Open</th>
            </tr>
          </thead>
          <tbody>
            {reconciliation.documents.map((d) => (
              <tr key={d.document_id}>
                <th scope="row">
                  {d.kind === "settlement"
                    ? "Settlement"
                    : `Damage charge ${d.number ?? ""}`}
                </th>
                <td>{money(d.amount_minor, c)}</td>
                <td>{d.state === "issued" ? "Issued" : "Draft"}</td>
                <td>{money(d.principal_minor, c)}</td>
                <td>{money(d.paid_minor, c)}</td>
                <td>{money(d.credited_minor, c)}</td>
                <td>{money(d.open_minor, c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {reconciliation.refunds.length > 0 && (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Reconciliation refunds table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Reconciliation refunds">
            <thead>
              <tr>
                <th scope="col">Refund</th>
                <th scope="col">Method</th>
                <th scope="col">Amount</th>
                <th scope="col">State</th>
                <th scope="col">Owed back</th>
              </tr>
            </thead>
            <tbody>
              {reconciliation.refunds.map((r) => (
                <tr key={r.number}>
                  <th scope="row">{r.number}</th>
                  <td>
                    {r.method === "external" ? "External" : "Credit note"}
                  </td>
                  <td>{money(r.amount_minor, c)}</td>
                  <td>{r.state}</td>
                  <td>
                    {r.refund_obligation_minor === null
                      ? "—"
                      : money(
                          r.refund_obligation_minor -
                            (r.refund_paid_minor ?? 0),
                          c,
                        )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p>
        {s
          ? `Security in the reconciliation: ${s.state}; held ${money(s.held, c)}, captured ` +
            `${money(s.captured, c)}, released ${money(s.released, c)}, expired ` +
            `${money(s.expired, c)}, remaining ${money(s.remaining, c)} ${c}`
          : "No security was requested."}
      </p>
      <p>
        {`Totals: charged ${money(t.charged_minor, c)}, invoiced ${money(t.invoiced_minor, c)}, ` +
          `paid ${money(t.paid_minor, c)}, credited ${money(t.credited_minor, c)}, open ` +
          `${money(t.open_minor, c)}, refunded externally ${money(t.refunded_external_minor, c)}, ` +
          `refund owed ${money(t.refund_owed_minor, c)} ${c}`}
      </p>
    </section>
  );
}
