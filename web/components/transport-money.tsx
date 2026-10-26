"use client";

// M7b (package M, ADR-0033): an order's rate and customer invoice, a trip's pay components and their
// accruals. A company-wide finance member works here; issuing and payment stay on the finance screens.
// Every command keeps its record id and key until it succeeds; refusals are shown in words.
import React, { useEffect, useId, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import {
  accrueComponent,
  createOrderInvoice,
  fetchOrderInvoice,
  fetchPay,
  fetchRate,
  saveComponent,
  saveRate,
} from "../lib/transport-api";
import type {
  Component,
  Order,
  OrderInvoice,
  Pay,
  Rate,
  Trip,
} from "../lib/transport-contracts";
import {
  AccountSelect,
  allAccounts,
  allActiveParties,
  allBooks,
  type Account,
  type Book,
  type Party,
} from "./visit-billing";

type Notify = (text: string) => void;

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

const STATE: Record<string, string> = { draft: "Draft", issued: "Issued" };
const ROLES: [Component["role"], string][] = [
  ["driver", "Driver"],
  ["owner_operator", "Owner-operator"],
  ["dispatch_fee", "Dispatch fee"],
  ["other", "Other"],
];
const roleLabel = (role: string) =>
  ROLES.find(([value]) => value === role)?.[1] ?? role;

/** The books and, for the chosen one, its accounts. */
function useBooks(businessId: string, onError: (text: string) => void) {
  const [books, setBooks] = useState<Book[]>([]);
  const [book, setBook] = useState("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  useEffect(() => {
    allBooks(businessId)
      .then(setBooks)
      .catch((failure: unknown) =>
        onError(`The books could not be read: ${refusal(failure)}`),
      );
  }, [businessId, onError]);
  useEffect(() => {
    if (!book) return;
    let live = true;
    allAccounts(businessId, book)
      .then((found) => {
        if (live) setAccounts(found);
      })
      .catch((failure: unknown) =>
        onError(`The accounts could not be read: ${refusal(failure)}`),
      );
    return () => {
      live = false;
    };
  }, [businessId, book, onError]);
  // Another book's accounts never stay on the form.
  const choose = (value: string) => {
    setBook(value);
    setAccounts([]);
  };
  return { books, book, setBook: choose, accounts };
}

function BookSelect({
  books,
  value,
  onChange,
}: {
  books: Book[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      Book
      <select
        aria-label="Book"
        value={value}
        onChange={(e) => onChange(e.target.value)}
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
  );
}

type Extra = {
  key: string;
  description: string;
  amount: string;
  account: string;
};

export function OrderMoney({
  businessId,
  order,
  notify,
}: {
  businessId: string;
  order: Order;
  notify: Notify;
}) {
  const headingId = useId();
  const [rate, setRate] = useState<Rate | null>(null);
  const [invoice, setInvoice] = useState<OrderInvoice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [basis, setBasis] = useState<"fixed" | "per_mile">("fixed");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("USD");
  const { books, book, setBook, accounts } = useBooks(businessId, setError);
  const [receivable, setReceivable] = useState("");
  const [revenue, setRevenue] = useState("");
  const [date, setDate] = useState("");
  const [number, setNumber] = useState("");
  const [miles, setMiles] = useState("");
  const [extras, setExtras] = useState<Extra[]>([]);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchRate(businessId, order.order_id),
      fetchOrderInvoice(businessId, order.order_id),
    ])
      .then(([read, billed]) => {
        if (!live) return;
        setRate(read);
        setInvoice(billed);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The order's money could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId, order.order_id]);

  async function submitRate(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    setBusy(true);
    try {
      setRate(
        await saveRate(businessId, order.order_id, {
          schema_version: 1,
          expected_revision: rate?.current?.revision ?? 0,
          currency: currency.trim().toUpperCase(),
          basis,
          amount: amount.trim(),
        }),
      );
      setAmount("");
      notify("Rate saved.");
    } catch (failure) {
      setError(`The rate was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function submitInvoice(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    setBusy(true);
    try {
      setInvoice(
        await createOrderInvoice(businessId, order.order_id, {
          schema_version: 1,
          book_id: book,
          control_account_id: receivable,
          revenue_account_id: revenue,
          invoice_date: date,
          number: number.trim(),
          miles: miles.trim() || null,
          extra_lines: extras.map((x) => ({
            description: x.description.trim(),
            amount: x.amount.trim(),
            account_id: x.account,
          })),
        }),
      );
      notify("Invoice draft created.");
    } catch (failure) {
      setError(`The invoice was not created: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const current = rate?.current;
  const document = invoice?.invoice;
  return (
    <section className="transport-money" aria-labelledby={headingId}>
      <h2 id={headingId}>Money for {order.reference}</h2>
      <p>
        {current
          ? `Rate: ${current.basis === "per_mile" ? "Per mile" : "Fixed for the order"} ${current.amount} ${current.currency} (version ${current.revision})`
          : "No rate yet."}
      </p>
      {!invoice && (
        <form aria-label="Rate" onSubmit={submitRate}>
          <h3>Rate</h3>
          <label>
            Basis
            <select
              aria-label="Basis"
              value={basis}
              onChange={(e) => setBasis(e.target.value as "fixed" | "per_mile")}
            >
              <option value="fixed">Fixed for the order</option>
              <option value="per_mile">Per mile</option>
            </select>
          </label>
          <label>
            Amount
            <input
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </label>
          <label>
            Currency
            <input
              value={currency}
              maxLength={3}
              onChange={(e) => setCurrency(e.target.value)}
              required
            />
          </label>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Save rate
            </button>
          </div>
        </form>
      )}
      {document ? (
        <>
          <div
            className="mgmt-table-container"
            role="region"
            aria-label="Invoice lines table"
            tabIndex={0}
          >
            <table className="mgmt-table" aria-label="Invoice lines">
              <thead>
                <tr>
                  <th scope="col">Line</th>
                  <th scope="col">Amount</th>
                </tr>
              </thead>
              <tbody>
                {document.lines.map((line) => (
                  <tr key={line.line_id}>
                    <th scope="row">{line.description}</th>
                    <td>{line.amount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            Total {document.total} {document.currency} · Invoice{" "}
            {document.number} · {STATE[document.state] ?? document.state} ·{" "}
            {invoice?.obligation
              ? `paid ${invoice.obligation.paid}, open ${invoice.obligation.available}`
              : "not issued yet; issue it on the financial documents screen"}
          </p>
        </>
      ) : (
        current && (
          <form aria-label="Customer invoice" onSubmit={submitInvoice}>
            <h3>Customer invoice</h3>
            <BookSelect books={books} value={book} onChange={setBook} />
            <AccountSelect
              label="Receivable account"
              accounts={accounts}
              types={["asset"]}
              value={receivable}
              onChange={setReceivable}
            />
            <AccountSelect
              label="Revenue account"
              accounts={accounts}
              types={["revenue"]}
              value={revenue}
              onChange={setRevenue}
            />
            <label>
              Invoice date
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
                maxLength={64}
                onChange={(e) => setNumber(e.target.value)}
                required
              />
            </label>
            <label>
              Miles
              <input
                inputMode="decimal"
                value={miles}
                onChange={(e) => setMiles(e.target.value)}
              />
            </label>
            <p className="muted">
              Billed miles are needed for a per-mile rate.
            </p>
            {extras.map((extra, index) => (
              <fieldset key={extra.key}>
                <legend>Extra {index + 1}</legend>
                <label>
                  Description
                  <input
                    value={extra.description}
                    maxLength={500}
                    onChange={(e) =>
                      setExtras((rows) =>
                        rows.map((x, i) =>
                          i === index
                            ? { ...x, description: e.target.value }
                            : x,
                        ),
                      )
                    }
                    required
                  />
                </label>
                <label>
                  Amount
                  <input
                    inputMode="decimal"
                    value={extra.amount}
                    onChange={(e) =>
                      setExtras((rows) =>
                        rows.map((x, i) =>
                          i === index ? { ...x, amount: e.target.value } : x,
                        ),
                      )
                    }
                    required
                  />
                </label>
                <AccountSelect
                  label="Account"
                  accounts={accounts}
                  types={["revenue", "liability"]}
                  value={extra.account}
                  onChange={(value) =>
                    setExtras((rows) =>
                      rows.map((x, i) =>
                        i === index ? { ...x, account: value } : x,
                      ),
                    )
                  }
                />
                <button
                  type="button"
                  onClick={() =>
                    setExtras((rows) => rows.filter((_, i) => i !== index))
                  }
                >
                  Remove extra {index + 1}
                </button>
              </fieldset>
            ))}
            <div className="mgmt-form-actions">
              {extras.length < 20 && (
                <button
                  type="button"
                  onClick={() =>
                    setExtras((rows) => [
                      ...rows,
                      {
                        key: crypto.randomUUID(),
                        description: "",
                        amount: "",
                        account: "",
                      },
                    ])
                  }
                >
                  Add an extra
                </button>
              )}
              <button type="submit" disabled={busy}>
                Create invoice
              </button>
            </div>
          </form>
        )
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

function formula(c: Component): string {
  if (c.basis === "per_mile") return `${c.rate} ${c.currency} per mile`;
  if (c.basis === "percent") return `${c.percent}% of ${c.base} ${c.currency}`;
  return `${c.amount} ${c.currency}`;
}

export function TripPay({
  businessId,
  trip,
  notify,
}: {
  businessId: string;
  trip: Trip;
  notify: Notify;
}) {
  const headingId = useId();
  const [pay, setPay] = useState<Pay | null>(null);
  const [parties, setParties] = useState<Party[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Pay component.
  const [componentId, setComponentId] = useState(() => crypto.randomUUID());
  const [recipient, setRecipient] = useState("");
  const [role, setRole] = useState<Component["role"]>("driver");
  const [currency, setCurrency] = useState("USD");
  const [basis, setBasis] = useState<Component["basis"]>("fixed");
  const [amount, setAmount] = useState("");
  const [rate, setRate] = useState("");
  const [percent, setPercent] = useState("");
  const [agreed, setAgreed] = useState("");
  // Accrue.
  const [chosen, setChosen] = useState("");
  const { books, book, setBook, accounts } = useBooks(businessId, setError);
  const [expense, setExpense] = useState("");
  const [payable, setPayable] = useState("");
  const [date, setDate] = useState("");
  const [number, setNumber] = useState("");
  const [miles, setMiles] = useState("");

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchPay(businessId, trip.trip_id),
      allActiveParties(businessId),
    ])
      .then(([read, people]) => {
        if (!live) return;
        setPay(read);
        setParties(people);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The trip's pay could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId, trip.trip_id]);

  const nameOf = (id: string) =>
    parties.find((p) => p.counterparty_id === id)?.display_name ?? "Unknown";
  const changed = (component: Component) =>
    setPay((current) =>
      current
        ? {
            ...current,
            components: current.components.some(
              (c) => c.component_id === component.component_id,
            )
              ? current.components.map((c) =>
                  c.component_id === component.component_id ? component : c,
                )
              : [...current.components, component],
          }
        : current,
    );

  async function register(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    setBusy(true);
    try {
      changed(
        await saveComponent(businessId, trip.trip_id, componentId, {
          schema_version: 1,
          counterparty_id: recipient,
          role,
          currency: currency.trim().toUpperCase(),
          basis,
          amount: basis === "fixed" ? amount.trim() : null,
          rate: basis === "per_mile" ? rate.trim() : null,
          percent: basis === "percent" ? percent.trim() : null,
          base: basis === "percent" ? agreed.trim() : null,
        }),
      );
      setComponentId(crypto.randomUUID());
      setAmount("");
      setRate("");
      setPercent("");
      setAgreed("");
      notify("Pay component registered.");
    } catch (failure) {
      setError(`The pay component was not registered: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function accrue(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    notify("");
    setBusy(true);
    try {
      changed(
        await accrueComponent(businessId, trip.trip_id, chosen, {
          schema_version: 1,
          book_id: book,
          expense_account_id: expense,
          payable_account_id: payable,
          accrual_date: date,
          number: number.trim(),
          miles: miles.trim() || null,
        }),
      );
      setChosen("");
      setNumber("");
      setMiles("");
      notify("Pay accrued.");
    } catch (failure) {
      setError(`The pay was not accrued: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const open = pay?.components.filter((c) => c.accrual === null) ?? [];
  return (
    <section className="transport-pay" aria-labelledby={headingId}>
      <h3 id={headingId}>Trip pay</h3>
      <div
        className="mgmt-table-container"
        role="region"
        aria-label="Pay components table"
        tabIndex={0}
      >
        <table className="mgmt-table" aria-label="Pay components">
          <thead>
            <tr>
              <th scope="col">Role</th>
              <th scope="col">Recipient</th>
              <th scope="col">Formula</th>
              <th scope="col">Accrual</th>
            </tr>
          </thead>
          <tbody>
            {!pay || pay.components.length === 0 ? (
              <tr>
                <td colSpan={4}>No pay components yet.</td>
              </tr>
            ) : (
              pay.components.map((c) => (
                <tr key={c.component_id}>
                  <th scope="row">{roleLabel(c.role)}</th>
                  <td>{nameOf(c.counterparty_id)}</td>
                  <td>{formula(c)}</td>
                  <td>
                    {c.accrual
                      ? `${c.accrual.accrual.total} ${c.accrual.accrual.currency} · ${STATE[c.accrual.accrual.state] ?? c.accrual.accrual.state}${c.accrual.obligation ? ` · paid ${c.accrual.obligation.paid}, open ${c.accrual.obligation.available}` : ""}`
                      : "Not accrued"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <form aria-label="Pay component" onSubmit={register}>
        <h4>Pay component</h4>
        <label>
          Recipient
          <select
            aria-label="Recipient"
            value={recipient}
            onChange={(e) => setRecipient(e.target.value)}
            required
          >
            <option value="">Choose</option>
            {parties.map((p) => (
              <option key={p.counterparty_id} value={p.counterparty_id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Role
          <select
            aria-label="Role"
            value={role}
            onChange={(e) => setRole(e.target.value as Component["role"])}
          >
            {ROLES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Currency
          <input
            value={currency}
            maxLength={3}
            onChange={(e) => setCurrency(e.target.value)}
            required
          />
        </label>
        <label>
          Formula
          <select
            aria-label="Formula"
            value={basis}
            onChange={(e) => setBasis(e.target.value as Component["basis"])}
          >
            <option value="fixed">Fixed amount</option>
            <option value="per_mile">Per mile</option>
            <option value="percent">Percent of an agreed base</option>
          </select>
        </label>
        {basis === "fixed" && (
          <label>
            Amount
            <input
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </label>
        )}
        {basis === "per_mile" && (
          <label>
            Rate per mile
            <input
              inputMode="decimal"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              required
            />
          </label>
        )}
        {basis === "percent" && (
          <>
            <label>
              Percent
              <input
                inputMode="decimal"
                value={percent}
                onChange={(e) => setPercent(e.target.value)}
                required
              />
            </label>
            <label>
              Agreed base
              <input
                inputMode="decimal"
                value={agreed}
                onChange={(e) => setAgreed(e.target.value)}
                required
              />
            </label>
          </>
        )}
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            Register
          </button>
        </div>
      </form>
      {open.length > 0 && (
        <form aria-label="Accrue" onSubmit={accrue}>
          <h4>Accrue</h4>
          <label>
            Component
            <select
              aria-label="Component"
              value={chosen}
              onChange={(e) => setChosen(e.target.value)}
              required
            >
              <option value="">Choose</option>
              {open.map((c) => (
                <option key={c.component_id} value={c.component_id}>
                  {`${roleLabel(c.role)} · ${nameOf(c.counterparty_id)}`}
                </option>
              ))}
            </select>
          </label>
          <BookSelect books={books} value={book} onChange={setBook} />
          <AccountSelect
            label="Expense account"
            accounts={accounts}
            types={["expense"]}
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
            Accrual date
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
              maxLength={64}
              onChange={(e) => setNumber(e.target.value)}
              required
            />
          </label>
          <label>
            Miles
            <input
              inputMode="decimal"
              value={miles}
              onChange={(e) => setMiles(e.target.value)}
            />
          </label>
          <p className="muted">
            Miles are needed for a per-mile component; the trip must be closed.
          </p>
          <div className="mgmt-form-actions">
            <button type="submit" disabled={busy}>
              Accrue
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
