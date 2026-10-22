"use client";

// L7b2a (package L): bill a visit and accrue its specialist's commission from the visit desk.
// Finance issues the invoice and records the payment on its own screens; the desk shows both.
import React, { useEffect, useId, useState } from "react";
import { fetchCounterparties } from "../lib/counterparty-api";
import { fetchAccounts, fetchLedger } from "../lib/ledger-api";
import {
  accrueVisitCommission,
  billVisit,
  fetchVisitCommission,
  fetchVisitInvoice,
  ManagementApiError,
  type VisitCommissionView,
  type VisitInvoiceView,
} from "../lib/management-api";

type Book = { book_id: string; legal_name: string };
type Account = { account_id: string; code: string; name: string; type: string };
export type Party = {
  counterparty_id: string;
  display_name: string;
  roles: string[];
};

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function unsafe(): never {
  throw new ManagementApiError(
    "INVALID_RESPONSE",
    "Unable to load the complete list safely.",
  );
}

async function allBooks(business: string): Promise<Book[]> {
  const books: Book[] = [];
  const seen = new Set<string>();
  let after: string | undefined;
  for (;;) {
    const page = await fetchLedger(business, after);
    for (const item of page.items)
      if (item.book)
        books.push({ book_id: item.book.book_id, legal_name: item.legal_name });
    if (page.next_cursor === null) return books;
    if (seen.has(page.next_cursor)) unsafe();
    seen.add(page.next_cursor);
    after = page.next_cursor;
  }
}

async function allAccounts(business: string, book: string): Promise<Account[]> {
  const accounts: Account[] = [];
  const seen = new Set<string>();
  let after: string | undefined;
  for (;;) {
    const page = await fetchAccounts(business, book, after);
    accounts.push(...page.items.filter((a) => !a.archived));
    if (page.next_cursor === null) return accounts;
    if (seen.has(page.next_cursor)) unsafe();
    seen.add(page.next_cursor);
    after = page.next_cursor;
  }
}

/** Every active counterparty of the business, paged to the end. */
export async function allActiveParties(business: string): Promise<Party[]> {
  const parties: Party[] = [];
  const seen = new Set<string>();
  let after: string | undefined;
  for (;;) {
    const page = await fetchCounterparties(business, "", "active", after);
    parties.push(...page.items);
    if (page.next_cursor === null) return parties;
    if (seen.has(page.next_cursor)) unsafe();
    seen.add(page.next_cursor);
    after = page.next_cursor;
  }
}

function AccountSelect({
  label,
  accounts,
  types,
  value,
  onChange,
}: {
  label: string;
  accounts: Account[];
  types: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  const fitting = accounts.filter((a) => types.includes(a.type));
  return (
    <label>
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
      >
        <option value="">Choose an account</option>
        {fitting.map((a) => (
          <option key={a.account_id} value={a.account_id}>
            {a.code} {a.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function VisitBillingSection({
  salonId,
  bookingId,
  today,
}: {
  salonId: string;
  bookingId: string;
  today: string;
}) {
  const headingId = useId();
  const invoiceHeadingId = useId();
  const commissionHeadingId = useId();
  const [invoice, setInvoice] = useState<VisitInvoiceView | null>(null);
  const [commission, setCommission] = useState<VisitCommissionView | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);
  const [unavailable, setUnavailable] = useState<string | null>(null);
  const [books, setBooks] = useState<Book[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [book, setBook] = useState("");
  const [customer, setCustomer] = useState("");
  const [control, setControl] = useState("");
  const [revenue, setRevenue] = useState("");
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(today);
  const [expense, setExpense] = useState("");
  const [payable, setPayable] = useState("");
  const [accrualNumber, setAccrualNumber] = useState("");
  const [accrualDate, setAccrualDate] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchVisitInvoice(salonId, bookingId),
      fetchVisitCommission(salonId, bookingId),
      allBooks(salonId),
      allActiveParties(salonId),
    ])
      .then(([billed, accrued, bookList, partyList]) => {
        if (!live) return;
        setInvoice(billed);
        setCommission(accrued);
        setBooks(bookList);
        setParties(partyList);
        setBook((current) => current || (bookList[0]?.book_id ?? ""));
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live)
          setUnavailable(`Billing is not available here: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [salonId, bookingId]);

  // The accounts of the book in use: the invoice's book once there is one.
  const activeBook = invoice?.book_id ?? book;
  useEffect(() => {
    if (!activeBook) return;
    let live = true;
    allAccounts(salonId, activeBook)
      .then((list) => {
        if (live) setAccounts(list);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The accounts could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [salonId, activeBook]);

  async function bill(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setInvoice(
        await billVisit(salonId, bookingId, {
          book_id: book,
          counterparty_id: customer,
          control_account_id: control,
          revenue_account_id: revenue,
          invoice_date: invoiceDate,
          number: invoiceNumber.trim(),
        }),
      );
      setNotice("Invoice saved as a draft.");
    } catch (failure) {
      setError(`The invoice was not created: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function accrue(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const accrued = await accrueVisitCommission(salonId, bookingId, {
        expense_account_id: expense,
        payable_account_id: payable,
        accrual_date: accrualDate,
        number: accrualNumber.trim(),
      });
      setCommission(accrued);
      setNotice(`Commission accrued: ${accrued.accrual.total}`);
    } catch (failure) {
      setError(`The commission was not accrued: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const customers = parties.filter((p) => p.roles.includes("customer"));
  const obligation = invoice?.obligation ?? null;

  return (
    <section aria-labelledby={headingId} className="visit-billing">
      <h3 id={headingId}>Billing</h3>
      {unavailable && (
        <p className="muted" role="status">
          {unavailable}
        </p>
      )}
      {!loaded && !unavailable && (
        <p className="muted" role="status">
          Loading the billing…
        </p>
      )}
      {loaded && invoice === null && (
        <form onSubmit={bill} aria-labelledby={invoiceHeadingId}>
          <h4 id={invoiceHeadingId}>Invoice</h4>
          <p className="muted">
            Saved as a draft; finance issues it and records the payment.
          </p>
          <label>
            Book
            <select
              aria-label="Book"
              value={book}
              onChange={(e) => {
                setBook(e.target.value);
                setControl("");
                setRevenue("");
              }}
              required
            >
              <option value="">Choose a book</option>
              {books.map((b) => (
                <option key={b.book_id} value={b.book_id}>
                  {b.legal_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Customer
            <select
              aria-label="Customer"
              value={customer}
              onChange={(e) => setCustomer(e.target.value)}
              required
            >
              <option value="">Choose a customer</option>
              {customers.map((p) => (
                <option key={p.counterparty_id} value={p.counterparty_id}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </label>
          <AccountSelect
            label="Receivable account"
            accounts={accounts}
            types={["asset"]}
            value={control}
            onChange={setControl}
          />
          <AccountSelect
            label="Revenue account"
            accounts={accounts}
            types={["revenue", "liability"]}
            value={revenue}
            onChange={setRevenue}
          />
          <label>
            Number
            <input
              type="text"
              value={invoiceNumber}
              maxLength={64}
              onChange={(e) => setInvoiceNumber(e.target.value)}
              required
            />
          </label>
          <label>
            Invoice date
            <input
              type="date"
              value={invoiceDate}
              onChange={(e) => setInvoiceDate(e.target.value)}
              required
            />
          </label>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              {busy ? "Creating…" : "Create invoice"}
            </button>
          </div>
        </form>
      )}
      {invoice !== null && (
        <>
          <p className="hold-note">
            Invoice {invoice.invoice.number}: {invoice.invoice.state}
          </p>
          {obligation ? (
            <p className="muted">
              Paid {obligation.paid} of {obligation.principal}
            </p>
          ) : (
            <p className="muted">
              Finance issues the invoice; the commission follows its payment.
            </p>
          )}
        </>
      )}
      {commission !== null && (
        <p className="hold-note">
          Commission {commission.accrual.number}: {commission.accrual.total}
        </p>
      )}
      {invoice !== null && obligation !== null && commission === null && (
        <form onSubmit={accrue} aria-labelledby={commissionHeadingId}>
          <h4 id={commissionHeadingId}>Commission</h4>
          <p className="muted">
            Accrued once, from the specialist&apos;s plan, after the visit is
            paid in full.
          </p>
          <AccountSelect
            label="Expense account"
            accounts={accounts}
            types={["expense", "asset"]}
            value={expense}
            onChange={setExpense}
          />
          <AccountSelect
            label="Payable account"
            accounts={accounts}
            types={["liability"]}
            value={payable}
            onChange={setPayable}
          />
          <label>
            Number
            <input
              type="text"
              value={accrualNumber}
              maxLength={64}
              onChange={(e) => setAccrualNumber(e.target.value)}
              required
            />
          </label>
          <label>
            Accrual date
            <input
              type="date"
              value={accrualDate}
              onChange={(e) => setAccrualDate(e.target.value)}
              required
            />
          </label>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              {busy ? "Accruing…" : "Accrue commission"}
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="hold-note" role="status">
          {notice}
        </p>
      )}
    </section>
  );
}
