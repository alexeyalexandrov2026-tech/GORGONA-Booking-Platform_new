"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchConfiguration, ManagementApiError } from "../lib/management-api";
import {
  executeLedgerCommand,
  fetchAccounts,
  fetchBook,
  fetchEntries,
  fetchEntry,
  fetchLedger,
  fetchPeriod,
  fetchTrialBalance,
  resolveLedgerCommand,
} from "../lib/ledger-api";
import type {
  LedgerAccount,
  LedgerBook,
  LedgerCommand,
  LedgerEntries,
  LedgerEntry,
  LedgerOverview,
  LedgerPeriod,
  TrialBalance,
} from "../lib/ledger-contracts";
import { AccountEditor, BookEditor, EntryEditor } from "./ledger-editors";
import {
  readLedgerRecovery,
  preserveLedgerRecovery,
  clearLedgerRecovery,
  type LedgerRecovery,
} from "../lib/ledger-recovery";

const failure = (e: unknown) =>
  e instanceof Error ? e.message : "Unable to complete this action.";
const uncertain = (e: unknown) =>
  !(e instanceof ManagementApiError) ||
  e.status === undefined ||
  e.status >= 500;

export function Ledger({
  businessId,
  actorId,
}: {
  businessId: string;
  actorId: string;
}) {
  const [overview, setOverview] = useState<LedgerOverview | null>(null);
  const [entity, setEntity] = useState("");
  const [recoveredBook, setRecoveredBook] = useState<string | null>(null);
  const [book, setBook] = useState<LedgerBook | null>(null);
  const [accounts, setAccounts] = useState<LedgerAccount[]>([]);
  const [accountCursor, setAccountCursor] = useState<string | null>(null);
  const [account, setAccount] = useState<LedgerAccount | null>(null);
  const [entries, setEntries] = useState<LedgerEntries | null>(null);
  const [entry, setEntry] = useState<LedgerEntry | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<LedgerCommand | null>(null);
  const [recovery, setRecovery] = useState<LedgerRecovery | null>(null);
  const [recovering, setRecovering] = useState(true);
  const [unknown, setUnknown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [periodText, setPeriodText] = useState("");
  const [period, setPeriod] = useState<LedgerPeriod | null>(null);
  const [reason, setReason] = useState("");
  const [reversalDate, setReversalDate] = useState("");
  const [reversalNote, setReversalNote] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [currency, setCurrency] = useState("");
  const [report, setReport] = useState<TrialBalance | null>(null);
  const locked =
    busy || loading || recovering || Boolean(pending) || Boolean(recovery);
  const disabled = locked || !enabled;
  const currentEntity = overview?.items.find(
    (x) => x.legal_entity_id === entity,
  );
  const bookId = currentEntity?.book?.book_id;

  useEffect(() => {
    let active = true;
    Promise.resolve()
      .then(async () => {
        const saved = readLedgerRecovery(actorId, businessId);
        if (!active) return;
        if (saved) {
          setRecovery(saved);
          setRecoveredBook(saved.reference.book_id);
          const state = await resolveLedgerCommand(
            businessId,
            saved.key,
            saved.reference,
          );
          if (!active) return;
          if (state.state !== "unresolved") {
            clearLedgerRecovery(actorId, businessId, saved.key);
            setRecovery(null);
            setMessage(
              state.state === "committed"
                ? "Recovered a saved ledger command."
                : "The unresolved request was cancelled.",
            );
            setTick((t) => t + 1);
          }
        }
        if (active) setRecovering(false);
      })
      .catch((e) => {
        if (active) {
          setError(failure(e));
          // Keep writes blocked if the recovery store cannot be read safely.
        }
      });
    return () => {
      active = false;
    };
  }, [actorId, businessId]);

  useEffect(() => {
    let active = true;
    Promise.all([fetchLedger(businessId), fetchConfiguration(businessId)])
      .then(async ([data, config]) => {
        if (
          recoveredBook &&
          !data.items.some((x) => x.book?.book_id === recoveredBook)
        ) {
          const pointed = await fetchLedger(
            businessId,
            undefined,
            recoveredBook,
          );
          data = {
            ...data,
            items: [
              ...data.items,
              ...pointed.items.filter(
                (x) =>
                  !data.items.some(
                    (y) => y.legal_entity_id === x.legal_entity_id,
                  ),
              ),
            ],
          };
        }
        if (!active) return;
        setOverview(data);
        setEnabled(config.effective_module_ids.includes("finance"));
        setEntity(
          (previous) =>
            data.items.find((x) => x.book?.book_id === recoveredBook)
              ?.legal_entity_id ??
            (data.items.some((x) => x.legal_entity_id === previous)
              ? previous
              : (data.items[0]?.legal_entity_id ?? "")),
        );
      })
      .catch((e) => {
        if (active) setError(failure(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, tick, recoveredBook]);

  const loadBook = useCallback(
    async (id: string) => {
      const [saved, chart, journal] = await Promise.all([
        fetchBook(businessId, id),
        fetchAccounts(businessId, id),
        fetchEntries(businessId, id),
      ]);
      return { saved, chart, journal };
    },
    [businessId],
  );
  useEffect(() => {
    let active = true;
    if (bookId)
      loadBook(bookId)
        .then((data) => {
          if (!active) return;
          setBook(data.saved);
          setAccounts(data.chart.items);
          setAccountCursor(data.chart.next_cursor);
          setEntries(data.journal);
          setAccount(null);
          setEntry(null);
          setReport(null);
          setPeriod(null);
        })
        .catch((e) => {
          if (active) setError(failure(e));
        });
    return () => {
      active = false;
    };
  }, [bookId, loadBook, tick]);

  const readAction = async (action: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  };
  const execute = async (command: LedgerCommand) => {
    let replaying = false;
    try {
      replaying = readLedgerRecovery(actorId, businessId) !== null;
      const saved = preserveLedgerRecovery(actorId, businessId, command);
      setRecovery(saved);
    } catch (e) {
      setError(failure(e));
      return;
    }
    setPending(command);
    setBusy(true);
    setUnknown(false);
    setError(null);
    setMessage(null);
    let succeeded = false;
    try {
      await executeLedgerCommand(businessId, command);
      succeeded = true;
      setRecoveredBook(command.book);
      clearLedgerRecovery(actorId, businessId, command.key);
      setRecovery(null);
      setPending(null);
      setMessage("Ledger command saved.");
      setTick((t) => t + 1);
    } catch (e) {
      setError(failure(e));
      if (succeeded) {
        setPending(null);
        setUnknown(false);
        setMessage(
          "The ledger command was saved. Check its recovered result before starting another.",
        );
        setTick((t) => t + 1);
      } else if (uncertain(e)) setUnknown(true);
      else {
        setPending(null);
        if (!replaying) {
          try {
            clearLedgerRecovery(actorId, businessId, command.key);
            setRecovery(null);
          } catch {
            setMessage(
              "The request was refused. Resolve its recovery reference before starting another.",
            );
          }
        }
        if (e instanceof ManagementApiError && e.status === 409)
          setTick((t) => t + 1);
      }
    } finally {
      setBusy(false);
    }
  };
  const send = (command: LedgerCommand) => {
    void execute(command);
  };
  const recover = async (cancel = false) => {
    if (!recovery) return;
    setBusy(true);
    setError(null);
    try {
      const state = await resolveLedgerCommand(
        businessId,
        recovery.key,
        recovery.reference,
        cancel,
      );
      if (state.state === "unresolved") {
        setMessage(
          "No saved result is available yet. Check again or cancel the unresolved request before starting another.",
        );
      } else {
        clearLedgerRecovery(actorId, businessId, recovery.key);
        setRecovery(null);
        setPending(null);
        setUnknown(false);
        setRecovering(false);
        setMessage(
          state.state === "committed"
            ? "The original ledger command was already saved."
            : "The unresolved request was cancelled.",
        );
        setTick((t) => t + 1);
      }
    } catch (e) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="documents ledger">
      <h1>Ledger</h1>
      <p>
        Books and balanced entries for each legal entity. Each currency is
        reported separately.
      </p>
      {error && (
        <div role="alert" className="mgmt-error">
          {error}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {unknown && pending && (
        <section aria-label="Uncertain ledger command">
          <p>
            The result of the last ledger command is uncertain. Retry the same
            command to check its saved result.
          </p>
          <button disabled={busy} onClick={() => send(pending)}>
            Retry same ledger command
          </button>
        </section>
      )}
      {recovery && (!pending || unknown) && (
        <section aria-label="Ledger command recovery">
          <h2>Resolve the earlier ledger request</h2>
          <p>
            An earlier {recovery.reference.operation} request from{" "}
            {recovery.saved_at} needs a saved result before another financial
            command can start.
          </p>
          <p>
            Checking keeps any saved entry. Cancelling checks first, then
            prevents an unsaved request from arriving later. It does not reverse
            a saved entry.
          </p>
          <button disabled={busy} onClick={() => void recover()}>
            Check saved result
          </button>
          <button disabled={busy} onClick={() => void recover(true)}>
            Cancel unresolved request
          </button>
        </section>
      )}
      <button
        disabled={locked}
        onClick={() => {
          setError(null);
          setLoading(true);
          setTick((t) => t + 1);
        }}
      >
        Refresh ledger
      </button>
      {loading && <p role="status">Loading ledger…</p>}
      {!enabled && overview && (
        <p>
          Finance is not enabled for this company. Existing records remain
          readable. Enable the module in{" "}
          <Link href="/business/">Business profile</Link> when its technical
          acceptance permits it.
        </p>
      )}
      {overview && !overview.items.length && (
        <p>
          Create a legal entity in{" "}
          <Link href="/business/">Business profile</Link> before opening a book.
        </p>
      )}
      {overview && Boolean(overview.items.length) && (
        <>
          <label>
            Legal entity
            <select
              value={entity}
              disabled={locked}
              onChange={(e) => {
                if (e.target.value === entity) return;
                setEntity(e.target.value);
                setRecoveredBook(
                  overview.items.find(
                    (x) => x.legal_entity_id === e.target.value,
                  )?.book?.book_id ?? null,
                );
                setBook(null);
                setAccounts([]);
                setAccount(null);
                setEntries(null);
                setEntry(null);
                setPeriod(null);
                setReport(null);
              }}
            >
              {overview.items.map((x) => (
                <option key={x.legal_entity_id} value={x.legal_entity_id}>
                  {x.code} · {x.legal_name}
                </option>
              ))}
            </select>
          </label>
          {overview.next_cursor && (
            <button
              disabled={locked}
              onClick={() =>
                void readAction(async () => {
                  const page = await fetchLedger(
                    businessId,
                    overview.next_cursor!,
                  );
                  const merged = new Map(
                    overview.items.map((item) => [item.legal_entity_id, item]),
                  );
                  for (const item of page.items)
                    merged.set(item.legal_entity_id, item);
                  setOverview({ ...page, items: [...merged.values()] });
                })
              }
            >
              More legal entities
            </button>
          )}
          {currentEntity && (!bookId || book?.book_id === bookId) && (
            <details open={!bookId}>
              <summary>
                {bookId
                  ? `Book settings · version ${book?.revision}`
                  : "Open a ledger book"}
              </summary>
              <BookEditor
                key={`${entity}-${book?.revision ?? 0}`}
                entity={entity}
                book={bookId ? book : null}
                currencies={overview.currencies}
                disabled={disabled}
                onSave={(body) =>
                  send({
                    type: "book",
                    book: bookId ?? crypto.randomUUID(),
                    key: crypto.randomUUID(),
                    body,
                  })
                }
              />
            </details>
          )}
        </>
      )}
      {book && book.book_id === bookId && overview && (
        <>
          <details key={book.book_id}>
            <summary>Chart of accounts ({accounts.length} loaded)</summary>
            <section aria-label="Chart of accounts">
              <h2>Chart of accounts</h2>
              <div className="mgmt-table-container">
                <table className="mgmt-table">
                  <caption>Accounts · book version {book.revision}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Code</th>
                      <th scope="col">Name</th>
                      <th scope="col">Type</th>
                      <th scope="col">State</th>
                      <th scope="col">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accounts.map((a) => (
                      <tr key={a.account_id}>
                        <th scope="row">{a.code}</th>
                        <td>{a.name}</td>
                        <td>{a.type}</td>
                        <td>
                          {a.archived ? "Archived" : "Active"} · v{a.revision}
                        </td>
                        <td>
                          <button
                            disabled={locked}
                            onClick={() => setAccount(a)}
                          >
                            Edit {a.code}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {accountCursor && (
                <button
                  disabled={locked}
                  onClick={() =>
                    void readAction(async () => {
                      const page = await fetchAccounts(
                        businessId,
                        book.book_id,
                        accountCursor,
                      );
                      setAccounts([...accounts, ...page.items]);
                      setAccountCursor(page.next_cursor);
                    })
                  }
                >
                  More accounts
                </button>
              )}
              <button disabled={locked} onClick={() => setAccount(null)}>
                New account
              </button>
              <AccountEditor
                key={`${account?.account_id ?? "new"}-${account?.revision ?? 0}-${tick}`}
                account={account}
                disabled={disabled}
                onSave={(id, body) =>
                  send({
                    type: "account",
                    book: book.book_id,
                    id,
                    key: crypto.randomUUID(),
                    body,
                  })
                }
              />
            </section>
          </details>
          <EntryEditor
            key={`${book.book_id}-${tick}`}
            accounts={accounts}
            currencies={overview.currencies}
            disabled={disabled}
            onSave={(body) =>
              send({
                type: "entry",
                book: book.book_id,
                id: crypto.randomUUID(),
                key: crypto.randomUUID(),
                body,
              })
            }
          />
          <section aria-label="Journal">
            <h2>Journal</h2>
            {!entries?.items.length && <p>No posted entries.</p>}
            {entries?.items.map((item) => (
              <div key={item.entry_id} className="ledger-journal-row">
                <span>
                  {item.entry_date} · {item.currency} {item.total} ·{" "}
                  {item.source_kind}
                  {item.reversed_by_entry_id ? " · reversed" : ""}
                </span>
                <button
                  disabled={locked}
                  onClick={() =>
                    void readAction(async () =>
                      setEntry(
                        await fetchEntry(
                          businessId,
                          book.book_id,
                          item.entry_id,
                        ),
                      ),
                    )
                  }
                >
                  Read entry {item.source_id}
                </button>
              </div>
            ))}
            {entries?.next_cursor && (
              <button
                disabled={locked}
                onClick={() =>
                  void readAction(async () => {
                    const page = await fetchEntries(
                      businessId,
                      book.book_id,
                      entries.next_cursor!,
                    );
                    if (entries.schema_version !== page.schema_version) {
                      setEntries(await fetchEntries(businessId, book.book_id));
                    } else if (
                      entries.schema_version === 1 &&
                      page.schema_version === 1
                    ) {
                      setEntries({
                        ...page,
                        items: [...entries.items, ...page.items],
                      });
                    } else if (
                      entries.schema_version === 2 &&
                      page.schema_version === 2
                    ) {
                      setEntries({
                        ...page,
                        items: [...entries.items, ...page.items],
                      });
                    }
                  })
                }
              >
                More entries
              </button>
            )}
          </section>
          {entry && (
            <section aria-label="Saved journal entry">
              <h3>
                Saved entry · {entry.currency} {entry.total}
              </h3>
              <p>
                {entry.entry_date} · {entry.source_id} · {entry.memo}
              </p>
              <ul>
                {entry.lines.map((line) => (
                  <li key={line.line_no}>
                    {line.account_code} · {line.account_name} · {line.side}{" "}
                    {line.amount}
                  </li>
                ))}
              </ul>
              {(entry.source_kind === "manual" ||
                entry.source_kind === "opening") &&
                !entry.reversed_by_entry_id && (
                  <form
                    aria-label="Reverse journal entry"
                    onSubmit={(e) => {
                      e.preventDefault();
                      send({
                        type: "reverse",
                        book: book.book_id,
                        id: entry.entry_id,
                        key: crypto.randomUUID(),
                        body: {
                          schema_version: 1,
                          reversal_entry_id: crypto.randomUUID(),
                          entry_date: reversalDate,
                          memo: reversalNote || null,
                        },
                      });
                    }}
                  >
                    <fieldset disabled={disabled}>
                      <legend>Post a reversal</legend>
                      <label>
                        Reversal date
                        <input
                          type="date"
                          required
                          min={entry.entry_date}
                          value={reversalDate}
                          onChange={(e) => setReversalDate(e.target.value)}
                        />
                      </label>
                      <label>
                        Reversal note
                        <input
                          maxLength={500}
                          value={reversalNote}
                          onChange={(e) => setReversalNote(e.target.value)}
                        />
                      </label>
                      <p>
                        Creates the opposite entry. The original stays
                        unchanged.
                      </p>
                      <button type="submit">Post reversal</button>
                    </fieldset>
                  </form>
                )}
            </section>
          )}
          <section aria-label="Ledger periods">
            <h2>Monthly periods</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void readAction(async () =>
                  setPeriod(
                    await fetchPeriod(businessId, book.book_id, periodText),
                  ),
                );
              }}
            >
              <label>
                Ledger month
                <input
                  required
                  type="month"
                  disabled={locked}
                  value={periodText}
                  onChange={(e) => {
                    setPeriodText(e.target.value);
                    setPeriod(null);
                  }}
                />
              </label>
              <button disabled={locked}>Read month</button>
            </form>
            {period && (
              <>
                <p>
                  Month {period.period}: {period.state} · change{" "}
                  {period.sequence}
                </p>
                <label>
                  Period reason
                  <input
                    disabled={disabled}
                    maxLength={500}
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </label>
                <button
                  disabled={
                    disabled || (period.state === "closed" && !reason.trim())
                  }
                  onClick={() =>
                    send(
                      period.state === "closed"
                        ? {
                            type: "reopen",
                            book: book.book_id,
                            period: period.period,
                            key: crypto.randomUUID(),
                            body: {
                              schema_version: 1,
                              expected_sequence: period.sequence,
                              reason,
                            },
                          }
                        : {
                            type: "close",
                            book: book.book_id,
                            period: period.period,
                            key: crypto.randomUUID(),
                            body: {
                              schema_version: 1,
                              expected_sequence: period.sequence,
                              reason: reason || null,
                            },
                          },
                    )
                  }
                >
                  {period.state === "closed" ? "Reopen month" : "Close month"}
                </button>
                <p>
                  Closing prevents new entries in this month. Reopening requires
                  a reason.
                </p>
                <ol>
                  {period.events.map((event) => (
                    <li key={event.sequence}>
                      {event.action} · {event.decided_at} · {event.reason}
                    </li>
                  ))}
                </ol>
              </>
            )}
          </section>
          <section aria-label="Trial balance">
            <h2>Trial balance</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void readAction(async () =>
                  setReport(
                    await fetchTrialBalance(
                      businessId,
                      book.book_id,
                      from,
                      to,
                      currency,
                    ),
                  ),
                );
              }}
            >
              <fieldset disabled={locked}>
                <legend>Report period and currency</legend>
                <label>
                  From month
                  <input
                    required
                    type="month"
                    value={from}
                    onChange={(e) => {
                      setFrom(e.target.value);
                      setReport(null);
                    }}
                  />
                </label>
                <label>
                  To month
                  <input
                    required
                    type="month"
                    min={from}
                    value={to}
                    onChange={(e) => {
                      setTo(e.target.value);
                      setReport(null);
                    }}
                  />
                </label>
                <label>
                  Report currency
                  <select
                    required
                    value={currency}
                    onChange={(e) => {
                      setCurrency(e.target.value);
                      setReport(null);
                    }}
                  >
                    <option value="">Choose a currency</option>
                    {overview.currencies.map((c) => (
                      <option key={c.code}>{c.code}</option>
                    ))}
                  </select>
                </label>
                <button>Read trial balance</button>
              </fieldset>
            </form>
            {report && (
              <div
                className="mgmt-table-container"
                role="region"
                aria-label="Trial balance table"
                tabIndex={0}
              >
                <table className="mgmt-table">
                  <caption>
                    {report.currency} · {report.period_from} to{" "}
                    {report.period_to}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Account</th>
                      {[
                        "Opening debit",
                        "Opening credit",
                        "Debit",
                        "Credit",
                        "Closing debit",
                        "Closing credit",
                      ].map((title) => (
                        <th scope="col" key={title}>
                          {title}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.rows.map((row) => (
                      <tr key={row.account_id}>
                        <th scope="row">
                          {row.code} · {row.name}
                        </th>
                        {[
                          row.opening_debit,
                          row.opening_credit,
                          row.debit,
                          row.credit,
                          row.closing_debit,
                          row.closing_credit,
                        ].map((value, i) => (
                          <td key={i}>{value}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <th scope="row">Total {report.currency}</th>
                      {[
                        report.totals.opening_debit,
                        report.totals.opening_credit,
                        report.totals.debit,
                        report.totals.credit,
                        report.totals.closing_debit,
                        report.totals.closing_credit,
                      ].map((value, i) => (
                        <td key={i}>{value}</td>
                      ))}
                    </tr>
                  </tfoot>
                </table>
                {!report.rows.length && <p>No entries in this report.</p>}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
