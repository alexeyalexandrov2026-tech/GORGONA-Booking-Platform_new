"use client";
import {
  fetchCounterpartyFamily,
  fetchLinkedBookings,
  fetchBookingLinkHistory,
  fetchCounterpartyHistory,
  fetchCounterparty,
} from "../lib/counterparty-api";
import type {
  Counterparty,
  CounterpartyPage,
  CounterpartyHistory,
  MatchDecisions,
  BookingCandidates,
  LinkedBookings,
  BookingLinkHistory,
  CounterpartyCommand,
} from "../lib/counterparty-contracts";

export function CounterpartyRelationships({
  businessId,
  selected,
  family,
  setFamily,
  decisions,
  candidates,
  bookings,
  setBookings,
  links,
  setLinks,
  history,
  setHistory,
  historical,
  setHistorical,
  bookingIds,
  setBookingIds,
  setProposal,
  onInspect,
  onRead,
  locked,
  readLocked,
  busy,
}: {
  businessId: string;
  selected: Counterparty;
  family: CounterpartyPage | null;
  setFamily: (v: CounterpartyPage) => void;
  decisions: MatchDecisions | null;
  candidates: BookingCandidates | null;
  bookings: LinkedBookings | null;
  setBookings: (v: LinkedBookings) => void;
  links: BookingLinkHistory | null;
  setLinks: (v: BookingLinkHistory) => void;
  history: CounterpartyHistory | null;
  setHistory: (v: CounterpartyHistory) => void;
  historical: Counterparty | null;
  setHistorical: (v: Counterparty) => void;
  bookingIds: string[];
  setBookingIds: (v: string[]) => void;
  setProposal: (v: {
    command: CounterpartyCommand;
    explanation: string;
  }) => void;
  onInspect: (id: string) => void;
  onRead: (action: () => Promise<void>) => void;
  locked: boolean;
  readLocked: boolean;
  busy: boolean;
}) {
  function load<T>(operation: () => Promise<T>, apply: (value: T) => void) {
    onRead(async () => apply(await operation()));
  }
  return (
    <>
      {family && family.items.length > 0 && (
        <section aria-label="Merged cards" className="mgmt-card">
          <h2>Merged cards and contacts</h2>
          <p>Each original card retains its contacts and versions.</p>
          <ul>
            {family.items.map((row) => (
              <li key={row.counterparty_id}>
                <button
                  className="secondary"
                  disabled={readLocked}
                  onClick={() => void onInspect(row.counterparty_id)}
                >
                  Read merged card: {row.display_name}
                </button>
              </li>
            ))}
          </ul>
          {family.next_cursor && (
            <button
              disabled={busy}
              onClick={() =>
                load(
                  () =>
                    fetchCounterpartyFamily(
                      businessId,
                      selected!.counterparty_id,
                      family.next_cursor!,
                    ),
                  (page) =>
                    setFamily({
                      ...page,
                      items: [...family.items, ...page.items],
                    }),
                )
              }
            >
              More merged cards
            </button>
          )}
        </section>
      )}
      {decisions && (
        <section aria-label="Match decisions" className="mgmt-card">
          <h2>Match decisions</h2>
          <ul>
            {decisions.items.map((decision) => (
              <li key={decision.decision_id}>
                {decision.kind} · version{" "}
                {decision.counterparty_revision ?? "unchanged"} ·{" "}
                {new Date(decision.decided_at).toLocaleString()}
                {decision.reversed && " · reversed"}
                {decision.kind === "merged" &&
                  !decision.reversed &&
                  decision.counterparty_id === selected?.counterparty_id && (
                    <button
                      className="secondary"
                      disabled={locked}
                      onClick={() =>
                        setProposal({
                          command: {
                            type: "match",
                            id: selected.counterparty_id,
                            key: crypto.randomUUID(),
                            body: {
                              decision: "separate",
                              decision_id: decision.decision_id,
                              expected_revision: selected.revision,
                            },
                          },
                          explanation:
                            "Separate these cards. Their original contacts and booking links stay with their original cards.",
                        })
                      }
                    >
                      Review separation
                    </button>
                  )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {candidates && selected?.state === "active" && (
        <section aria-label="Booking candidates" className="mgmt-card">
          <h2>Booking candidates</h2>
          <p>
            Up to 100 matches. Select only bookings whose customer you have
            verified. Details are checked again when you confirm.
          </p>
          {candidates.items.map((candidate) => (
            <label key={candidate.booking.booking_id}>
              <input
                type="checkbox"
                disabled={
                  locked ||
                  (!bookingIds.includes(candidate.booking.booking_id) &&
                    bookingIds.length >= 50)
                }
                checked={bookingIds.includes(candidate.booking.booking_id)}
                onChange={(e) =>
                  setBookingIds(
                    e.target.checked
                      ? [...bookingIds, candidate.booking.booking_id]
                      : bookingIds.filter(
                          (id) => id !== candidate.booking.booking_id,
                        ),
                  )
                }
              />{" "}
              {candidate.booking.customer_name} ·{" "}
              {new Date(candidate.booking.starts_at).toLocaleString()} ·{" "}
              {candidate.basis.join(", ")}
            </label>
          ))}
          {candidates.items.length === 0 && (
            <p>No unlinked matching bookings.</p>
          )}
          <button
            disabled={locked || !bookingIds.length}
            onClick={() =>
              setProposal({
                command: {
                  type: "link",
                  id: selected.counterparty_id,
                  key: crypto.randomUUID(),
                  body: { action: "link", booking_ids: bookingIds },
                },
                explanation: `Confirm ${bookingIds.length} booking links. This does not change the customer details on any booking.`,
              })
            }
          >
            Review selected booking links
          </button>
        </section>
      )}
      {bookings && (
        <section aria-label="Linked bookings" className="mgmt-card">
          <h2>Linked bookings</h2>
          <ul>
            {bookings.items.map((row) => (
              <li key={row.booking.booking_id}>
                {row.booking.customer_name} ·{" "}
                {new Date(row.booking.starts_at).toLocaleString()} ·{" "}
                {row.booking.status}
                {!row.still_matches && (
                  <strong> · contact details no longer match</strong>
                )}
                {row.counterparty_id === selected?.counterparty_id ? (
                  <button
                    className="secondary"
                    disabled={locked}
                    onClick={() =>
                      setProposal({
                        command: {
                          type: "link",
                          id: row.counterparty_id,
                          key: crypto.randomUUID(),
                          body: {
                            action: "unlink",
                            booking_id: row.booking.booking_id,
                            expected_sequence: row.sequence,
                          },
                        },
                        explanation:
                          "Remove this link while preserving its history and the booking.",
                      })
                    }
                  >
                    Review unlink
                  </button>
                ) : (
                  <span> · linked through a merged card</span>
                )}
              </li>
            ))}
          </ul>
          {bookings.next_cursor && (
            <button
              disabled={busy}
              onClick={() =>
                load(
                  () =>
                    fetchLinkedBookings(
                      businessId,
                      selected!.counterparty_id,
                      bookings.next_cursor!,
                    ),
                  (page) =>
                    setBookings({
                      ...page,
                      items: [...bookings.items, ...page.items],
                    }),
                )
              }
            >
              More linked bookings
            </button>
          )}
        </section>
      )}
      {links && (
        <details className="mgmt-card">
          <summary>Booking link history</summary>
          <ul>
            {links.items.map((row) => (
              <li key={row.link_id}>
                {row.action} · change {row.sequence} ·{" "}
                {new Date(row.decided_at).toLocaleString()}
              </li>
            ))}
          </ul>
          {links.next_cursor && (
            <button
              disabled={busy}
              onClick={() =>
                load(
                  () =>
                    fetchBookingLinkHistory(
                      businessId,
                      selected!.counterparty_id,
                      links.next_cursor!,
                    ),
                  (page) =>
                    setLinks({
                      ...page,
                      items: [...links.items, ...page.items],
                    }),
                )
              }
            >
              More link history
            </button>
          )}
        </details>
      )}
      {history && (
        <section aria-label="Card history" className="mgmt-card">
          <h2>Card history</h2>
          <ul>
            {history.items.map((version) => (
              <li key={version.revision}>
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    load(
                      () =>
                        fetchCounterparty(
                          businessId,
                          selected!.counterparty_id,
                          version.revision,
                        ),
                      setHistorical,
                    )
                  }
                >
                  Read version {version.revision}
                </button>{" "}
                {version.display_name} · {version.state}
              </li>
            ))}
          </ul>
          {history.next_cursor && (
            <button
              disabled={busy}
              onClick={() =>
                load(
                  () =>
                    fetchCounterpartyHistory(
                      businessId,
                      selected!.counterparty_id,
                      history.next_cursor!,
                    ),
                  (page) =>
                    setHistory({
                      ...page,
                      items: [...history.items, ...page.items],
                    }),
                )
              }
            >
              More card history
            </button>
          )}
        </section>
      )}
      {historical && (
        <section aria-label="Saved card version" className="mgmt-card">
          <h2>Saved version {historical.revision}</h2>
          <p>
            {historical.display_name} · {historical.kind} · {historical.state}
          </p>
          <p>
            {historical.legal_name} {historical.tax_id}{" "}
            {historical.registration_number}
          </p>
          <p>
            {historical.email} {historical.phone}
          </p>
          <ul>
            {historical.contacts.map((c) => (
              <li key={c.position}>
                {c.name} · {c.job_title} · {c.email} · {c.phone}
              </li>
            ))}
          </ul>
          <p>This saved version is read-only.</p>
        </section>
      )}
    </>
  );
}
