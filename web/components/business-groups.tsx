"use client";

import { useEffect, useState } from "react";

import type { BusinessGroup } from "../lib/group-contracts";
import {
  changeGroup,
  fetchGroups,
  ManagementApiError,
  type GroupCommand,
} from "../lib/management-api";

const MAX_PAGES = 10;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STATUS: Record<string, string> = {
  invited: "Invited",
  active: "Member",
  declined: "Declined",
  left: "Left the group",
  removed: "Removed",
};
const DONE: Record<GroupCommand["kind"], string> = {
  create: "Group created.",
  invite: "Invitation sent.",
  remove: "Membership ended.",
  accept: "You joined the group.",
  decline: "Invitation declined.",
  leave: "You left the group.",
};

interface Pending {
  groupId: string;
  key: string;
  command: GroupCommand;
}

export function BusinessGroups({
  businessId,
  canManage,
}: {
  businessId: string;
  canManage: boolean;
}) {
  const [items, setItems] = useState<BusinessGroup[]>([]);
  const [complete, setComplete] = useState(true);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [invites, setInvites] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<Pending | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    (async () => {
      const found: BusinessGroup[] = [];
      let after: string | undefined;
      for (let page = 0; page < MAX_PAGES; page += 1) {
        const result = await fetchGroups(businessId, after);
        found.push(...result.items);
        if (!result.next_cursor) return { found, done: true };
        after = result.next_cursor;
      }
      return { found, done: false };
    })()
      .then(({ found, done }) => {
        if (!active) return;
        setItems(found);
        setComplete(done);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error ? err.message : "Unable to load groups.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reload]);

  async function run(next: Pending) {
    if (busy) return;
    setPending(next);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await changeGroup(
        businessId,
        next.groupId,
        next.command,
        next.key,
      );
      setItems((current) => [
        ...current.filter((item) => item.group_id !== saved.group_id),
        saved,
      ]);
      setPending(null);
      setMessage(DONE[next.command.kind]);
      if (next.command.kind === "create") {
        setCode("");
        setName("");
      }
      if (next.command.kind === "invite")
        setInvites((all) => ({ ...all, [next.groupId]: "" }));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unable to save.");
      if (
        err instanceof ManagementApiError &&
        err.status &&
        err.status >= 400 &&
        err.status < 500
      ) {
        setPending(null);
        if (err.status === 409) {
          setInvites({});
          setReload((value) => value + 1);
        }
      }
    } finally {
      setBusy(false);
    }
  }

  function start(groupId: string, command: GroupCommand) {
    if (!pending) void run({ groupId, key: crypto.randomUUID(), command });
  }

  const locked = !canManage || busy || Boolean(pending);
  const own = (group: BusinessGroup) =>
    group.memberships.find((item) => item.member_business_id === businessId);

  return (
    <section aria-label="Company groups" className="business-groups">
      <h2>Company groups</h2>
      <p className="muted">
        A group records which independent businesses belong together. It does
        not give any business access to another one’s records.
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
            Retry same group action
          </button>
        </div>
      )}
      {loading ? (
        <p role="status">Loading groups…</p>
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
            Reload groups
          </button>
          {!complete && (
            <p className="muted">
              Only the first {MAX_PAGES} pages of groups are shown.
            </p>
          )}
          {items.length === 0 && !error && <p>No groups yet.</p>}
          <ul className="delegation-list">
            {[...items]
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((group) => {
                const mine = own(group);
                return (
                  <li key={group.group_id}>
                    <p>
                      <strong>{group.name}</strong> · {group.code} ·{" "}
                      {group.role === "organizer"
                        ? "Organized by this business"
                        : `Organized by ${group.organizer_name}`}
                    </p>
                    {group.role === "organizer" ? (
                      <>
                        <ul>
                          {group.memberships.map((item) => (
                            <li key={item.membership_id}>
                              {item.member_name ??
                                `Business ${item.member_business_id}`}{" "}
                              · {STATUS[item.status]}{" "}
                              {canManage &&
                                (item.status === "invited" ||
                                  item.status === "active") && (
                                  <button
                                    type="button"
                                    className="secondary"
                                    disabled={locked}
                                    onClick={() =>
                                      start(group.group_id, {
                                        kind: "remove",
                                        member: item.member_business_id,
                                        revision: item.revision,
                                      })
                                    }
                                  >
                                    End membership of{" "}
                                    {item.member_name ?? "this business"}
                                  </button>
                                )}
                            </li>
                          ))}
                        </ul>
                        {canManage && (
                          <form
                            onSubmit={(event) => {
                              event.preventDefault();
                              const member = (
                                invites[group.group_id] ?? ""
                              ).trim();
                              if (!UUID.test(member)) {
                                setError("Enter the other business's ID.");
                                return;
                              }
                              start(group.group_id, {
                                kind: "invite",
                                member: member.toLowerCase(),
                              });
                            }}
                          >
                            <label htmlFor={`invite-${group.group_id}`}>
                              Invite business by ID to {group.name}
                            </label>
                            <input
                              id={`invite-${group.group_id}`}
                              value={invites[group.group_id] ?? ""}
                              disabled={locked}
                              onChange={(event) =>
                                setInvites((all) => ({
                                  ...all,
                                  [group.group_id]: event.target.value,
                                }))
                              }
                            />
                            <button type="submit" disabled={locked}>
                              Send invitation
                            </button>
                          </form>
                        )}
                      </>
                    ) : (
                      mine && (
                        <div className="business-formats">
                          <p>{STATUS[mine.status]}</p>
                          {canManage && mine.status === "invited" && (
                            <>
                              <button
                                type="button"
                                disabled={locked}
                                onClick={() =>
                                  start(group.group_id, {
                                    kind: "accept",
                                    revision: mine.revision,
                                  })
                                }
                              >
                                Join {group.name}
                              </button>
                              <button
                                type="button"
                                className="secondary"
                                disabled={locked}
                                onClick={() =>
                                  start(group.group_id, {
                                    kind: "decline",
                                    revision: mine.revision,
                                  })
                                }
                              >
                                Decline invitation
                              </button>
                            </>
                          )}
                          {canManage && mine.status === "active" && (
                            <button
                              type="button"
                              className="secondary"
                              disabled={locked}
                              onClick={() =>
                                start(group.group_id, {
                                  kind: "leave",
                                  revision: mine.revision,
                                })
                              }
                            >
                              Leave {group.name}
                            </button>
                          )}
                        </div>
                      )
                    )}
                  </li>
                );
              })}
          </ul>
          {canManage && (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                start(crypto.randomUUID(), {
                  kind: "create",
                  code,
                  name: name.trim(),
                });
              }}
            >
              <fieldset disabled={locked}>
                <legend>New group</legend>
                <label htmlFor="group-code">Internal reference</label>
                <input
                  id="group-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  pattern="[A-Z0-9][A-Z0-9_-]*"
                  maxLength={64}
                  required
                />
                <label htmlFor="group-name">Group name</label>
                <input
                  id="group-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  required
                />
              </fieldset>
              <button type="submit" disabled={locked}>
                Create group
              </button>
            </form>
          )}
        </>
      )}
    </section>
  );
}
