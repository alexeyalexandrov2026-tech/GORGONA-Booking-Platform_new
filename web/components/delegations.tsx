"use client";

import { useEffect, useState } from "react";

import {
  ACCESS_LEVELS,
  type Delegation,
  type DelegationDecision,
  type DelegationIssue,
} from "../lib/delegation-contracts";
import {
  decideDelegation,
  fetchDelegations,
  fetchMembers,
  issueDelegation,
  ManagementApiError,
  type MemberView,
} from "../lib/management-api";

const MAX_PAGES = 10;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Action = "accept" | "decline" | "revoke" | "delegates";

// Local calendar day `days` from today; the server allows at most 366 days of access.
function dayOffset(days: number): string {
  const day = new Date();
  day.setDate(day.getDate() + days);
  const month = String(day.getMonth() + 1).padStart(2, "0");
  return `${day.getFullYear()}-${month}-${String(day.getDate()).padStart(2, "0")}`;
}

// One command at a time; after an uncertain result the same command is retried.
type Command =
  | { kind: "issue"; grantId: string; key: string; body: DelegationIssue }
  | {
      kind: Action;
      grantId: string;
      key: string;
      body: DelegationDecision;
    };

interface Location {
  id: string;
  name: string;
}

function accessLabel(grant: Delegation): string {
  const permissions = [...grant.permissions].sort().join(",");
  if (permissions === [...ACCESS_LEVELS.manage].sort().join(","))
    return "Manage bookings";
  if (permissions === [...ACCESS_LEVELS.view].sort().join(","))
    return "View bookings";
  return grant.permissions.join(", ");
}

function statusLabel(grant: Delegation): string {
  if (grant.status === "revoked")
    return grant.revoked_by_side === "owner"
      ? "Revoked by the business owner"
      : "Ended by the serving business";
  if (grant.expired) return "Expired";
  return {
    pending: "Waiting for acceptance",
    active: "Active",
    declined: "Declined",
  }[grant.status];
}

const ACTION_DONE: Record<Command["kind"], string> = {
  issue: "Access offered. It starts after the other business accepts.",
  accept: "Access accepted.",
  decline: "Offer declined.",
  revoke: "Access revoked. It stops at the next action.",
  delegates: "Delegates updated.",
};

export function Delegations({
  businessId,
  canIssue,
  canManage,
  locations,
}: {
  businessId: string;
  canIssue: boolean;
  canManage: boolean;
  locations: readonly Location[];
}) {
  const [items, setItems] = useState<Delegation[]>([]);
  const [members, setMembers] = useState<MemberView[]>([]);
  const [complete, setComplete] = useState(true);
  const [choices, setChoices] = useState<Record<string, string[]>>({});
  const [servicer, setServicer] = useState("");
  const [level, setLevel] = useState<"manage" | "view">("manage");
  const [locationId, setLocationId] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [pending, setPending] = useState<Command | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    (async () => {
      const found: Delegation[] = [];
      let after: string | undefined;
      let done = false;
      for (let page = 0; page < MAX_PAGES && !done; page += 1) {
        const result = await fetchDelegations(businessId, after);
        found.push(...result.items);
        done = result.next_cursor === null;
        after = result.next_cursor ?? undefined;
      }
      const people = await fetchMembers(businessId);
      return { found, done, people };
    })()
      .then(({ found, done, people }) => {
        if (!active) return;
        setItems(found);
        setComplete(done);
        // Only company-wide active employees can serve another business.
        setMembers(
          people.filter(
            (person) => person.status === "active" && !person.location_id,
          ),
        );
        setError(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error ? err.message : "Unable to load access.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reload]);

  async function run(command: Command) {
    if (busy) return;
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved =
        command.kind === "issue"
          ? await issueDelegation(
              businessId,
              command.grantId,
              command.body,
              command.key,
            )
          : await decideDelegation(
              businessId,
              command.grantId,
              command.kind,
              command.body,
              command.key,
            );
      setItems((current) => [
        ...current.filter((item) => item.grant_id !== saved.grant_id),
        saved,
      ]);
      setPending(null);
      setMessage(ACTION_DONE[command.kind]);
      if (command.kind === "issue") {
        setServicer("");
        setEndsOn("");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unable to save access.");
      if (
        err instanceof ManagementApiError &&
        err.status &&
        err.status >= 400 &&
        err.status < 500
      ) {
        setPending(null);
        // A stale decision is resolved by reloading the current relationship.
        if (err.status === 409) {
          setChoices({});
          setReload((value) => value + 1);
        }
      }
    } finally {
      setBusy(false);
    }
  }

  function issue(event: React.FormEvent) {
    event.preventDefault();
    if (!canIssue || pending) return;
    const ends = new Date(`${endsOn}T23:59:59`);
    if (!UUID.test(servicer.trim()) || Number.isNaN(ends.getTime())) {
      setError("Enter the serving business ID and the last day of access.");
      return;
    }
    void run({
      kind: "issue",
      grantId: crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: {
        schema_version: 1,
        servicer_business_id: servicer.trim().toLowerCase(),
        permissions: ACCESS_LEVELS[level],
        location_id: locationId || null,
        expires_at: ends.toISOString(),
      },
    });
  }

  function decide(grant: Delegation, kind: Action) {
    if (pending) return;
    const body: DelegationDecision = {
      schema_version: 1,
      expected_revision: grant.revision,
    };
    if (kind === "accept" || kind === "delegates")
      body.delegate_user_ids = choices[grant.grant_id] ?? [];
    void run({
      kind,
      grantId: grant.grant_id,
      key: crypto.randomUUID(),
      body,
    });
  }

  function chosen(grant: Delegation): string[] {
    return (
      choices[grant.grant_id] ??
      grant.delegates.map((delegate) => delegate.user_id)
    );
  }

  function toggle(grant: Delegation, userId: string, checked: boolean) {
    const current = chosen(grant);
    setChoices((all) => ({
      ...all,
      [grant.grant_id]: checked
        ? [...current, userId]
        : current.filter((item) => item !== userId),
    }));
  }

  const locationName = (id: string | null) =>
    id
      ? (locations.find((item) => item.id === id)?.name ?? "One location")
      : "All locations";
  const locked = busy || Boolean(pending);
  const given = items.filter((item) => item.owner_business_id === businessId);
  const received = items.filter(
    (item) => item.servicer_business_id === businessId,
  );

  function delegatePicker(grant: Delegation) {
    return (
      <fieldset disabled={locked}>
        <legend>Employees who may serve {grant.owner_name}</legend>
        {members.length === 0 && (
          <p className="muted">
            No company-wide active employees are available.
          </p>
        )}
        <div className="business-formats">
          {members.map((person) => (
            <label key={person.user_id}>
              <input
                type="checkbox"
                checked={chosen(grant).includes(person.user_id)}
                onChange={(event) =>
                  toggle(grant, person.user_id, event.target.checked)
                }
              />{" "}
              {person.display_name ?? "Unnamed employee"} ({person.role})
            </label>
          ))}
        </div>
      </fieldset>
    );
  }

  function describe(grant: Delegation, other: string) {
    return (
      <>
        <p>
          <strong>{other}</strong> · {statusLabel(grant)}
        </p>
        <p className="muted">
          {accessLabel(grant)} · {locationName(grant.location_id)} · until{" "}
          {new Date(grant.expires_at).toLocaleString()}
          {grant.delegates.length > 0 &&
            ` · Delegates: ${grant.delegates.map((item) => item.display_name).join(", ")}`}
        </p>
      </>
    );
  }

  const open = (grant: Delegation) =>
    (grant.status === "pending" || grant.status === "active") && !grant.expired;

  return (
    <section aria-label="Delegated access" className="delegations">
      <h2>Delegated access</h2>
      <p className="muted">
        Another independent business can work on your bookings only with access
        you offer and it accepts. Each company keeps its own records.
      </p>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {pending && !busy && (
        <div className="business-formats">
          <p>The result is uncertain. Retry the same action to confirm it.</p>
          <button type="button" onClick={() => void run(pending)}>
            Retry same access action
          </button>
        </div>
      )}
      {loading ? (
        <p role="status">Loading access…</p>
      ) : (
        <>
          <button
            type="button"
            className="secondary"
            disabled={locked}
            onClick={() => {
              setLoading(true);
              setChoices({});
              setReload((value) => value + 1);
            }}
          >
            Reload delegated access
          </button>
          {!complete && (
            <p className="muted">
              Only the first {MAX_PAGES} pages of records are shown.
            </p>
          )}
          <h3>Access you offer</h3>
          {given.length === 0 && <p>No access offered.</p>}
          <ul className="delegation-list">
            {given.map((grant) => (
              <li key={grant.grant_id}>
                {describe(
                  grant,
                  grant.servicer_name ??
                    `Business ${grant.servicer_business_id}`,
                )}
                {canManage &&
                  (grant.status === "active" || grant.status === "pending") && (
                    <button
                      type="button"
                      className="secondary"
                      disabled={locked}
                      onClick={() => decide(grant, "revoke")}
                    >
                      Revoke access for {grant.servicer_name ?? "this business"}
                    </button>
                  )}
              </li>
            ))}
          </ul>
          <h3>Access you serve</h3>
          {received.length === 0 && <p>No access received.</p>}
          <ul className="delegation-list">
            {received.map((grant) => (
              <li key={grant.grant_id}>
                {describe(grant, grant.owner_name)}
                {canManage && open(grant) && delegatePicker(grant)}
                {canManage && (
                  <div className="business-formats">
                    {grant.status === "pending" && !grant.expired && (
                      <>
                        <button
                          type="button"
                          disabled={locked || chosen(grant).length === 0}
                          onClick={() => decide(grant, "accept")}
                        >
                          Accept access from {grant.owner_name}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={locked}
                          onClick={() => decide(grant, "decline")}
                        >
                          Decline
                        </button>
                      </>
                    )}
                    {grant.status === "active" && !grant.expired && (
                      <button
                        type="button"
                        disabled={locked || chosen(grant).length === 0}
                        onClick={() => decide(grant, "delegates")}
                      >
                        Save delegates
                      </button>
                    )}
                    {grant.status === "active" && (
                      <button
                        type="button"
                        className="secondary"
                        disabled={locked}
                        onClick={() => decide(grant, "revoke")}
                      >
                        End access for {grant.owner_name}
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
          {canIssue && (
            <form onSubmit={issue}>
              <fieldset disabled={locked}>
                <legend>Offer access to another business</legend>
                <label htmlFor="delegation-servicer">Serving business ID</label>
                <input
                  id="delegation-servicer"
                  value={servicer}
                  onChange={(event) => setServicer(event.target.value)}
                  required
                  aria-describedby="delegation-servicer-help"
                />
                <p id="delegation-servicer-help" className="muted">
                  Ask the other business for its ID. Its name appears after it
                  accepts.
                </p>
                <label htmlFor="delegation-level">Access</label>
                <select
                  id="delegation-level"
                  value={level}
                  onChange={(event) =>
                    setLevel(event.target.value as "manage" | "view")
                  }
                >
                  <option value="manage">Manage bookings</option>
                  <option value="view">View bookings</option>
                </select>
                <label htmlFor="delegation-location">Location</label>
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
                <label htmlFor="delegation-ends">Last day of access</label>
                <input
                  id="delegation-ends"
                  type="date"
                  value={endsOn}
                  onChange={(event) => setEndsOn(event.target.value)}
                  min={dayOffset(1)}
                  max={dayOffset(365)}
                  required
                />
              </fieldset>
              <button type="submit" disabled={locked}>
                Offer access
              </button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
