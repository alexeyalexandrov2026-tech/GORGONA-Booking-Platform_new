"use client";

// PROPERTY-01 (5c UI): maintenance requests, approvals, contractor company binding,
// contractor updates and separate FIN-03 obligation links for one property object.
// Branch managers read the list only; company-wide owners and managers manage lifecycle.
import Link from "next/link";
import React, { useEffect, useId, useRef, useState } from "react";
import { businessDateTime } from "../lib/business-time";
import type { Delegation } from "../lib/delegation-contracts";
import { fetchDelegations } from "../lib/management-api";
import {
  contractorWorkHref,
  createMaintenanceRequest,
  fetchContractorCompany,
  fetchContractorUpdates,
  fetchMaintenanceEvents,
  fetchMaintenanceObligations,
  fetchMaintenanceRequests,
  maintenanceConflict,
  recordMaintenanceEvent,
  refusal,
  saveContractorCompany,
} from "../lib/property-api";
import {
  MAINTENANCE_CATEGORIES,
  MAINTENANCE_PRIORITIES,
  formatMinorUnits,
  parseMinorUnits,
  type ContractorCompanyView,
  type ContractorUpdateKind,
  type ContractorUpdateView,
  type MaintenanceAction,
  type MaintenanceCategory,
  type MaintenanceEventView,
  type MaintenanceObligationView,
  type MaintenancePriority,
  type MaintenanceRequestView,
  type MaintenanceState,
  type PropertyView,
} from "../lib/property-contracts";

type Named = { id: string; name: string };

export const CATEGORY_LABELS: Record<MaintenanceCategory, string> = {
  plumbing: "Plumbing",
  electrical: "Electrical",
  hvac: "HVAC",
  structural: "Structural",
  appliance: "Appliance",
  general: "General",
};

export const PRIORITY_LABELS: Record<MaintenancePriority, string> = {
  emergency: "Emergency",
  urgent: "Urgent",
  routine: "Routine",
};

export const STATE_LABELS: Record<MaintenanceState, string> = {
  open: "Open",
  approved: "Approved",
  assigned: "Assigned",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const ACTION_LABELS: Record<MaintenanceAction, string> = {
  approve: "Approved",
  assign: "Assigned",
  complete: "Completed",
  cancel: "Cancelled",
};

export const UPDATE_KIND_LABELS: Record<ContractorUpdateKind, string> = {
  acknowledged: "Acknowledged",
  in_progress: "In progress",
  parts_needed: "Parts needed",
  work_done: "Work done",
};

function when(instant: string, zone: string | undefined): string {
  if (!zone) return instant;
  try {
    const local = businessDateTime(instant, zone);
    return `${local.date} ${local.time}`;
  } catch {
    return instant;
  }
}

async function allDelegations(businessId: string): Promise<Delegation[]> {
  const all: Delegation[] = [];
  let after: string | undefined;
  for (;;) {
    const page = await fetchDelegations(businessId, after);
    all.push(...page.items);
    if (!page.next_cursor) return all;
    after = page.next_cursor;
  }
}

function isLiveContractorGrant(
  grant: Delegation,
  businessId: string,
  locationId: string,
): boolean {
  return (
    grant.owner_business_id === businessId &&
    grant.status === "active" &&
    !grant.expired &&
    Date.parse(grant.expires_at) > Date.now() &&
    grant.permissions.includes("property.contractor_work") &&
    (grant.location_id === null || grant.location_id === locationId) &&
    grant.delegates.length > 0
  );
}

export function PropertyMaintenance({
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
  const headingRef = useRef<HTMLHeadingElement>(null);
  const headingId = useId();
  const [items, setItems] = useState<MaintenanceRequestView[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchMaintenanceRequests(businessId, property.object_id)
      .then((list) => {
        if (!live) return;
        setItems(list);
        setError("");
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(
            `Maintenance requests could not be read: ${refusal(failure)}`,
          );
      });
    return () => {
      live = false;
    };
  }, [businessId, property.object_id, attempt]);

  function reload() {
    setError("");
    setAttempt((value) => value + 1);
  }

  function announce(message: string) {
    setNotice(message);
    reload();
  }

  const partyName = (id: string | null) =>
    id === null
      ? "None"
      : (parties.find((p) => p.id === id)?.name ?? "Unknown counterparty");

  const selected = openId
    ? (items.find((item) => item.request_id === openId) ?? null)
    : null;

  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId} ref={headingRef} tabIndex={-1}>
        Maintenance
      </h3>
      <p role="status">{notice}</p>
      {!loaded && !error ? (
        <p className="muted" role="status">
          Loading maintenance requests…
        </p>
      ) : null}
      {error ? (
        <div className="property-error">
          <p className="error" role="alert">
            {error}
          </p>
          <button type="button" onClick={reload}>
            Reload maintenance
          </button>
        </div>
      ) : null}
      {loaded && items.length === 0 ? (
        <p className="muted">No maintenance requests for this property.</p>
      ) : null}
      {loaded && items.length > 0 ? (
        <div
          className="mgmt-table-container"
          role="region"
          aria-label="Maintenance requests table"
          tabIndex={0}
        >
          <table className="mgmt-table" aria-label="Maintenance requests">
            <thead>
              <tr>
                <th scope="col">Title</th>
                <th scope="col">Category</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Approved limit</th>
                <th scope="col">Revision</th>
                <th scope="col">Recorded</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.request_id}>
                  <th scope="row">
                    {canManage ? (
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => setOpenId(item.request_id)}
                      >
                        {item.title}
                      </button>
                    ) : (
                      item.title
                    )}
                  </th>
                  <td>{CATEGORY_LABELS[item.category]}</td>
                  <td>{PRIORITY_LABELS[item.priority]}</td>
                  <td>{STATE_LABELS[item.state]}</td>
                  <td>
                    {item.approved_limit_minor !== null && item.currency
                      ? formatMinorUnits(
                          item.approved_limit_minor,
                          item.currency,
                        )
                      : "None"}
                  </td>
                  <td>{item.revision}</td>
                  <td>{when(item.recorded_at, timezone)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {canManage && selected ? (
        <MaintenanceDetail
          key={`${selected.request_id}:${selected.revision}`}
          businessId={businessId}
          property={property}
          request={selected}
          parties={parties}
          partyName={partyName}
          timezone={timezone}
          onUpdated={(saved, message) => {
            setItems((list) =>
              list.map((item) =>
                item.request_id === saved.request_id ? saved : item,
              ),
            );
            announce(message);
          }}
          onNotice={setNotice}
          onReload={reload}
          onClose={() => {
            setOpenId(null);
            requestAnimationFrame(() => headingRef.current?.focus());
          }}
        />
      ) : null}
      {canManage && loaded ? (
        <NewMaintenanceForm
          businessId={businessId}
          objectId={property.object_id}
          onCreated={(saved) => {
            setItems((list) => [saved, ...list]);
            setOpenId(saved.request_id);
            announce(`Maintenance request ${saved.title} created.`);
          }}
        />
      ) : null}
    </section>
  );
}

function NewMaintenanceForm({
  businessId,
  objectId,
  onCreated,
}: {
  businessId: string;
  objectId: string;
  onCreated: (saved: MaintenanceRequestView) => void;
}) {
  const running = useRef(false);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<MaintenanceCategory>("plumbing");
  const [priority, setPriority] = useState<MaintenancePriority>("urgent");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (running.current) return;
    const cleanedTitle = title.trim();
    const cleanedDescription = description.trim();
    if (!cleanedTitle || !cleanedDescription) {
      setError("Enter a title and description.");
      return;
    }
    running.current = true;
    setSaving(true);
    setError("");
    try {
      const saved = await createMaintenanceRequest(businessId, requestId, {
        schema_version: 1,
        object_id: objectId,
        lease_id: null,
        category,
        priority,
        title: cleanedTitle,
        description: cleanedDescription,
      });
      setRequestId(crypto.randomUUID());
      setTitle("");
      setDescription("");
      onCreated(saved);
    } catch (failure) {
      setError(`Maintenance request was not saved: ${refusal(failure)}`);
    } finally {
      running.current = false;
      setSaving(false);
    }
  }

  return (
    <form
      aria-label="New maintenance request"
      className="mgmt-form"
      onSubmit={(event) => void submit(event)}
    >
      <h4>New maintenance request</h4>
      <div className="property-operation-fields">
        <label>
          Request title
          <input
            value={title}
            maxLength={200}
            required
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label>
          Category
          <select
            value={category}
            onChange={(event) => {
              const next = MAINTENANCE_CATEGORIES.find(
                (item) => item === event.target.value,
              );
              if (next) setCategory(next);
            }}
          >
            {MAINTENANCE_CATEGORIES.map((item) => (
              <option key={item} value={item}>
                {CATEGORY_LABELS[item]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select
            value={priority}
            onChange={(event) => {
              const next = MAINTENANCE_PRIORITIES.find(
                (item) => item === event.target.value,
              );
              if (next) setPriority(next);
            }}
          >
            {MAINTENANCE_PRIORITIES.map((item) => (
              <option key={item} value={item}>
                {PRIORITY_LABELS[item]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Issue description
          <textarea
            value={description}
            maxLength={4000}
            required
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
      </div>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mgmt-form-actions">
        <button type="submit" aria-disabled={saving}>
          {saving ? "Saving…" : "Create maintenance request"}
        </button>
      </div>
    </form>
  );
}

function MaintenanceDetail({
  businessId,
  property,
  request,
  parties,
  partyName,
  timezone,
  onUpdated,
  onNotice,
  onReload,
  onClose,
}: {
  businessId: string;
  property: PropertyView;
  request: MaintenanceRequestView;
  parties: Named[];
  partyName: (id: string | null) => string;
  timezone: string | undefined;
  onUpdated: (saved: MaintenanceRequestView, message: string) => void;
  onNotice: (message: string) => void;
  onReload: () => void;
  onClose: () => void;
}) {
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const [events, setEvents] = useState<MaintenanceEventView[]>([]);
  const [obligations, setObligations] = useState<MaintenanceObligationView[]>(
    [],
  );
  const [company, setCompany] = useState<ContractorCompanyView | null>(null);
  const [updates, setUpdates] = useState<ContractorUpdateView[]>([]);
  const [grants, setGrants] = useState<Delegation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [reads, setReads] = useState(0);

  // Action form state
  const [limitText, setLimitText] = useState("250.00");
  const [currency, setCurrency] = useState("USD");
  const [contractorId, setContractorId] = useState("");
  const [actionNote, setActionNote] = useState("");
  const [cancelNote, setCancelNote] = useState("");
  const [companyChoice, setCompanyChoice] = useState("");
  const [actionError, setActionError] = useState("");
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const running = useRef(false);

  useEffect(() => {
    let live = true;
    Promise.all([
      fetchMaintenanceEvents(businessId, request.request_id),
      fetchMaintenanceObligations(businessId, request.request_id),
      fetchContractorCompany(businessId, request.request_id),
      fetchContractorUpdates(businessId, request.request_id),
      allDelegations(businessId).catch(() => [] as Delegation[]),
    ])
      .then(([ev, ob, comp, upd, del]) => {
        if (!live) return;
        setEvents(ev);
        setObligations(ob);
        setCompany(comp);
        setCompanyChoice(comp.company_id ?? "");
        setUpdates(upd);
        setGrants(del);
        setError("");
        setLoaded(true);
      })
      .catch((failure: unknown) => {
        if (live)
          setError(`Maintenance detail could not be read: ${refusal(failure)}`);
      });
    return () => {
      live = false;
    };
  }, [businessId, request.request_id, reads]);

  useEffect(() => {
    detailHeading.current?.focus();
  }, [request.request_id]);

  const liveGrants = grants.filter((grant) =>
    isLiveContractorGrant(grant, businessId, property.location_id),
  );
  const companyOptions = Array.from(
    new Map(
      liveGrants.map((grant) => [
        grant.servicer_business_id,
        grant.servicer_business_id,
      ]),
    ).entries(),
  );
  const matchedGrant =
    company?.company_id != null
      ? (liveGrants.find(
          (grant) => grant.servicer_business_id === company.company_id,
        ) ?? null)
      : null;

  async function runApprove(event: React.FormEvent) {
    event.preventDefault();
    if (running.current) return;
    const minor = parseMinorUnits(limitText);
    const code = currency.trim().toUpperCase();
    if (minor === null || !/^[A-Z]{3}$/.test(code)) {
      setActionError("Enter a positive limit and 3-letter currency code.");
      return;
    }
    running.current = true;
    setBusy(true);
    setActionError("");
    try {
      const saved = await recordMaintenanceEvent(
        businessId,
        request.request_id,
        {
          schema_version: 1,
          action: "approve",
          expected_revision: request.revision,
          approved_limit_minor: minor,
          currency: code,
          note: actionNote.trim() || null,
        },
      );
      setActionNote("");
      onUpdated(saved, `Maintenance request ${saved.title} approved.`);
    } catch (failure) {
      if (maintenanceConflict(failure)) {
        setStale(true);
        setActionError(
          "This maintenance request changed. Reload before acting.",
        );
      } else setActionError(refusal(failure));
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  async function runAssign(event: React.FormEvent) {
    event.preventDefault();
    if (running.current) return;
    if (!contractorId) {
      setActionError("Choose a contractor.");
      return;
    }
    running.current = true;
    setBusy(true);
    setActionError("");
    try {
      const saved = await recordMaintenanceEvent(
        businessId,
        request.request_id,
        {
          schema_version: 1,
          action: "assign",
          expected_revision: request.revision,
          contractor_id: contractorId,
          note: actionNote.trim() || null,
        },
      );
      setActionNote("");
      onUpdated(saved, `Maintenance request ${saved.title} assigned.`);
    } catch (failure) {
      if (maintenanceConflict(failure)) {
        setStale(true);
        setActionError(
          "This maintenance request changed. Reload before acting.",
        );
      } else setActionError(refusal(failure));
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  async function runTerminal(
    event: React.FormEvent,
    action: "complete" | "cancel",
    noteText: string,
  ) {
    event.preventDefault();
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setActionError("");
    try {
      const saved = await recordMaintenanceEvent(
        businessId,
        request.request_id,
        {
          schema_version: 1,
          action,
          expected_revision: request.revision,
          note: noteText.trim() || null,
        },
      );
      setActionNote("");
      setCancelNote("");
      onUpdated(
        saved,
        `Maintenance request ${saved.title} ${action === "complete" ? "completed" : "cancelled"}.`,
      );
    } catch (failure) {
      if (maintenanceConflict(failure)) {
        setStale(true);
        setActionError(
          "This maintenance request changed. Reload before acting.",
        );
      } else setActionError(refusal(failure));
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  async function runBindCompany(event: React.FormEvent) {
    event.preventDefault();
    if (running.current || !company) return;
    running.current = true;
    setBusy(true);
    setActionError("");
    try {
      const saved = await saveContractorCompany(
        businessId,
        request.request_id,
        {
          schema_version: 1,
          expected_revision: company.revision,
          company_id: companyChoice || null,
        },
      );
      setCompany(saved);
      setCompanyChoice(saved.company_id ?? "");
      onNotice(
        saved.company_id
          ? "Contractor company access bound."
          : "Contractor company access cleared.",
      );
      setReads((n) => n + 1);
    } catch (failure) {
      if (maintenanceConflict(failure)) {
        setStale(true);
        setActionError(
          "Contractor company access changed. Reload before saving.",
        );
      } else setActionError(refusal(failure));
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="property-maintenance-detail">
      <h4 ref={detailHeading} tabIndex={-1}>
        {`Maintenance request: ${request.title}`}
      </h4>
      <dl className="property-facts">
        <div>
          <dt>Status</dt>
          <dd>{STATE_LABELS[request.state]}</dd>
        </div>
        <div>
          <dt>Category</dt>
          <dd>{CATEGORY_LABELS[request.category]}</dd>
        </div>
        <div>
          <dt>Priority</dt>
          <dd>{PRIORITY_LABELS[request.priority]}</dd>
        </div>
        <div>
          <dt>Approved limit</dt>
          <dd>
            {request.approved_limit_minor !== null && request.currency
              ? formatMinorUnits(request.approved_limit_minor, request.currency)
              : "None"}
          </dd>
        </div>
        <div>
          <dt>Contractor</dt>
          <dd>{partyName(request.contractor_id)}</dd>
        </div>
        <div>
          <dt>Revision</dt>
          <dd>{request.revision}</dd>
        </div>
      </dl>
      <p>{request.description}</p>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {actionError ? (
        <div className="property-error">
          <p className="error" role="alert">
            {actionError}
          </p>
          {stale ? (
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setStale(false);
                setActionError("");
                onReload();
                setReads((n) => n + 1);
              }}
            >
              Reload request
            </button>
          ) : null}
        </div>
      ) : null}

      {request.state === "open" ? (
        <form
          aria-label="Approve maintenance request"
          className="mgmt-form"
          onSubmit={(event) => void runApprove(event)}
        >
          <h5>Approve request</h5>
          <div className="property-operation-fields">
            <label>
              Approved limit
              <input
                value={limitText}
                required
                inputMode="decimal"
                onChange={(event) => setLimitText(event.target.value)}
              />
            </label>
            <label>
              Approval currency
              <input
                value={currency}
                maxLength={3}
                required
                onChange={(event) => setCurrency(event.target.value)}
              />
            </label>
            <label>
              Approval note (optional)
              <textarea
                value={actionNote}
                maxLength={2000}
                onChange={(event) => setActionNote(event.target.value)}
              />
            </label>
          </div>
          <div className="mgmt-form-actions">
            <button type="submit" aria-disabled={busy}>
              {busy ? "Saving…" : "Approve request"}
            </button>
          </div>
        </form>
      ) : null}

      {request.state === "approved" ? (
        <form
          aria-label="Assign contractor"
          className="mgmt-form"
          onSubmit={(event) => void runAssign(event)}
        >
          <h5>Assign contractor</h5>
          <div className="property-operation-fields">
            <label>
              Contractor counterparty
              <select
                value={contractorId}
                required
                onChange={(event) => setContractorId(event.target.value)}
              >
                <option value="">Choose a contractor</option>
                {parties.map((party) => (
                  <option key={party.id} value={party.id}>
                    {party.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Assignment note (optional)
              <textarea
                value={actionNote}
                maxLength={2000}
                onChange={(event) => setActionNote(event.target.value)}
              />
            </label>
          </div>
          <div className="mgmt-form-actions">
            <button type="submit" aria-disabled={busy}>
              {busy ? "Saving…" : "Assign contractor"}
            </button>
          </div>
        </form>
      ) : null}

      {loaded && company && request.state === "assigned" ? (
        <form
          aria-label="Contractor company access"
          className="mgmt-form"
          onSubmit={(event) => void runBindCompany(event)}
        >
          <h5>Contractor company access</h5>
          <div className="property-operation-fields">
            <label>
              Contractor company
              <select
                value={companyChoice}
                onChange={(event) => setCompanyChoice(event.target.value)}
              >
                <option value="">No contractor company</option>
                {company.company_id &&
                !companyOptions.some(([id]) => id === company.company_id) ? (
                  <option value={company.company_id}>
                    {company.company_id}
                  </option>
                ) : null}
                {companyOptions.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!companyOptions.length ? (
            <p className="muted">
              No active delegation grant with contractor work permission for
              this branch.
            </p>
          ) : null}
          <div className="mgmt-form-actions">
            <button type="submit" aria-disabled={busy}>
              {busy ? "Saving…" : "Save contractor company"}
            </button>
          </div>
          {matchedGrant && company.company_id ? (
            <div className="property-contractor-link">
              <p>
                <Link
                  href={contractorWorkHref({
                    business: businessId,
                    request: request.request_id,
                    grant: matchedGrant.grant_id,
                  })}
                >
                  Open contractor work order
                </Link>
              </p>
              <code>
                {contractorWorkHref({
                  business: businessId,
                  request: request.request_id,
                  grant: matchedGrant.grant_id,
                })}
              </code>
            </div>
          ) : null}
        </form>
      ) : null}

      {request.state === "assigned" ? (
        <form
          aria-label="Complete maintenance request"
          className="mgmt-form"
          onSubmit={(event) => void runTerminal(event, "complete", actionNote)}
        >
          <h5>Complete request</h5>
          <div className="property-operation-fields">
            <label>
              Completion note (optional)
              <textarea
                value={actionNote}
                maxLength={2000}
                onChange={(event) => setActionNote(event.target.value)}
              />
            </label>
          </div>
          <div className="mgmt-form-actions">
            <button type="submit" aria-disabled={busy}>
              {busy ? "Saving…" : "Complete request"}
            </button>
          </div>
        </form>
      ) : null}

      {request.state === "open" ||
      request.state === "approved" ||
      request.state === "assigned" ? (
        <form
          aria-label="Cancel maintenance request"
          className="mgmt-form"
          onSubmit={(event) => void runTerminal(event, "cancel", cancelNote)}
        >
          <h5>Cancel request</h5>
          <div className="property-operation-fields">
            <label>
              Cancellation note (optional)
              <textarea
                value={cancelNote}
                maxLength={2000}
                onChange={(event) => setCancelNote(event.target.value)}
              />
            </label>
          </div>
          <div className="mgmt-form-actions">
            <button type="submit" className="secondary" aria-disabled={busy}>
              {busy ? "Saving…" : "Cancel request"}
            </button>
          </div>
        </form>
      ) : null}

      {loaded ? (
        <>
          <div className="property-error">
            <h5>Contractor updates</h5>
            <button
              type="button"
              className="secondary"
              onClick={() => setReads((n) => n + 1)}
            >
              Refresh updates
            </button>
          </div>
          {updates.length === 0 ? (
            <p className="muted">No contractor updates yet.</p>
          ) : (
            <ol aria-label="Contractor updates">
              {updates.map((item) => (
                <li key={item.number}>
                  <strong>{`Update ${item.number}: ${UPDATE_KIND_LABELS[item.kind]}`}</strong>
                  {` (${item.company_name}, ${when(item.created_at, timezone)}) — ${item.note}`}
                </li>
              ))}
            </ol>
          )}

          <h5>Event history</h5>
          {events.length === 0 ? (
            <p className="muted">No lifecycle events yet.</p>
          ) : (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Maintenance event history table"
              tabIndex={0}
            >
              <table
                className="mgmt-table"
                aria-label="Maintenance event history"
              >
                <thead>
                  <tr>
                    <th scope="col">Revision</th>
                    <th scope="col">Action</th>
                    <th scope="col">Limit</th>
                    <th scope="col">Contractor</th>
                    <th scope="col">Note</th>
                    <th scope="col">Recorded</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.revision}>
                      <th scope="row">{ev.revision}</th>
                      <td>{ACTION_LABELS[ev.action]}</td>
                      <td>
                        {ev.approved_limit_minor !== null && ev.currency
                          ? formatMinorUnits(
                              ev.approved_limit_minor,
                              ev.currency,
                            )
                          : "—"}
                      </td>
                      <td>
                        {ev.contractor_id ? partyName(ev.contractor_id) : "—"}
                      </td>
                      <td>{ev.note ?? "—"}</td>
                      <td>{when(ev.recorded_at, timezone)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <h5>Linked obligations</h5>
          {obligations.length === 0 ? (
            <p className="muted">No linked obligations yet.</p>
          ) : (
            <div
              className="mgmt-table-container"
              role="region"
              aria-label="Maintenance obligations table"
              tabIndex={0}
            >
              <table
                className="mgmt-table"
                aria-label="Maintenance obligations"
              >
                <thead>
                  <tr>
                    <th scope="col">Number</th>
                    <th scope="col">Amount</th>
                    <th scope="col">Note</th>
                    <th scope="col">Recorded</th>
                  </tr>
                </thead>
                <tbody>
                  {obligations.map((ob) => (
                    <tr key={ob.number}>
                      <th scope="row">{ob.number}</th>
                      <td>{formatMinorUnits(ob.amount_minor, ob.currency)}</td>
                      <td>{ob.note ?? "—"}</td>
                      <td>{when(ob.recorded_at, timezone)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}

      <div className="mgmt-form-actions">
        <button type="button" className="secondary" onClick={onClose}>
          Close maintenance request
        </button>
      </div>
    </div>
  );
}
