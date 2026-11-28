"use client";

import { useEffect, useId, useState } from "react";
import {
  deleteByokAiConfig,
  fetchByokAiConfig,
  saveByokAiConfig,
  testByokAiConfig,
  type ByokAiConfig,
  type ByokProviderId,
} from "../lib/app-hub-api";
import { formatDate, formatTime } from "../lib/management-api";

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}

export function ByokAiPanel({ businessId }: { businessId: string }) {
  const [config, setConfig] = useState<ByokAiConfig | null>(null);
  const [provider, setProvider] = useState<ByokProviderId>("anthropic");
  const [model, setModel] = useState("claude-sonnet-4-20250514");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const providerId = useId();
  const modelId = useId();
  const keyId = useId();

  useEffect(() => {
    let active = true;
    fetchByokAiConfig(businessId)
      .then((res) => {
        if (!active) return;
        setConfig(res);
        if (res.provider) {
          setProvider(res.provider);
          setModel(res.model ?? "");
          setEnabled(res.enabled);
        } else {
          const first = res.supported_providers[0];
          if (first) {
            setProvider(first.id);
            setModel(first.default_model);
          }
        }
        setError(null);
      })
      .catch((err: unknown) => {
        if (active) setError(errText(err));
      });
    return () => {
      active = false;
    };
  }, [businessId, tick]);

  const activeSpec =
    config?.supported_providers.find((p) => p.id === provider) ?? null;

  function onProviderChange(next: ByokProviderId) {
    setProvider(next);
    const spec = config?.supported_providers.find((p) => p.id === next);
    if (spec) setModel(spec.default_model);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    const trimmedKey = apiKey.trim();
    if (!config?.configured && trimmedKey.length < 12) {
      setError("Enter a valid provider API key (at least 12 characters).");
      return;
    }
    setBusy(true);
    try {
      const saved = await saveByokAiConfig(businessId, {
        provider,
        model: model.trim() || undefined,
        api_key: trimmedKey || undefined,
        enabled,
      });
      setConfig(saved);
      setApiKey("");
      setNotice(
        `BYOK AI configuration saved (${saved.provider ?? provider}, key ${saved.key_hint ?? "***"}).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  async function onTest() {
    setTesting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await testByokAiConfig(businessId);
      if (res.ok) setNotice(res.message);
      else setError(res.message);
    } catch (err) {
      setError(errText(err));
    } finally {
      setTesting(false);
    }
  }

  async function onDelete() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await deleteByokAiConfig(businessId);
      setApiKey("");
      setConfirmRemove(false);
      setNotice(
        "BYOK AI key deleted from the encrypted vault. AMARKAL platform AI fallback is active.",
      );
      setTick((t) => t + 1);
    } catch (err) {
      setError(errText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="usr-card" aria-labelledby="hub-byok-ai-heading">
      <div className="usr-inline" style={{ justifyContent: "space-between" }}>
        <h3 id="hub-byok-ai-heading" style={{ margin: 0 }}>
          Bring Your Own AI Key (Anthropic · Google Gemini · OpenAI)
        </h3>
        {config && (
          <span
            className={`usr-badge ${
              config.configured && config.enabled
                ? "usr-badge-ai"
                : config.configured
                  ? "usr-badge-fallback"
                  : "usr-badge-off"
            }`}
          >
            {config.configured && config.enabled
              ? `BYOK active (${config.provider})`
              : config.configured
                ? "BYOK paused"
                : "Platform default AI"}
          </span>
        )}
      </div>
      <p className="usr-muted">
        Optional: connect your company&apos;s own commercial API key from
        Anthropic (Claude), Google (Gemini), or OpenAI. Keys are encrypted at
        rest with per-tenant AES-256-GCM and never shown again. Grounded PG18
        facts, FORCE RLS isolation, and Human-in-the-Loop controls remain
        strictly enforced.
      </p>

      {config?.configured && (
        <p className="hold-note" style={{ marginTop: 0 }}>
          Stored encrypted key: <code>{config.key_hint ?? "***"}</code> · Model:{" "}
          <code>{config.model ?? "default"}</code>
          {config.updated_at
            ? ` · Updated ${formatDate(config.updated_at)} ${formatTime(config.updated_at)}`
            : ""}
        </p>
      )}

      {!config && !error && (
        <p className="mgmt-loading" aria-live="polite">
          Loading AI provider settings…
        </p>
      )}

      {config && (
        <form
          onSubmit={(e) => void onSubmit(e)}
          aria-label="Configure BYOK AI provider"
        >
          <div className="usr-grid">
            <label htmlFor={providerId}>
              AI Vendor
              <select
                id={providerId}
                value={provider}
                onChange={(e) =>
                  onProviderChange(e.target.value as ByokProviderId)
                }
              >
                {config.supported_providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor={modelId}>
              Model ID
              <input
                id={modelId}
                type="text"
                maxLength={80}
                value={model}
                placeholder={activeSpec?.default_model ?? ""}
                onChange={(e) => setModel(e.target.value)}
              />
            </label>
          </div>

          {activeSpec && activeSpec.suggested_models.length > 0 && (
            <div className="usr-inline" style={{ margin: "8px 0 12px" }}>
              <span className="usr-muted">Suggested models:</span>
              {activeSpec.suggested_models.map((m) => (
                <button
                  key={m}
                  type="button"
                  className="secondary usr-small-btn"
                  onClick={() => setModel(m)}
                >
                  {m}
                </button>
              ))}
            </div>
          )}

          <label htmlFor={keyId}>
            {config.configured
              ? "Rotate API Key (leave blank to keep stored encrypted key)"
              : `Provider API Key (${activeSpec?.key_prefix_hint ?? "API key"})`}
            <input
              id={keyId}
              type="password"
              autoComplete="off"
              spellCheck={false}
              maxLength={512}
              value={apiKey}
              placeholder={
                config.configured
                  ? `Encrypted (${config.key_hint ?? "***"}) — enter new key to rotate`
                  : (activeSpec?.key_prefix_hint ?? "Paste your vendor API key")
              }
              onChange={(e) => setApiKey(e.target.value)}
            />
          </label>

          <label className="usr-check" style={{ margin: "12px 0" }}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <span>
              Route AMARKAL Copilot &amp; AI Booking Assistant through my
              organization&apos;s API key (automatic fallback if unavailable)
            </span>
          </label>

          <div className="usr-inline">
            <button type="submit" disabled={busy}>
              {busy
                ? "Encrypting & saving…"
                : config.configured
                  ? "Update BYOK AI settings"
                  : "Save encrypted AI key"}
            </button>
            {config.configured && (
              <button
                type="button"
                className="secondary usr-small-btn"
                disabled={testing || busy}
                onClick={() => void onTest()}
              >
                {testing ? "Testing connection…" : "Test live connection"}
              </button>
            )}
            {config.configured && !confirmRemove && (
              <button
                type="button"
                className="usr-danger usr-small-btn"
                disabled={busy}
                onClick={() => setConfirmRemove(true)}
              >
                Remove key
              </button>
            )}
          </div>
        </form>
      )}

      {confirmRemove && (
        <div
          className="usr-inline"
          role="group"
          aria-label="Confirm removing BYOK AI key"
          style={{ marginTop: 12 }}
        >
          <span>Delete stored BYOK AI key permanently?</span>
          <button
            type="button"
            className="usr-danger usr-small-btn"
            disabled={busy}
            onClick={() => void onDelete()}
          >
            {busy ? "Deleting…" : "Confirm delete"}
          </button>
          <button
            type="button"
            className="secondary usr-small-btn"
            disabled={busy}
            onClick={() => setConfirmRemove(false)}
          >
            Cancel
          </button>
        </div>
      )}

      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      <p role="status" className="usr-muted" style={{ marginBottom: 0 }}>
        {notice ?? ""}
      </p>
    </section>
  );
}
