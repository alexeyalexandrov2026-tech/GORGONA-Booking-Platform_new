"use client";

import { useEffect, useState } from "react";

import type {
  Configuration,
  ConfigurationPreview,
  ConfigurationVersion,
  ModuleCatalog,
  PlatformModule,
} from "../lib/configuration-contracts";
import {
  changeConfiguration,
  fetchConfiguration,
  fetchConfigurationPreview,
  fetchConfigurationVersions,
  fetchModuleCatalog,
  ManagementApiError,
  type ConfigurationCommand,
} from "../lib/management-api";

const READINESS: Record<PlatformModule["readiness"], string> = {
  planned: "Planned",
  implemented: "Implemented, not yet verified",
  technically_verified: "Technically verified",
  pilot_accepted: "Accepted in a pilot",
  production_approved: "Approved for production",
};
const STATE: Record<ConfigurationVersion["state"], string> = {
  draft: "Draft",
  validated: "Validated",
  published: "Published",
  superseded: "Replaced",
};
const DONE: Record<ConfigurationCommand["kind"], string> = {
  draft: "Draft saved. Check the preview, then validate it.",
  validate: "Draft validated. It can now be published.",
  publish: "Configuration published.",
};

interface Pending {
  key: string;
  command: ConfigurationCommand;
}

interface Loaded {
  catalog: ModuleCatalog;
  configuration: Configuration;
  history: ConfigurationVersion[];
  more: boolean;
  preview: ConfigurationPreview | null;
}

export function BusinessConfiguration({
  businessId,
  canManage,
  profileRevision,
  industryNames,
}: {
  businessId: string;
  canManage: boolean;
  profileRevision: number | null;
  industryNames: Record<number, string>;
}) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState<Pending | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    (async () => {
      const [catalog, configuration, history] = await Promise.all([
        fetchModuleCatalog(businessId),
        fetchConfiguration(businessId),
        fetchConfigurationVersions(businessId),
      ]);
      const latest = configuration.latest;
      const preview =
        latest && (latest.state === "draft" || latest.state === "validated")
          ? await fetchConfigurationPreview(businessId, latest.version)
          : null;
      return {
        catalog,
        configuration,
        history: history.items,
        more: history.next_cursor !== null,
        preview,
      };
    })()
      .then((data) => {
        if (!active) return;
        setLoaded(data);
        const optional = new Set(
          data.catalog.modules
            .filter((item) => item.kind === "optional")
            .map((item) => item.id),
        );
        setSelected(
          (
            data.configuration.latest?.module_ids ??
            data.configuration.effective_module_ids
          ).filter((id) => optional.has(id)),
        );
        setError(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load configuration.",
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
    setConfirming(false);
    setError(null);
    setMessage(null);
    try {
      await changeConfiguration(businessId, next.command, next.key);
      setPending(null);
      setMessage(DONE[next.command.kind]);
      setReload((value) => value + 1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Unable to save.");
      if (
        err instanceof ManagementApiError &&
        err.status &&
        err.status >= 400 &&
        err.status < 500
      ) {
        setPending(null);
        setReload((value) => value + 1);
      }
    } finally {
      setBusy(false);
    }
  }

  function start(command: ConfigurationCommand) {
    if (!pending) void run({ key: crypto.randomUUID(), command });
  }

  const locked = !canManage || busy || Boolean(pending);
  const configuration = loaded?.configuration;
  const latest = configuration?.latest ?? null;
  const open =
    latest && (latest.state === "draft" || latest.state === "validated")
      ? latest
      : null;
  const names = new Map(
    (loaded?.catalog.modules ?? []).map((item) => [item.id, item.name]),
  );
  const moduleName = (id: string) => names.get(id) ?? id;
  const preview = loaded?.preview ?? null;

  return (
    <section aria-label="Configuration" className="business-configuration">
      <h2>Configuration</h2>
      <p className="muted">
        Choose which modules this business uses. A draft is checked by the
        server, previewed and then published; published versions never change
        and earlier ones stay in the history.
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
            Retry same configuration action
          </button>
        </div>
      )}
      {loading || !loaded || !configuration ? (
        !error && <p role="status">Loading configuration…</p>
      ) : (
        <>
          <p>
            {configuration.published
              ? `Published version ${configuration.published.version}.`
              : "No published version yet: the business keeps its current setup, with booking on."}{" "}
            Active modules:{" "}
            {configuration.effective_module_ids.map(moduleName).join(", ")}.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (profileRevision === null) {
                setError("Save the business profile before a configuration.");
                return;
              }
              start({
                kind: "draft",
                expectedVersion: latest?.version ?? 0,
                profileRevision,
                moduleIds: [...selected].sort(),
              });
            }}
          >
            <fieldset disabled={locked}>
              <legend>Modules for the next draft</legend>
              <ul className="configuration-modules">
                {loaded.catalog.modules.map((item) => (
                  <li key={item.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={
                          item.kind === "core" || selected.includes(item.id)
                        }
                        disabled={
                          item.kind === "core" ||
                          (!item.enableable && !selected.includes(item.id))
                        }
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, item.id]
                              : current.filter((id) => id !== item.id),
                          )
                        }
                      />
                      <span>
                        <strong>{item.name}</strong> ·{" "}
                        {item.kind === "core"
                          ? "Always on"
                          : READINESS[item.readiness]}
                        <span className="muted">{item.limits}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
            {canManage && (
              <button type="submit" disabled={locked}>
                Save configuration draft
              </button>
            )}
          </form>
          {open && (
            <div className="configuration-open">
              <h3>
                Version {open.version} · {STATE[open.state]}
              </h3>
              <p>
                Pins business profile revision {open.profile_revision}. Modules:{" "}
                {open.module_ids.length
                  ? open.module_ids.map(moduleName).join(", ")
                  : "core modules only"}
                .
              </p>
              {preview && preview.version === open.version && (
                <div aria-label="Configuration preview" role="region">
                  <h4>Preview</h4>
                  {preview.enabling.length > 0 && (
                    <p>
                      Turns on: {preview.enabling.map(moduleName).join(", ")}.
                    </p>
                  )}
                  {preview.stopping.map((item) => (
                    <p key={item.module_id}>
                      Turns off {moduleName(item.module_id)}. Stops:{" "}
                      {item.stops}
                    </p>
                  ))}
                  {preview.enabling.length === 0 &&
                    preview.disabling.length === 0 && <p>No module changes.</p>}
                  {(preview.industries_added.length > 0 ||
                    preview.industries_removed.length > 0) && (
                    <p>
                      Activities added:{" "}
                      {preview.industries_added
                        .map((id) => industryNames[id] ?? `#${id}`)
                        .join(", ") || "none"}
                      ; removed:{" "}
                      {preview.industries_removed
                        .map((id) => industryNames[id] ?? `#${id}`)
                        .join(", ") || "none"}
                      .
                    </p>
                  )}
                  {preview.problems.length > 0 && (
                    <ul aria-label="Problems to fix">
                      {preview.problems.map((item, index) => (
                        <li key={`${item.code}-${item.module_id}-${index}`}>
                          {item.message}
                        </li>
                      ))}
                    </ul>
                  )}
                  {preview.warnings.map((item, index) => (
                    <p className="muted" key={`${item.code}-${index}`}>
                      {item.message}
                    </p>
                  ))}
                </div>
              )}
              {canManage && open.state === "draft" && (
                <button
                  type="button"
                  disabled={locked}
                  onClick={() =>
                    start({
                      kind: "validate",
                      version: open.version,
                      revision: open.revision,
                    })
                  }
                >
                  Validate version {open.version}
                </button>
              )}
              {canManage &&
                open.state === "validated" &&
                (confirming ? (
                  <div className="business-formats">
                    <p>
                      Publish version {open.version}?{" "}
                      {preview?.stopping.length
                        ? "Operations listed above will stop."
                        : "Nothing will stop."}
                    </p>
                    <button
                      type="button"
                      disabled={locked}
                      onClick={() =>
                        start({
                          kind: "publish",
                          version: open.version,
                          revision: open.revision,
                        })
                      }
                    >
                      Confirm publication
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() => setConfirming(false)}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={locked}
                    onClick={() => setConfirming(true)}
                  >
                    Publish version {open.version}
                  </button>
                ))}
            </div>
          )}
          <h3>History</h3>
          {loaded.more && (
            <p className="muted">
              Only the {loaded.history.length} most recent versions are shown.
            </p>
          )}
          {loaded.history.length === 0 ? (
            <p>No configuration versions yet.</p>
          ) : (
            <ul className="delegation-list" aria-label="Configuration history">
              {loaded.history.map((item) => (
                <li key={item.version}>
                  Version {item.version} · {STATE[item.state]} ·{" "}
                  {item.module_ids.length
                    ? item.module_ids.map(moduleName).join(", ")
                    : "core modules only"}
                  {item.superseded_by_version &&
                    ` · replaced by version ${item.superseded_by_version}`}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
