"use client";

import { useEffect, useState } from "react";

import {
  DELEGABLE_PERMISSIONS,
  PERMISSION_LABELS,
  WRITE_REQUIRES,
  withDependencies,
  type DelegablePermission,
  type DelegationGrant,
  type DelegationGrantInput,
  type IncomingDelegation,
  type Member,
} from "../lib/delegation-contracts";
import {
  changeDelegate,
  fetchDelegation,
  fetchDelegations,
  fetchIncomingDelegations,
  fetchMembers,
  ManagementApiError,
  revokeDelegation,
  saveDelegation,
} from "../lib/management-api";

interface Location {
  id: string;
  name: string;
  timezone: string;
}

const STATE_LABELS = {
  scheduled: "Starts later",
  active: "Active",
  expired: "Expired",
  revoked: "Revoked",
} as const;

function message(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

/** A command is kept after an uncertain result, so a retry cannot apply it twice. */
function clientError(err: unknown): boolean {
  return (
    err instanceof ManagementApiError &&
    err.status !== undefined &&
    err.status >= 400 &&
    err.status < 500
  );
}

function localInput(iso: string): string {
  const date = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function instant(local: string): string {
  return new Date(local).toISOString();
}

function when(iso: string): string {
  return new Date(iso).toLocaleString();
}

function locationName(locations: Location[], id: string | null): string {
  if (id === null) return "All locations";
  return locations.find((item) => item.id === id)?.name ?? "One location";
}

export function Delegations({
  businessId,
  locations,
}: {
  businessId: string;
  locations: Location[];
}) {
  return (
    <>
      <OutgoingDelegations businessId={businessId} locations={locations} />
      <IncomingDelegations businessId={businessId} />
    </>
  );
}

interface SaveCommand {
  grantId: string;
  key: string;
  body: DelegationGrantInput;
}

function OutgoingDelegations({
  businessId,
  locations,
}: {
  businessId: string;
  locations: Location[];
}) {
  const [items, setItems] = useState<DelegationGrant[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<DelegationGrant | null>(null);
  const [grantee, setGrantee] = useState("");
  const [purpose, setPurpose] = useState("");
  const [permissions, setPermissions] = useState<DelegablePermission[]>([]);
  const [locationId, setLocationId] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [history, setHistory] = useState<DelegationGrant | null>(null);
  const [pending, setPending] = useState<SaveCommand | null>(null);
  const [revoking, setRevoking] = useState<{
    grantId: string;
    key: string;
    revision: number;
  } | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    fetchDelegations(businessId)
      .then((page) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(message(err, "Unable to load delegations."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reload]);

  function select(grant: DelegationGrant | null) {
    setSelected(grant);
    setGrantee(grant?.grantee_business_id ?? "");
    setPurpose(grant?.purpose ?? "");
    setPermissions(grant ? [...grant.permissions] : []);
    setLocationId(grant?.location_id ?? "");
    setValidFrom(grant ? localInput(grant.valid_from) : "");
    setValidUntil(grant ? localInput(grant.valid_until) : "");
    setHistory(null);
    setConflict(false);
    setConfirmRevoke(false);
    setNotice(null);
    setError(null);
  }

  function remember(grant: DelegationGrant) {
    setItems((current) =>
      [
        ...current.filter((item) => item.grant_id !== grant.grant_id),
        grant,
      ].sort((a, b) => a.grant_id.localeCompare(b.grant_id)),
    );
    select(grant);
  }

  function toggle(permission: DelegablePermission, checked: boolean) {
    setPermissions((current) =>
      withDependencies(
        checked
          ? [...current, permission]
          : current.filter((item) => item !== permission),
      ),
    );
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (busy || conflict || selected?.state === "revoked") return;
    const command = pending ?? {
      grantId: selected?.grant_id ?? crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: {
        schema_version: 1 as const,
        expected_revision: selected?.current_revision ?? 0,
        grantee_business_id: grantee.trim().toLowerCase(),
        purpose: purpose.trim(),
        permissions: withDependencies(permissions),
        location_id: locationId || null,
        valid_from: instant(validFrom),
        valid_until: instant(validUntil),
      },
    };
    setPending(command);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const grant = await saveDelegation(
        businessId,
        command.grantId,
        command.body,
        command.key,
      );
      setPending(null);
      remember(grant);
      setNotice(`Delegation saved. Version ${grant.revision}.`);
    } catch (err: unknown) {
      setError(message(err, "Unable to save this delegation."));
      if (clientError(err)) {
        setPending(null);
        setConflict(
          err instanceof ManagementApiError &&
            err.status === 409 &&
            selected !== null,
        );
      }
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!selected || busy || pending) return;
    if (!confirmRevoke && !revoking) {
      setConfirmRevoke(true);
      return;
    }
    const command = revoking ?? {
      grantId: selected.grant_id,
      key: crypto.randomUUID(),
      revision: selected.current_revision,
    };
    setRevoking(command);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const grant = await revokeDelegation(
        businessId,
        command.grantId,
        command.revision,
        command.key,
      );
      setRevoking(null);
      remember(grant);
      setNotice(
        "Access revoked. The serving business can no longer use this delegation.",
      );
    } catch (err: unknown) {
      setError(message(err, "Unable to revoke this delegation."));
      if (clientError(err)) {
        setRevoking(null);
        setConfirmRevoke(false);
        setConflict(err instanceof ManagementApiError && err.status === 409);
      }
    } finally {
      setBusy(false);
    }
  }

  async function refreshSelected() {
    if (!selected || busy || pending || revoking) return;
    setBusy(true);
    setError(null);
    try {
      remember(await fetchDelegation(businessId, selected.grant_id));
      setNotice("Latest delegation version loaded.");
    } catch (err: unknown) {
      setError(message(err, "Unable to reload this delegation."));
    } finally {
      setBusy(false);
    }
  }

  async function previousVersion() {
    const revision = history?.revision ?? selected?.revision ?? 0;
    if (!selected || revision <= 1 || busy) return;
    setBusy(true);
    setError(null);
    try {
      setHistory(
        await fetchDelegation(businessId, selected.grant_id, revision - 1),
      );
    } catch (err: unknown) {
      setError(message(err, "Unable to load the previous version."));
    } finally {
      setBusy(false);
    }
  }

  async function loadMore() {
    if (!nextCursor || busy) return;
    setBusy(true);
    setError(null);
    try {
      const page = await fetchDelegations(businessId, nextCursor);
      setItems((current) => {
        const merged = new Map(current.map((item) => [item.grant_id, item]));
        page.items.forEach((item) => merged.set(item.grant_id, item));
        return [...merged.values()];
      });
      setNextCursor(page.next_cursor);
    } catch (err: unknown) {
      setError(message(err, "Unable to load more delegations."));
    } finally {
      setBusy(false);
    }
  }

  const uncertain = Boolean(pending) || Boolean(revoking);
  const revoked = selected?.state === "revoked";
  const locked = busy || uncertain || conflict || revoked;
  const complete =
    grantee.trim() !== "" &&
    purpose.trim() !== "" &&
    permissions.length > 0 &&
    validFrom !== "" &&
    validUntil !== "";
  return (
    <section
      aria-label="Delegations to other businesses"
      className="delegations"
    >
      <h2>Access for other businesses</h2>
      <p className="muted">
        Let another business, such as a call centre, work on your bookings. Your
        records stay in your business. Their owner chooses which of their
        employees may act, and every action is recorded here.
      </p>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
          {conflict && (
            <p>
              Your edits are still shown. Reload the latest version before
              changing this delegation again.
            </p>
          )}
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {loading ? (
        <p role="status">Loading delegations…</p>
      ) : (
        <>
          <div className="business-formats">
            <button
              type="button"
              className="secondary"
              disabled={busy || uncertain}
              onClick={() => {
                setLoading(true);
                setReload((value) => value + 1);
              }}
            >
              Reload delegations
            </button>
            <button
              type="button"
              disabled={busy || uncertain}
              onClick={() => select(null)}
            >
              New delegation
            </button>
          </div>
          {items.length === 0 && !error && <p>No delegations yet.</p>}
          <ul className="legal-entity-list">
            {items.map((grant) => (
              <li key={grant.grant_id}>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || uncertain}
                  onClick={() => select(grant)}
                >
                  {grant.purpose} · {STATE_LABELS[grant.effective_state]} ·
                  until {when(grant.valid_until)} · {grant.delegates.length}{" "}
                  designated
                </button>
              </li>
            ))}
          </ul>
          {nextCursor && (
            <button
              type="button"
              className="secondary"
              disabled={busy || uncertain}
              onClick={() => void loadMore()}
            >
              Load more delegations
            </button>
          )}
          <form onSubmit={(event) => void save(event)}>
            <fieldset disabled={locked}>
              <legend>
                {selected ? "Selected delegation" : "New delegation"}
              </legend>
              <label htmlFor="delegation-grantee">Serving business ID</label>
              <input
                id="delegation-grantee"
                value={grantee}
                onChange={(event) => setGrantee(event.target.value)}
                pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                required
                readOnly={selected !== null}
                aria-describedby="delegation-grantee-help"
              />
              <p id="delegation-grantee-help" className="muted">
                Ask the other business for its business ID. It cannot be changed
                later.
              </p>
              <label htmlFor="delegation-purpose">Purpose</label>
              <input
                id="delegation-purpose"
                value={purpose}
                onChange={(event) => setPurpose(event.target.value)}
                maxLength={200}
                required
              />
              <fieldset>
                <legend>Allowed work</legend>
                {DELEGABLE_PERMISSIONS.map((permission) => (
                  <label key={permission} className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={permissions.includes(permission)}
                      disabled={
                        permissions.includes("booking.write") &&
                        WRITE_REQUIRES.includes(permission)
                      }
                      onChange={(event) =>
                        toggle(permission, event.target.checked)
                      }
                    />
                    {PERMISSION_LABELS[permission]}
                  </label>
                ))}
              </fieldset>
              <label htmlFor="delegation-location">Locations</label>
              <select
                id="delegation-location"
                value={locationId}
                onChange={(event) => setLocationId(event.target.value)}
              >
                <option value="">All locations</option>
                {locations.map((location) => (
                  <option key={location.id} value={location.id}>
                    {location.name}
                  </option>
                ))}
              </select>
              <label htmlFor="delegation-from">Starts</label>
              <input
                id="delegation-from"
                type="datetime-local"
                value={validFrom}
                onChange={(event) => setValidFrom(event.target.value)}
                required
              />
              <label htmlFor="delegation-until">Ends</label>
              <input
                id="delegation-until"
                type="datetime-local"
                value={validUntil}
                onChange={(event) => setValidUntil(event.target.value)}
                required
                aria-describedby="delegation-until-help"
              />
              <p id="delegation-until-help" className="muted">
                Times use this device’s time zone. One version can last up to
                366 days; renew it with a new version.
              </p>
            </fieldset>
            {uncertain && !busy && (
              <p>
                The result is uncertain. Retry the same action to confirm it.
              </p>
            )}
            <div className="business-formats">
              {!revoked && (
                <button
                  type="submit"
                  disabled={busy || conflict || revoking !== null || !complete}
                >
                  {busy && pending
                    ? "Saving…"
                    : pending
                      ? "Retry same delegation save"
                      : "Save delegation"}
                </button>
              )}
              {selected && !revoked && (
                <button
                  type="button"
                  className="danger"
                  disabled={busy || pending !== null || conflict}
                  onClick={() => void revoke()}
                >
                  {revoking
                    ? "Retry same revocation"
                    : confirmRevoke
                      ? "Confirm revocation"
                      : "Revoke access"}
                </button>
              )}
              {selected && (
                <>
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy || uncertain}
                    onClick={() => void refreshSelected()}
                  >
                    Reload selected delegation
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    disabled={
                      busy || (history?.revision ?? selected.revision) <= 1
                    }
                    onClick={() => void previousVersion()}
                  >
                    View previous delegation version
                  </button>
                </>
              )}
            </div>
          </form>
          {selected && (
            <div className="hold-note" role="note">
              <p>
                {STATE_LABELS[selected.effective_state]} · version{" "}
                {selected.revision} ·{" "}
                {locationName(locations, selected.location_id)} ·{" "}
                {when(selected.valid_from)} to {when(selected.valid_until)}
              </p>
              <p>
                Designated by the serving business:{" "}
                {selected.delegates.length === 0
                  ? "nobody yet"
                  : selected.delegates
                      .map((item) => `user ${item.user_id}`)
                      .join(", ")}
              </p>
            </div>
          )}
          {history && (
            <p className="hold-note" role="note">
              Previous delegation version {history.revision}: {history.purpose},{" "}
              {history.permissions.map((p) => PERMISSION_LABELS[p]).join(", ")}.
              The saved version has been preserved.
            </p>
          )}
        </>
      )}
    </section>
  );
}

interface DelegateCommand {
  grantId: string;
  membershipId: string;
  designated: boolean;
  key: string;
}

function IncomingDelegations({ businessId }: { businessId: string }) {
  const [items, setItems] = useState<IncomingDelegation[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [choice, setChoice] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<DelegateCommand | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchIncomingDelegations(businessId),
      fetchMembers(businessId),
    ])
      .then(([page, people]) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
        setMembers(people.filter((item) => item.status === "active"));
        setError(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(message(err, "Unable to load delegations you received."));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reload]);

  async function change(command: DelegateCommand) {
    if (busy || (pending && pending !== command)) return;
    setPending(command);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await changeDelegate(
        businessId,
        command.grantId,
        command.membershipId,
        command.designated,
        command.key,
      );
      setItems((current) =>
        current.map((item) =>
          item.grant_id === updated.grant_id ? updated : item,
        ),
      );
      setPending(null);
      setNotice(
        command.designated
          ? "Employee designated. They can now work for this business."
          : "Designation removed. The employee can no longer use this delegation.",
      );
    } catch (err: unknown) {
      setError(message(err, "Unable to change this designation."));
      if (clientError(err)) setPending(null);
    } finally {
      setBusy(false);
    }
  }

  async function loadMore() {
    if (!nextCursor || busy) return;
    setBusy(true);
    try {
      const page = await fetchIncomingDelegations(businessId, nextCursor);
      setItems((current) => [...current, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch (err: unknown) {
      setError(message(err, "Unable to load more delegations."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Delegations received" className="delegations">
      <h2>Work you do for other businesses</h2>
      <p className="muted">
        Other businesses can let yours work on their bookings. Choose which of
        your employees may act for them. Their owner can end this access at any
        time.
      </p>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
        </div>
      )}
      {notice && <p role="status">{notice}</p>}
      {pending && !busy && (
        <p>
          The result is uncertain. Retry the same designation change to confirm
          it.
        </p>
      )}
      {loading ? (
        <p role="status">Loading delegations you received…</p>
      ) : (
        <>
          <button
            type="button"
            className="secondary"
            disabled={busy || Boolean(pending)}
            onClick={() => {
              setLoading(true);
              setReload((value) => value + 1);
            }}
          >
            Reload received delegations
          </button>
          {items.length === 0 && !error && <p>No delegations received.</p>}
          <ul className="delegation-list">
            {items.map((grant) => {
              const usable =
                grant.effective_state === "active" ||
                grant.effective_state === "scheduled";
              const available = members.filter(
                (member) =>
                  !grant.delegates.some(
                    (item) => item.membership_id === member.membership_id,
                  ),
              );
              const selectedMember = choice[grant.grant_id] ?? "";
              return (
                <li key={grant.grant_id}>
                  <h3>{grant.purpose}</h3>
                  <p>
                    {STATE_LABELS[grant.effective_state]} · from business{" "}
                    {grant.grantor_business_id} · until{" "}
                    {when(grant.valid_until)} ·{" "}
                    {grant.location_id === null
                      ? "all locations"
                      : "one location"}
                  </p>
                  <p>
                    Allowed:{" "}
                    {grant.permissions
                      .map((item) => PERMISSION_LABELS[item])
                      .join(", ")}
                  </p>
                  <ul>
                    {grant.delegates.map((delegate) => (
                      <li key={delegate.designation_id}>
                        {delegate.display_name ?? `User ${delegate.user_id}`}{" "}
                        <button
                          type="button"
                          className="secondary"
                          disabled={
                            busy ||
                            (pending !== null &&
                              pending.membershipId !== delegate.membership_id)
                          }
                          onClick={() =>
                            void change(
                              pending?.membershipId === delegate.membership_id
                                ? pending
                                : {
                                    grantId: grant.grant_id,
                                    membershipId: delegate.membership_id,
                                    designated: false,
                                    key: crypto.randomUUID(),
                                  },
                            )
                          }
                        >
                          Remove {delegate.display_name ?? "employee"}
                        </button>
                      </li>
                    ))}
                  </ul>
                  {usable && (
                    <div className="business-formats">
                      <label htmlFor={`delegate-${grant.grant_id}`}>
                        Employee
                      </label>
                      <select
                        id={`delegate-${grant.grant_id}`}
                        value={selectedMember}
                        disabled={busy || Boolean(pending)}
                        onChange={(event) =>
                          setChoice((current) => ({
                            ...current,
                            [grant.grant_id]: event.target.value,
                          }))
                        }
                      >
                        <option value="">Choose an employee</option>
                        {available.map((member) => (
                          <option
                            key={member.membership_id}
                            value={member.membership_id}
                          >
                            {member.display_name ?? member.user_id} (
                            {member.role})
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={
                          busy ||
                          !selectedMember ||
                          (pending !== null &&
                            pending.membershipId !== selectedMember)
                        }
                        onClick={() =>
                          void change(
                            pending?.membershipId === selectedMember
                              ? pending
                              : {
                                  grantId: grant.grant_id,
                                  membershipId: selectedMember,
                                  designated: true,
                                  key: crypto.randomUUID(),
                                },
                          )
                        }
                      >
                        Designate employee
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
          {nextCursor && (
            <button
              type="button"
              className="secondary"
              disabled={busy || Boolean(pending)}
              onClick={() => void loadMore()}
            >
              Load more received delegations
            </button>
          )}
        </>
      )}
    </section>
  );
}
