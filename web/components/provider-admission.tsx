"use client";
import { useEffect, useState } from "react";
import { fetchLedger } from "../lib/ledger-api";
import { fetchConfiguration, ManagementApiError } from "../lib/management-api";
import type { LedgerOverview } from "../lib/ledger-contracts";
import {
  admissionInputSchema,
  clearAdmissionRecovery,
  fetchAdmission,
  fetchAdmissions,
  preserveAdmissionRecovery,
  readAdmissionRecovery,
  resolveAdmission,
  saveAdmission,
  type AdmissionInput,
  type AdmissionRecovery,
  type AdmissionView,
} from "../lib/admission-api";

const initial: AdmissionInput = {
  schema_version: 1,
  expected_revision: 0,
  provider: "stripe_connect",
  country: "",
  business_activity: "",
  requested_operation: "charge",
  account_reference: null,
  evidence_references: [],
  notes: null,
  assessment: "not_checked",
};
const message = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to complete this request.";
export function ProviderAdmission({
  businessId,
  actorId,
}: {
  businessId: string;
  actorId: string;
}) {
  const [overview, setOverview] = useState<LedgerOverview | null>(null);
  const [book, setBook] = useState("");
  const [items, setItems] = useState<AdmissionView[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<AdmissionView | null>(null);
  const [input, setInput] = useState(initial);
  const [evidence, setEvidence] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [recovering, setRecovering] = useState(true);
  const [recovery, setRecovery] = useState<AdmissionRecovery | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [historyRevision, setHistoryRevision] = useState(1);
  const [history, setHistory] = useState<AdmissionView | null>(null);
  const locked = loading || busy || recovering || Boolean(recovery);
  useEffect(() => {
    let active = true;
    Promise.resolve()
      .then(async () => {
        const saved = readAdmissionRecovery(actorId, businessId);
        if (saved) {
          if (active) {
            setRecovery(saved);
            setBook(saved.reference.book_id);
          }
          const state = await resolveAdmission(
            businessId,
            saved.key,
            saved.reference,
          );
          if (state.state !== "unresolved") {
            clearAdmissionRecovery(actorId, businessId, saved.key);
            if (active) {
              setRecovery(null);
              setNotice(
                state.state === "committed"
                  ? "Recovered a saved admission request."
                  : "The earlier request was cancelled.",
              );
            }
          }
        }
        const [books, config] = await Promise.all([
          fetchLedger(businessId),
          fetchConfiguration(businessId),
        ]);
        if (active) {
          setOverview(books);
          setEnabled(config.published?.module_ids.includes("finance") ?? false);
          setLoading(false);
          setRecovering(false);
        }
      })
      .catch((e) => {
        if (active) {
          setError(message(e));
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [actorId, businessId]);
  useEffect(() => {
    let active = true;
    if (!book) return;
    fetchAdmissions(businessId, book)
      .then((result) => {
        if (active) {
          setItems(result.items);
          setCursor(result.next_after);
        }
      })
      .catch((e) => {
        if (active) setError(message(e));
      });
    return () => {
      active = false;
    };
  }, [businessId, book]);
  function edit(view: AdmissionView | null) {
    setSelected(view);
    setHistory(null);
    setHistoryRevision(view?.revision ?? 1);
    setInput(
      view
        ? {
            schema_version: 1,
            expected_revision: view.revision,
            provider: view.provider,
            country: view.country,
            business_activity: view.business_activity,
            requested_operation: view.requested_operation,
            account_reference: view.account_reference,
            evidence_references: view.evidence_references,
            notes: view.notes,
            assessment: view.assessment,
          }
        : initial,
    );
    setEvidence(view?.evidence_references.join("\n") ?? "");
  }
  async function refresh(id?: string) {
    const result = await fetchAdmissions(businessId, book);
    setItems(result.items);
    setCursor(result.next_after);
    if (id) edit(await fetchAdmission(businessId, book, id));
  }
  async function run(action?: "submit" | "withdraw") {
    if (locked || !book || (action !== "withdraw" && !enabled)) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    const key = crypto.randomUUID(),
      id = selected?.request_id ?? crypto.randomUUID();
    const revision = selected?.revision ?? 0;
    try {
      const body = action
        ? { schema_version: 1 as const, expected_revision: revision }
        : admissionInputSchema.parse({
            ...input,
            expected_revision: revision,
            evidence_references: evidence
              .split("\n")
              .map((x) => x.trim())
              .filter(Boolean),
          });
      const saved = preserveAdmissionRecovery(actorId, businessId, key, {
        schema_version: 1,
        operation:
          action === "submit"
            ? "admission_submit"
            : action === "withdraw"
              ? "admission_withdraw"
              : "admission_draft",
        book_id: book,
        subject_id: id,
        revision: revision + 1,
      });
      setRecovery(saved);
      await saveAdmission(businessId, book, id, key, body, action);
      clearAdmissionRecovery(actorId, businessId, key);
      setRecovery(null);
      setNotice(
        "Admission metadata saved. Payment capabilities remain disabled.",
      );
      await refresh(id);
    } catch (e) {
      if (
        e instanceof ManagementApiError &&
        e.status !== undefined &&
        e.status < 500
      ) {
        clearAdmissionRecovery(actorId, businessId, key);
        setRecovery(null);
      }
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  async function recover(cancel: boolean) {
    if (!recovery || busy) return;
    setBusy(true);
    setError(null);
    try {
      const state = await resolveAdmission(
        businessId,
        recovery.key,
        recovery.reference,
        cancel,
      );
      if (state.state === "unresolved") {
        setError(
          "The outcome remains unknown. Resolve or cancel this request before starting another.",
        );
        return;
      }
      clearAdmissionRecovery(actorId, businessId, recovery.key);
      setRecovery(null);
      setRecovering(false);
      setNotice(
        state.state === "committed"
          ? "Recovered a saved admission request."
          : "The earlier request was cancelled.",
      );
      await refresh(
        state.state === "committed" ? recovery.reference.subject_id : undefined,
      );
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }
  const readOnly =
    locked || !enabled || (selected !== null && selected.state !== "draft");
  return (
    <div className="provider-admission">
      <h1>Provider admission</h1>
      <p>
        Record a request for Stripe Connect review. These are manually supplied,
        unverified references. Charges, refunds, transfers and payouts remain
        disabled.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!enabled && !loading && (
        <p>Finance is off. History and request recovery remain available.</p>
      )}
      {loading && <p role="status">Loading admission records…</p>}
      {recovery && (
        <section aria-label="Admission recovery">
          <h2>Earlier request outcome</h2>
          <p>Resolve the earlier request before making another change.</p>
          <button disabled={busy} onClick={() => void recover(false)}>
            Resolve admission request
          </button>
          <button disabled={busy} onClick={() => void recover(true)}>
            Cancel unresolved admission request
          </button>
        </section>
      )}
      <label>
        Admission book
        <select
          value={book}
          disabled={locked}
          onChange={(e) => {
            if (e.target.value === book) return;
            setBook(e.target.value);
            edit(null);
            setItems([]);
            setCursor(null);
          }}
        >
          <option value="">Choose a book</option>
          {overview?.items
            .filter((x) => x.book)
            .map((x) => (
              <option key={x.book!.book_id} value={x.book!.book_id}>
                {x.code} · {x.legal_name}
              </option>
            ))}
        </select>
      </label>
      {book && (
        <>
          <section aria-label="Admission requests">
            <h2>Requests</h2>
            <button disabled={locked || !enabled} onClick={() => edit(null)}>
              New admission request
            </button>
            {items.length === 0 && <p>No admission requests in this book.</p>}
            <ul>
              {items.map((view) => (
                <li key={view.request_id}>
                  <button
                    disabled={locked}
                    onClick={() => {
                      edit(view);
                    }}
                  >
                    {view.country} · {view.requested_operation} · {view.state} ·
                    revision {view.revision}
                  </button>
                </li>
              ))}
            </ul>
            {cursor && (
              <button
                disabled={locked}
                onClick={() => {
                  setBusy(true);
                  void fetchAdmissions(businessId, book, cursor)
                    .then((result) => {
                      setItems((prior) => [...prior, ...result.items]);
                      setCursor(result.next_after);
                    })
                    .catch((e) => setError(message(e)))
                    .finally(() => setBusy(false));
                }}
              >
                More admission requests
              </button>
            )}
          </section>
          <section aria-label="Admission details">
            <h2>{selected ? "Request details" : "New request"}</h2>
            {selected && (
              <>
                <p>
                  State: {selected.state}. Assessment: {selected.assessment}.
                  Revision: {selected.revision}.
                </p>
                <p>All payment capabilities: disabled.</p>
              </>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void run();
              }}
            >
              <fieldset disabled={readOnly}>
                <legend>Declared request information</legend>
                <label>
                  Country code
                  <input
                    required
                    maxLength={2}
                    pattern="[A-Z]{2}"
                    value={input.country}
                    onChange={(e) =>
                      setInput({
                        ...input,
                        country: e.target.value.toUpperCase(),
                      })
                    }
                  />
                </label>
                <label>
                  Business activity
                  <input
                    required
                    maxLength={500}
                    value={input.business_activity}
                    onChange={(e) =>
                      setInput({ ...input, business_activity: e.target.value })
                    }
                  />
                </label>
                <label>
                  Requested operation
                  <select
                    value={input.requested_operation}
                    onChange={(e) =>
                      setInput({
                        ...input,
                        requested_operation: e.target
                          .value as AdmissionInput["requested_operation"],
                      })
                    }
                  >
                    {["charge", "refund", "transfer", "payout"].map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Account reference
                  <input
                    maxLength={160}
                    autoComplete="off"
                    value={input.account_reference ?? ""}
                    onChange={(e) =>
                      setInput({
                        ...input,
                        account_reference: e.target.value || null,
                      })
                    }
                  />
                </label>
                <p>
                  Provide a reference only. Do not enter API keys, tokens or
                  credentials.
                </p>
                <label>
                  Evidence references (one per line)
                  <textarea
                    maxLength={2056}
                    value={evidence}
                    onChange={(e) => setEvidence(e.target.value)}
                  />
                </label>
                <label>
                  Declared assessment
                  <select
                    value={input.assessment}
                    onChange={(e) =>
                      setInput({
                        ...input,
                        assessment: e.target
                          .value as AdmissionInput["assessment"],
                      })
                    }
                  >
                    {["not_checked", "suspended", "unsupported"].map(
                      (value) => (
                        <option key={value}>{value}</option>
                      ),
                    )}
                  </select>
                </label>
                <label>
                  Review notes
                  <textarea
                    maxLength={2000}
                    value={input.notes ?? ""}
                    onChange={(e) =>
                      setInput({ ...input, notes: e.target.value || null })
                    }
                  />
                </label>
                <button type="submit">Save admission draft</button>
              </fieldset>
            </form>
            {selected?.state === "draft" && (
              <button
                disabled={
                  locked ||
                  !enabled ||
                  selected.evidence_references.length === 0
                }
                onClick={() => void run("submit")}
              >
                Submit admission request
              </button>
            )}
            {selected && selected.state !== "withdrawn" && (
              <button disabled={locked} onClick={() => void run("withdraw")}>
                Withdraw admission request
              </button>
            )}
          </section>
          {selected && (
            <section aria-label="Admission history">
              <h2>Immutable history</h2>
              <label>
                Admission revision
                <input
                  type="number"
                  min={1}
                  max={selected.revision}
                  value={historyRevision}
                  onChange={(e) => setHistoryRevision(Number(e.target.value))}
                />
              </label>
              <button
                disabled={locked}
                onClick={() => {
                  setBusy(true);
                  void fetchAdmission(
                    businessId,
                    book,
                    selected.request_id,
                    historyRevision,
                  )
                    .then(setHistory)
                    .catch((e) => setError(message(e)))
                    .finally(() => setBusy(false));
                }}
              >
                Read admission revision
              </button>
              {history && (
                <p>
                  Revision {history.revision}: {history.state};{" "}
                  {history.country}; {history.requested_operation};{" "}
                  {history.assessment}. All capabilities disabled.
                </p>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
