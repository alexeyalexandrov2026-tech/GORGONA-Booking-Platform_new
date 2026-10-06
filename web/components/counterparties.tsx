"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CounterpartyEditor } from "./counterparty-editor";
import { CounterpartyRelationships } from "./counterparty-relationships";
import { CounterpartyDocumentsPanel } from "./counterparty-documents";
import { CounterpartyAgreements } from "./agreements";
import {
  fetchCounterparties,
  fetchCounterparty,
  fetchCounterpartyHistory,
  fetchCounterpartyFamily,
  fetchCounterpartyDuplicates,
  fetchCounterpartyDecisions,
  fetchBookingCandidates,
  fetchLinkedBookings,
  fetchBookingLinkHistory,
  checkCounterpartyMatches,
  executeCounterpartyCommand,
} from "../lib/counterparty-api";
import { fetchConfiguration, ManagementApiError } from "../lib/management-api";
import type {
  Counterparty,
  CounterpartyInput,
  CounterpartyPage,
  CounterpartyHistory,
  Matches,
  MatchDecisions,
  BookingCandidates,
  LinkedBookings,
  BookingLinkHistory,
  CounterpartyCommand,
} from "../lib/counterparty-contracts";

const empty = (): CounterpartyInput => ({
  schema_version: 1,
  expected_revision: 0,
  kind: "person",
  display_name: "",
  legal_name: null,
  tax_id: null,
  registration_number: null,
  email: null,
  phone: null,
  roles: [],
  archived: false,
  contacts: [],
});
const failure = (error: unknown) =>
  error instanceof Error ? error.message : "Unable to complete this action.";
type Proposal = { command: CounterpartyCommand; explanation: string };

export function Counterparties({ businessId }: { businessId: string }) {
  const [items, setItems] = useState<CounterpartyPage["items"]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<Counterparty | null>(null);
  const [form, setForm] = useState<CounterpartyInput>(empty);
  const [enabled, setEnabled] = useState(false);
  const [history, setHistory] = useState<CounterpartyHistory | null>(null);
  const [historical, setHistorical] = useState<Counterparty | null>(null);
  const [family, setFamily] = useState<CounterpartyPage | null>(null);
  const [matches, setMatches] = useState<Matches | null>(null);
  const [decisions, setDecisions] = useState<MatchDecisions | null>(null);
  const [candidates, setCandidates] = useState<BookingCandidates | null>(null);
  const [bookings, setBookings] = useState<LinkedBookings | null>(null);
  const [links, setLinks] = useState<BookingLinkHistory | null>(null);
  const [bookingIds, setBookingIds] = useState<string[]>([]);
  const [pending, setPending] = useState<CounterpartyCommand | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [conflict, setConflict] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchCounterparties(businessId, "", ""),
      fetchConfiguration(businessId),
    ])
      .then(([page, configuration]) => {
        if (!active) return;
        setItems(page.items);
        setCursor(page.next_cursor);
        setEnabled(
          configuration.effective_module_ids.includes("counterparties"),
        );
      })
      .catch((e: unknown) => {
        if (active) setError(failure(e));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  function choose(card: Counterparty | null) {
    setSelected(card);
    setForm(
      card
        ? {
            schema_version: 1,
            expected_revision: card.revision,
            kind: card.kind,
            display_name: card.display_name,
            legal_name: card.legal_name,
            tax_id: card.tax_id,
            registration_number: card.registration_number,
            email: card.email,
            phone: card.phone,
            roles: card.roles,
            archived: card.state === "archived",
            contacts: card.contacts.map((contact) => ({
              name: contact.name,
              job_title: contact.job_title,
              email: contact.email,
              phone: contact.phone,
            })),
          }
        : empty(),
    );
    setHistorical(null);
    setHistory(null);
    setFamily(null);
    setMatches(null);
    setDecisions(null);
    setCandidates(null);
    setBookings(null);
    setLinks(null);
    setBookingIds([]);
    setProposal(null);
    setConflict(false);
  }

  async function inspect(id: string) {
    if (busy || pending || proposal) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const card = await fetchCounterparty(businessId, id);
      choose(card);
      const [
        versions,
        merged,
        duplicates,
        decisions,
        candidates,
        bookings,
        links,
        configuration,
      ] = await Promise.all([
        fetchCounterpartyHistory(businessId, id),
        fetchCounterpartyFamily(businessId, id),
        fetchCounterpartyDuplicates(businessId, id),
        fetchCounterpartyDecisions(businessId, id),
        fetchBookingCandidates(businessId, id),
        fetchLinkedBookings(businessId, id),
        fetchBookingLinkHistory(businessId, id),
        fetchConfiguration(businessId),
      ]);
      setHistory(versions);
      setFamily(merged);
      setMatches(duplicates);
      setDecisions(decisions);
      setCandidates(candidates);
      setBookings(bookings);
      setLinks(links);
      setEnabled(configuration.effective_module_ids.includes("counterparties"));
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  async function search(after?: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const page = await fetchCounterparties(
        businessId,
        query.trim(),
        filter,
        after,
      );
      setItems((previous) =>
        after
          ? [
              ...previous,
              ...page.items.filter(
                (row) =>
                  !previous.some(
                    (p) => p.counterparty_id === row.counterparty_id,
                  ),
              ),
            ]
          : page.items,
      );
      setCursor(page.next_cursor);
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  async function run(command: CounterpartyCommand) {
    if (busy) return;
    setPending(command);
    setProposal(null);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await executeCounterpartyCommand(businessId, command);
      setPending(null);
      setMessage(
        command.type === "save" ? "Counterparty saved." : "Decision recorded.",
      );
      // The command succeeded. Any following read failure is separate from its receipt.
      const card = await fetchCounterparty(businessId, command.id);
      choose(card);
      const [
        page,
        versions,
        family,
        matches,
        decisions,
        candidates,
        bookings,
        links,
      ] = await Promise.all([
        fetchCounterparties(businessId, query.trim(), filter),
        fetchCounterpartyHistory(businessId, command.id),
        fetchCounterpartyFamily(businessId, command.id),
        fetchCounterpartyDuplicates(businessId, command.id),
        fetchCounterpartyDecisions(businessId, command.id),
        fetchBookingCandidates(businessId, command.id),
        fetchLinkedBookings(businessId, command.id),
        fetchBookingLinkHistory(businessId, command.id),
      ]);
      setItems(page.items);
      setCursor(page.next_cursor);
      setHistory(versions);
      setFamily(family);
      setMatches(matches);
      setDecisions(decisions);
      setCandidates(candidates);
      setBookings(bookings);
      setLinks(links);
    } catch (e: unknown) {
      setError(failure(e));
      if (
        e instanceof ManagementApiError &&
        e.status &&
        e.status >= 400 &&
        e.status < 500
      ) {
        setPending(null);
        setConflict(e.status === 409);
        if (e.code === "MODULE_DISABLED") setEnabled(false);
      }
    } finally {
      setBusy(false);
    }
  }

  async function prepareSave(event: React.FormEvent) {
    event.preventDefault();
    if (!enabled || busy || pending || conflict || selected?.state === "merged")
      return;
    setBusy(true);
    setError(null);
    const command: CounterpartyCommand = {
      type: "save",
      id: selected?.counterparty_id ?? crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: form,
    };
    try {
      const checked = await checkCounterpartyMatches(
        businessId,
        form,
        selected?.counterparty_id,
      );
      setMatches(checked);
      setProposal({
        command,
        explanation: checked.items.length
          ? "Possible matches found. Compare the records before saving a separate card. Saving does not merge them."
          : "Save this card as entered. It will not merge records or link bookings.",
      });
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  async function prepareMerge(id: string) {
    if (!selected || locked) return;
    setBusy(true);
    setError(null);
    try {
      const into = await fetchCounterparty(businessId, id);
      setProposal({
        command: {
          type: "match",
          id: selected.counterparty_id,
          key: crypto.randomUUID(),
          body: {
            decision: "merge",
            into_id: id,
            expected_revision: selected.revision,
            into_expected_revision: into.revision,
          },
        },
        explanation: `Merge ${selected.display_name} into ${into.display_name} (${into.kind}; email: ${into.email ?? "not provided"}; phone: ${into.phone ?? "not provided"}). Both cards and their contacts remain in history. Linked bookings are shown together. You can later record a separation.`,
      });
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  async function readDetails(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e: unknown) {
      setError(failure(e));
    } finally {
      setBusy(false);
    }
  }

  const locked =
    busy || !enabled || Boolean(pending) || conflict || Boolean(proposal);
  const formLocked = locked || selected?.state === "merged";
  if (loading) return <p role="status">Loading counterparties…</p>;
  return (
    <div className="mgmt-page counterparties">
      <h1>Counterparties</h1>
      <p>
        Customers, suppliers, contractors and partners in one company. Matches
        are suggestions; each link and merge requires your decision.
      </p>
      {!enabled && (
        <p className="warning">
          Counterparties is turned off. Saved cards and history remain readable.
          Enable it through a validated{" "}
          <Link href="/business/">business configuration</Link> before making
          changes.
        </p>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {pending && !busy && (
        <div className="warning">
          <p>
            The result of the last command is uncertain. Editing is paused until
            the same command is retried.
          </p>
          <button disabled={busy} onClick={() => void run(pending)}>
            Retry same counterparty command
          </button>
        </div>
      )}
      {conflict && (
        <p className="warning">
          The data or configuration changed. Reload the card before continuing.
        </p>
      )}
      <section aria-label="Counterparty list" className="mgmt-card">
        <form
          className="mgmt-filter-bar"
          onSubmit={(e) => {
            e.preventDefault();
            void search();
          }}
        >
          <label>
            Search counterparties
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={200}
            />
          </label>
          <label>
            Card state
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">Active and archived</option>
              <option value="active">Active</option>
              <option value="archived">Archived</option>
              <option value="merged">Merged</option>
            </select>
          </label>
          <button disabled={busy}>Search</button>
          <button
            type="button"
            className="secondary"
            disabled={locked}
            onClick={() => {
              choose(null);
              setError(null);
              setMessage(null);
            }}
          >
            New counterparty
          </button>
        </form>
        {items.length === 0 && <p>No cards match this search.</p>}
        <ul className="cp-list">
          {items.map((item) => (
            <li key={item.counterparty_id}>
              <button
                className="secondary"
                disabled={busy || Boolean(pending) || Boolean(proposal)}
                onClick={() => void inspect(item.counterparty_id)}
              >
                {item.display_name}
              </button>{" "}
              <span>
                {item.kind} · {item.state} · version {item.revision}
              </span>
            </li>
          ))}
        </ul>
        {cursor && (
          <button disabled={busy} onClick={() => void search(cursor)}>
            Load more cards
          </button>
        )}
      </section>
      <CounterpartyEditor
        selected={selected}
        form={form}
        setForm={setForm}
        locked={formLocked}
        reloadDisabled={busy || Boolean(pending) || Boolean(proposal)}
        onReload={() => void inspect(selected!.counterparty_id)}
        onSubmit={(e) => void prepareSave(e)}
      />
      {proposal && (
        <section aria-label="Confirm counterparty action" className="mgmt-card">
          <h2>Review your decision</h2>
          <p>{proposal.explanation}</p>
          <button disabled={busy} onClick={() => void run(proposal.command)}>
            Confirm counterparty action
          </button>
          <button
            className="secondary"
            disabled={busy}
            onClick={() => setProposal(null)}
          >
            Keep editing
          </button>
        </section>
      )}
      {matches && (
        <section aria-label="Possible matches" className="mgmt-card">
          <h2>Possible matches</h2>
          <p>
            Up to 100 suggestions. A shared name is a weak match; shared contact
            or registration details need human review.
          </p>
          {matches.items.length === 0 && <p>No possible matches found.</p>}
          <ul className="cp-list">
            {matches.items.map((candidate) => (
              <li key={candidate.counterparty_id}>
                <strong>{candidate.display_name}</strong> · {candidate.strength}{" "}
                · {candidate.reasons.join(", ")} · {candidate.state}
                {selected && !proposal && (
                  <div className="mgmt-form-actions">
                    <button
                      disabled={locked}
                      onClick={() =>
                        void prepareMerge(candidate.counterparty_id)
                      }
                    >
                      Review merge into {candidate.display_name}
                    </button>
                    <button
                      className="secondary"
                      disabled={locked}
                      onClick={() =>
                        void run({
                          type: "match",
                          id: selected.counterparty_id,
                          key: crypto.randomUUID(),
                          body: {
                            decision: "distinct",
                            other_id: candidate.counterparty_id,
                          },
                        })
                      }
                    >
                      Mark {candidate.display_name} as different
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {selected && (
        <CounterpartyRelationships
          businessId={businessId}
          selected={selected}
          family={family}
          setFamily={setFamily}
          decisions={decisions}
          candidates={candidates}
          bookings={bookings}
          setBookings={setBookings}
          links={links}
          setLinks={setLinks}
          history={history}
          setHistory={setHistory}
          historical={historical}
          setHistorical={setHistorical}
          bookingIds={bookingIds}
          setBookingIds={setBookingIds}
          setProposal={setProposal}
          onInspect={(id) => void inspect(id)}
          onRead={(action) => void readDetails(action)}
          locked={locked}
          readLocked={busy || Boolean(pending) || Boolean(proposal)}
          busy={busy}
        />
      )}
      {selected && (
        <CounterpartyDocumentsPanel
          key={`${selected.counterparty_id}:${selected.revision}`}
          businessId={businessId}
          counterpartyId={selected.counterparty_id}
        />
      )}
      {selected && (
        <CounterpartyAgreements
          key={selected.counterparty_id}
          businessId={businessId}
          counterpartyId={selected.counterparty_id}
          cardActive={selected.state === "active"}
          enabled={enabled}
        />
      )}
    </div>
  );
}
