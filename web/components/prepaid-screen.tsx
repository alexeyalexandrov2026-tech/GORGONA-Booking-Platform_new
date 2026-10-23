"use client";

// L7b2b (package L): the business's prepaid balances and selling one. A package names a service and
// its units, a certificate only a value; the sale is a draft invoice on a prepayment liability that
// finance issues and settles. Words stay neutral: any direction can sell time or value in advance.
import React, { useCallback, useEffect, useId, useState } from "react";
import { businessToday } from "../lib/business-time";
import { fetchFinancialOverview } from "../lib/financial-api";
import {
  fetchAllPrepaid,
  fetchServices,
  ManagementApiError,
  type PrepaidView,
  sellPrepaid,
  type ServiceView,
} from "../lib/management-api";
import {
  type Account,
  AccountSelect,
  allAccounts,
  allActiveParties,
  allBooks,
  type Book,
  type Party,
  prepaidLabel,
} from "./visit-billing";

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

export function PrepaidScreen({ salonId }: { salonId: string }) {
  const formId = useId();
  const [balances, setBalances] = useState<PrepaidView[]>([]);
  const [services, setServices] = useState<ServiceView[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [books, setBooks] = useState<Book[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [filter, setFilter] = useState("");
  const [kind, setKind] = useState<"package" | "certificate">("package");
  const [customer, setCustomer] = useState("");
  const [variant, setVariant] = useState("");
  const [units, setUnits] = useState("1");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [book, setBook] = useState("");
  const [control, setControl] = useState("");
  const [prepayment, setPrepayment] = useState("");
  const [number, setNumber] = useState("");
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(
    () =>
      fetchAllPrepaid(salonId, filter || undefined).then((list) => {
        setBalances(list);
        setLoaded(true);
      }),
    [salonId, filter],
  );

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchServices(salonId),
      allActiveParties(salonId),
      allBooks(salonId),
      fetchFinancialOverview(salonId),
    ])
      .then(([serviceList, partyList, bookList, overview]) => {
        if (!live) return;
        setServices(serviceList);
        setParties(partyList);
        setBooks(bookList);
        setBook((current) => current || (bookList[0]?.book_id ?? ""));
        setDate((current) => current || businessToday(overview.timezone));
      })
      .catch((failure: unknown) => {
        if (live) setError(`The screen could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [salonId]);

  useEffect(() => {
    reload().catch((failure: unknown) =>
      setError(`The balances could not be read: ${refusal(failure)}`),
    );
  }, [reload]);

  useEffect(() => {
    if (!book) return;
    let live = true;
    allAccounts(salonId, book)
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
  }, [salonId, book]);

  async function sell(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await sellPrepaid(salonId, {
        kind,
        counterparty_id: customer,
        ...(kind === "package"
          ? { variant_id: variant, units: Number(units) }
          : {}),
        price: price.trim(),
        currency: currency.trim().toUpperCase(),
        book_id: book,
        control_account_id: control,
        prepayment_account_id: prepayment,
        invoice_date: date,
        number: number.trim(),
      });
      setNotice("Prepaid balance saved; finance issues its invoice.");
      await reload();
    } catch (failure) {
      setError(`The balance was not sold: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const customers = parties.filter((p) => p.roles.includes("customer"));
  const nameOf = (party: string) =>
    parties.find((p) => p.counterparty_id === party)?.display_name ?? party;

  return (
    <div className="prepaid-screen">
      <h1>Prepaid balances</h1>
      <p className="muted">
        Packages of a service and certificates of a value, paid in advance and
        redeemed from the visit desk.
      </p>
      <label className="prepaid-filter">
        Customer filter
        <select
          aria-label="Customer filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="">All customers</option>
          {customers.map((p) => (
            <option key={p.counterparty_id} value={p.counterparty_id}>
              {p.display_name}
            </option>
          ))}
        </select>
      </label>
      {!loaded && !error && (
        <p className="muted" role="status">
          Loading the balances…
        </p>
      )}
      {loaded &&
        (balances.length === 0 ? (
          <p className="muted">No prepaid balances yet.</p>
        ) : (
          <div
            className="mgmt-table-container"
            role="region"
            aria-label="Prepaid balances table"
            tabIndex={0}
          >
            <table className="mgmt-table" aria-label="Prepaid balances">
              <thead>
                <tr>
                  <th scope="col">Customer</th>
                  <th scope="col">Balance</th>
                  <th scope="col">Invoice</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {balances.map((b) => (
                  <tr key={b.prepaid_id}>
                    <th scope="row">{nameOf(b.counterparty_id)}</th>
                    <td>{prepaidLabel(b, services)}</td>
                    <td>
                      {b.sale.number}: {b.sale.state}
                    </td>
                    <td>{b.usable ? "Usable" : "Waiting for payment"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      <form onSubmit={sell} aria-labelledby={formId}>
        <h2 id={formId}>Sell a prepaid balance</h2>
        <label>
          Kind
          <select
            aria-label="Kind"
            value={kind}
            onChange={(e) =>
              setKind(e.target.value as "package" | "certificate")
            }
          >
            <option value="package">Package</option>
            <option value="certificate">Certificate</option>
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
        {kind === "package" && (
          <>
            <label>
              Service
              <select
                aria-label="Service"
                value={variant}
                onChange={(e) => setVariant(e.target.value)}
                required
              >
                <option value="">Choose a service</option>
                {services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Units
              <input
                type="number"
                min={1}
                max={1000}
                value={units}
                onChange={(e) => setUnits(e.target.value)}
                required
              />
            </label>
          </>
        )}
        <label>
          Price
          <input
            type="text"
            inputMode="decimal"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            required
          />
        </label>
        <label>
          Currency
          <input
            type="text"
            value={currency}
            maxLength={3}
            pattern="[A-Za-z]{3}"
            onChange={(e) => setCurrency(e.target.value)}
            required
          />
        </label>
        <label>
          Book
          <select
            aria-label="Book"
            value={book}
            onChange={(e) => {
              setBook(e.target.value);
              setControl("");
              setPrepayment("");
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
        <AccountSelect
          label="Receivable account"
          accounts={accounts}
          types={["asset"]}
          value={control}
          onChange={setControl}
        />
        <AccountSelect
          label="Prepayment account"
          accounts={accounts}
          types={["liability"]}
          value={prepayment}
          onChange={setPrepayment}
        />
        <label>
          Number
          <input
            type="text"
            value={number}
            maxLength={64}
            onChange={(e) => setNumber(e.target.value)}
            required
          />
        </label>
        <label>
          Invoice date
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            required
          />
        </label>
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            {busy ? "Selling…" : "Sell"}
          </button>
        </div>
      </form>
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
    </div>
  );
}
