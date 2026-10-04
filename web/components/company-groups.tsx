"use client";

import { useCallback, useEffect, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import {
  fetchGroups,
  fetchGroup,
  saveGroup,
  fetchGroupInvitations,
  inviteToGroup,
  confirmGroupConsent,
  withdrawGroupInvitation,
  fetchGroupReport,
} from "../lib/group-api";
import type {
  CompanyGroup,
  GroupInvitation,
  GroupInput,
  ConsentInput,
  GroupReport,
} from "../lib/group-contracts";

type Command = { key: string } & (
  | { kind: "group"; id: string; body: GroupInput }
  | { kind: "invite"; id: string; group: string; participant: string }
  | { kind: "consent"; id: string; body: ConsentInput }
  | { kind: "withdraw"; id: string; group: string; body: ConsentInput }
);

export function CompanyGroups({ businessId }: { businessId: string }) {
  const [groups, setGroups] = useState<CompanyGroup[]>([]);
  const [groupCursor, setGroupCursor] = useState<string | null>(null);
  const [incoming, setIncoming] = useState<GroupInvitation[]>([]);
  const [incomingCursor, setIncomingCursor] = useState<string | null>(null);
  const [outgoing, setOutgoing] = useState<GroupInvitation[]>([]);
  const [outgoingCursor, setOutgoingCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<CompanyGroup | null>(null);
  const [history, setHistory] = useState<CompanyGroup | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [participant, setParticipant] = useState("");
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const [report, setReport] = useState<GroupReport | null>(null);
  const [reportAfter, setReportAfter] = useState<string | undefined>();
  const [pending, setPending] = useState<Command | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [page, received] = await Promise.all([
      fetchGroups(businessId),
      fetchGroupInvitations(businessId),
    ]);
    setGroups(page.items);
    setGroupCursor(page.next_cursor);
    setIncoming(received.items);
    setIncomingCursor(received.next_cursor);
  }, [businessId]);
  useEffect(() => {
    let active = true;
    // Do not keep another company's records after a business switch.
    void Promise.all([
      fetchGroups(businessId),
      fetchGroupInvitations(businessId),
    ])
      .then(([page, received]) => {
        if (!active) return;
        setGroups(page.items);
        setGroupCursor(page.next_cursor);
        setIncoming(received.items);
        setIncomingCursor(received.next_cursor);
      })
      .catch((e: unknown) => {
        if (active)
          setError(
            e instanceof Error ? e.message : "Unable to load company groups.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  async function select(group: CompanyGroup | null) {
    setSelected(group);
    setCode(group?.code ?? "");
    setName(group?.name ?? "");
    setHistory(null);
    setReport(null);
    setReportAfter(undefined);
    setOutgoing([]);
    setOutgoingCursor(null);
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      if (group) {
        const page = await fetchGroupInvitations(businessId, group.group_id);
        setOutgoing(page.items);
        setOutgoingCursor(page.next_cursor);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unable to load participants.");
    } finally {
      setBusy(false);
    }
  }
  async function execute(command: Command) {
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    setReport(null);
    try {
      if (command.kind === "group") {
        const saved = await saveGroup(
          businessId,
          command.id,
          command.body,
          command.key,
        );
        setSelected(saved);
        setCode(saved.code);
        setName(saved.name);
        setHistory(null);
      } else if (command.kind === "invite") {
        await inviteToGroup(
          businessId,
          command.group,
          command.id,
          command.participant,
          command.key,
        );
        setParticipant("");
      } else if (command.kind === "consent") {
        await confirmGroupConsent(
          businessId,
          command.id,
          command.body,
          command.key,
        );
      } else {
        await withdrawGroupInvitation(
          businessId,
          command.group,
          command.id,
          command.body,
          command.key,
        );
      }
      // A receipt may describe an older accepted version; always refresh the current relationship.
      setPending(null);
      setMessage("Company group change saved.");
      await load();
      const groupId =
        command.kind === "group" ? command.id : selected?.group_id;
      if (groupId) {
        const page = await fetchGroupInvitations(businessId, groupId);
        setOutgoing(page.items);
        setOutgoingCursor(page.next_cursor);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unable to save this change.");
      if (
        e instanceof ManagementApiError &&
        [403, 404, 409, 422].includes(e.status ?? 0)
      ) {
        setPending(null);
        if (e.status === 409) setConflict(true);
      }
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      await load();
      if (selected)
        await select(await fetchGroup(businessId, selected.group_id));
      setConflict(false);
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Unable to refresh company groups.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function showReport(after?: string) {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const data = await fetchGroupReport(
        businessId,
        selected.group_id,
        new Date(from).toISOString(),
        new Date(until).toISOString(),
        after,
      );
      setReport(data);
      setReportAfter(after);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Unable to read this report.");
    } finally {
      setBusy(false);
    }
  }
  async function more(which: "groups" | "incoming" | "outgoing") {
    setBusy(true);
    setError(null);
    try {
      if (which === "groups" && groupCursor) {
        const p = await fetchGroups(businessId, groupCursor);
        setGroups((current) => [
          ...current,
          ...p.items.filter(
            (i) => !current.some((c) => c.group_id === i.group_id),
          ),
        ]);
        setGroupCursor(p.next_cursor);
      } else if (which === "incoming" && incomingCursor) {
        const p = await fetchGroupInvitations(
          businessId,
          undefined,
          incomingCursor,
        );
        setIncoming((current) => [
          ...current,
          ...p.items.filter(
            (i) => !current.some((c) => c.invitation_id === i.invitation_id),
          ),
        ]);
        setIncomingCursor(p.next_cursor);
      } else if (which === "outgoing" && outgoingCursor && selected) {
        const p = await fetchGroupInvitations(
          businessId,
          selected.group_id,
          outgoingCursor,
        );
        setOutgoing((current) => [
          ...current,
          ...p.items.filter(
            (i) => !current.some((c) => c.invitation_id === i.invitation_id),
          ),
        ]);
        setOutgoingCursor(p.next_cursor);
      }
    } catch (e: unknown) {
      setError(
        e instanceof Error ? e.message : "Unable to load the next page.",
      );
    } finally {
      setBusy(false);
    }
  }
  const locked = busy || !!pending || conflict;
  return (
    <section aria-label="Company groups" className="legal-entities">
      <h2>Company groups</h2>
      <p className="muted">
        Each company keeps its own records. Its owner must accept an invitation.
        Participation gives no access to its data; a separate report permission
        and employee designation are required.
      </p>
      {loading ? (
        <p role="status">Loading company groups…</p>
      ) : (
        <>
          {error && <p role="alert">{error}</p>}
          {message && <p role="status">{message}</p>}
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={busy || !!pending}
          >
            Reload company groups
          </button>
          {pending && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void execute(pending)}
            >
              Retry same group change
            </button>
          )}
          {conflict && (
            <p>
              Another change was saved. Reload the current version before making
              another change.
            </p>
          )}
          <ul className="legal-entity-list">
            {groups.map((g) => (
              <li key={g.group_id}>
                <button
                  type="button"
                  disabled={locked}
                  onClick={() => void select(g)}
                >
                  {g.code} · {g.name} · version {g.revision}
                </button>
              </li>
            ))}
          </ul>
          {groupCursor && (
            <button
              type="button"
              disabled={locked}
              onClick={() => void more("groups")}
            >
              More groups
            </button>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!locked)
                void execute({
                  kind: "group",
                  id: selected?.group_id ?? crypto.randomUUID(),
                  key: crypto.randomUUID(),
                  body: {
                    schema_version: 1,
                    expected_revision: selected?.revision ?? 0,
                    code,
                    name: name.trim(),
                  },
                });
            }}
          >
            <fieldset disabled={locked}>
              <legend>
                {selected ? "Selected company group" : "New company group"}
              </legend>
              <label htmlFor="group-code">Group internal reference</label>
              <input
                id="group-code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                pattern="[A-Z0-9][A-Z0-9_-]*"
                maxLength={64}
                required
                readOnly={!!selected}
              />
              <label htmlFor="group-name">Group name</label>
              <input
                id="group-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
                required
              />
              <button type="submit">Save company group</button>
              <button type="button" onClick={() => void select(null)}>
                New group
              </button>
            </fieldset>
          </form>
          {selected && (
            <>
              {selected.revision > 1 && (
                <button
                  type="button"
                  disabled={locked}
                  onClick={() => {
                    setBusy(true);
                    void fetchGroup(
                      businessId,
                      selected.group_id,
                      selected.revision - 1,
                    )
                      .then(setHistory)
                      .catch((e: unknown) =>
                        setError(
                          e instanceof Error
                            ? e.message
                            : "Unable to read history.",
                        ),
                      )
                      .finally(() => setBusy(false));
                  }}
                >
                  Previous group version
                </button>
              )}
              {history && (
                <p role="note">
                  Saved version {history.revision}: {history.name}
                </p>
              )}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!locked)
                    void execute({
                      kind: "invite",
                      group: selected.group_id,
                      id: crypto.randomUUID(),
                      participant,
                      key: crypto.randomUUID(),
                    });
                }}
              >
                <fieldset disabled={locked}>
                  <legend>Invite an independent company</legend>
                  <label htmlFor="group-participant">
                    Participant business ID
                  </label>
                  <input
                    id="group-participant"
                    value={participant}
                    onChange={(e) => setParticipant(e.target.value)}
                    pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                    required
                  />
                  <button type="submit">Send group invitation</button>
                </fieldset>
              </form>
              <h3>Invited companies</h3>
              {!outgoing.length && <p>No invitations for this group.</p>}
              <ul className="legal-entity-list">
                {outgoing.map((i) => (
                  <li key={i.invitation_id}>
                    <p>
                      Business {i.participant_business_id} · invitation{" "}
                      {i.state} · consent {i.consent_state ?? "pending"}
                    </p>
                    {i.state === "active" && (
                      <button
                        type="button"
                        disabled={locked}
                        onClick={() =>
                          void execute({
                            kind: "withdraw",
                            group: i.group_id,
                            id: i.invitation_id,
                            key: crypto.randomUUID(),
                            body: {
                              schema_version: 1,
                              expected_revision: i.revision,
                              state: "withdrawn",
                            },
                          })
                        }
                      >
                        Withdraw invitation
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {outgoingCursor && (
                <button
                  type="button"
                  disabled={locked}
                  onClick={() => void more("outgoing")}
                >
                  More invited companies
                </button>
              )}
              <h3>Booking counts</h3>
              <p className="muted">
                Live counts by company and branch. These are not payments or
                revenue. Legal entities are unassigned in existing bookings.
                Times use your device time zone; the start is included and the
                end is excluded. Choose at most 366 days.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void showReport();
                }}
              >
                <fieldset disabled={locked}>
                  <legend>Report period</legend>
                  <label htmlFor="group-report-from">Report starts</label>
                  <input
                    id="group-report-from"
                    type="datetime-local"
                    required
                    value={from}
                    onChange={(e) => {
                      setFrom(e.target.value);
                      setReport(null);
                    }}
                  />
                  <label htmlFor="group-report-until">Report ends</label>
                  <input
                    id="group-report-until"
                    type="datetime-local"
                    required
                    value={until}
                    onChange={(e) => {
                      setUntil(e.target.value);
                      setReport(null);
                    }}
                  />
                  <button type="submit">Read booking counts</button>
                </fieldset>
              </form>
              {report && (
                <div aria-label="Group booking report">
                  <p>
                    {report.sources.length} companies permitted on this page.{" "}
                    {report.excluded_business_ids.length} accepted companies
                    excluded because current report access could not be
                    confirmed.
                  </p>
                  <ul>
                    {report.sources.map((s) => (
                      <li key={s.owner_business_id}>
                        Business {s.owner_business_id} ·{" "}
                        {s.location_id
                          ? `branch ${s.location_id} only`
                          : "all branches"}{" "}
                        · grant version {s.grant_revision}
                      </li>
                    ))}
                  </ul>
                  {!report.items.length && (
                    <p>No permitted bookings in this period.</p>
                  )}
                  <ul>
                    {report.items.map((r) => (
                      <li
                        key={`${r.owner_business_id}:${r.location_id}:${r.status}`}
                      >
                        Business {r.owner_business_id} · branch {r.location_id}{" "}
                        · legal entity unassigned · {r.status}:{" "}
                        {r.booking_count}
                      </li>
                    ))}
                  </ul>
                  {reportAfter && (
                    <button
                      type="button"
                      disabled={locked}
                      onClick={() => void showReport()}
                    >
                      First report page
                    </button>
                  )}
                  {report.next_cursor && (
                    <button
                      type="button"
                      disabled={locked}
                      onClick={() => void showReport(report.next_cursor!)}
                    >
                      Next report page
                    </button>
                  )}
                </div>
              )}
            </>
          )}
          <h3>Invitations received by your company</h3>
          {!incoming.length && <p>No group invitations received.</p>}
          <ul className="legal-entity-list">
            {incoming.map((i) => (
              <li key={i.invitation_id}>
                <p>
                  {i.group_name} · operator {i.operator_business_id} ·
                  invitation {i.state} · consent {i.consent_state ?? "pending"}
                </p>
                {i.state === "active" && i.consent_state === null && (
                  <button
                    type="button"
                    disabled={locked}
                    onClick={() =>
                      void execute({
                        kind: "consent",
                        id: i.invitation_id,
                        key: crypto.randomUUID(),
                        body: {
                          schema_version: 1,
                          expected_revision: 0,
                          state: "accepted",
                        },
                      })
                    }
                  >
                    Accept group membership
                  </button>
                )}
                {i.consent_state === "accepted" && (
                  <button
                    type="button"
                    disabled={locked}
                    onClick={() =>
                      void execute({
                        kind: "consent",
                        id: i.invitation_id,
                        key: crypto.randomUUID(),
                        body: {
                          schema_version: 1,
                          expected_revision: i.consent_revision,
                          state: "withdrawn",
                        },
                      })
                    }
                  >
                    Withdraw group consent
                  </button>
                )}
              </li>
            ))}
          </ul>
          {incomingCursor && (
            <button
              type="button"
              disabled={locked}
              onClick={() => void more("incoming")}
            >
              More received invitations
            </button>
          )}
        </>
      )}
    </section>
  );
}
