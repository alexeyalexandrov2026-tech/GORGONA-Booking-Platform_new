"use client";
import { useState } from "react";
import {
  minorUnits,
  type AccountInput,
  type BookInput,
  type EntryInput,
  type LedgerAccount,
  type LedgerBook,
  type LedgerOverview,
} from "../lib/ledger-contracts";

export function BookEditor({
  entity,
  book,
  currencies,
  disabled,
  onSave,
}: {
  entity: string;
  book: LedgerBook | null;
  currencies: LedgerOverview["currencies"];
  disabled: boolean;
  onSave: (body: BookInput) => void;
}) {
  const [currency, setCurrency] = useState(book?.base_currency ?? "");
  const [start, setStart] = useState(book?.accounting_start ?? "");
  const [fiscal, setFiscal] = useState(book?.fiscal_year_start_month ?? 1);
  return (
    <form
      aria-label="Book settings"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({
          schema_version: 1,
          expected_revision: book?.revision ?? 0,
          legal_entity_id: entity,
          base_currency: currency,
          accounting_start: start,
          fiscal_year_start_month: fiscal,
          ...(!book ? { chart: "starter" as const } : {}),
        });
      }}
    >
      <fieldset disabled={disabled}>
        <legend>{book ? "Book settings" : "Create a ledger book"}</legend>
        <label>
          Base currency
          <select
            required
            value={currency}
            disabled={book?.has_entries}
            onChange={(e) => setCurrency(e.target.value)}
          >
            <option value="">Choose a currency</option>
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code}
              </option>
            ))}
          </select>
        </label>
        <label>
          Accounting start
          <input
            required
            type="date"
            value={start}
            disabled={book?.has_entries}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          First fiscal month
          <select
            value={fiscal}
            onChange={(e) => setFiscal(Number(e.target.value))}
          >
            {Array.from({ length: 12 }, (_, i) => (
              <option key={i + 1} value={i + 1}>
                {i + 1}
              </option>
            ))}
          </select>
        </label>
        <p>
          {book
            ? `Saved version ${book.revision}. Base currency and accounting start are fixed after the first entry.`
            : "Creates a neutral starter chart of accounts. Entries require your explicit confirmation."}
        </p>
        <button type="submit" className="mgmt-btn-primary">
          {book ? "Save book settings" : "Create book"}
        </button>
      </fieldset>
    </form>
  );
}

export function AccountEditor({
  account,
  disabled,
  onSave,
}: {
  account: LedgerAccount | null;
  disabled: boolean;
  onSave: (id: string, body: AccountInput) => void;
}) {
  const [code, setCode] = useState(account?.code ?? "");
  const [name, setName] = useState(account?.name ?? "");
  const [type, setType] = useState<AccountInput["type"]>(
    account?.type ?? "asset",
  );
  const [archived, setArchived] = useState(account?.archived ?? false);
  return (
    <form
      aria-label="Account editor"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(account?.account_id ?? crypto.randomUUID(), {
          schema_version: 1,
          expected_revision: account?.revision ?? 0,
          code,
          name,
          type,
          archived,
        });
      }}
    >
      <fieldset disabled={disabled}>
        <legend>{account ? "Edit account" : "Add account"}</legend>
        <label>
          Account code
          <input
            required
            pattern="[0-9A-Za-z][0-9A-Za-z.-]{0,31}"
            value={code}
            disabled={Boolean(account)}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
        <label>
          Account name
          <input
            required
            maxLength={200}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label>
          Account type
          <select
            value={type}
            disabled={Boolean(account)}
            onChange={(e) => setType(e.target.value as AccountInput["type"])}
          >
            {(
              ["asset", "liability", "equity", "revenue", "expense"] as const
            ).map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => setArchived(e.target.checked)}
          />
          Archived
        </label>
        <p>
          Code and type stay fixed. Archived accounts remain in reports and
          history.
        </p>
        <button className="mgmt-btn-primary" type="submit">
          Save account
        </button>
      </fieldset>
    </form>
  );
}

export function EntryEditor({
  accounts,
  currencies,
  disabled,
  onSave,
}: {
  accounts: LedgerAccount[];
  currencies: LedgerOverview["currencies"];
  disabled: boolean;
  onSave: (body: EntryInput) => void;
}) {
  const [date, setDate] = useState("");
  const [currency, setCurrency] = useState("");
  const [source, setSource] = useState<EntryInput["source_kind"]>("manual");
  const [operation, setOperation] = useState("");
  const [memo, setMemo] = useState("");
  const [lines, setLines] = useState<EntryInput["lines"]>([
    { account_id: "", side: "debit", amount: "" },
    { account_id: "", side: "credit", amount: "" },
  ]);
  const places = currencies.find((c) => c.code === currency)?.minor_units;
  const values = lines.map((l) => minorUnits(l.amount, places ?? -1));
  const valid = values.every(
    (v) => v !== null && v > BigInt(0) && v <= BigInt("999999999999999999"),
  );
  const debit = values.reduce<bigint>(
    (sum, v, i) =>
      sum + (lines[i]?.side === "debit" ? (v ?? BigInt(0)) : BigInt(0)),
    BigInt(0),
  );
  const credit = values.reduce<bigint>(
    (sum, v, i) =>
      sum + (lines[i]?.side === "credit" ? (v ?? BigInt(0)) : BigInt(0)),
    BigInt(0),
  );
  const balanced = valid && debit === credit;
  const patch = (i: number, change: Partial<EntryInput["lines"][number]>) =>
    setLines(lines.map((l, n) => (n === i ? { ...l, ...change } : l)));
  return (
    <form
      aria-label="Post journal entry"
      onSubmit={(e) => {
        e.preventDefault();
        if (!balanced) return;
        onSave({
          schema_version: 1,
          entry_date: date,
          currency,
          source_kind: source,
          source_id: operation || null,
          memo: memo || null,
          lines,
        });
      }}
    >
      <fieldset disabled={disabled}>
        <legend>New journal entry</legend>
        <label>
          Entry date
          <input
            required
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <label>
          Entry currency
          <select
            required
            value={currency}
            onChange={(e) => setCurrency(e.target.value)}
          >
            <option value="">Choose a currency</option>
            {currencies.map((c) => (
              <option key={c.code} value={c.code}>
                {c.code} · {c.minor_units} decimals
              </option>
            ))}
          </select>
        </label>
        <label>
          Entry source
          <select
            value={source}
            onChange={(e) =>
              setSource(e.target.value as EntryInput["source_kind"])
            }
          >
            <option value="manual">Manual</option>
            <option value="opening">Opening balance</option>
          </select>
        </label>
        <label>
          Business operation ID (optional)
          <input
            maxLength={128}
            pattern="[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
            value={operation}
            onChange={(e) => setOperation(e.target.value)}
          />
        </label>
        <label>
          Entry note (optional)
          <input
            maxLength={500}
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
          />
        </label>
        {lines.map((line, i) => (
          <fieldset key={i} className="ledger-line">
            <legend>Line {i + 1}</legend>
            <label>
              Account {i + 1}
              <select
                required
                value={line.account_id}
                onChange={(e) => patch(i, { account_id: e.target.value })}
              >
                <option value="">Choose an account</option>
                {accounts
                  .filter((a) => !a.archived)
                  .map((a) => (
                    <option key={a.account_id} value={a.account_id}>
                      {a.code} · {a.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Side {i + 1}
              <select
                value={line.side}
                onChange={(e) =>
                  patch(i, { side: e.target.value as "debit" | "credit" })
                }
              >
                <option value="debit">Debit</option>
                <option value="credit">Credit</option>
              </select>
            </label>
            <label>
              Amount {i + 1}
              <input
                required
                inputMode="decimal"
                value={line.amount}
                onChange={(e) => patch(i, { amount: e.target.value })}
              />
            </label>
            {lines.length > 2 && (
              <button
                type="button"
                onClick={() => setLines(lines.filter((_, n) => n !== i))}
              >
                Remove line {i + 1}
              </button>
            )}
          </fieldset>
        ))}
        <button
          type="button"
          disabled={lines.length >= 200}
          onClick={() =>
            setLines([...lines, { account_id: "", side: "debit", amount: "" }])
          }
        >
          Add line
        </button>
        <p aria-live="polite">
          {balanced
            ? "Debits and credits balance."
            : "Enter positive amounts in the selected currency. Debits and credits must balance."}
        </p>
        <p>
          Posted entries are permanent. Correct an entry by posting a reversal,
          then a replacement.
        </p>
        <button type="submit" className="mgmt-btn-primary" disabled={!balanced}>
          Post entry
        </button>
      </fieldset>
    </form>
  );
}
