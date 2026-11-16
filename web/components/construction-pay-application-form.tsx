"use client";

import React, { useEffect, useId, useState } from "react";
import { businessToday, shiftDate } from "../lib/business-time";
import { refusal, type PayApplicationBody } from "../lib/construction-api";
import type { Project } from "../lib/construction-contracts";
import {
  AccountSelect,
  allAccounts,
  allBooks,
  type Account,
  type Book,
} from "./visit-billing";

export function PayApplicationForm({
  business,
  project,
  lastPeriod,
  busy,
  onCreate,
  onCancel,
}: {
  business: string;
  project: Project;
  lastPeriod: string | undefined;
  busy: boolean;
  onCreate: (body: PayApplicationBody) => void;
  onCancel: () => void;
}) {
  const bookId = useId();
  const [books, setBooks] = useState<Book[]>();
  const [accounts, setAccounts] = useState<Account[]>();
  const [book, setBook] = useState("");
  const [receivable, setReceivable] = useState("");
  const [revenue, setRevenue] = useState("");
  const [retainage, setRetainage] = useState("");
  const [error, setError] = useState("");
  const [readError, setReadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const today = businessToday(project.time_zone);
  const earliest = lastPeriod ? shiftDate(lastPeriod, 1) : undefined;

  useEffect(() => {
    let current = true;
    const load = book
      ? allAccounts(business, book).then((items) => {
          if (current) setAccounts(items);
        })
      : allBooks(business).then((items) => {
          if (current) setBooks(items);
        });
    load.catch((failure: unknown) => {
      if (current) setReadError(refusal(failure));
    });
    return () => {
      current = false;
    };
  }, [attempt, book, business]);

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !accounts || !receivable || !revenue || !retainage) return;
    const fd = new FormData(event.currentTarget);
    const value = (key: string) => String(fd.get(key) ?? "").trim();
    const period = value("period");
    const invoiceDate = value("invoice_date");
    const dueDate = value("due_date");
    const number = value("number");
    const title = value("title");
    if (
      !today ||
      !period ||
      period > today ||
      (earliest && period < earliest)
    ) {
      setError(
        "Choose an unbilled period ending by today at the project site.",
      );
      return;
    }
    if (!invoiceDate || (dueDate && dueDate < invoiceDate)) {
      setError(
        "Enter an invoice date and a due date on or after it, if needed.",
      );
      return;
    }
    if (!number || !title) {
      setError("Enter an invoice number and title.");
      return;
    }
    setError("");
    onCreate({
      schema_version: 1,
      period_end: period,
      book_id: book,
      receivable_account_id: receivable,
      revenue_account_id: revenue,
      retainage_account_id: retainage,
      invoice_date: invoiceDate,
      due_date: dueDate || null,
      number,
      title,
    });
  }

  return (
    <form
      className="mgmt-form"
      aria-label="New pay application"
      onSubmit={submit}
    >
      <fieldset disabled={busy}>
        <legend>New pay application</legend>
        <p>
          Saving closes the period for measurements and creates draft documents
          in Finance.
        </p>
        <label>
          Period end{" "}
          <input
            name="period"
            type="date"
            min={earliest}
            max={today || undefined}
            required
          />
        </label>
        <label>
          Invoice date{" "}
          <input
            name="invoice_date"
            type="date"
            defaultValue={today}
            required
          />
        </label>
        <label>
          Due date <input name="due_date" type="date" />
        </label>
        <label>
          Invoice number <input name="number" maxLength={62} required />
        </label>
        <label>
          Invoice title{" "}
          <input
            name="title"
            defaultValue="Pay application"
            maxLength={200}
            required
          />
        </label>
        <label htmlFor={bookId}>Ledger book</label>
        <select
          id={bookId}
          value={book}
          disabled={!books?.length}
          required
          onChange={(event) => {
            setBook(event.target.value);
            setAccounts(undefined);
            setReceivable("");
            setRevenue("");
            setRetainage("");
            setReadError("");
            setError("");
          }}
        >
          <option value="">Choose a ledger book</option>
          {books?.map((item) => (
            <option key={item.book_id} value={item.book_id}>
              {item.legal_name}
            </option>
          ))}
        </select>
        {!books && !readError && <p role="status">Loading ledger books…</p>}
        {books?.length === 0 && <p>No ledger books are available.</p>}
        {book && !accounts && !readError && (
          <p role="status">Loading ledger accounts…</p>
        )}
        {accounts && (
          <>
            <AccountSelect
              label="Receivable account"
              accounts={accounts}
              types={["asset"]}
              value={receivable}
              onChange={(value) => {
                setReceivable(value);
                if (value === retainage) setRetainage("");
              }}
            />
            <AccountSelect
              label="Revenue account"
              accounts={accounts}
              types={["revenue"]}
              value={revenue}
              onChange={setRevenue}
            />
            <AccountSelect
              label="Retainage account"
              accounts={accounts.filter(
                (item) => item.account_id !== receivable,
              )}
              types={["asset"]}
              value={retainage}
              onChange={setRetainage}
            />
          </>
        )}
        {readError && (
          <>
            <p role="alert">{readError}</p>
            <button
              type="button"
              onClick={() => {
                setReadError("");
                setAttempt((current) => current + 1);
              }}
            >
              Retry ledger
            </button>
          </>
        )}
        {error && <p role="alert">{error}</p>}
        <button
          type="submit"
          disabled={!accounts || !receivable || !revenue || !retainage}
        >
          Create pay application
        </button>
        <button type="button" onClick={onCancel}>
          Cancel
        </button>
      </fieldset>
    </form>
  );
}
