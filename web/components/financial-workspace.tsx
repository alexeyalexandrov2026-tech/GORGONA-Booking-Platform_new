"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import { fetchLedger, fetchAccounts } from "../lib/ledger-api";
import type { LedgerOverview, LedgerAccount } from "../lib/ledger-contracts";
import {
  fetchCounterparties,
  fetchCounterparty,
} from "../lib/counterparty-api";
import type { CounterpartyPage } from "../lib/counterparty-contracts";
import * as api from "../lib/financial-api";
import type {
  FinancialCommand,
  FinancialReference,
  FinancialOverview,
  Invoice,
  Credit,
  Obligation,
  Settlement,
  Payment,
} from "../lib/financial-contracts";
import {
  readFinancialRecovery,
  preserveFinancialRecovery,
  clearFinancialRecovery,
  type FinancialRecovery,
} from "../lib/financial-recovery";
import {
  Field,
  InvoiceEditor,
  DocumentIssue,
  CreditEditor,
  CreditVoid,
  SettlementPrepare,
  SettlementActions,
  PaymentEditor,
} from "./financial-editors";

type BookData = {
  book: string;
  tick: number;
  accounts: LedgerAccount[];
  accountCursor: string | null;
  invoices: Awaited<ReturnType<typeof api.fetchInvoices>>;
  accruals: Awaited<ReturnType<typeof api.fetchInvoices>>;
  credits: Awaited<ReturnType<typeof api.fetchCredits>>;
  obligations: Awaited<ReturnType<typeof api.fetchObligations>>;
  settlements: Awaited<ReturnType<typeof api.fetchSettlements>>;
};
const failure = (e: unknown) =>
  e instanceof ManagementApiError
    ? `${e.message} (${e.code})`
    : "Unable to verify the financial response. Refresh or resolve the pending command.";
const uncertain = (e: unknown) =>
  !(e instanceof ManagementApiError) ||
  e.status === undefined ||
  e.status >= 500;
async function creditContext(
  business: string,
  book: string,
  obligation: Obligation,
) {
  if (obligation.source_kind === "credit_refund")
    throw new Error("Refund obligations cannot be credited again.");
  const original = await api.fetchInvoice(
    business,
    book,
    obligation.source_id,
    obligation.source_kind === "invoice" ? "invoice" : "manual_accrual",
    obligation.source_revision,
  );
  const party = await fetchCounterparty(business, obligation.counterparty_id);
  if (
    original.obligation_id !== obligation.obligation_id ||
    original.counterparty_id !== obligation.counterparty_id ||
    original.currency !== obligation.currency ||
    original.direction !== obligation.direction ||
    original.control_account_id !== obligation.control_account_id
  )
    throw new ManagementApiError(
      "INVALID_RESPONSE",
      "Unexpected credited document and obligation context.",
    );
  return { original, obligation, partyRevision: party.revision };
}

export function FinancialWorkspace({
  businessId,
  actorId,
}: {
  businessId: string;
  actorId: string;
}) {
  const [ledger, setLedger] = useState<LedgerOverview | null>(null),
    [capability, setCapability] = useState<FinancialOverview | null>(null),
    [parties, setParties] = useState<CounterpartyPage | null>(null);
  const [bookId, setBookId] = useState(""),
    [data, setData] = useState<BookData | null>(null),
    [tick, setTick] = useState(0),
    [busy, setBusy] = useState(false),
    [recovering, setRecovering] = useState(true),
    [recovery, setRecovery] = useState<FinancialRecovery | null>(null),
    [pending, setPending] = useState<FinancialCommand | null>(null),
    [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState<string | null>(null);
  const [pane, setPane] = useState<"documents" | "settlements" | "credits">(
      "documents",
    ),
    [kind, setKind] = useState<"invoice" | "manual_accrual">("invoice"),
    [invoice, setInvoice] = useState<Invoice | null>(null),
    [invoiceEditor, setInvoiceEditor] = useState(false),
    [credit, setCredit] = useState<Credit | null>(null),
    [creditEditor, setCreditEditor] = useState(false),
    [creditSource, setCreditSource] = useState<{
      original: Invoice;
      obligation: Obligation;
      partyRevision: number;
    } | null>(null),
    [settlement, setSettlement] = useState<Settlement | null>(null),
    [prepare, setPrepare] = useState<Obligation | null>(null),
    [payment, setPayment] = useState<Payment | null>(null),
    [paymentMode, setPaymentMode] = useState<
      "confirm" | "correct" | "void" | null
    >(null),
    [historyRevision, setHistoryRevision] = useState("");
  const inFlight = useRef(false);
  const [invoiceLatestRevision, setInvoiceLatestRevision] = useState(0),
    [creditLatestRevision, setCreditLatestRevision] = useState(0);
  const selectedBook =
    ledger?.items.find((x) => x.book?.book_id === bookId)?.book ?? null;
  const current = data?.book === bookId && data.tick === tick ? data : null;
  const blocked =
    busy || recovering || Boolean(recovery) || Boolean(pending) || !current;
  const writeDisabled = blocked || !capability?.write_enabled;
  const resetDetails = useCallback(() => {
    setInvoice(null);
    setInvoiceEditor(false);
    setCredit(null);
    setCreditEditor(false);
    setCreditSource(null);
    setSettlement(null);
    setPrepare(null);
    setPayment(null);
    setPaymentMode(null);
    setHistoryRevision("");
  }, []);
  const acceptResult = useCallback((result: Invoice | Credit | Settlement) => {
    if ("settlement_id" in result) {
      setSettlement(result);
      setPrepare(null);
      setPayment(null);
      setPaymentMode(null);
      setPane("settlements");
    } else if ("credited_obligation_id" in result) {
      setCredit(result);
      setCreditLatestRevision(result.revision);
      setCreditEditor(false);
      setPane("credits");
    } else {
      setInvoice(result);
      setInvoiceLatestRevision(result.revision);
      setKind(result.kind);
      setInvoiceEditor(false);
      setPane("documents");
    }
  }, []);
  const reread = useCallback(
    async (reference: FinancialReference) => {
      setBookId(reference.book_id);
      if (reference.operation.startsWith("settlement_"))
        acceptResult(
          await api.fetchSettlement(
            businessId,
            reference.book_id,
            reference.subject_id,
          ),
        );
      else if (reference.operation.startsWith("credit_")) {
        const result = await api.fetchCredit(
          businessId,
          reference.book_id,
          reference.subject_id,
        );
        const obligation = await api.fetchObligation(
          businessId,
          reference.book_id,
          result.credited_obligation_id,
        );
        setCreditSource(
          await creditContext(businessId, reference.book_id, obligation),
        );
        acceptResult(result);
      } else
        acceptResult(
          await api.fetchInvoice(
            businessId,
            reference.book_id,
            reference.subject_id,
            reference.operation.startsWith("invoice_")
              ? "invoice"
              : "manual_accrual",
          ),
        );
    },
    [businessId, acceptResult],
  );
  useEffect(() => {
    let active = true;
    Promise.resolve()
      .then(async () => {
        const saved = readFinancialRecovery(actorId, businessId);
        if (!active) return;
        if (saved) {
          setRecovery(saved);
          setBookId(saved.reference.book_id);
          const result = await api.resolveFinancialCommand(
            businessId,
            saved.key,
            saved.reference,
          );
          if (!active) return;
          if (result.state !== "unresolved") {
            if (result.state === "committed") await reread(saved.reference);
            if (!active) return;
            clearFinancialRecovery(actorId, businessId, saved.key);
            setRecovery(null);
            setMessage(
              result.state === "committed"
                ? "Recovered the recorded financial command."
                : "The earlier request is cancelled.",
            );
            setTick((t) => t + 1);
          }
        }
        if (active) setRecovering(false);
      })
      .catch((e) => {
        if (active) setError(failure(e));
      });
    return () => {
      active = false;
    };
  }, [actorId, businessId, reread]);
  useEffect(() => {
    let active = true;
    Promise.all([
      fetchLedger(businessId),
      api.fetchFinancialOverview(businessId),
      fetchCounterparties(businessId, "", ""),
    ])
      .then(async ([overview, status, parties]) => {
        if (bookId && !overview.items.some((x) => x.book?.book_id === bookId)) {
          const pointed = await fetchLedger(businessId, undefined, bookId);
          overview = {
            ...overview,
            items: [
              ...overview.items,
              ...pointed.items.filter(
                (x) =>
                  !overview.items.some(
                    (y) => y.legal_entity_id === x.legal_entity_id,
                  ),
              ),
            ],
          };
        }
        if (!active) return;
        setLedger(overview);
        setCapability(status);
        setParties(parties);
        setBookId(
          (previous) =>
            previous || overview.items.find((x) => x.book)?.book?.book_id || "",
        );
      })
      .catch((e) => {
        if (active) {
          setCapability(null);
          setError(failure(e));
        }
      });
    return () => {
      active = false;
    };
  }, [businessId, bookId, tick]);
  useEffect(() => {
    let active = true;
    if (bookId)
      Promise.all([
        fetchAccounts(businessId, bookId),
        api.fetchInvoices(businessId, bookId, "invoice"),
        api.fetchInvoices(businessId, bookId, "manual_accrual"),
        api.fetchCredits(businessId, bookId),
        api.fetchObligations(businessId, bookId),
        api.fetchSettlements(businessId, bookId),
      ])
        .then(
          ([
            accounts,
            invoices,
            accruals,
            credits,
            obligations,
            settlements,
          ]) => {
            if (active)
              setData({
                book: bookId,
                tick,
                accounts: accounts.items,
                accountCursor: accounts.next_cursor,
                invoices,
                accruals,
                credits,
                obligations,
                settlements,
              });
          },
        )
        .catch((e) => {
          if (active) setError(failure(e));
        });
    return () => {
      active = false;
    };
  }, [businessId, bookId, tick]);
  const readAction = async (action: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(failure(e));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const resolve = async (cancel = false) => {
    if (!recovery) return;
    await readAction(async () => {
      const status = await api.resolveFinancialCommand(
        businessId,
        recovery.key,
        recovery.reference,
        cancel,
      );
      if (status.state === "unresolved") {
        setMessage(
          "Outcome is still unknown. Resolve again, retry the retained request, or cancel its key before a new request.",
        );
        return;
      }
      if (status.state === "committed") await reread(recovery.reference);
      clearFinancialRecovery(actorId, businessId, recovery.key);
      setPending(null);
      setRecovery(null);
      setRecovering(false);
      setTick((t) => t + 1);
      setMessage(
        status.state === "committed"
          ? "Recorded command found; refreshing its actual state."
          : "Request key cancelled. It cannot later record a financial effect.",
      );
    });
  };
  const submit = async (command: FinancialCommand, retry = false) => {
    if (
      inFlight.current ||
      recovering ||
      (!retry && (recovery || pending)) ||
      !current
    )
      return;
    if (
      !capability?.write_enabled &&
      !["settlement_release", "settlement_cancel"].includes(command.operation)
    ) {
      setError(
        "Financial recording is unavailable. Read history or resolve existing reserves.",
      );
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError(null);
    setMessage(null);
    let saved: FinancialRecovery | null = null;
    try {
      saved = preserveFinancialRecovery(actorId, businessId, command);
      setRecovery(saved);
      setPending(command);
      await api.executeFinancialCommand(businessId, command);
      await reread(saved.reference);
      clearFinancialRecovery(actorId, businessId, command.key);
      setRecovery(null);
      setPending(null);
      setMessage("Financial fact recorded. Balances are refreshing.");
      setTick((t) => t + 1);
    } catch (e) {
      setError(failure(e));
      if (saved && !uncertain(e)) {
        clearFinancialRecovery(actorId, businessId, command.key);
        setRecovery(null);
        setPending(null);
        setTick((t) => t + 1);
      }
      // Network, 5xx and invalid responses keep both the exact body in memory and the minimal durable reference.
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };
  const selectInvoice = async (id: string, revision?: number) => {
    const latest = await api.fetchInvoice(businessId, bookId, id, kind);
    const record =
      revision && revision !== latest.revision
        ? await api.fetchInvoice(businessId, bookId, id, kind, revision)
        : latest;
    setInvoiceLatestRevision(latest.revision);
    setInvoice(record);
    setInvoiceEditor(false);
    setHistoryRevision(String(record.revision));
  };
  const loadCreditSource = async (obligation: Obligation) => {
    if (obligation.source_kind === "credit_refund")
      throw new Error("Refund obligations cannot be credited again.");
    setCreditSource(await creditContext(businessId, bookId, obligation));
  };
  const selectCredit = async (id: string, revision?: number) => {
    const latest = await api.fetchCredit(businessId, bookId, id);
    const record =
      revision && revision !== latest.revision
        ? await api.fetchCredit(businessId, bookId, id, revision)
        : latest;
    const obligation = await api.fetchObligation(
      businessId,
      bookId,
      record.credited_obligation_id,
    );
    await loadCreditSource(obligation);
    setCreditLatestRevision(latest.revision);
    setCredit(record);
    setCreditEditor(false);
    setHistoryRevision(String(record.revision));
  };
  const latestInvoice =
    invoice && current && invoiceLatestRevision === invoice.revision;
  const latestCredit =
    credit && current && creditLatestRevision === credit.revision;
  const accounts = current?.accounts ?? [];
  const common = {
    book: bookId,
    accounts,
    disabled: writeDisabled,
    send: (command: FinancialCommand) => submit(command),
  };
  const name = (id: string) =>
    parties?.items.find((x) => x.counterparty_id === id)?.display_name ?? id;
  const loadMore = async (
    type: "invoices" | "accruals" | "credits" | "obligations" | "settlements",
  ) => {
    if (!current) return;
    const cursor = current[type].next_cursor;
    if (!cursor) return;
    if (type === "invoices" || type === "accruals") {
      const page = await api.fetchInvoices(
        businessId,
        bookId,
        type === "invoices" ? "invoice" : "manual_accrual",
        cursor,
      );
      setData({
        ...current,
        [type]: { ...page, items: [...current[type].items, ...page.items] },
      });
    }
    if (type === "credits") {
      const page = await api.fetchCredits(businessId, bookId, cursor);
      setData({
        ...current,
        credits: { ...page, items: [...current.credits.items, ...page.items] },
      });
    }
    if (type === "obligations") {
      const page = await api.fetchObligations(businessId, bookId, cursor);
      setData({
        ...current,
        obligations: {
          ...page,
          items: [...current.obligations.items, ...page.items],
        },
      });
    }
    if (type === "settlements") {
      const page = await api.fetchSettlements(businessId, bookId, cursor);
      setData({
        ...current,
        settlements: {
          ...page,
          items: [...current.settlements.items, ...page.items],
        },
      });
    }
  };
  const switchBook = (id: string) => {
    if (id === bookId) return;
    setBookId(id);
    resetDetails();
    setData(null);
    setCapability(null);
  };
  return (
    <div className="financial-workspace">
      <header className="financial-heading">
        <div>
          <p className="financial-eyebrow">Finance</p>
          <h1>Financial documents</h1>
          <p>
            Invoices, obligations and manually attested external settlements,
            with immutable history.
          </p>
        </div>
        <Link href="/ledger/">Open ledger</Link>
      </header>
      {error && (
        <div role="alert" className="mgmt-error-banner">
          {error}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {recovery && (
        <section
          className="financial-recovery"
          aria-label="Financial command recovery"
        >
          <h2>Resolve the earlier request</h2>
          <p>
            The outcome of {recovery.reference.operation.replaceAll("_", " ")}{" "}
            is unknown. New mutations stay blocked. Stored recovery contains
            identifiers only.
          </p>
          <p>
            After reload, the financial body is unavailable; it is never
            reconstructed for a retry.
          </p>
          <div className="financial-actions">
            <button disabled={busy} onClick={() => void resolve()}>
              Resolve financial command
            </button>
            {pending && (
              <button
                disabled={busy || !current}
                onClick={() => void submit(pending, true)}
              >
                Retry same financial command
              </button>
            )}
            <button
              disabled={busy}
              className="secondary"
              onClick={() => void resolve(true)}
            >
              Cancel unresolved request
            </button>
          </div>
        </section>
      )}
      {recovering && !recovery && (
        <p role="status">Checking earlier financial requests…</p>
      )}
      <section className="financial-toolbar" aria-label="Financial context">
        <Field label="Financial book">
          <select
            value={bookId}
            disabled={busy || Boolean(recovery)}
            onChange={(e) => switchBook(e.target.value)}
          >
            <option value="">Choose legal-entity book</option>
            {ledger?.items
              .filter((x) => x.book)
              .map((x) => (
                <option key={x.book!.book_id} value={x.book!.book_id}>
                  {x.legal_name} · {x.book!.base_currency} · revision{" "}
                  {x.book!.revision}
                </option>
              ))}
          </select>
        </Field>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => {
            setError(null);
            setTick((t) => t + 1);
          }}
        >
          Refresh financial records
        </button>
        {ledger?.next_cursor && (
          <button
            className="secondary"
            disabled={busy}
            onClick={() =>
              void readAction(async () => {
                const more = await fetchLedger(
                  businessId,
                  ledger.next_cursor ?? undefined,
                );
                setLedger({
                  ...more,
                  items: [
                    ...ledger.items,
                    ...more.items.filter(
                      (x) =>
                        !ledger.items.some(
                          (y) => y.legal_entity_id === x.legal_entity_id,
                        ),
                    ),
                  ],
                });
              })
            }
          >
            Load more financial books
          </button>
        )}
      </section>
      <p className="financial-capability" role="status">
        {capability?.write_enabled
          ? "Financial recording available in this environment."
          : capability?.blocked_reason === "module_disabled"
            ? "Financial recording is disabled. Read history, recovery and explicit reserve resolution remain available."
            : "Financial recording is not ready. Read history, recovery and explicit reserve resolution remain available."}
      </p>
      {bookId && !current && (
        <p role="status">Loading this book’s verified financial records…</p>
      )}
      {!bookId && (
        <p>Create a legal-entity book in Ledger, then choose it here.</p>
      )}
      {current && selectedBook && (
        <>
          <section
            className="financial-toolbar"
            aria-label="Financial reference data"
          >
            <p>
              {accounts.length} accounts loaded. Archived accounts can only be
              used by verified historical reversals.
            </p>
            {current.accountCursor && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  void readAction(async () => {
                    const page = await fetchAccounts(
                      businessId,
                      bookId,
                      current.accountCursor ?? undefined,
                    );
                    setData({
                      ...current,
                      accounts: [...current.accounts, ...page.items],
                      accountCursor: page.next_cursor,
                    });
                  })
                }
              >
                Load more accounts
              </button>
            )}
            {parties?.next_cursor && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  void readAction(async () => {
                    const page = await fetchCounterparties(
                      businessId,
                      "",
                      "",
                      parties.next_cursor ?? undefined,
                    );
                    setParties({
                      ...page,
                      items: [...parties.items, ...page.items],
                    });
                  })
                }
              >
                Load more counterparties
              </button>
            )}
          </section>
          <nav className="financial-tabs" aria-label="Financial areas">
            {(
              [
                ["documents", "Invoices and accruals"],
                ["settlements", "Obligations and settlements"],
                ["credits", "Credit notes"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                className={pane === value ? "" : "secondary"}
                aria-pressed={pane === value}
                disabled={blocked}
                onClick={() => setPane(value)}
              >
                {label}
              </button>
            ))}
          </nav>
          {pane === "documents" && (
            <section aria-label="Invoices and accruals">
              <div className="financial-toolbar">
                <h2>{kind === "invoice" ? "Invoices" : "Manual accruals"}</h2>
                <Field label="Document kind">
                  <select
                    value={kind}
                    disabled={blocked}
                    onChange={(e) => {
                      setKind(e.target.value as "invoice" | "manual_accrual");
                      setInvoice(null);
                      setInvoiceEditor(false);
                    }}
                  >
                    <option value="invoice">Invoice</option>
                    <option value="manual_accrual">Manual accrual</option>
                  </select>
                </Field>
                <button
                  disabled={writeDisabled}
                  onClick={() => {
                    setInvoice(null);
                    setInvoiceEditor(true);
                  }}
                >
                  New {kind === "invoice" ? "invoice" : "manual accrual"}
                </button>
              </div>
              <DocumentList
                items={
                  (kind === "invoice" ? current.invoices : current.accruals)
                    .items
                }
                busy={busy}
                name={name}
                open={(id) => void readAction(() => selectInvoice(id))}
              />
              {(kind === "invoice" ? current.invoices : current.accruals)
                .next_cursor && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void readAction(() =>
                      loadMore(kind === "invoice" ? "invoices" : "accruals"),
                    )
                  }
                >
                  Load more documents
                </button>
              )}
              {invoiceEditor && (
                <InvoiceEditor
                  key={`${kind}:${invoice?.document_id ?? "new"}:${invoice?.revision ?? 0}`}
                  {...common}
                  document={invoice}
                  kind={kind}
                  parties={parties?.items ?? []}
                  currencies={ledger?.currencies.map((x) => x.code) ?? []}
                />
              )}
              {invoice && !invoiceEditor && (
                <section
                  className="financial-detail"
                  aria-label="Financial document detail"
                >
                  <h2>
                    {invoice.number} · revision {invoice.revision} ·{" "}
                    {invoice.state}
                  </h2>
                  <p>
                    {invoice.title} · {name(invoice.counterparty_id)} (version{" "}
                    {invoice.counterparty_revision}) · {invoice.direction}
                  </p>
                  <p>
                    {invoice.total} {invoice.currency} · document date{" "}
                    {invoice.invoice_date} · due{" "}
                    {invoice.due_date ?? "not specified"}
                  </p>
                  <FinancialLines lines={invoice.lines} accounts={accounts} />
                  <FactReferences record={invoice} />
                  <HistoryPicker
                    revision={historyRevision}
                    max={invoiceLatestRevision}
                    set={setHistoryRevision}
                    disabled={busy}
                    load={() =>
                      void readAction(() =>
                        selectInvoice(
                          invoice.document_id,
                          Number(historyRevision),
                        ),
                      )
                    }
                  />
                  {latestInvoice && invoice.state === "draft" && (
                    <>
                      <button
                        disabled={writeDisabled}
                        className="secondary"
                        onClick={() => setInvoiceEditor(true)}
                      >
                        Edit saved draft
                      </button>
                      <DocumentIssue
                        key={`${invoice.document_id}:${invoice.revision}`}
                        document={invoice}
                        {...common}
                      />
                    </>
                  )}
                </section>
              )}
            </section>
          )}
          {pane === "settlements" && (
            <section aria-label="Obligations and settlements">
              <h2>Obligations</h2>
              <p>
                A = principal; P = confirmed payments; C = unpaid credits; R =
                active reserves. Available = A − P − C − R. A refund is a
                separate opposite-direction claim.
              </p>
              <div className="financial-table-scroll">
                <table>
                  <caption>Obligation balances</caption>
                  <thead>
                    <tr>
                      <th scope="col">Source / party</th>
                      <th scope="col">Direction</th>
                      <th scope="col">A</th>
                      <th scope="col">P</th>
                      <th scope="col">C</th>
                      <th scope="col">R</th>
                      <th scope="col">Available</th>
                      <th scope="col">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {current.obligations.items.map((x) => (
                      <tr key={x.obligation_id}>
                        <th scope="row">
                          {x.source_kind.replaceAll("_", " ")} ·{" "}
                          {name(x.counterparty_id)}
                          <small>{x.obligation_id}</small>
                        </th>
                        <td>{x.direction}</td>
                        <td>
                          {x.principal} {x.currency}
                        </td>
                        <td>{x.paid}</td>
                        <td>{x.credited}</td>
                        <td>{x.reserved}</td>
                        <td>{x.available}</td>
                        <td>
                          <button
                            disabled={writeDisabled}
                            onClick={() => {
                              setPrepare(x);
                              setSettlement(null);
                            }}
                          >
                            Prepare settlement
                          </button>
                          {x.source_kind !== "credit_refund" && (
                            <button
                              disabled={writeDisabled}
                              className="secondary"
                              onClick={() =>
                                void readAction(async () => {
                                  const fresh = await api.fetchObligation(
                                    businessId,
                                    bookId,
                                    x.obligation_id,
                                  );
                                  await loadCreditSource(fresh);
                                  setCredit(null);
                                  setCreditEditor(true);
                                  setPane("credits");
                                })
                              }
                            >
                              Create credit
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {current.obligations.items.length === 0 && (
                <p>No issued obligations in this book.</p>
              )}
              {current.obligations.next_cursor && (
                <button
                  disabled={busy}
                  onClick={() => void readAction(() => loadMore("obligations"))}
                >
                  Load more obligations
                </button>
              )}
              {prepare && (
                <SettlementPrepare
                  key={prepare.obligation_id}
                  book={bookId}
                  selected={prepare}
                  obligations={current.obligations.items}
                  disabled={writeDisabled}
                  send={common.send}
                />
              )}
              <h2>Settlements</h2>
              <ul className="financial-records">
                {current.settlements.items.map((x) => (
                  <li key={x.settlement_id}>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void readAction(async () => {
                          setSettlement(
                            await api.fetchSettlement(
                              businessId,
                              bookId,
                              x.settlement_id,
                            ),
                          );
                          setPrepare(null);
                          setPayment(null);
                          setPaymentMode(null);
                        })
                      }
                    >
                      {name(x.counterparty_id)} · {x.total} {x.currency} ·{" "}
                      {x.status.replaceAll("_", " ")} · sequence {x.sequence}
                    </button>
                  </li>
                ))}
              </ul>
              {current.settlements.items.length === 0 && (
                <p>No settlement documents yet.</p>
              )}
              {current.settlements.next_cursor && (
                <button
                  disabled={busy}
                  onClick={() => void readAction(() => loadMore("settlements"))}
                >
                  Load more settlements
                </button>
              )}
              {settlement && (
                <section
                  className="financial-detail"
                  aria-label="Settlement detail"
                >
                  <h2>
                    Settlement · {settlement.status.replaceAll("_", " ")} ·
                    sequence {settlement.sequence}
                  </h2>
                  <p>
                    {name(settlement.counterparty_id)} · {settlement.direction}{" "}
                    · planned {settlement.total}, confirmed{" "}
                    {settlement.confirmed}, reserved {settlement.reserved}{" "}
                    {settlement.currency}
                  </p>
                  <p>
                    {settlement.approved_by === null
                      ? "Not yet approved."
                      : settlement.approved_by_preparer
                        ? "Prepared and approved by the same authorized person."
                        : "Approved by a different authorized person."}
                  </p>
                  <SettlementActions
                    key={`${settlement.settlement_id}:${settlement.sequence}`}
                    settlement={settlement}
                    book={bookId}
                    disabled={writeDisabled}
                    releaseDisabled={blocked}
                    send={common.send}
                  />
                  {["reserved", "sent", "partially_confirmed"].includes(
                    settlement.status,
                  ) && (
                    <button
                      disabled={writeDisabled}
                      onClick={() => {
                        setPayment(null);
                        setPaymentMode("confirm");
                      }}
                    >
                      Record external payment
                    </button>
                  )}
                  <h3>Settlement history</h3>
                  <ol>
                    {settlement.events.map((x) => (
                      <li key={x.sequence}>
                        Sequence {x.sequence} · {x.kind.replaceAll("_", " ")} ·{" "}
                        {new Date(x.created_at).toLocaleString()} · actor{" "}
                        {x.created_by}
                        {x.reason && (
                          <p>
                            {x.reason} · evidence:{" "}
                            {x.evidence_source ?? "not specified"}
                          </p>
                        )}
                        {x.payment_id && (
                          <button
                            disabled={busy}
                            className="secondary"
                            onClick={() =>
                              void readAction(async () => {
                                const latest = await api.fetchSettlement(
                                  businessId,
                                  bookId,
                                  settlement.settlement_id,
                                );
                                const detail = await api.fetchPayment(
                                  businessId,
                                  bookId,
                                  x.payment_id!,
                                  settlement.settlement_id,
                                );
                                if (
                                  detail.currency !== latest.currency ||
                                  detail.direction !== latest.direction
                                )
                                  throw new Error(
                                    "Unexpected payment context.",
                                  );
                                setSettlement(latest);
                                setPayment(detail);
                                setPaymentMode(null);
                              })
                            }
                          >
                            View payment {x.payment_id}
                          </button>
                        )}
                      </li>
                    ))}
                  </ol>
                  {payment && (
                    <section aria-label="External payment detail">
                      <h3>
                        External payment · {payment.state} · revision{" "}
                        {payment.revision}
                      </h3>
                      <p>
                        Manually attested, not provider-verified. Permanent
                        identity: {payment.source_account_alias} ·{" "}
                        {payment.external_reference}
                      </p>
                      <p>
                        Originally {payment.amount} {payment.currency} on{" "}
                        {payment.actual_external_date}; effective amount{" "}
                        {payment.effective_amount}. Journal {payment.entry_id}.
                      </p>
                      <ol>
                        {payment.revisions.map((x) => (
                          <li key={x.revision}>
                            Revision {x.revision} · {x.kind} · settlement
                            sequence {x.sequence} ·{" "}
                            {x.amount ?? "no effective payment"}{" "}
                            {payment.currency}
                            <p>
                              {x.reason} · {x.evidence_source}; historical
                              mirror {x.reversal_entry_id}
                              {x.entry_id ? `; replacement ${x.entry_id}` : ""}.
                            </p>
                          </li>
                        ))}
                      </ol>
                      {payment.state !== "voided" && (
                        <div className="financial-actions">
                          <button
                            disabled={writeDisabled}
                            onClick={() => setPaymentMode("correct")}
                          >
                            Correct payment confirmation
                          </button>
                          <button
                            disabled={writeDisabled}
                            className="secondary"
                            onClick={() => setPaymentMode("void")}
                          >
                            Void erroneous confirmation
                          </button>
                        </div>
                      )}
                    </section>
                  )}
                  {paymentMode && (
                    <PaymentEditor
                      key={`${settlement.settlement_id}:${settlement.sequence}:${payment?.payment_id ?? "new"}:${paymentMode}`}
                      settlement={settlement}
                      payment={payment}
                      mode={paymentMode}
                      {...common}
                    />
                  )}
                </section>
              )}
            </section>
          )}
          {pane === "credits" && (
            <section aria-label="Credit notes">
              <h2>Credit notes</h2>
              <p>
                Start a new credit from its issued obligation. Unpaid credit and
                refund claims remain distinct from received cash.
              </p>
              <ul className="financial-records">
                {current.credits.items.map((x) => (
                  <li key={x.document_id}>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void readAction(() => selectCredit(x.document_id))
                      }
                    >
                      {x.number} · {x.title} · {x.total} {x.currency} ·{" "}
                      {x.state} · revision {x.revision}
                    </button>
                  </li>
                ))}
              </ul>
              {current.credits.items.length === 0 && (
                <p>No credit notes yet.</p>
              )}
              {current.credits.next_cursor && (
                <button
                  disabled={busy}
                  onClick={() => void readAction(() => loadMore("credits"))}
                >
                  Load more credit notes
                </button>
              )}
              {creditEditor && creditSource && (
                <CreditEditor
                  key={`${credit?.document_id ?? creditSource.obligation.obligation_id}:${credit?.revision ?? 0}`}
                  {...common}
                  original={creditSource.original}
                  obligation={creditSource.obligation}
                  credit={credit}
                  partyRevision={creditSource.partyRevision}
                />
              )}
              {credit && !creditEditor && (
                <section
                  className="financial-detail"
                  aria-label="Credit note detail"
                >
                  <h2>
                    {credit.number} · revision {credit.revision} ·{" "}
                    {credit.state}
                  </h2>
                  <p>
                    {credit.title} · {credit.total} {credit.currency} · credits
                    obligation {credit.credited_obligation_id}
                  </p>
                  <FinancialLines lines={credit.lines} accounts={accounts} />
                  <p>
                    {credit.state === "voided"
                      ? "Historical issue split — unpaid credit: "
                      : "Applied unpaid credit: "}
                    {credit.applied ?? "not issued"}; separate refund:{" "}
                    {credit.refund ?? "not issued"}.
                  </p>
                  {credit.state === "voided" && (
                    <p>
                      The unpaid credit has been unwound and its untouched
                      refund claim cancelled. These historical amounts are not
                      current credits or money refunded.
                    </p>
                  )}
                  <FactReferences record={credit} />
                  {credit.refund_obligation_id && (
                    <p>
                      Refund obligation {credit.refund_obligation_id}
                      {credit.state === "voided"
                        ? " is cancelled by this void."
                        : ": inspect its current balance and history in Obligations and settlements."}
                    </p>
                  )}
                  {credit.void_entry_id && (
                    <p>
                      Historical mirror {credit.void_entry_id} on{" "}
                      {credit.voided_on}: {credit.void_reason}; evidence{" "}
                      {credit.void_evidence_source}.
                    </p>
                  )}
                  <HistoryPicker
                    revision={historyRevision}
                    max={creditLatestRevision}
                    set={setHistoryRevision}
                    disabled={busy}
                    load={() =>
                      void readAction(() =>
                        selectCredit(
                          credit.document_id,
                          Number(historyRevision),
                        ),
                      )
                    }
                  />
                  {latestCredit && credit.state === "draft" && (
                    <>
                      <button
                        disabled={writeDisabled}
                        className="secondary"
                        onClick={() => setCreditEditor(true)}
                      >
                        Edit credit draft
                      </button>
                      <DocumentIssue
                        key={`${credit.document_id}:${credit.revision}`}
                        {...common}
                        document={credit}
                        obligation={creditSource?.obligation}
                      />
                    </>
                  )}
                  {latestCredit && credit.state === "issued" && (
                    <CreditVoid
                      key={`${credit.document_id}:${credit.revision}`}
                      book={bookId}
                      credit={credit}
                      disabled={writeDisabled}
                      send={common.send}
                    />
                  )}
                </section>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
function DocumentList({
  items,
  busy,
  name,
  open,
}: {
  items: Awaited<ReturnType<typeof api.fetchInvoices>>["items"];
  busy: boolean;
  name: (id: string) => string;
  open: (id: string) => void;
}) {
  return (
    <>
      <ul className="financial-records">
        {items.map((x) => (
          <li key={x.document_id}>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => open(x.document_id)}
            >
              {x.number} · {x.title} · {name(x.counterparty_id)} · {x.total}{" "}
              {x.currency} · {x.state} · revision {x.revision}
            </button>
          </li>
        ))}
      </ul>
      {items.length === 0 && <p>No financial documents of this kind yet.</p>}
    </>
  );
}
function FinancialLines({
  lines,
  accounts,
}: {
  lines: Invoice["lines"];
  accounts: LedgerAccount[];
}) {
  return (
    <ol>
      {lines.map((x) => (
        <li key={x.line_id}>
          {x.description} · {x.amount} ·{" "}
          {accounts.find((a) => a.account_id === x.counter_account_id)?.name ??
            x.counter_account_id}
        </li>
      ))}
    </ol>
  );
}
function FactReferences({ record }: { record: Invoice | Credit }) {
  return (
    <details>
      <summary>Audit references</summary>
      <p>
        Book {record.book_id}; document {record.document_id}; control account{" "}
        {record.control_account_id}.
        {record.entry_id
          ? ` Journal ${record.entry_id}.`
          : " No issued journal."}
        {"obligation_id" in record && record.obligation_id
          ? ` Obligation ${record.obligation_id}.`
          : ""}
      </p>
    </details>
  );
}
function HistoryPicker({
  revision,
  max,
  set,
  load,
  disabled,
}: {
  revision: string;
  max: number;
  set: (revision: string) => void;
  load: () => void;
  disabled: boolean;
}) {
  return (
    <div className="financial-toolbar">
      <Field label="Saved revision">
        <input
          type="number"
          min={1}
          max={max}
          step={1}
          value={revision}
          onChange={(e) => set(e.target.value)}
        />
      </Field>
      <button
        className="secondary"
        disabled={
          disabled ||
          !Number.isInteger(Number(revision)) ||
          Number(revision) < 1 ||
          Number(revision) > max
        }
        onClick={load}
      >
        Read saved version
      </button>
    </div>
  );
}
