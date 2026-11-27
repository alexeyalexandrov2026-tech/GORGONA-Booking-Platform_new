"use client";

import { useEffect, useId, useState } from "react";
import {
  createCustomPlugin,
  deleteCustomPlugin,
  fetchCustomPlugins,
  probeCustomPlugin,
  updateCustomPlugin,
  type CustomPlugin,
  type CustomPluginAuthScheme,
  type CustomPluginProtocol,
} from "../lib/app-hub-api";
import { formatDate, formatTime } from "../lib/management-api";

const PROTOCOL_LABELS: Record<CustomPluginProtocol, string> = {
  https_api: "External HTTPS API",
  mcp_remote: "Remote MCP Server (JSON-RPC 2.0)",
  webhook_bridge: "Webhook / Automation Bridge",
  oauth2_custom: "Custom OAuth2 App",
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

export function CustomPluginsPanel({
  businessId,
  scopes,
  events,
}: {
  businessId: string;
  scopes: string[];
  events: string[];
}) {
  const [plugins, setPlugins] = useState<CustomPlugin[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const [slug, setSlug] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [category, setCategory] = useState("Custom Integration");
  const [protocol, setProtocol] = useState<CustomPluginProtocol>("https_api");
  const [endpointUrl, setEndpointUrl] = useState("https://");
  const [authScheme, setAuthScheme] =
    useState<CustomPluginAuthScheme>("Bearer");
  const [authHeader, setAuthHeader] = useState("Authorization");
  const [authCredential, setAuthCredential] = useState("");
  const [description, setDescription] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<string[]>(["mcp:read"]);
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const slugId = useId();
  const nameId = useId();
  const catId = useId();
  const protoId = useId();
  const urlId = useId();
  const schemeId = useId();
  const headerId = useId();
  const credId = useId();
  const descId = useId();

  useEffect(() => {
    let active = true;
    fetchCustomPlugins(businessId)
      .then((list) => {
        if (!active) return;
        setPlugins(list);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setNotice(null);
    const cleanSlug = slug.trim().toLowerCase();
    const cleanName = displayName.trim();
    const cleanUrl = endpointUrl.trim();
    if (!/^[a-z0-9][a-z0-9_-]{1,62}$/.test(cleanSlug)) {
      setFormError(
        "Slug must be 2-63 lowercase characters (a-z, 0-9, _ or -).",
      );
      return;
    }
    if (cleanName.length < 2) {
      setFormError("Display name must be at least 2 characters.");
      return;
    }
    if (!cleanUrl.startsWith("https://") || cleanUrl.length < 12) {
      setFormError("Endpoint URL must start with https://.");
      return;
    }
    setCreating(true);
    try {
      const created = await createCustomPlugin(businessId, {
        slug: cleanSlug,
        display_name: cleanName,
        category: category.trim() || "Custom Integration",
        protocol,
        endpoint_url: cleanUrl,
        auth_header_name: authHeader.trim() || "Authorization",
        auth_scheme: authScheme,
        auth_credential:
          authScheme !== "None" && authCredential.trim()
            ? authCredential.trim()
            : undefined,
        scopes: selectedScopes,
        subscribed_events: selectedEvents,
        description: description.trim(),
      });
      setSlug("");
      setDisplayName("");
      setEndpointUrl("https://");
      setAuthCredential("");
      setDescription("");
      setNotice(
        `Custom plugin "${created.display_name}" installed (${created.has_secret ? `credential encrypted: ${created.secret_hint ?? "***"}` : "no secret stored"}).`,
      );
      setTick((t) => t + 1);
    } catch (err) {
      setFormError(errText(err));
    } finally {
      setCreating(false);
    }
  }

  async function onToggleStatus(p: CustomPlugin) {
    setBusyId(p.id);
    setError(null);
    setNotice(null);
    const nextStatus = p.status === "active" ? "paused" : "active";
    try {
      await updateCustomPlugin(businessId, p.id, { status: nextStatus });
      setNotice(
        `Plugin "${p.display_name}" ${nextStatus === "active" ? "resumed" : "paused"}.`,
      );
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusyId(null);
    }
  }

  async function onProbe(p: CustomPlugin) {
    setBusyId(p.id);
    setError(null);
    setNotice(null);
    try {
      const res = await probeCustomPlugin(businessId, p.id);
      if (res.ok) setNotice(`${p.display_name}: ${res.message}`);
      else setError(`${p.display_name}: ${res.message}`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(p: CustomPlugin) {
    setBusyId(p.id);
    setError(null);
    setNotice(null);
    try {
      await deleteCustomPlugin(businessId, p.id);
      setConfirmDeleteId(null);
      setNotice(`Custom plugin "${p.display_name}" removed.`);
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="usr-card" aria-labelledby="hub-custom-plugins-heading">
      <h3 id="hub-custom-plugins-heading">
        Custom Plugins &amp; Open Manifests (Any External Software)
      </h3>
      <p className="usr-muted">
        Connect any external ERP, CRM, Remote MCP Server, or internal corporate
        API over HTTPS without running untrusted code inside AMARKAL. Optional
        API tokens are stored in your per-tenant AES-256-GCM encrypted vault and
        outbound probes enforce strict public-IP SSRF protection.
      </p>

      <form
        onSubmit={(e) => void onCreate(e)}
        aria-label="Install a custom plugin"
      >
        <div className="usr-grid">
          <label htmlFor={nameId}>
            Plugin name
            <input
              id={nameId}
              type="text"
              maxLength={120}
              value={displayName}
              placeholder="Example: Procore ERP Bridge or Internal MCP"
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </label>
          <label htmlFor={slugId}>
            Unique slug
            <input
              id={slugId}
              type="text"
              maxLength={63}
              value={slug}
              placeholder="procore_erp"
              onChange={(e) => setSlug(e.target.value)}
            />
          </label>
        </div>

        <div className="usr-grid">
          <label htmlFor={protoId}>
            Protocol
            <select
              id={protoId}
              value={protocol}
              onChange={(e) =>
                setProtocol(e.target.value as CustomPluginProtocol)
              }
            >
              {Object.entries(PROTOCOL_LABELS).map(([k, label]) => (
                <option key={k} value={k}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label htmlFor={catId}>
            Category
            <input
              id={catId}
              type="text"
              maxLength={64}
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </label>
        </div>

        <label htmlFor={urlId}>
          HTTPS Endpoint URL
          <input
            id={urlId}
            type="url"
            inputMode="url"
            maxLength={500}
            value={endpointUrl}
            onChange={(e) => setEndpointUrl(e.target.value)}
          />
        </label>

        <div className="usr-grid">
          <label htmlFor={schemeId}>
            Authentication scheme
            <select
              id={schemeId}
              value={authScheme}
              onChange={(e) =>
                setAuthScheme(e.target.value as CustomPluginAuthScheme)
              }
            >
              <option value="Bearer">Bearer Token</option>
              <option value="ApiKey">API Key Header</option>
              <option value="None">No outbound credential</option>
            </select>
          </label>
          <label htmlFor={headerId}>
            Auth header name
            <input
              id={headerId}
              type="text"
              maxLength={64}
              value={authHeader}
              disabled={authScheme === "None"}
              onChange={(e) => setAuthHeader(e.target.value)}
            />
          </label>
        </div>

        {authScheme !== "None" && (
          <label htmlFor={credId}>
            API Token / Secret (optional — encrypted with AES-256-GCM)
            <input
              id={credId}
              type="password"
              autoComplete="off"
              spellCheck={false}
              maxLength={1024}
              value={authCredential}
              placeholder="Paste token or leave blank"
              onChange={(e) => setAuthCredential(e.target.value)}
            />
          </label>
        )}

        <label htmlFor={descId}>
          Description (optional)
          <input
            id={descId}
            type="text"
            maxLength={400}
            value={description}
            placeholder="What this integration synchronizes"
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>

        <fieldset className="usr-checks" style={{ marginTop: 12 }}>
          <legend>Allowed scopes (optional)</legend>
          {scopes.map((s) => (
            <label key={s} className="usr-check">
              <input
                type="checkbox"
                checked={selectedScopes.includes(s)}
                onChange={() =>
                  setSelectedScopes((prev) =>
                    prev.includes(s)
                      ? prev.filter((x) => x !== s)
                      : [...prev, s],
                  )
                }
              />
              <code>{s}</code>
            </label>
          ))}
        </fieldset>

        <fieldset className="usr-checks" style={{ marginTop: 12 }}>
          <legend>Subscribed webhook events (optional)</legend>
          {events.map((ev) => (
            <label key={ev} className="usr-check">
              <input
                type="checkbox"
                checked={selectedEvents.includes(ev)}
                onChange={() =>
                  setSelectedEvents((prev) =>
                    prev.includes(ev)
                      ? prev.filter((x) => x !== ev)
                      : [...prev, ev],
                  )
                }
              />
              <code>{ev}</code>
            </label>
          ))}
        </fieldset>

        {formError && (
          <p className="usr-field-error" role="alert">
            {formError}
          </p>
        )}
        <button type="submit" disabled={creating} style={{ marginTop: 12 }}>
          {creating ? "Installing plugin…" : "Install custom plugin"}
        </button>
      </form>

      <p role="status" className="usr-muted">
        {notice ?? ""}
      </p>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="secondary"
            onClick={() => setTick((t) => t + 1)}
          >
            Retry
          </button>
        </div>
      )}
      {!plugins && !error && (
        <p className="mgmt-loading" aria-live="polite">
          Loading custom plugins…
        </p>
      )}
      {plugins && plugins.length === 0 && (
        <p className="usr-muted">No custom plugins installed yet.</p>
      )}
      {plugins && plugins.length > 0 && (
        <ul className="usr-rows" style={{ listStyle: "none", padding: 0 }}>
          {plugins.map((p) => (
            <li key={p.id} className="usr-connector">
              <div
                className="usr-inline"
                style={{ justifyContent: "space-between" }}
              >
                <strong>
                  {p.display_name} (<code>{p.slug}</code>)
                </strong>
                <span
                  className={`usr-badge ${p.status === "active" ? "usr-badge-ai" : "usr-badge-fallback"}`}
                >
                  {p.status === "active" ? "Active" : "Paused"}
                </span>
              </div>
              <span className="usr-muted">
                {p.category} · {PROTOCOL_LABELS[p.protocol]} ·{" "}
                {p.has_secret
                  ? `Encrypted secret (${p.secret_hint ?? "***"})`
                  : `Auth: ${p.auth_scheme}`}
              </span>
              <code style={{ overflowWrap: "anywhere" }}>{p.endpoint_url}</code>
              {p.description && <span>{p.description}</span>}
              <span className="usr-muted">
                Updated {formatDate(p.updated_at)} · {formatTime(p.updated_at)}
              </span>
              {confirmDeleteId === p.id ? (
                <div
                  className="usr-inline"
                  role="group"
                  aria-label={`Confirm deleting ${p.display_name}`}
                >
                  <span>Remove {p.display_name}?</span>
                  <button
                    type="button"
                    className="usr-danger usr-small-btn"
                    disabled={busyId === p.id}
                    onClick={() => void onDelete(p)}
                  >
                    {busyId === p.id ? "Removing…" : "Remove plugin"}
                  </button>
                  <button
                    type="button"
                    className="secondary usr-small-btn"
                    disabled={busyId === p.id}
                    onClick={() => setConfirmDeleteId(null)}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="usr-inline">
                  <button
                    type="button"
                    className="secondary usr-small-btn"
                    disabled={busyId === p.id}
                    onClick={() => void onProbe(p)}
                  >
                    {busyId === p.id ? "Testing…" : "Test endpoint"}
                  </button>
                  <button
                    type="button"
                    className="secondary usr-small-btn"
                    disabled={busyId === p.id}
                    onClick={() => void onToggleStatus(p)}
                  >
                    {p.status === "active" ? "Pause" : "Resume"}
                  </button>
                  <button
                    type="button"
                    className="usr-danger usr-small-btn"
                    disabled={busyId === p.id}
                    onClick={() => setConfirmDeleteId(p.id)}
                  >
                    Remove
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
