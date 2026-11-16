"use client";

// PROPERTY-01 (catalog screen): the internal parcel, building and unit catalog. Every member who
// may read sees the catalog fields of the branches they serve; only company-wide owners and
// managers see the private owner and manager history and the edit controls. A save keeps its
// object id and Idempotency-Key until it succeeds (ADR-0030); a stale revision is never retried
// silently, the member reloads the property and applies the change again.
import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { PropertyLease } from "./property-lease";
import { PropertyOperations } from "./property-operations";
import { businessDateTime } from "../lib/business-time";
import { fetchCounterparties } from "../lib/counterparty-api";
import {
  fetchMembers,
  fetchWorkspace,
  type LocationItem,
} from "../lib/management-api";
import {
  fetchHistory,
  fetchProperties,
  fetchProperty,
  refusal,
  saveProperty,
  staleRevision,
} from "../lib/property-api";
import {
  KEEP_PARTY,
  NO_PARTY,
  PROPERTY_KINDS,
  parentOptions,
  propertyBody,
  type PropertyKind,
  type PropertyRevision,
  type PropertyView,
} from "../lib/property-contracts";

type Named = { id: string; name: string };

const KIND_LABEL: Record<PropertyKind, string> = {
  parcel: "Parcel",
  building: "Building",
  unit: "Unit",
};

async function allCounterparties(businessId: string): Promise<Named[]> {
  const found: Named[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchCounterparties(businessId, "", "active", after);
    for (const c of page.items)
      found.push({ id: c.counterparty_id, name: c.display_name });
    if (!page.next_cursor) return found;
    after = page.next_cursor;
  }
}

function replace(list: PropertyView[], item: PropertyView): PropertyView[] {
  const view: PropertyView = {
    schema_version: 1,
    object_id: item.object_id,
    location_id: item.location_id,
    kind: item.kind,
    name: item.name,
    parent_id: item.parent_id,
    revision: item.revision,
    recorded_at: item.recorded_at,
  };
  return list.some((x) => x.object_id === item.object_id)
    ? list.map((x) => (x.object_id === item.object_id ? view : x))
    : [...list, view];
}

function when(instant: string, zone: string | undefined) {
  if (!zone) return instant;
  try {
    const local = businessDateTime(instant, zone);
    return `${local.date} ${local.time}`;
  } catch {
    return instant;
  }
}

export function PropertyScreen({
  businessId,
  canManage,
}: {
  businessId: string;
  canManage: boolean;
}) {
  const [items, setItems] = useState<PropertyView[]>([]);
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [parties, setParties] = useState<Named[]>([]);
  const [members, setMembers] = useState<Named[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchProperties(businessId),
      fetchWorkspace(businessId).then((w) => w.locations),
      // Names only make history readable; the catalog still works without them.
      canManage
        ? allCounterparties(businessId).catch(() => [] as Named[])
        : Promise.resolve([] as Named[]),
      canManage
        ? fetchMembers(businessId)
            .then((list) =>
              list.map((m) => ({
                id: m.user_id,
                name: m.display_name ?? "Member",
              })),
            )
            .catch(() => [] as Named[])
        : Promise.resolve([] as Named[]),
    ])
      .then(([objects, places, people, staff]) => {
        if (!live) return;
        setItems(objects);
        setLocations(places);
        setParties(people);
        setMembers(staff);
        setError(null);
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(
            `The property catalog could not be read: ${refusal(failure)}`,
          );
      });
    return () => {
      live = false;
    };
  }, [businessId, canManage, attempt]);

  const branch = (id: string) => locations.find((l) => l.id === id);
  const branchName = (id: string) => branch(id)?.name ?? "Unknown branch";
  const objectName = (id: string | null) =>
    id === null
      ? "None"
      : (items.find((x) => x.object_id === id)?.name ?? "Unknown property");
  const partyName = (id: string | null) =>
    id === null
      ? "None"
      : (parties.find((p) => p.id === id)?.name ?? "Unknown counterparty");
  const memberName = (id: string) =>
    members.find((m) => m.id === id)?.name ?? "Member";

  return (
    <div className="property-screen">
      <h1>Property</h1>
      <p className="muted">
        Parcels, buildings and units of each branch, with every saved revision.
      </p>
      <p className="property-status" role="status">
        {notice}
      </p>
      {!loaded && !error && (
        <p className="muted" role="status">
          Loading the property catalog…
        </p>
      )}
      {error && (
        <div className="property-error">
          <p className="error" role="alert">
            {error}
          </p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setAttempt((n) => n + 1);
            }}
          >
            Try again
          </button>
        </div>
      )}
      {loaded && (
        <>
          <CatalogSection
            items={items}
            branchName={branchName}
            objectName={objectName}
            onOpen={setOpenId}
          />
          {openId && (
            <PropertyDetail
              key={openId}
              businessId={businessId}
              objectId={openId}
              canManage={canManage}
              items={items}
              parties={parties}
              zone={(id) => branch(id)?.timezone}
              branchName={branchName}
              objectName={objectName}
              partyName={partyName}
              memberName={memberName}
              onChanged={(saved) => {
                setItems((list) => replace(list, saved));
                setNotice(
                  `Property ${saved.name} saved as revision ${saved.revision}.`,
                );
              }}
              onClose={() => setOpenId(null)}
            />
          )}
          {canManage && (
            <PropertyForm
              key="new"
              businessId={businessId}
              editing={null}
              items={items}
              locations={locations}
              parties={parties}
              partyName={partyName}
              onSaved={(saved) => {
                setItems((list) => replace(list, saved));
                setNotice(
                  `Property ${saved.name} saved as revision ${saved.revision}.`,
                );
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

function CatalogSection({
  items,
  branchName,
  objectName,
  onOpen,
}: {
  items: PropertyView[];
  branchName: (id: string) => string;
  objectName: (id: string | null) => string;
  onOpen: (id: string) => void;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <h2 id={headingId}>Catalog</h2>
      {items.length === 0 ? (
        <p className="muted">No properties yet.</p>
      ) : (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Property catalog table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Property catalog">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Type</th>
                <th scope="col">Branch</th>
                <th scope="col">Part of</th>
                <th scope="col">Revision</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.object_id}>
                  <th scope="row">
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => onOpen(item.object_id)}
                    >
                      {item.name}
                    </button>
                  </th>
                  <td>{KIND_LABEL[item.kind]}</td>
                  <td>{branchName(item.location_id)}</td>
                  <td>{objectName(item.parent_id)}</td>
                  <td>{item.revision}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function PropertyDetail({
  businessId,
  objectId,
  canManage,
  items,
  parties,
  zone,
  branchName,
  objectName,
  partyName,
  memberName,
  onChanged,
  onClose,
}: {
  businessId: string;
  objectId: string;
  canManage: boolean;
  items: PropertyView[];
  parties: Named[];
  zone: (location: string) => string | undefined;
  branchName: (id: string) => string;
  objectName: (id: string | null) => string;
  partyName: (id: string | null) => string;
  memberName: (id: string) => string;
  onChanged: (saved: PropertyRevision) => void;
  onClose: () => void;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const historyId = useId();
  const [view, setView] = useState<PropertyView | null>(null);
  const [history, setHistory] = useState<PropertyRevision[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reads, setReads] = useState(0);

  const load = useCallback(async () => {
    const [current, revisions] = await Promise.all([
      fetchProperty(businessId, objectId),
      canManage
        ? fetchHistory(businessId, objectId)
        : Promise.resolve([] as PropertyRevision[]),
    ]);
    return { current, revisions };
  }, [businessId, objectId, canManage]);

  useEffect(() => {
    let live = true;
    load()
      .then(({ current, revisions }) => {
        if (!live) return;
        setError(null);
        setView(current);
        setHistory(revisions);
        // Keyboard and screen reader users land on what they opened.
        requestAnimationFrame(() => headingRef.current?.focus());
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`The property could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [load, reads]);

  const latest = history.at(-1);
  return (
    <section aria-labelledby={headingId} className="property-detail">
      <h2 id={headingId} ref={headingRef} tabIndex={-1}>
        {view ? `Property ${view.name}` : "Property"}
      </h2>
      {!view && !error && (
        <p className="muted" role="status">
          Loading the property…
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {view && (
        <>
          <dl className="property-facts">
            <div>
              <dt>Type</dt>
              <dd>{KIND_LABEL[view.kind]}</dd>
            </div>
            <div>
              <dt>Branch</dt>
              <dd>{branchName(view.location_id)}</dd>
            </div>
            <div>
              <dt>Part of</dt>
              <dd>{objectName(view.parent_id)}</dd>
            </div>
            <div>
              <dt>Revision</dt>
              <dd>{view.revision}</dd>
            </div>
            <div>
              <dt>Recorded</dt>
              <dd>{when(view.recorded_at, zone(view.location_id))}</dd>
            </div>
            {canManage && latest && (
              <>
                <div>
                  <dt>Owner</dt>
                  <dd>{partyName(latest.owner_id)}</dd>
                </div>
                <div>
                  <dt>Manager</dt>
                  <dd>{partyName(latest.manager_id)}</dd>
                </div>
              </>
            )}
          </dl>
          {canManage && (
            <>
              <h3 id={historyId}>History</h3>
              <div
                className="mgmt-table-container"
                role="region"
                aria-label="Property history table"
                tabIndex={0}
              >
                <table className="mgmt-table" aria-labelledby={historyId}>
                  <thead>
                    <tr>
                      <th scope="col">Revision</th>
                      <th scope="col">Name</th>
                      <th scope="col">Part of</th>
                      <th scope="col">Owner</th>
                      <th scope="col">Manager</th>
                      <th scope="col">Recorded by</th>
                      <th scope="col">Recorded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...history].reverse().map((r) => (
                      <tr key={r.revision}>
                        <th scope="row">{r.revision}</th>
                        <td>{r.name}</td>
                        <td>{objectName(r.parent_id)}</td>
                        <td>{partyName(r.owner_id)}</td>
                        <td>{partyName(r.manager_id)}</td>
                        <td>{memberName(r.recorded_by)}</td>
                        <td>{when(r.recorded_at, zone(r.location_id))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <PropertyForm
                key={`${view.object_id}:${view.revision}`}
                businessId={businessId}
                editing={view}
                items={items}
                locations={[]}
                parties={parties}
                partyName={partyName}
                current={latest}
                onSaved={(saved) => {
                  onChanged(saved);
                  setReads((n) => n + 1);
                }}
                onReload={() => setReads((n) => n + 1)}
              />
            </>
          )}
          {canManage && view.kind === "unit" && (
            <PropertyLease
              businessId={businessId}
              objectId={view.object_id}
              parties={parties}
              timezone={zone(view.location_id)}
            />
          )}
        </>
      )}
      {view && (
        <PropertyOperations
          businessId={businessId}
          property={view}
          canManage={canManage}
          parties={parties}
          timezone={zone(view.location_id)}
        />
      )}
      <div className="mgmt-form-actions">
        <button type="button" className="secondary" onClick={onClose}>
          Close property
        </button>
      </div>
    </section>
  );
}

function PropertyForm({
  businessId,
  editing,
  items,
  locations,
  parties,
  partyName,
  current,
  onSaved,
  onReload,
}: {
  businessId: string;
  editing: PropertyView | null;
  items: PropertyView[];
  locations: LocationItem[];
  parties: Named[];
  partyName: (id: string | null) => string;
  current?: PropertyRevision;
  onSaved: (saved: PropertyRevision) => void;
  onReload?: () => void;
}) {
  const headingId = useId();
  // A new object keeps its id until the save succeeds, so a retry saves it once.
  const [objectId, setObjectId] = useState(
    () => editing?.object_id ?? crypto.randomUUID(),
  );
  const [location, setLocation] = useState(editing?.location_id ?? "");
  const [kind, setKind] = useState<PropertyKind>(editing?.kind ?? "parcel");
  const [name, setName] = useState(editing?.name ?? "");
  const [parent, setParent] = useState(editing?.parent_id ?? "");
  const fresh = editing ? KEEP_PARTY : NO_PARTY;
  const [owner, setOwner] = useState(fresh);
  const [manager, setManager] = useState(fresh);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const parents = parentOptions(items, kind, location, editing?.object_id);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setStale(false);
    setBusy(true);
    try {
      const saved = await saveProperty(
        businessId,
        objectId,
        propertyBody({
          expectedRevision: editing?.revision ?? 0,
          locationId: location,
          kind,
          name,
          parentId: parent,
          owner,
          manager,
        }),
      );
      onSaved(saved);
      if (!editing) {
        setObjectId(crypto.randomUUID());
        setName("");
        setParent("");
        setOwner(NO_PARTY);
        setManager(NO_PARTY);
      }
    } catch (failure) {
      const revision = staleRevision(failure);
      if (revision !== undefined) {
        setStale(true);
        setError(
          `This property was saved by someone else after you opened it${
            revision ? ` (now revision ${revision})` : ""
          }. Reload it, then make your change again.`,
        );
      } else setError(`The property was not saved: ${refusal(failure)}`);
    } finally {
      setBusy(false);
    }
  }

  const label = editing ? `Edit property ${editing.name}` : "New property";
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId}>{label}</h3>
      <form aria-label={label} onSubmit={submit}>
        {editing ? (
          <p className="muted">
            {KIND_LABEL[editing.kind]}. The type and branch are fixed.
          </p>
        ) : (
          <>
            <label>
              Branch
              <select
                aria-label="Branch"
                value={location}
                onChange={(e) => {
                  setLocation(e.target.value);
                  setParent("");
                }}
                required
              >
                <option value="">Choose</option>
                {locations.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Type
              <select
                aria-label="Type"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as PropertyKind);
                  setParent("");
                }}
              >
                {PROPERTY_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABEL[k]}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <label>
          Name
          <input
            value={name}
            maxLength={200}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        {kind !== "parcel" && (
          <label>
            {kind === "unit" ? "Building" : "Parcel"}
            <select
              aria-label={kind === "unit" ? "Building" : "Parcel"}
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              required={kind === "unit"}
            >
              <option value="">
                {kind === "unit" ? "Choose" : "No parcel"}
              </option>
              {parents.map((p) => (
                <option key={p.object_id} value={p.object_id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <PartySelect
          label="Owner"
          value={owner}
          onChange={setOwner}
          parties={parties}
          current={editing ? partyName(current?.owner_id ?? null) : null}
        />
        <PartySelect
          label="Manager"
          value={manager}
          onChange={setManager}
          parties={parties}
          current={editing ? partyName(current?.manager_id ?? null) : null}
        />
        <div className="mgmt-form-actions">
          <button type="submit" disabled={busy}>
            {editing ? "Save changes" : "Save property"}
          </button>
          {stale && onReload && (
            <button type="button" className="secondary" onClick={onReload}>
              Reload property
            </button>
          )}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

function PartySelect({
  label,
  value,
  onChange,
  parties,
  current,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  parties: Named[];
  /** The stored party's name when editing; null for a new object. */
  current: string | null;
}) {
  return (
    <label>
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {current !== null && (
          <option value={KEEP_PARTY}>{`Keep current (${current})`}</option>
        )}
        <option value={NO_PARTY}>{`No ${label.toLowerCase()}`}</option>
        {parties.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </label>
  );
}
