"use client";

// L7b1 (package L): the visit desk — complete a visit with actual quantities and write its
// materials off; L7b2a adds billing and the commission. Words stay neutral: every direction that consumes materials uses this desk.
import React, { useEffect, useId, useState } from "react";
import { businessDateTime } from "../lib/business-time";
import { fetchAllItems, fetchAllPlaces } from "../lib/inventory-api";
import type { Item, Place } from "../lib/inventory-contracts";
import type { LegalEntity } from "../lib/legal-entity-contracts";
import {
  type BookingSummary,
  completeVisit,
  type CompletionView,
  fetchCompletion,
  fetchConfiguration,
  fetchLegalEntities,
  fetchNoShow,
  ManagementApiError,
  type NoShowView,
  postConsumption,
  recordNoShow,
  type RecipeLine,
} from "../lib/management-api";
import { VisitBillingSection } from "./visit-billing";

function refusal(error: unknown): string {
  if (error instanceof ManagementApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

async function allLegalEntities(salonId: string): Promise<LegalEntity[]> {
  const entities: LegalEntity[] = [];
  const seen = new Set<string>();
  let after: string | undefined;
  for (;;) {
    const page = await fetchLegalEntities(salonId, after);
    entities.push(...page.items);
    if (page.next_cursor === null) return entities;
    if (seen.has(page.next_cursor))
      throw new ManagementApiError(
        "INVALID_RESPONSE",
        "Unable to load the complete list of owners safely.",
      );
    seen.add(page.next_cursor);
    after = page.next_cursor;
  }
}

export function VisitDeskDialog({
  salonId,
  booking,
  onClose,
}: {
  salonId: string;
  booking: BookingSummary;
  onClose: () => void;
}) {
  const titleId = useId();
  const [completion, setCompletion] = useState<CompletionView | null>(null);
  const [loaded, setLoaded] = useState(false);
  // L9a: a visit recorded as a no-show is not completed; it is billed its policy fee.
  const [noShow, setNoShow] = useState<NoShowView | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [entities, setEntities] = useState<LegalEntity[]>([]);
  const [stockNote, setStockNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actuals, setActuals] = useState<RecipeLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [entity, setEntity] = useState("");
  const [place, setPlace] = useState("");
  const [today] = useState(
    () => businessDateTime(new Date(), booking.location_timezone).date,
  );
  const [day, setDay] = useState(today);
  // L8 decision 70: the enabled modules; null while unknown (the server still refuses).
  const [modules, setModules] = useState<string[] | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchCompletion(salonId, booking.booking_id),
      fetchNoShow(salonId, booking.booking_id),
    ])
      .then(([found, missed]) => {
        if (!live) return;
        setCompletion(found);
        setNoShow(missed);
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live) setError(`The visit could not be read: ${refusal(failure)}`);
      });
    fetchConfiguration(salonId)
      .then((configuration) => {
        if (live) setModules(configuration.effective_module_ids);
      })
      .catch(() => {
        // Without the right to read the configuration every step stays shown.
      });
    Promise.all([
      fetchAllItems(salonId),
      fetchAllPlaces(salonId),
      allLegalEntities(salonId),
    ])
      .then(([itemPage, placePage, owners]) => {
        if (!live) return;
        setItems(itemPage.items);
        const here = placePage.items.filter(
          (p) => p.location_id === booking.location_id && !p.archived,
        );
        setPlaces(here);
        setEntities(owners);
        setPlace((current) => current || (here[0]?.place_id ?? ""));
        setEntity((current) => current || (owners[0]?.legal_entity_id ?? ""));
      })
      .catch((failure: unknown) => {
        if (live)
          setStockNote(`Materials are not available here: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [salonId, booking.booking_id, booking.location_id]);

  const nameOf = (itemId: string) => {
    const item = items.find((i) => i.item_id === itemId);
    return item ? `${item.name} (${item.unit})` : itemId;
  };

  async function complete(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setCompletion(await completeVisit(salonId, booking.booking_id, actuals));
      setNotice("Visit completed.");
    } catch (failure) {
      setError(`The visit was not completed: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function markNoShow() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNoShow(await recordNoShow(salonId, booking.booking_id));
      setNotice("Recorded as a no-show.");
    } catch (failure) {
      setError(`The no-show was not recorded: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  async function writeOff(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setCompletion(
        await postConsumption(salonId, booking.booking_id, {
          legal_entity_id: entity,
          place_id: place,
          document_date: day,
        }),
      );
      setNotice("Materials written off.");
    } catch (failure) {
      setError(`The materials were not written off: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="mgmt-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div className="mgmt-modal-card visit-desk">
        <h2 id={titleId}>Visit desk</h2>
        <p className="muted">
          {booking.service_name} ({booking.variant_name}) with{" "}
          {booking.resource_name}
        </p>
        {!loaded && !error && (
          <p className="muted" role="status">
            Loading the visit…
          </p>
        )}
        {noShow !== null && (
          <p className="hold-note">
            No-show
            {noShow.fee !== null
              ? `: fee under the policy ${noShow.fee}.`
              : "; there is no fee under the policy."}
          </p>
        )}
        {loaded && completion === null && noShow === null && (
          <div className="mgmt-form-actions">
            <button
              type="button"
              className="secondary"
              onClick={markNoShow}
              disabled={busy}
            >
              Mark as no-show
            </button>
          </div>
        )}
        {loaded && completion === null && noShow === null && (
          <form onSubmit={complete} aria-labelledby="complete-heading">
            <h3 id="complete-heading">Complete the visit</h3>
            <p className="muted">
              The materials of every service are planned from their recipes;
              enter an actual quantity only where it differs.
            </p>
            {stockNote && (
              <p className="muted" role="status">
                {stockNote}
              </p>
            )}
            {actuals.map((row, index) => (
              <fieldset key={index} className="service-material-row">
                <legend>Actual quantity {index + 1}</legend>
                <label>
                  Material
                  <select
                    aria-label="Material"
                    value={row.item_id}
                    onChange={(e) =>
                      setActuals((current) =>
                        current.map((r, i) =>
                          i === index ? { ...r, item_id: e.target.value } : r,
                        ),
                      )
                    }
                  >
                    {items
                      .filter((item) => !item.archived)
                      .map((item) => (
                        <option key={item.item_id} value={item.item_id}>
                          {item.name} ({item.unit})
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Quantity
                  <input
                    type="text"
                    inputMode="decimal"
                    value={row.quantity}
                    onChange={(e) =>
                      setActuals((current) =>
                        current.map((r, i) =>
                          i === index ? { ...r, quantity: e.target.value } : r,
                        ),
                      )
                    }
                    required
                  />
                </label>
                <button
                  type="button"
                  className="secondary mgmt-btn-small"
                  onClick={() =>
                    setActuals((current) =>
                      current.filter((_, i) => i !== index),
                    )
                  }
                >
                  Remove actual quantity {index + 1}
                </button>
              </fieldset>
            ))}
            <div className="mgmt-form-actions">
              <button
                type="button"
                className="secondary"
                disabled={items.length === 0}
                onClick={() => {
                  const first = items.find((item) => !item.archived);
                  if (first)
                    setActuals((current) => [
                      ...current,
                      { item_id: first.item_id, quantity: "0" },
                    ]);
                }}
              >
                Add actual quantity
              </button>
              <button type="submit" disabled={busy}>
                {busy ? "Completing…" : "Complete visit"}
              </button>
            </div>
          </form>
        )}
        {completion !== null && (
          <section aria-labelledby="uses-heading">
            <h3 id="uses-heading">Materials</h3>
            {completion.materials.length === 0 ? (
              <p className="muted">No materials were used.</p>
            ) : (
              <div className="mgmt-table-container">
                <table className="mgmt-table" aria-label="Materials used">
                  <thead>
                    <tr>
                      <th scope="col">Material</th>
                      <th scope="col">Planned</th>
                      <th scope="col">Actual</th>
                    </tr>
                  </thead>
                  <tbody>
                    {completion.materials.map((use) => (
                      <tr key={use.item_id}>
                        <th scope="row">{nameOf(use.item_id)}</th>
                        <td>{use.planned}</td>
                        <td>{use.actual}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {completion.consumption_posted_at !== null ? (
              <p className="hold-note">
                {completion.stock_document_id
                  ? "Materials written off."
                  : "Nothing was left to write off."}
              </p>
            ) : modules !== null && !modules.includes("inventory") ? (
              <p className="muted">
                Materials are turned off in this business&apos;s configuration.
              </p>
            ) : (
              <form onSubmit={writeOff} aria-labelledby="writeoff-heading">
                <h3 id="writeoff-heading">Write off the materials</h3>
                <p className="muted">
                  Needs inventory and finance rights; posted once, at the
                  average cost.
                </p>
                <label>
                  Owner
                  <select
                    aria-label="Owner"
                    value={entity}
                    onChange={(e) => setEntity(e.target.value)}
                    required
                  >
                    {entities.map((owner) => (
                      <option
                        key={owner.legal_entity_id}
                        value={owner.legal_entity_id}
                      >
                        {owner.legal_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Storage place
                  <select
                    aria-label="Storage place"
                    value={place}
                    onChange={(e) => setPlace(e.target.value)}
                    required
                  >
                    {places.map((shelf) => (
                      <option key={shelf.place_id} value={shelf.place_id}>
                        {shelf.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Date
                  <input
                    type="date"
                    value={day}
                    onChange={(e) => setDay(e.target.value)}
                    required
                  />
                </label>
                <div className="mgmt-form-actions">
                  <button type="submit" disabled={busy || !entity || !place}>
                    {busy ? "Writing off…" : "Write off materials"}
                  </button>
                </div>
              </form>
            )}
          </section>
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
        <VisitBillingSection
          salonId={salonId}
          bookingId={booking.booking_id}
          today={today}
          modules={modules}
        />
        <div className="mgmt-form-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
