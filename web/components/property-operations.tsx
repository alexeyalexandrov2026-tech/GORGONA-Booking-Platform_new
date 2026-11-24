"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { businessDateTime, businessTimeToInstant } from "../lib/business-time";
import {
  currencyPlaces,
  formatMinor,
  toMinor,
} from "../lib/construction-rules";
import { fetchStaff, type StaffView } from "../lib/management-api";
import {
  cancelShowing,
  createShowing,
  fetchListing,
  fetchShowings,
  refusal,
  saveListing,
  staleRevision,
} from "../lib/property-api";
import type {
  ListingState,
  ListingView,
  PropertyView,
  ShowingView,
} from "../lib/property-contracts";

type Named = { id: string; name: string };

function localTime(instant: string, zone: string | undefined): string {
  if (!zone) return instant;
  const local = businessDateTime(instant, zone);
  return local.date + " " + local.time;
}

function field(data: FormData, key: string): string {
  return String(data.get(key) ?? "").trim();
}

export function PropertyOperations({
  businessId,
  property,
  canManage,
  parties,
  timezone,
}: {
  businessId: string;
  property: PropertyView;
  canManage: boolean;
  parties: Named[];
  timezone: string | undefined;
}) {
  const [listing, setListing] = useState<ListingView | null>(null);
  const [showings, setShowings] = useState<ShowingView[]>([]);
  const [staff, setStaff] = useState<StaffView[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [listingNotice, setListingNotice] = useState("");
  const [showingNotice, setShowingNotice] = useState("");
  const [showingError, setShowingError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const runningCancel = useRef(false);
  const heading = useId();
  const listingHeading = useRef<HTMLHeadingElement>(null);
  const objectId = property.object_id;

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchListing(businessId, objectId),
      fetchShowings(businessId, objectId),
      fetchStaff(businessId),
    ])
      .then(([current, schedule, hosts]) => {
        if (!live) return;
        setListing(current);
        setShowings(schedule);
        setStaff(hosts);
        setReady(true);
      })
      .catch((failure: unknown) => {
        if (live) setError(refusal(failure));
      });
    return () => {
      live = false;
    };
  }, [businessId, objectId, attempt]);

  function reload() {
    setError("");
    setReady(false);
    setAttempt((n) => n + 1);
  }

  function updateShowing(value: ShowingView) {
    setShowings((rows) => [
      value,
      ...rows.filter((r) => r.showing_id !== value.showing_id),
    ]);
  }

  async function cancel(id: string) {
    if (runningCancel.current) return;
    runningCancel.current = true;
    setCancelling(id);
    setError("");
    setShowingNotice("");
    try {
      updateShowing(await cancelShowing(businessId, id));
      setShowingError("");
      setShowingNotice("Showing cancelled.");
      requestAnimationFrame(() => document.getElementById(heading)?.focus());
    } catch (failure) {
      setError(refusal(failure));
    } finally {
      runningCancel.current = false;
      setCancelling(null);
    }
  }

  const hosts = staff.filter(
    (item) =>
      item.kind === "artist" &&
      item.is_active &&
      item.location_id === property.location_id,
  );

  return (
    <>
      <h3 ref={listingHeading} tabIndex={-1}>
        Listing
      </h3>
      <p role="status">{listingNotice}</p>
      {!ready && !error && <p role="status">Loading listings and showings…</p>}
      {error && (
        <div className="property-error">
          <p role="alert" className="error">
            {error}
          </p>
          <button type="button" onClick={reload}>
            Reload listings and showings
          </button>
        </div>
      )}
      {ready && (
        <>
          {listing ? (
            <dl className="property-facts">
              <div>
                <dt>Headline</dt>
                <dd>{listing.headline}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{listing.state}</dd>
              </div>
              <div>
                <dt>Monthly rent</dt>
                <dd>
                  {formatMinor(
                    listing.monthly_rent,
                    currencyPlaces(listing.currency) ?? 2,
                  )}{" "}
                  {listing.currency}
                </dd>
              </div>
              <div>
                <dt>Available from</dt>
                <dd>{listing.available_from}</dd>
              </div>
              <div>
                <dt>Listing revision</dt>
                <dd>{listing.revision}</dd>
              </div>
              {listing.description && (
                <div>
                  <dt>Description</dt>
                  <dd>{listing.description}</dd>
                </div>
              )}
            </dl>
          ) : (
            <p className="muted">No listing yet.</p>
          )}
          {canManage && (
            <ListingForm
              key={listing?.revision ?? 0}
              businessId={businessId}
              objectId={objectId}
              listing={listing}
              reload={reload}
              onSaved={(saved) => {
                setListing(saved);
                setListingNotice(
                  "Listing saved as revision " + saved.revision + ".",
                );
                requestAnimationFrame(() => listingHeading.current?.focus());
              }}
              clearNotice={() => setListingNotice("")}
            />
          )}
          <h3 id={heading} tabIndex={-1}>
            Showings
          </h3>
          <p role="status">{showingNotice}</p>
          {showings.length === 0 ? (
            <p className="muted">No showings scheduled.</p>
          ) : (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Showings table"
              tabIndex={0}
            >
              <table className="mgmt-table" aria-label="Property showings">
                <thead>
                  <tr>
                    <th scope="col">Starts</th>
                    <th scope="col">Ends</th>
                    <th scope="col">Host</th>
                    <th scope="col">Status</th>
                    {canManage && <th scope="col">Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {[...showings]
                    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))
                    .map((row) => (
                      <tr key={row.showing_id}>
                        <th scope="row">
                          {localTime(row.starts_at, timezone)}
                        </th>
                        <td>{localTime(row.ends_at, timezone)}</td>
                        <td>
                          {row.host_resource_id
                            ? (staff.find(
                                (item) => item.id === row.host_resource_id,
                              )?.display_name ?? "Assigned host")
                            : "None"}
                        </td>
                        <td>
                          {row.status === "active" ? "Active" : "Cancelled"}
                        </td>
                        {canManage && (
                          <td>
                            {row.status === "active" && (
                              <button
                                type="button"
                                className="secondary"
                                disabled={cancelling !== null}
                                onClick={() => void cancel(row.showing_id)}
                              >
                                {cancelling === row.showing_id
                                  ? "Cancelling…"
                                  : "Cancel showing"}
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
          {timezone && <p className="muted">Times shown in {timezone}.</p>}
          {canManage && (
            <ShowingForm
              businessId={businessId}
              objectId={objectId}
              parties={parties}
              hosts={hosts}
              timezone={timezone}
              error={showingError}
              setError={setShowingError}
              clearNotice={() => setShowingNotice("")}
              onSaved={(saved) => {
                updateShowing(saved);
                setShowingNotice("Showing scheduled.");
              }}
            />
          )}
        </>
      )}
    </>
  );
}

function ListingForm({
  businessId,
  objectId,
  listing,
  onSaved,
  reload,
  clearNotice,
}: {
  businessId: string;
  objectId: string;
  listing: ListingView | null;
  onSaved: (result: ListingView) => void;
  reload: () => void;
  clearNotice: () => void;
}) {
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [stale, setStale] = useState(false);
  const running = useRef(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (stale || running.current) return;
    const data = new FormData(event.currentTarget);
    clearNotice();
    const currency = field(data, "currency").toUpperCase();
    const places = /^[A-Z]{3}$/.test(currency)
      ? currencyPlaces(currency)
      : null;
    const rent = places === null ? null : toMinor(field(data, "rent"), places);
    const state = field(data, "state") as ListingState;
    if (rent === null || rent <= 0) {
      setError("Enter a positive amount and a valid three-letter currency.");
      return;
    }
    running.current = true;
    setSaving(true);
    setError("");
    try {
      const saved = await saveListing(businessId, objectId, {
        schema_version: 1,
        expected_revision: listing?.revision ?? 0,
        headline: field(data, "headline"),
        description: field(data, "description") || null,
        state,
        monthly_rent: rent,
        currency,
        available_from: field(data, "date"),
      });
      onSaved(saved);
    } catch (failure) {
      const revision = staleRevision(failure);
      setStale(revision !== undefined);
      setError(
        revision === undefined
          ? refusal(failure)
          : "This listing changed. Reload it before saving.",
      );
    } finally {
      running.current = false;
      setSaving(false);
    }
  }

  return (
    <form aria-label="Edit listing" className="mgmt-form" onSubmit={submit}>
      <div className="property-operation-fields">
        <label>
          Headline
          <input
            name="headline"
            required
            maxLength={120}
            defaultValue={listing?.headline}
          />
        </label>
        <label>
          Listing status
          <select name="state" defaultValue={listing?.state ?? "draft"}>
            <option value="draft">Draft</option>
            <option value="published">Published internally</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
        </label>
        <label>
          Monthly rent
          <input
            name="rent"
            required
            inputMode="decimal"
            defaultValue={
              listing
                ? formatMinor(
                    listing.monthly_rent,
                    currencyPlaces(listing.currency) ?? 2,
                  )
                : ""
            }
          />
        </label>
        <label>
          Currency
          <input
            name="currency"
            required
            maxLength={3}
            pattern="[A-Za-z]{3}"
            defaultValue={listing?.currency}
          />
        </label>
        <label>
          Available from
          <input
            type="date"
            name="date"
            required
            defaultValue={listing?.available_from}
          />
        </label>
        <label>
          Description
          <textarea
            name="description"
            maxLength={4000}
            defaultValue={listing?.description ?? ""}
          />
        </label>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="mgmt-form-actions">
        <button type="submit" disabled={saving || stale}>
          {saving ? "Saving…" : "Save listing"}
        </button>
        {stale && (
          <button type="button" className="secondary" onClick={reload}>
            Reload listing
          </button>
        )}
      </div>
    </form>
  );
}

function ShowingForm({
  businessId,
  objectId,
  timezone,
  parties,
  hosts,
  onSaved,
  clearNotice,
  error,
  setError,
}: {
  businessId: string;
  objectId: string;
  timezone: string | undefined;
  parties: Named[];
  hosts: StaffView[];
  onSaved: (showing: ShowingView) => void;
  clearNotice: () => void;
  error: string;
  setError: (message: string) => void;
}) {
  const showingId = useRef<string | null>(null);
  const running = useRef(false);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (running.current) return;
    const data = new FormData(event.currentTarget);
    clearNotice();
    setError("");
    running.current = true;
    setSaving(true);
    try {
      if (!timezone) throw new Error("Configure the branch time zone first.");
      const instant = (key: string) => {
        const [date = "", time = ""] = field(data, key).split("T");
        return businessTimeToInstant(date, time, timezone);
      };
      const start = instant("start");
      const end = instant("end");
      if (end <= start) throw new Error("The end must be after the start.");
      showingId.current ??= crypto.randomUUID();
      const result = await createShowing(businessId, showingId.current, {
        schema_version: 1,
        object_id: objectId,
        prospect_id: field(data, "prospect"),
        host_resource_id: field(data, "host") || null,
        starts_at: start,
        ends_at: end,
      });
      showingId.current = null;
      onSaved(result);
    } catch (failure) {
      setError(refusal(failure));
    } finally {
      running.current = false;
      setSaving(false);
    }
  }

  return (
    <form aria-label="Schedule showing" className="mgmt-form" onSubmit={submit}>
      <div className="property-operation-fields">
        <label>
          Prospect
          <select name="prospect" required defaultValue="">
            <option value="" disabled>
              Choose a counterparty
            </option>
            {parties.map((party) => (
              <option key={party.id} value={party.id}>
                {party.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Host
          <select name="host">
            <option value="">No host</option>
            {hosts.map((host) => (
              <option key={host.id} value={host.id}>
                {host.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Starts
          <input type="datetime-local" name="start" required />
        </label>
        <label>
          Ends
          <input type="datetime-local" name="end" required />
        </label>
      </div>
      {!parties.length && (
        <p className="muted">Add a counterparty to schedule a showing.</p>
      )}
      {!timezone && (
        <p className="muted">Set the branch time zone to schedule showings.</p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="mgmt-form-actions">
        <button type="submit" disabled={saving || !timezone || !parties.length}>
          {saving ? "Scheduling…" : "Schedule showing"}
        </button>
      </div>
    </form>
  );
}
