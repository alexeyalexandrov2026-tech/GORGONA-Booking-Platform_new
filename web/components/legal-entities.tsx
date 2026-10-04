"use client";

import { useEffect, useState } from "react";

import type {
  LegalEntity,
  LegalEntityInput,
} from "../lib/legal-entity-contracts";
import {
  fetchLegalEntities,
  fetchLegalEntity,
  ManagementApiError,
  saveLegalEntity,
} from "../lib/management-api";

interface Command {
  entityId: string;
  key: string;
  body: LegalEntityInput;
}

export function LegalEntities({
  businessId,
  canManage,
}: {
  businessId: string;
  canManage: boolean;
}) {
  const [items, setItems] = useState<LegalEntity[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<LegalEntity | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [history, setHistory] = useState<LegalEntity | null>(null);
  const [pending, setPending] = useState<Command | null>(null);
  const [conflict, setConflict] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    fetchLegalEntities(businessId)
      .then((page) => {
        if (!active) return;
        setItems(page.items);
        setNextCursor(page.next_cursor);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load legal entities.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reload]);

  function select(entity: LegalEntity | null) {
    setSelected(entity);
    setCode(entity?.code ?? "");
    setName(entity?.legal_name ?? "");
    setHistory(null);
    setConflict(false);
    setMessage(null);
    setError(null);
  }

  function remember(entity: LegalEntity) {
    setItems((current) =>
      [
        ...current.filter(
          (item) => item.legal_entity_id !== entity.legal_entity_id,
        ),
        entity,
      ].sort((a, b) => a.code.localeCompare(b.code)),
    );
    setSelected(entity);
    setCode(entity.code);
    setName(entity.legal_name);
    setHistory(null);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!canManage || busy || conflict) return;
    const command = pending ?? {
      entityId: selected?.legal_entity_id ?? crypto.randomUUID(),
      key: crypto.randomUUID(),
      body: {
        schema_version: 1 as const,
        expected_revision: selected?.revision ?? 0,
        code,
        legal_name: name.trim(),
      },
    };
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const entity = await saveLegalEntity(
        businessId,
        command.entityId,
        command.body,
        command.key,
      );
      remember(entity);
      setPending(null);
      setMessage(`Legal entity saved. Draft version ${entity.revision}.`);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to save this legal entity.",
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
      const entity = await fetchLegalEntity(
        businessId,
        selected.legal_entity_id,
      );
      remember(entity);
      setConflict(false);
      setMessage("Latest legal entity version loaded.");
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to reload this legal entity.",
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
        await fetchLegalEntity(
          businessId,
          selected.legal_entity_id,
          revision - 1,
        ),
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
      const page = await fetchLegalEntities(businessId, nextCursor);
      setItems((current) => {
        const merged = new Map(
          current.map((item) => [item.legal_entity_id, item]),
        );
        page.items.forEach((item) => merged.set(item.legal_entity_id, item));
        return [...merged.values()];
      });
      setNextCursor(page.next_cursor);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load more legal entities.",
      );
    } finally {
      setBusy(false);
    }
  }

  const locked = !canManage || busy || Boolean(pending) || conflict;
  return (
    <section aria-label="Legal entities" className="legal-entities">
      <h2>Legal entities</h2>
      <p className="muted">
        These are draft organization records. Registration details and financial
        setup will be added later.
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
        <p role="status">Loading legal entities…</p>
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
              Reload legal entity list
            </button>
            {canManage && (
              <button
                type="button"
                disabled={busy || Boolean(pending)}
                onClick={() => select(null)}
              >
                New legal entity
              </button>
            )}
          </div>
          {items.length === 0 && !error && <p>No legal entities saved yet.</p>}
          <ul className="legal-entity-list">
            {items.map((entity) => (
              <li key={entity.legal_entity_id}>
                <button
                  type="button"
                  className="secondary"
                  disabled={busy || Boolean(pending)}
                  onClick={() => select(entity)}
                >
                  {entity.code} · {entity.legal_name} · Draft version{" "}
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
              Load more legal entities
            </button>
          )}
          {(canManage || selected) && (
            <form onSubmit={(event) => void save(event)}>
              <fieldset disabled={locked}>
                <legend>
                  {selected ? "Selected legal entity" : "New legal entity"}
                </legend>
                <label htmlFor="legal-entity-reference">
                  Internal reference
                </label>
                <input
                  id="legal-entity-reference"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  pattern="[A-Z0-9][A-Z0-9_-]*"
                  maxLength={64}
                  required
                  readOnly={selected !== null}
                  aria-describedby="legal-reference-help"
                />
                <p id="legal-reference-help" className="muted">
                  Use uppercase letters, numbers, dashes or underscores. This
                  reference stays with the record.
                </p>
                <label htmlFor="legal-entity-name">Legal name</label>
                <input
                  id="legal-entity-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={200}
                  required
                />
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
                        ? "Retry same entity save"
                        : "Save legal entity"}
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
                      Reload selected entity
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
                      View previous entity version
                    </button>
                  </>
                )}
              </div>
            </form>
          )}
          {history && (
            <p className="hold-note" role="note">
              Previous entity version {history.revision}: {history.legal_name}.
              The saved version has been preserved.
            </p>
          )}
        </>
      )}
    </section>
  );
}
