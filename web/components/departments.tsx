"use client";
import type { LegalEntity } from "../lib/legal-entity-contracts";

import { useEffect, useState } from "react";

import type { Department, DepartmentInput } from "../lib/department-contracts";
import {
  fetchDepartments,
  fetchLegalEntities,
  fetchDepartment,
  ManagementApiError,
  saveDepartment,
} from "../lib/management-api";

interface Command {
  departmentId: string;
  key: string;
  body: DepartmentInput;
}

export function Departments({
  businessId,
  canManage,
  locations,
}: {
  businessId: string;
  canManage: boolean;
  locations: { id: string; name: string }[];
}) {
  const [items, setItems] = useState<Department[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<Department | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [legalId, setLegalId] = useState("");
  const [entities, setEntities] = useState<LegalEntity[]>([]);
  const [entityCursor, setEntityCursor] = useState<string | null>(null);
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
    Promise.all([fetchDepartments(businessId), fetchLegalEntities(businessId)])
      .then(([page, legalPage]) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
        setEntities(legalPage.items);
        setEntityCursor(legalPage.next_cursor);
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

  function select(entity: Department | null) {
    setSelected(entity);
    setCode(entity?.code ?? "");
    setName(entity?.name ?? "");
    setParentId(entity?.parent_department_id ?? "");
    setLocationId(entity?.location_id ?? "");
    setLegalId(entity?.legal_entity_id ?? "");
    setHistory(null);
    setConflict(false);
    setMessage(null);
    setError(null);
  }

  function remember(entity: Department) {
    setItems((current) =>
      [
        ...current.filter(
          (item) => item.department_id !== entity.department_id,
        ),
        entity,
      ].sort((a, b) => a.code.localeCompare(b.code)),
    );
    setSelected(entity);
    setCode(entity.code);
    setName(entity.name);
    setParentId(entity.parent_department_id ?? "");
    setLocationId(entity.location_id ?? "");
    setLegalId(entity.legal_entity_id ?? "");
    setHistory(null);
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
        location_id: locationId || null,
        legal_entity_id: legalId || null,
      },
    };
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const entity = await saveDepartment(
        businessId,
        command.departmentId,
        command.body,
        command.key,
      );
      remember(entity);
      setPending(null);
      setMessage(`Department saved. Draft version ${entity.revision}.`);
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
        // A duplicate reference on a new record can be corrected without discarding the name.
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
      const entity = await fetchDepartment(businessId, selected.department_id);
      remember(entity);
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

  async function loadMore() {
    if (!nextCursor || busy || pending) return;
    setBusy(true);
    setError(null);
    try {
      const page = await fetchDepartments(businessId, nextCursor);
      setItems((current) => {
        const merged = new Map(
          current.map((item) => [item.department_id, item]),
        );
        page.items.forEach((item) => merged.set(item.department_id, item));
        return [...merged.values()];
      });
      setNextCursor(page.next_cursor);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Unable to load more departments.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function loadMoreEntities() {
    if (!entityCursor || busy || pending) return;
    setBusy(true);
    setError(null);
    try {
      const page = await fetchLegalEntities(businessId, entityCursor);
      setEntities((current) => [
        ...new Map(
          [...current, ...page.items].map((item) => [
            item.legal_entity_id,
            item,
          ]),
        ).values(),
      ]);
      setEntityCursor(page.next_cursor);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Unable to load legal entities.",
      );
    } finally {
      setBusy(false);
    }
  }

  const locked = !canManage || busy || Boolean(pending) || conflict;
  return (
    <section aria-label="Departments" className="legal-entities">
      <h2>Departments</h2>
      <p className="muted">
        Organize your company with departments and optional parent, branch and
        legal entity links. These draft records do not change employee
        permissions.
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
          {items.length === 0 && !error && <p>No departments saved yet.</p>}
          <ul className="legal-entity-list">
            {items.map((entity) => (
              <li key={entity.department_id}>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || Boolean(pending)}
                  onClick={() => select(entity)}
                >
                  {entity.code} · {entity.name} · Draft version{" "}
                  {entity.revision}
                </button>
              </li>
            ))}
          </ul>
          {nextCursor && (
            <button
              type="button"
              className="secondary"
              disabled={busy || Boolean(pending)}
              onClick={() => void loadMore()}
            >
              Load more departments
            </button>
          )}
          {entityCursor && (
            <button
              type="button"
              className="secondary"
              disabled={busy || Boolean(pending)}
              onClick={() => void loadMoreEntities()}
            >
              Load more legal entity choices
            </button>
          )}
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
                  reference stays with the record.
                </p>
                <label htmlFor="department-name">Department name</label>
                <input
                  id="department-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  required
                />
                <label htmlFor="department-parent">
                  Parent department (optional)
                </label>
                <select
                  id="department-parent"
                  value={parentId}
                  onChange={(event) => setParentId(event.target.value)}
                >
                  <option value="">No parent department</option>
                  {parentId &&
                    !items.some((item) => item.department_id === parentId) && (
                      <option value={parentId}>Saved parent department</option>
                    )}
                  {items
                    .filter(
                      (item) => item.department_id !== selected?.department_id,
                    )
                    .map((item) => (
                      <option
                        key={item.department_id}
                        value={item.department_id}
                      >
                        {item.code} · {item.name}
                      </option>
                    ))}
                </select>
                <label htmlFor="department-branch">Branch (optional)</label>
                <select
                  id="department-branch"
                  value={locationId}
                  onChange={(event) => setLocationId(event.target.value)}
                >
                  <option value="">No branch link</option>
                  {locations.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </select>
                <label htmlFor="department-legal">
                  Legal entity (optional)
                </label>
                <select
                  id="department-legal"
                  value={legalId}
                  onChange={(event) => setLegalId(event.target.value)}
                >
                  <option value="">No legal entity link</option>
                  {legalId &&
                    !entities.some(
                      (item) => item.legal_entity_id === legalId,
                    ) && <option value={legalId}>Saved legal entity</option>}
                  {entities.map((item) => (
                    <option
                      key={item.legal_entity_id}
                      value={item.legal_entity_id}
                    >
                      {item.code} · {item.legal_name}
                    </option>
                  ))}
                </select>
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
              Previous department version {history.revision}: {history.name}.
              Parent link:{" "}
              {history.parent_department_id
                ? (items.find(
                    (item) =>
                      item.department_id === history.parent_department_id,
                  )?.name ?? "Saved parent department")
                : "None"}
              . Branch link:{" "}
              {history.location_id
                ? (locations.find((item) => item.id === history.location_id)
                    ?.name ?? "Saved branch")
                : "None"}
              . Legal entity link:{" "}
              {history.legal_entity_id
                ? (entities.find(
                    (item) => item.legal_entity_id === history.legal_entity_id,
                  )?.legal_name ?? "Saved legal entity")
                : "None"}
              . The saved version has been preserved.
            </p>
          )}
        </>
      )}
    </section>
  );
}
