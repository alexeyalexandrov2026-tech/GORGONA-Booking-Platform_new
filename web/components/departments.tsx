"use client";

import { useEffect, useState } from "react";

import type { Department, DepartmentInput } from "../lib/department-contracts";
import type { LegalEntity } from "../lib/legal-entity-contracts";
import {
  fetchDepartment,
  fetchDepartments,
  fetchLegalEntities,
  ManagementApiError,
  saveDepartment,
} from "../lib/management-api";

// Bounded loading: the structure form needs every option, not an endless scroll.
const MAX_PAGES = 20;

interface Command {
  departmentId: string;
  key: string;
  body: DepartmentInput;
}

interface Location {
  id: string;
  name: string;
}

async function loadAll<T>(
  fetchPage: (
    after?: string,
  ) => Promise<{ items: T[]; next_cursor: string | null }>,
): Promise<{ items: T[]; complete: boolean }> {
  const items: T[] = [];
  let after: string | undefined;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const result = await fetchPage(after);
    items.push(...result.items);
    if (!result.next_cursor) return { items, complete: true };
    after = result.next_cursor;
  }
  return { items, complete: false };
}

function byCode(a: Department, b: Department) {
  return a.code.localeCompare(b.code);
}

export function Departments({
  businessId,
  canManage,
  locations,
}: {
  businessId: string;
  canManage: boolean;
  locations: readonly Location[];
}) {
  const [items, setItems] = useState<Department[]>([]);
  const [entities, setEntities] = useState<LegalEntity[]>([]);
  const [complete, setComplete] = useState(true);
  const [selected, setSelected] = useState<Department | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [legalEntityId, setLegalEntityId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [archived, setArchived] = useState(false);
  const [history, setHistory] = useState<Department | null>(null);
  const [pending, setPending] = useState<Command | null>(null);
  const [conflict, setConflict] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    Promise.all([
      loadAll((after) => fetchDepartments(businessId, after)),
      loadAll((after) => fetchLegalEntities(businessId, after)),
    ])
      .then(([departments, legalEntities]) => {
        if (!active) return;
        setItems([...departments.items].sort(byCode));
        setEntities(legalEntities.items);
        setComplete(departments.complete && legalEntities.complete);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error ? err.message : "Unable to load departments.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reload]);

  function show(department: Department | null) {
    setSelected(department);
    setCode(department?.code ?? "");
    setName(department?.name ?? "");
    setParentId(department?.parent_department_id ?? "");
    setLegalEntityId(department?.legal_entity_id ?? "");
    setLocationId(department?.location_id ?? "");
    setArchived(department?.archived ?? false);
    setHistory(null);
  }

  function select(department: Department | null) {
    show(department);
    setConflict(false);
    setMessage(null);
    setError(null);
  }

  function remember(department: Department) {
    setItems((current) =>
      [
        ...current.filter(
          (item) => item.department_id !== department.department_id,
        ),
        department,
      ].sort(byCode),
    );
    show(department);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!canManage || busy || conflict) return;
    const command = pending ?? {
      departmentId: selected?.department_id ?? crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: {
        schema_version: 1 as const,
        expected_revision: selected?.revision ?? 0,
        code,
        name: name.trim(),
        parent_department_id: parentId || null,
        legal_entity_id: legalEntityId || null,
        location_id: locationId || null,
        archived,
      },
    };
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const department = await saveDepartment(
        businessId,
        command.departmentId,
        command.body,
        command.key,
      );
      remember(department);
      setPending(null);
      setMessage(`Department saved. Draft version ${department.revision}.`);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Unable to save this department.",
      );
      if (
        err instanceof ManagementApiError &&
        err.status &&
        err.status >= 400 &&
        err.status < 500
      ) {
        setPending(null);
        // A rejected structure keeps the form editable; only a stale version needs reload.
        setConflict(err.status === 409 && selected !== null);
      }
    } finally {
      setBusy(false);
    }
  }

  async function refreshSelected() {
    if (!selected || busy || pending) return;
    setBusy(true);
    setError(null);
    try {
      remember(await fetchDepartment(businessId, selected.department_id));
      setConflict(false);
      setMessage("Latest department version loaded.");
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to reload this department.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function previousVersion() {
    const revision = history?.revision ?? selected?.revision ?? 0;
    if (!selected || revision <= 1 || busy || pending) return;
    setBusy(true);
    setError(null);
    try {
      setHistory(
        await fetchDepartment(businessId, selected.department_id, revision - 1),
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load the previous version.",
      );
    } finally {
      setBusy(false);
    }
  }

  const codes = new Map(items.map((item) => [item.department_id, item.code]));
  const locked = !canManage || busy || Boolean(pending) || conflict;
  return (
    <section aria-label="Departments" className="departments">
      <h2>Departments</h2>
      <p className="muted">
        Departments organize this business. They do not grant access, assign
        employees or move records to another company.
      </p>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
          {conflict && (
            <p>
              Your edits are still shown. Reload the latest version before
              saving again.
            </p>
          )}
        </div>
      )}
      {message && <p role="status">{message}</p>}
      {loading ? (
        <p role="status">Loading departments…</p>
      ) : (
        <>
          <div className="business-formats">
            <button
              type="button"
              className="secondary"
              disabled={busy || Boolean(pending)}
              onClick={() => {
                setLoading(true);
                setReload((value) => value + 1);
              }}
            >
              Reload department list
            </button>
            {canManage && (
              <button
                type="button"
                disabled={busy || Boolean(pending)}
                onClick={() => select(null)}
              >
                New department
              </button>
            )}
          </div>
          {!complete && (
            <p className="muted">
              Only the first {MAX_PAGES} pages of records are shown.
            </p>
          )}
          {items.length === 0 && !error && <p>No departments saved yet.</p>}
          <ul className="department-list">
            {items.map((department) => (
              <li key={department.department_id}>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || Boolean(pending)}
                  onClick={() => select(department)}
                >
                  {department.code} · {department.name}
                  {department.parent_department_id &&
                    ` · in ${codes.get(department.parent_department_id) ?? "another department"}`}
                  {department.archived && " · Archived"} · Draft version{" "}
                  {department.revision}
                </button>
              </li>
            ))}
          </ul>
          {(canManage || selected) && (
            <form onSubmit={(event) => void save(event)}>
              <fieldset disabled={locked}>
                <legend>
                  {selected ? "Selected department" : "New department"}
                </legend>
                <label htmlFor="department-reference">Internal reference</label>
                <input
                  id="department-reference"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  pattern="[A-Z0-9][A-Z0-9_-]*"
                  maxLength={64}
                  required
                  readOnly={selected !== null}
                  aria-describedby="department-reference-help"
                />
                <p id="department-reference-help" className="muted">
                  Use uppercase letters, numbers, dashes or underscores. This
                  reference stays with the department.
                </p>
                <label htmlFor="department-name">Department name</label>
                <input
                  id="department-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  required
                />
                <label htmlFor="department-parent">Parent department</label>
                <select
                  id="department-parent"
                  value={parentId}
                  onChange={(event) => setParentId(event.target.value)}
                >
                  <option value="">No parent department</option>
                  {items
                    .filter(
                      (item) => item.department_id !== selected?.department_id,
                    )
                    .map((item) => (
                      <option
                        key={item.department_id}
                        value={item.department_id}
                        disabled={
                          item.archived && item.department_id !== parentId
                        }
                      >
                        {item.code} · {item.name}
                        {item.archived ? " (archived)" : ""}
                      </option>
                    ))}
                </select>
                <label htmlFor="department-legal-entity">Legal entity</label>
                <select
                  id="department-legal-entity"
                  value={legalEntityId}
                  onChange={(event) => setLegalEntityId(event.target.value)}
                >
                  <option value="">No legal entity</option>
                  {entities.map((entity) => (
                    <option
                      key={entity.legal_entity_id}
                      value={entity.legal_entity_id}
                    >
                      {entity.code} · {entity.legal_name}
                    </option>
                  ))}
                </select>
                <label htmlFor="department-location">Location</label>
                <select
                  id="department-location"
                  value={locationId}
                  onChange={(event) => setLocationId(event.target.value)}
                >
                  <option value="">No specific location</option>
                  {locations.map((location) => (
                    <option key={location.id} value={location.id}>
                      {location.name}
                    </option>
                  ))}
                </select>
                <div className="business-formats">
                  <label>
                    <input
                      type="checkbox"
                      checked={archived}
                      onChange={(event) => setArchived(event.target.checked)}
                    />{" "}
                    Archived
                  </label>
                </div>
              </fieldset>
              {pending && !busy && (
                <p>
                  The save result is uncertain. Retry the same save to confirm
                  it.
                </p>
              )}
              <div className="business-formats">
                {canManage && (
                  <button
                    type="submit"
                    disabled={busy || conflict || !name.trim() || !code}
                  >
                    {busy
                      ? "Saving…"
                      : pending
                        ? "Retry same department save"
                        : "Save department"}
                  </button>
                )}
                {selected && (
                  <>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy || Boolean(pending)}
                      onClick={() => void refreshSelected()}
                    >
                      Reload selected department
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={
                        busy ||
                        Boolean(pending) ||
                        (history?.revision ?? selected.revision) <= 1
                      }
                      onClick={() => void previousVersion()}
                    >
                      View previous department version
                    </button>
                  </>
                )}
              </div>
            </form>
          )}
          {history && (
            <p className="hold-note" role="note">
              Previous department version {history.revision}: {history.name}
              {history.archived ? " (archived)" : ""}. The saved version has
              been preserved.
            </p>
          )}
        </>
      )}
    </section>
  );
}
