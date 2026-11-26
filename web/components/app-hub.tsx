"use client";

import { useCallback, useEffect, useId, useState } from "react";
import {
  createApiKey,
  createWebhook,
  deleteWebhook,
  fetchApiKeys,
  fetchAppHubMeta,
  fetchConnectorCatalog,
  fetchWebhookDeliveries,
  fetchWebhooks,
  FALLBACK_SCOPES,
  FALLBACK_WEBHOOK_EVENTS,
  isSecretField,
  removeConnector,
  revokeApiKey,
  saveConnector,
  testWebhook,
  type ApiKey,
  type AppHubMeta,
  type Connector,
  type WebhookDelivery,
  type WebhookEndpoint,
} from "../lib/app-hub-api";
import { formatDate, formatTime } from "../lib/management-api";
import "../app/us-release-v2.css";

const AUTH_MODE_LABELS: Record<string, string> = {
  mcp_api_key: "Scoped API key",
  webhook: "Signed webhooks",
  byok: "Bring your own credentials",
  oauth_ready: "OAuth-ready (account IDs only)",
};

const SCOPE_LABELS: Record<string, string> = {
  "mcp:read": "MCP read (required for /v1/mcp)",
  "bookings:read": "Read bookings",
  "bookings:write": "Create and change bookings",
  "catalog:read": "Read services and prices",
  "finance:read": "Read financial summaries",
  "webhooks:manage": "Manage webhooks",
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return `${formatDate(iso)} · ${formatTime(iso)}`;
}

function fieldLabel(name: string): string {
  return name
    .split("_")
    .map((w) => (w === "id" ? "ID" : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  return (
    <>
      <button
        type="button"
        className="secondary usr-small-btn"
        onClick={() =>
          void copyText(text).then((ok) => setState(ok ? "copied" : "failed"))
        }
      >
        {label}
      </button>
      <span role="status" className="usr-muted">
        {state === "copied"
          ? "Copied to clipboard."
          : state === "failed"
            ? "Copy failed. Select the text and copy it manually."
            : ""}
      </span>
    </>
  );
}

/** A one-time secret. It lives only in component state and is cleared on dismiss. */
function OneTimeSecret({
  title,
  secret,
  onDismiss,
}: {
  title: string;
  secret: string;
  onDismiss: () => void;
}) {
  const inputId = useId();
  return (
    <div className="usr-secret" role="region" aria-label={title}>
      <h4 style={{ margin: "0 0 8px" }}>{title}</h4>
      <p style={{ margin: "0 0 12px" }}>
        <strong>Copy it now.</strong> GORGONA stores only a hash, so this value
        is shown once and cannot be displayed again. Store it in a password
        manager or secret vault; never paste it into chat, email, or code.
      </p>
      <label htmlFor={inputId} style={{ marginBottom: 8 }}>
        Secret value
      </label>
      <input
        id={inputId}
        type="text"
        readOnly
        value={secret}
        autoComplete="off"
        spellCheck={false}
        onFocus={(e) => e.currentTarget.select()}
      />
      <div className="usr-inline" style={{ marginTop: 12 }}>
        <CopyButton text={secret} label="Copy secret" />
        <button type="button" className="usr-small-btn" onClick={onDismiss}>
          I saved it — hide
        </button>
      </div>
    </div>
  );
}

function ConfirmInline({
  prompt,
  confirmLabel,
  busy,
  onConfirm,
  onCancel,
}: {
  prompt: string;
  confirmLabel: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="usr-inline" role="group" aria-label={prompt}>
      <span>{prompt}</span>
      <button
        type="button"
        className="usr-danger usr-small-btn"
        disabled={busy}
        onClick={onConfirm}
      >
        {busy ? "Working…" : confirmLabel}
      </button>
      <button
        type="button"
        className="secondary usr-small-btn"
        disabled={busy}
        onClick={onCancel}
      >
        Cancel
      </button>
    </div>
  );
}

export function AppHub({ businessId }: { businessId: string }) {
  const [meta, setMeta] = useState<AppHubMeta | null>(null);
  useEffect(() => {
    let active = true;
    fetchAppHubMeta(businessId)
      .then((m) => {
        if (active) setMeta(m);
      })
      .catch(() => {
        /* the allow-lists fall back to the documented defaults */
      });
    return () => {
      active = false;
    };
  }, [businessId]);
  const scopes = meta?.allowed_scopes ?? FALLBACK_SCOPES;
  const events = meta?.allowed_webhook_events ?? FALLBACK_WEBHOOK_EVENTS;
  const mcpPath = meta?.mcp_endpoint ?? "/v1/mcp";

  return (
    <div className="usr-stack">
      <div className="mgmt-section-header">
        <div>
          <h2>GORGONA App Hub</h2>
          <p className="usr-muted" style={{ margin: "4px 0 0" }}>
            The only place external services connect to your business:
            connectors, scoped API keys, signed webhooks, and the native MCP
            server for AI agents.
          </p>
        </div>
      </div>
      <ConnectorsSection businessId={businessId} />
      <ApiKeysSection businessId={businessId} scopes={scopes} />
      <WebhooksSection businessId={businessId} events={events} />
      <McpSection mcpPath={mcpPath} />
    </div>
  );
}

function ConnectorsSection({ businessId }: { businessId: string }) {
  const [items, setItems] = useState<Connector[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let active = true;
    fetchConnectorCatalog(businessId)
      .then((list) => {
        if (!active) return;
        setItems(list);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  return (
    <section className="usr-card" aria-labelledby="hub-connectors-heading">
      <h3 id="hub-connectors-heading">Connectors</h3>
      <p className="usr-muted">
        Install a US connector, add its account identifiers, and pause or remove
        it at any time. Raw credentials are never stored; values whose names
        look like secrets are masked.
      </p>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
          <button type="button" className="secondary" onClick={reload}>
            Retry
          </button>
        </div>
      )}
      {!items && !error && (
        <p className="mgmt-loading" aria-live="polite">
          Loading connectors…
        </p>
      )}
      {items && (
        <ul
          className="usr-connector-grid"
          style={{ listStyle: "none", padding: 0, margin: 0 }}
        >
          {items.map((c) => (
            <ConnectorCard
              key={c.id}
              businessId={businessId}
              connector={c}
              onChanged={reload}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function ConnectorCard({
  businessId,
  connector: c,
  onChanged,
}: {
  businessId: string;
  connector: Connector;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const headingId = useId();
  const status = c.installed ? (c.status ?? "installed") : "not_installed";

  /** Non-secret saved values; masked secrets are never round-tripped. */
  function currentConfig(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(c.config_masked)) {
      if (!isSecretField(k) && typeof v === "string") out[k] = v;
    }
    return out;
  }

  function openForm() {
    const saved = currentConfig();
    const initial: Record<string, string> = {};
    for (const f of c.fields)
      initial[f] = isSecretField(f) ? "" : (saved[f] ?? "");
    setValues(initial);
    setError(null);
    setNotice(null);
    setEditing(true);
  }

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(done);
      setEditing(false);
      setConfirmRemove(false);
      onChanged();
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const config: Record<string, string> = { ...currentConfig() };
    for (const [k, v] of Object.entries(values)) {
      const clean = v.trim();
      if (clean) config[k] = clean;
      else delete config[k];
    }
    const nextStatus = c.status === "paused" ? "paused" : "installed";
    void run(
      () => saveConnector(businessId, c.id, nextStatus, config),
      c.installed ? `${c.name} configuration saved.` : `${c.name} installed.`,
    );
  }

  return (
    <li className="usr-connector">
      <div className="usr-inline" style={{ justifyContent: "space-between" }}>
        <h4 id={headingId}>{c.name}</h4>
        <span
          className={`usr-badge ${status === "installed" ? "usr-badge-ai" : status === "paused" ? "usr-badge-fallback" : "usr-badge-off"}`}
        >
          {status === "installed"
            ? "Installed"
            : status === "paused"
              ? "Paused"
              : "Not installed"}
        </span>
      </div>
      <p className="usr-muted">
        {c.category} · {AUTH_MODE_LABELS[c.auth_mode] ?? c.auth_mode}
      </p>
      <p>{c.summary}</p>
      <p className="usr-muted">
        <strong>US advantage:</strong> {c.us_highlight}
      </p>
      {c.installed && Object.keys(c.config_masked).length > 0 && (
        <dl className="usr-muted" style={{ margin: 0 }}>
          {Object.entries(c.config_masked).map(([k, v]) => (
            <div key={k} className="usr-inline">
              <dt style={{ fontWeight: 600 }}>{fieldLabel(k)}:</dt>
              <dd style={{ margin: 0 }}>{String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {c.installed && c.updated_at && (
        <p className="usr-muted">Updated {when(c.updated_at)}</p>
      )}

      {editing && (
        <form onSubmit={submit} aria-label={`Configure ${c.name}`}>
          {c.fields.length === 0 && (
            <p className="usr-muted">This connector has no settings.</p>
          )}
          {c.fields.map((f) => (
            <label key={f}>
              {fieldLabel(f)}
              <input
                type={isSecretField(f) ? "password" : "text"}
                autoComplete="off"
                maxLength={240}
                value={values[f] ?? ""}
                placeholder={
                  isSecretField(f) ? "Saved value is hidden" : undefined
                }
                onChange={(e) =>
                  setValues((v) => ({ ...v, [f]: e.target.value }))
                }
              />
            </label>
          ))}
          <div className="usr-inline">
            <button type="submit" className="usr-small-btn" disabled={busy}>
              {busy
                ? "Saving…"
                : c.installed
                  ? "Save configuration"
                  : "Install connector"}
            </button>
            <button
              type="button"
              className="secondary usr-small-btn"
              disabled={busy}
              onClick={() => setEditing(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {!editing && !confirmRemove && (
        <div className="usr-inline" style={{ marginTop: "auto" }}>
          {!c.installed ? (
            <button type="button" className="usr-small-btn" onClick={openForm}>
              Install
            </button>
          ) : (
            <>
              <button
                type="button"
                className="secondary usr-small-btn"
                onClick={openForm}
              >
                Configure
              </button>
              <button
                type="button"
                className="secondary usr-small-btn"
                disabled={busy}
                onClick={() =>
                  void run(
                    () =>
                      saveConnector(
                        businessId,
                        c.id,
                        c.status === "paused" ? "installed" : "paused",
                        currentConfig(),
                      ),
                    c.status === "paused"
                      ? `${c.name} resumed.`
                      : `${c.name} paused.`,
                  )
                }
              >
                {c.status === "paused" ? "Resume" : "Pause"}
              </button>
              <button
                type="button"
                className="usr-danger usr-small-btn"
                onClick={() => setConfirmRemove(true)}
              >
                Remove
              </button>
            </>
          )}
        </div>
      )}
      {confirmRemove && (
        <ConfirmInline
          prompt={`Remove ${c.name}?`}
          confirmLabel="Remove connector"
          busy={busy}
          onConfirm={() =>
            void run(
              () => removeConnector(businessId, c.id),
              `${c.name} removed.`,
            )
          }
          onCancel={() => setConfirmRemove(false)}
        />
      )}
      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      <p role="status" className="usr-muted" style={{ margin: 0 }}>
        {notice ?? ""}
      </p>
    </li>
  );
}

function ApiKeysSection({
  businessId,
  scopes,
}: {
  businessId: string;
  scopes: string[];
}) {
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<string[]>([
    "mcp:read",
    "catalog:read",
    "bookings:read",
  ]);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ name: string; value: string } | null>(
    null,
  );
  const [revoking, setRevoking] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const nameId = useId();

  useEffect(() => {
    let active = true;
    fetchApiKeys(businessId)
      .then((list) => {
        if (!active) return;
        setKeys(list);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setNotice(null);
    const clean = name.trim();
    if (clean.length < 2 || clean.length > 120) {
      setFormError("Name the key with 2–120 characters.");
      return;
    }
    if (!chosen.length) {
      setFormError("Choose at least one scope.");
      return;
    }
    setCreating(true);
    try {
      const created = await createApiKey(businessId, clean, chosen);
      setSecret({ name: created.key.name, value: created.secret_token });
      setName("");
      setTick((t) => t + 1);
    } catch (err) {
      setFormError(errText(err));
    } finally {
      setCreating(false);
    }
  }

  async function revoke(key: ApiKey) {
    setBusy(true);
    setError(null);
    try {
      await revokeApiKey(businessId, key.id);
      setNotice(`API key “${key.name}” revoked.`);
      setRevoking(null);
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="usr-card" aria-labelledby="hub-keys-heading">
      <h3 id="hub-keys-heading">Scoped API Keys</h3>
      <p className="usr-muted">
        Give each integration or AI agent its own key with only the scopes it
        needs. Revoke a key to cut its access immediately.
      </p>
      <form onSubmit={(e) => void create(e)} aria-label="Create an API key">
        <label htmlFor={nameId}>Key name</label>
        <input
          id={nameId}
          type="text"
          maxLength={120}
          value={name}
          placeholder="Example: Front-desk voice agent"
          onChange={(e) => setName(e.target.value)}
        />
        <fieldset className="usr-checks" style={{ marginTop: 16 }}>
          <legend>Scopes</legend>
          {scopes.map((s) => (
            <label key={s} className="usr-check">
              <input
                type="checkbox"
                checked={chosen.includes(s)}
                onChange={() =>
                  setChosen((c) =>
                    c.includes(s) ? c.filter((x) => x !== s) : [...c, s],
                  )
                }
              />
              <span>
                <code>{s}</code>
                {SCOPE_LABELS[s] ? ` — ${SCOPE_LABELS[s]}` : ""}
              </span>
            </label>
          ))}
        </fieldset>
        {formError && (
          <p className="usr-field-error" role="alert">
            {formError}
          </p>
        )}
        <button type="submit" disabled={creating}>
          {creating ? "Creating key…" : "Create API key"}
        </button>
      </form>
      {secret && (
        <OneTimeSecret
          title={`New API key “${secret.name}”`}
          secret={secret.value}
          onDismiss={() => setSecret(null)}
        />
      )}
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
      {!keys && !error && (
        <p className="mgmt-loading" aria-live="polite">
          Loading API keys…
        </p>
      )}
      {keys && keys.length === 0 && (
        <p className="usr-muted">No API keys yet.</p>
      )}
      {keys && keys.length > 0 && (
        <div className="usr-table-wrap" tabIndex={0} aria-label="API keys">
          <table className="usr-table">
            <caption
              className="usr-muted"
              style={{ textAlign: "left", padding: "8px 12px" }}
            >
              Secrets are never listed. Only the key prefix is shown.
            </caption>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Prefix</th>
                <th scope="col">Scopes</th>
                <th scope="col">Status</th>
                <th scope="col">Last used</th>
                <th scope="col">Created</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id}>
                  <td>
                    <strong>{k.name}</strong>
                  </td>
                  <td>
                    <code>{k.key_prefix}…</code>
                  </td>
                  <td>{k.scopes.join(", ")}</td>
                  <td>
                    <span
                      className={`usr-badge ${k.status === "active" ? "usr-badge-ai" : "usr-badge-off"}`}
                    >
                      {k.status === "active" ? "Active" : "Revoked"}
                    </span>
                  </td>
                  <td>{when(k.last_used_at)}</td>
                  <td>{when(k.created_at)}</td>
                  <td>
                    {k.status !== "active" ? (
                      <span className="usr-muted">
                        Revoked {when(k.revoked_at)}
                      </span>
                    ) : revoking === k.id ? (
                      <ConfirmInline
                        prompt={`Revoke “${k.name}”?`}
                        confirmLabel="Revoke key"
                        busy={busy}
                        onConfirm={() => void revoke(k)}
                        onCancel={() => setRevoking(null)}
                      />
                    ) : (
                      <button
                        type="button"
                        className="usr-danger usr-small-btn"
                        aria-label={`Revoke API key ${k.name}`}
                        onClick={() => setRevoking(k.id)}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function WebhooksSection({
  businessId,
  events,
}: {
  businessId: string;
  events: string[];
}) {
  const [hooks, setHooks] = useState<WebhookEndpoint[] | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const [url, setUrl] = useState("https://");
  const [description, setDescription] = useState("");
  const [chosen, setChosen] = useState<string[]>([
    "booking.created",
    "invoice.issued",
  ]);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ url: string; value: string } | null>(
    null,
  );
  const [pending, setPending] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const urlId = useId();
  const descId = useId();

  useEffect(() => {
    let active = true;
    Promise.all([fetchWebhooks(businessId), fetchWebhookDeliveries(businessId)])
      .then(([list, log]) => {
        if (!active) return;
        setHooks(list);
        setDeliveries(log);
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setNotice(null);
    const clean = url.trim();
    let valid = false;
    try {
      const parsed = new URL(clean);
      valid = parsed.protocol === "https:" && clean.length >= 12;
    } catch {
      valid = false;
    }
    if (!valid || clean.length > 500) {
      setFormError("Enter an https:// endpoint URL (up to 500 characters).");
      return;
    }
    if (!chosen.length) {
      setFormError("Choose at least one event.");
      return;
    }
    setCreating(true);
    try {
      const created = await createWebhook(businessId, {
        url: clean,
        description: description.trim(),
        events: chosen,
      });
      if (created.signing_secret)
        setSecret({ url: created.endpoint.url, value: created.signing_secret });
      else setNotice("Webhook endpoint created.");
      setUrl("https://");
      setDescription("");
      setTick((t) => t + 1);
    } catch (err) {
      setFormError(errText(err));
    } finally {
      setCreating(false);
    }
  }

  async function sendTest(hook: WebhookEndpoint) {
    setPending(hook.id);
    setError(null);
    setNotice(null);
    try {
      const d = await testWebhook(businessId, hook.id);
      setNotice(
        `Test delivery to ${hook.url}: ${d.status}${d.http_status ? ` (HTTP ${d.http_status})` : ""}.`,
      );
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err));
    } finally {
      setPending(null);
    }
  }

  async function remove(hook: WebhookEndpoint) {
    setPending(hook.id);
    setError(null);
    try {
      await deleteWebhook(businessId, hook.id);
      setNotice(`Webhook endpoint ${hook.url} deleted.`);
      setDeleting(null);
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err));
    } finally {
      setPending(null);
    }
  }

  const urlFor = (endpointId: string) =>
    hooks?.find((h) => h.id === endpointId)?.url ?? "Deleted endpoint";

  return (
    <section className="usr-card" aria-labelledby="hub-webhooks-heading">
      <h3 id="hub-webhooks-heading">HMAC-signed Webhooks</h3>
      <p className="usr-muted">
        Send business events to Zapier, Make, n8n, or your own HTTPS endpoint.
        Each delivery carries an HMAC-SHA256 signature header in the form{" "}
        <code>v1=&lt;hex&gt;</code>.
      </p>
      <form onSubmit={(e) => void create(e)} aria-label="Create a webhook">
        <div className="usr-grid">
          <label htmlFor={urlId}>
            Endpoint URL (https only)
            <input
              id={urlId}
              type="url"
              inputMode="url"
              maxLength={500}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <label htmlFor={descId}>
            Description (optional)
            <input
              id={descId}
              type="text"
              maxLength={240}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
        </div>
        <fieldset className="usr-checks">
          <legend>Events</legend>
          {events.map((ev) => (
            <label key={ev} className="usr-check">
              <input
                type="checkbox"
                checked={chosen.includes(ev)}
                onChange={() =>
                  setChosen((c) =>
                    c.includes(ev) ? c.filter((x) => x !== ev) : [...c, ev],
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
        <button type="submit" disabled={creating}>
          {creating ? "Creating endpoint…" : "Create webhook endpoint"}
        </button>
      </form>
      {secret && (
        <OneTimeSecret
          title={`Signing secret for ${secret.url}`}
          secret={secret.value}
          onDismiss={() => setSecret(null)}
        />
      )}
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
      {!hooks && !error && (
        <p className="mgmt-loading" aria-live="polite">
          Loading webhooks…
        </p>
      )}
      {hooks && hooks.length === 0 && (
        <p className="usr-muted">No webhook endpoints yet.</p>
      )}
      {hooks && hooks.length > 0 && (
        <ul className="usr-rows" style={{ listStyle: "none", padding: 0 }}>
          {hooks.map((h) => (
            <li key={h.id} className="usr-connector">
              <strong style={{ overflowWrap: "anywhere" }}>{h.url}</strong>
              {h.description && <span>{h.description}</span>}
              <span className="usr-muted">
                Events: {h.events.join(", ")} · Secret prefix{" "}
                <code>{h.signing_secret_prefix}…</code> ·{" "}
                {h.is_active ? "Active" : "Inactive"} · Created{" "}
                {when(h.created_at)}
              </span>
              {deleting === h.id ? (
                <ConfirmInline
                  prompt={`Delete the endpoint ${h.url}?`}
                  confirmLabel="Delete endpoint"
                  busy={pending === h.id}
                  onConfirm={() => void remove(h)}
                  onCancel={() => setDeleting(null)}
                />
              ) : (
                <div className="usr-inline">
                  <button
                    type="button"
                    className="secondary usr-small-btn"
                    disabled={!h.is_active || pending === h.id}
                    aria-label={`Test Delivery to ${h.url}`}
                    onClick={() => void sendTest(h)}
                  >
                    {pending === h.id ? "Sending…" : "Test Delivery"}
                  </button>
                  <button
                    type="button"
                    className="usr-danger usr-small-btn"
                    aria-label={`Delete webhook ${h.url}`}
                    onClick={() => setDeleting(h.id)}
                  >
                    Delete
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      <h4>Deliveries log</h4>
      {deliveries && deliveries.length === 0 && (
        <p className="usr-muted">No deliveries recorded yet.</p>
      )}
      {deliveries && deliveries.length > 0 && (
        <div
          className="usr-table-wrap"
          tabIndex={0}
          aria-label="Webhook deliveries log"
        >
          <table className="usr-table">
            <thead>
              <tr>
                <th scope="col">Event</th>
                <th scope="col">Endpoint</th>
                <th scope="col">Status</th>
                <th scope="col">HTTP</th>
                <th scope="col">Attempts</th>
                <th scope="col">Created</th>
                <th scope="col">Delivered</th>
              </tr>
            </thead>
            <tbody>
              {deliveries.map((d) => (
                <tr key={d.id}>
                  <td>
                    <code>{d.event_type}</code>
                  </td>
                  <td style={{ overflowWrap: "anywhere" }}>
                    {urlFor(d.endpoint_id)}
                  </td>
                  <td>
                    {d.status}
                    {d.last_error ? (
                      <div className="usr-field-error">{d.last_error}</div>
                    ) : null}
                  </td>
                  <td>{d.http_status ?? "—"}</td>
                  <td>{d.attempts}</td>
                  <td>{when(d.created_at)}</td>
                  <td>{when(d.delivered_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function McpSection({ mcpPath }: { mcpPath: string }) {
  // Rendered only in the browser after sign-in, so the page origin is known.
  const [origin] = useState(() =>
    typeof window === "undefined"
      ? "https://your-gorgona-host"
      : window.location.origin,
  );
  const endpoint = `${origin}${mcpPath}`;
  const config = JSON.stringify(
    {
      mcpServers: {
        gorgona: {
          type: "http",
          url: endpoint,
          headers: { Authorization: "Bearer gorg_live_YOUR_SCOPED_API_KEY" },
        },
      },
    },
    null,
    2,
  );
  const curl = [
    `curl -X POST ${endpoint} \\`,
    `  -H "Authorization: Bearer gorg_live_YOUR_SCOPED_API_KEY" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`,
  ].join("\n");

  return (
    <section className="usr-card" aria-labelledby="hub-mcp-heading">
      <h3 id="hub-mcp-heading">GORGONA Native MCP Server</h3>
      <p className="usr-muted">
        Connect MCP-compatible AI agents to your live services and business
        summary over JSON-RPC 2.0. Create a Scoped API Key with the{" "}
        <code>mcp:read</code> scope and send it as{" "}
        <code>Authorization: Bearer gorg_live_…</code>. Every call is limited to
        this business.
      </p>
      <p>
        <strong>Endpoint:</strong> <code>{endpoint}</code>{" "}
        <span className="usr-inline" style={{ display: "inline-flex" }}>
          <CopyButton text={endpoint} label="Copy endpoint" />
        </span>
      </p>
      <p className="usr-muted">
        Methods: <code>initialize</code>, <code>tools/list</code>,{" "}
        <code>tools/call</code>. Tools: <code>get_business_summary</code>,{" "}
        <code>list_services</code>, <code>ask_business_copilot</code>.
      </p>
      <h4>MCP client configuration</h4>
      <pre
        className="usr-code"
        tabIndex={0}
        aria-label="MCP client configuration"
      >
        {config}
      </pre>
      <div className="usr-inline">
        <CopyButton text={config} label="Copy configuration" />
      </div>
      <h4>Test with curl</h4>
      <pre className="usr-code" tabIndex={0} aria-label="curl example">
        {curl}
      </pre>
      <p className="hold-note">
        Replace the placeholder with your own key. Never share a real key in
        screenshots, tickets, or source code.
      </p>
    </section>
  );
}
