"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import {
  fetchMarketplaceCatalog,
  installMarketplacePlugin,
  InstallStatus,
  MarketplaceCatalogResponse,
  PluginProtocol,
  submitDeveloperManifest,
  updateInstallationStatus,
  validateDeveloperManifest,
  ValidateManifestResponse,
} from "../lib/plugin-marketplace-api";

type MarketplaceTab = "catalog" | "installed" | "sdk";

function protocolLabel(p: PluginProtocol): string {
  if (p === "https_api") return "HTTPS API";
  if (p === "mcp_remote") return "Remote MCP";
  if (p === "webhook_bridge") return "HMAC Webhook";
  return "OAuth 2.0";
}

export function PluginMarketplaceHub({ businessId }: { businessId: string }) {
  const [activeTab, setActiveTab] = useState<MarketplaceTab>("catalog");
  const [data, setData] = useState<MarketplaceCatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busySlug, setBusySlug] = useState<string | null>(null);
  const [busySdk, setBusySdk] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Catalog filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("All");

  // Developer SDK editor
  const [manifestText, setManifestText] = useState("");
  const [validationResult, setValidationResult] =
    useState<ValidateManifestResponse | null>(null);
  const [publishMode, setPublishMode] = useState<
    "published_private" | "submitted_for_review"
  >("published_private");

  const reload = async () => {
    const res = await fetchMarketplaceCatalog(businessId);
    setData(res);
    setManifestText(
      (prev) => prev || JSON.stringify(res.sdk_manifest_template, null, 2),
    );
  };

  useEffect(() => {
    let active = true;
    fetchMarketplaceCatalog(businessId)
      .then((res) => {
        if (!active) return;
        setData(res);
        setManifestText(
          (prev) => prev || JSON.stringify(res.sdk_manifest_template, null, 2),
        );
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(
          err instanceof ManagementApiError
            ? err.message
            : "Unable to load Plugin Marketplace catalog.",
        );
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId]);

  const categories = useMemo(() => {
    const cats = new Set<string>(["All"]);
    for (const item of data?.catalog ?? []) {
      cats.add(item.category);
    }
    return Array.from(cats);
  }, [data]);

  const filteredCatalog = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return (data?.catalog ?? []).filter((item) => {
      if (selectedCategory !== "All" && item.category !== selectedCategory) {
        return false;
      }
      if (!q) return true;
      const haystack =
        `${item.display_name} ${item.summary} ${item.publisher_name} ${item.category} ${item.naics_tags.join(" ")}`.toLowerCase();
      return haystack.includes(q);
    });
  }, [data, searchQuery, selectedCategory]);

  const activeInstalledCount = useMemo(
    () =>
      (data?.installations ?? []).filter((i) => i.status === "installed")
        .length,
    [data],
  );

  const handleInstall = async (slug: string) => {
    setBusySlug(slug);
    setError(null);
    setNotice(null);
    try {
      const inst = await installMarketplacePlugin(businessId, {
        plugin_slug: slug,
      });
      await reload();
      setNotice(
        `Installed "${inst.display_name}" (v${inst.plugin_version}) with ${inst.granted_scopes.length} least-privilege scopes.`,
      );
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Plugin installation failed.",
      );
    } finally {
      setBusySlug(null);
    }
  };

  const handleStatusChange = async (
    slug: string,
    nextStatus: InstallStatus,
  ) => {
    setBusySlug(slug);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateInstallationStatus(
        businessId,
        slug,
        nextStatus,
      );
      await reload();
      setNotice(
        `Updated "${updated.display_name}" status to ${updated.status.toUpperCase()}.`,
      );
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Failed to update plugin status.",
      );
    } finally {
      setBusySlug(null);
    }
  };

  const parseEditorJson = (): Record<string, unknown> | null => {
    try {
      const parsed: unknown = JSON.parse(manifestText);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError("Manifest must be a JSON object.");
        return null;
      }
      return parsed as Record<string, unknown>;
    } catch (exc) {
      setError(
        `Invalid JSON syntax: ${exc instanceof Error ? exc.message : "check commas and quotes."}`,
      );
      return null;
    }
  };

  const handleValidateManifest = async () => {
    const obj = parseEditorJson();
    if (!obj) return;
    setBusySdk(true);
    setError(null);
    setNotice(null);
    try {
      const res = await validateDeveloperManifest(businessId, obj);
      setValidationResult(res);
      if (res.valid) {
        setNotice(
          "amarkal-plugin.json passed SSRF, HTTPS, and least-privilege scope validation.",
        );
      }
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Manifest validation request failed.",
      );
    } finally {
      setBusySdk(false);
    }
  };

  const handleSubmitManifest = async () => {
    const obj = parseEditorJson();
    if (!obj) return;
    setBusySdk(true);
    setError(null);
    setNotice(null);
    try {
      const sub = await submitDeveloperManifest(businessId, obj, publishMode);
      await reload();
      setNotice(
        `Registered "${sub.display_name}" v${sub.version} (${sub.validation_status}). It is now available for 1-click install in your Plugin Catalog.`,
      );
    } catch (err) {
      setError(
        err instanceof ManagementApiError
          ? err.message
          : "Manifest submission failed.",
      );
    } finally {
      setBusySdk(false);
    }
  };

  return (
    <div className="usr-stack">
      <section className="usr-card">
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: "16px",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div className="usr-inline" style={{ marginBottom: "8px" }}>
              <span className="usr-badge usr-badge-ai">
                CLEAN CORE · SCOPED SANDBOX PLUGINS
              </span>
              <span className="usr-badge">amarkal-plugin.json SDK v1.0</span>
              <span className="usr-badge">ZERO UNTRUSTED CORE CODE</span>
            </div>
            <h1 style={{ margin: "0 0 6px", fontSize: "1.65rem" }}>
              AMARKAL Plugin Marketplace &amp; Developer SDK
            </h1>
            <p className="usr-muted" style={{ margin: 0 }}>
              Install verified vertical extensions (US Customs ACE, X12 EDI,
              Samsara ELD, Avalara Tax, HL7 FHIR, Procore, DocuSign, Remote MCP)
              in 1 click — or validate and publish your own custom{" "}
              <code>amarkal-plugin.json</code> integration.
            </p>
          </div>
          <div className="usr-inline">
            <Link
              href="/integrations/"
              className="button secondary usr-small-btn"
            >
              App Hub &amp; Secret Vault →
            </Link>
          </div>
        </div>

        <div
          role="tablist"
          aria-label="Plugin Marketplace workspace sections"
          className="usr-tablist"
          style={{ marginTop: "18px", marginBottom: 0 }}
        >
          <button
            type="button"
            role="tab"
            id="tab-mkt-catalog"
            aria-selected={activeTab === "catalog"}
            aria-controls="panel-mkt-catalog"
            className="usr-tab"
            onClick={() => setActiveTab("catalog")}
          >
            Plugin Catalog ({data?.catalog.length ?? 0})
          </button>
          <button
            type="button"
            role="tab"
            id="tab-mkt-installed"
            aria-selected={activeTab === "installed"}
            aria-controls="panel-mkt-installed"
            className="usr-tab"
            onClick={() => setActiveTab("installed")}
          >
            Installed Extensions ({activeInstalledCount})
          </button>
          <button
            type="button"
            role="tab"
            id="tab-mkt-sdk"
            aria-selected={activeTab === "sdk"}
            aria-controls="panel-mkt-sdk"
            className="usr-tab"
            onClick={() => setActiveTab("sdk")}
          >
            Developer SDK (amarkal-plugin.json)
          </button>
        </div>
      </section>

      {error ? (
        <div className="usr-errors" role="alert">
          <strong>Marketplace error:</strong> {error}
        </div>
      ) : null}

      {notice ? (
        <div
          className="usr-card"
          role="status"
          style={{
            padding: "14px 20px",
            background: "#e9f6ee",
            borderColor: "#a9dbb9",
            color: "#165430",
          }}
        >
          {notice}
        </div>
      ) : null}

      {activeTab === "catalog" ? (
        <section
          id="panel-mkt-catalog"
          role="tabpanel"
          aria-labelledby="tab-mkt-catalog"
          className="usr-stack"
        >
          <div className="usr-card" style={{ marginBottom: 0 }}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "12px",
              }}
            >
              <label style={{ margin: 0, flex: "1 1 260px" }}>
                <span className="sr-only">Search marketplace plugins</span>
                <input
                  type="search"
                  aria-label="Search marketplace plugins"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by NAICS, EDI, Customs, ELD, FHIR, Tax, MCP..."
                />
              </label>
              <div
                className="usr-inline"
                role="group"
                aria-label="Filter plugins by category"
              >
                {categories.map((cat) => (
                  <button
                    key={cat}
                    type="button"
                    aria-pressed={selectedCategory === cat}
                    className="usr-small-btn"
                    style={{
                      borderRadius: "999px",
                      border: "1px solid var(--line)",
                      background:
                        selectedCategory === cat ? "#111318" : "#f4f5f8",
                      color: selectedCategory === cat ? "#ffffff" : "#2f3440",
                      cursor: "pointer",
                    }}
                    onClick={() => setSelectedCategory(cat)}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {loading ? (
            <div className="usr-card">
              <p className="usr-muted" style={{ margin: 0 }}>
                Loading verified marketplace extensions...
              </p>
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(auto-fit, minmax(min(320px, 100%), 1fr))",
                gap: "16px",
              }}
            >
              {filteredCatalog.map((plugin) => {
                const isInstalled = plugin.install_status === "installed";
                const isPaused = plugin.install_status === "paused";
                const isBusy = busySlug === plugin.slug;
                return (
                  <article
                    key={plugin.slug}
                    className="usr-card"
                    style={{
                      marginBottom: 0,
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      gap: "14px",
                    }}
                  >
                    <div>
                      <div
                        className="usr-inline"
                        style={{ marginBottom: "8px" }}
                      >
                        <span
                          className={
                            plugin.verified
                              ? "usr-badge usr-badge-ai"
                              : "usr-badge usr-badge-fallback"
                          }
                        >
                          {plugin.verified ? "VERIFIED" : "PRIVATE SDK"}
                        </span>
                        <span className="usr-badge">
                          {protocolLabel(plugin.protocol)}
                        </span>
                        <span className="usr-badge">v{plugin.version}</span>
                      </div>
                      <h2
                        id={`plugin-card-${plugin.slug}`}
                        style={{ margin: "0 0 4px", fontSize: "1.1rem" }}
                      >
                        {plugin.display_name}
                      </h2>
                      <div
                        className="usr-muted"
                        style={{ fontSize: "0.8rem", marginBottom: "8px" }}
                      >
                        {plugin.publisher_name} · {plugin.category}
                      </div>
                      <p
                        style={{
                          margin: "0 0 10px",
                          fontSize: "0.88rem",
                          color: "#2f3440",
                        }}
                      >
                        {plugin.summary}
                      </p>
                      <div
                        className="usr-inline"
                        style={{ gap: "6px", marginBottom: "8px" }}
                      >
                        {plugin.naics_tags.map((tag) => (
                          <span key={tag} className="usr-badge">
                            {tag}
                          </span>
                        ))}
                      </div>
                      <div
                        className="usr-muted"
                        style={{ fontSize: "0.78rem" }}
                      >
                        Scopes: {plugin.requested_scopes.join(", ")}
                      </div>
                    </div>

                    <div className="usr-inline">
                      {isInstalled ? (
                        <>
                          <span className="usr-badge usr-badge-ai">
                            INSTALLED
                          </span>
                          <button
                            type="button"
                            className="button secondary usr-small-btn"
                            disabled={isBusy}
                            onClick={() =>
                              handleStatusChange(plugin.slug, "paused")
                            }
                          >
                            Pause
                          </button>
                          <button
                            type="button"
                            className="usr-small-btn usr-danger"
                            disabled={isBusy}
                            onClick={() =>
                              handleStatusChange(plugin.slug, "uninstalled")
                            }
                          >
                            Uninstall
                          </button>
                        </>
                      ) : isPaused ? (
                        <>
                          <span className="usr-badge usr-badge-fallback">
                            PAUSED
                          </span>
                          <button
                            type="button"
                            className="button usr-small-btn"
                            disabled={isBusy}
                            onClick={() =>
                              handleStatusChange(plugin.slug, "installed")
                            }
                          >
                            Resume
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          className="button usr-small-btn"
                          disabled={isBusy}
                          onClick={() => handleInstall(plugin.slug)}
                        >
                          1-Click Install
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      ) : null}

      {activeTab === "installed" ? (
        <section
          id="panel-mkt-installed"
          role="tabpanel"
          aria-labelledby="tab-mkt-installed"
          className="usr-card"
        >
          <h2 style={{ marginBottom: "6px" }}>
            Installed Workspace Extensions
          </h2>
          <p className="usr-muted" style={{ marginTop: 0 }}>
            All extensions run in isolated HTTPS / Remote MCP / HMAC-SHA256
            boundaries and never gain direct SQL access to your PostgreSQL
            workspace.
          </p>
          {!data || data.installations.length === 0 ? (
            <p className="usr-muted" style={{ margin: 0 }}>
              No marketplace plugins installed yet. Choose any verified
              connector from the Plugin Catalog tab.
            </p>
          ) : (
            <div
              style={{ overflowX: "auto" }}
              tabIndex={0}
              role="region"
              aria-label="Installed workspace extensions table"
            >
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  minWidth: "740px",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--line)",
                      textAlign: "left",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <th style={{ padding: "8px 10px" }}>Extension</th>
                    <th style={{ padding: "8px 10px" }}>Protocol</th>
                    <th style={{ padding: "8px 10px" }}>Granted Scopes</th>
                    <th style={{ padding: "8px 10px" }}>Status</th>
                    <th style={{ padding: "8px 10px" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {data.installations.map((inst) => (
                    <tr
                      key={inst.id}
                      style={{ borderBottom: "1px solid var(--line)" }}
                    >
                      <td style={{ padding: "8px 10px" }}>
                        <strong>{inst.display_name}</strong>
                        <div
                          className="usr-muted"
                          style={{ fontSize: "0.78rem" }}
                        >
                          {inst.plugin_slug} · v{inst.plugin_version}
                        </div>
                      </td>
                      <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                        <span className="usr-badge">
                          {protocolLabel(inst.protocol)}
                        </span>
                      </td>
                      <td style={{ padding: "8px 10px", fontSize: "0.82rem" }}>
                        {inst.granted_scopes.join(", ")}
                      </td>
                      <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                        <span
                          className={
                            inst.status === "installed"
                              ? "usr-badge usr-badge-ai"
                              : "usr-badge"
                          }
                        >
                          {inst.status.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                        <div className="usr-inline" style={{ gap: "6px" }}>
                          {inst.status === "installed" ? (
                            <button
                              type="button"
                              className="button secondary usr-small-btn"
                              disabled={busySlug === inst.plugin_slug}
                              onClick={() =>
                                handleStatusChange(inst.plugin_slug, "paused")
                              }
                            >
                              Pause
                            </button>
                          ) : (
                            <button
                              type="button"
                              className="button usr-small-btn"
                              disabled={busySlug === inst.plugin_slug}
                              onClick={() =>
                                handleStatusChange(
                                  inst.plugin_slug,
                                  "installed",
                                )
                              }
                            >
                              Activate
                            </button>
                          )}
                          {inst.status !== "uninstalled" ? (
                            <button
                              type="button"
                              className="usr-small-btn usr-danger"
                              disabled={busySlug === inst.plugin_slug}
                              onClick={() =>
                                handleStatusChange(
                                  inst.plugin_slug,
                                  "uninstalled",
                                )
                              }
                            >
                              Uninstall
                            </button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ) : null}

      {activeTab === "sdk" ? (
        <section
          id="panel-mkt-sdk"
          role="tabpanel"
          aria-labelledby="tab-mkt-sdk"
          className="usr-stack"
        >
          <div className="usr-card" style={{ marginBottom: 0 }}>
            <h2 style={{ marginBottom: "6px" }}>
              Developer SDK Manifest Editor (<code>amarkal-plugin.json</code>)
            </h2>
            <p className="usr-muted" style={{ marginTop: 0 }}>
              Build bespoke vertical integrations (custom medical devices,
              regional customs terminals, ERP bridges) with strict HTTPS SSRF
              protection and explicit least-privilege scopes.
            </p>

            <div className="usr-stack">
              <div className="usr-inline">
                <button
                  type="button"
                  className="button secondary usr-small-btn"
                  onClick={() => {
                    if (data) {
                      setManifestText(
                        JSON.stringify(data.sdk_manifest_template, null, 2),
                      );
                    }
                  }}
                >
                  Reset to SDK v1.0 Template
                </button>
                <label style={{ margin: 0 }}>
                  <span className="sr-only">Submission visibility mode</span>
                  <select
                    aria-label="Submission visibility mode"
                    value={publishMode}
                    onChange={(e) =>
                      setPublishMode(
                        e.target.value as
                          "published_private" | "submitted_for_review",
                      )
                    }
                  >
                    <option value="published_private">
                      Publish Privately to My Workspace
                    </option>
                    <option value="submitted_for_review">
                      Submit for Public Marketplace Review
                    </option>
                  </select>
                </label>
              </div>

              <label>
                Manifest JSON (amarkal-plugin.json)
                <textarea
                  className="usr-textarea"
                  rows={14}
                  style={{ fontFamily: "var(--font-mono), monospace" }}
                  value={manifestText}
                  onChange={(e) => setManifestText(e.target.value)}
                />
              </label>

              <div className="usr-inline">
                <button
                  type="button"
                  className="button secondary usr-small-btn"
                  disabled={busySdk}
                  onClick={handleValidateManifest}
                >
                  Validate Manifest (Dry Run)
                </button>
                <button
                  type="button"
                  className="button usr-small-btn"
                  disabled={busySdk}
                  onClick={handleSubmitManifest}
                >
                  Save &amp; Register Extension
                </button>
              </div>

              {validationResult ? (
                <div
                  style={{
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    padding: "14px",
                    background: validationResult.valid ? "#e9f6ee" : "#fcf0ee",
                  }}
                >
                  <strong>
                    {validationResult.valid
                      ? "✓ Manifest Validated Successfully"
                      : "✗ Manifest Validation Errors"}
                  </strong>
                  {validationResult.errors.length > 0 ? (
                    <ul style={{ margin: "6px 0 0", color: "#8a1c19" }}>
                      {validationResult.errors.map((e, idx) => (
                        <li key={idx}>{e}</li>
                      ))}
                    </ul>
                  ) : null}
                  {validationResult.warnings.length > 0 ? (
                    <ul style={{ margin: "6px 0 0", color: "#6b4e16" }}>
                      {validationResult.warnings.map((w, idx) => (
                        <li key={idx}>Warning: {w}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>

          {data && data.submissions.length > 0 ? (
            <div className="usr-card" style={{ marginBottom: 0 }}>
              <h2 style={{ marginBottom: "8px" }}>
                Your Workspace SDK Submissions ({data.submissions.length})
              </h2>
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Developer SDK submissions table"
              >
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid var(--line)",
                        textAlign: "left",
                      }}
                    >
                      <th style={{ padding: "8px 10px" }}>Slug &amp; Name</th>
                      <th style={{ padding: "8px 10px" }}>Version</th>
                      <th style={{ padding: "8px 10px" }}>Protocol</th>
                      <th style={{ padding: "8px 10px" }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.submissions.map((sub) => (
                      <tr
                        key={sub.id}
                        style={{ borderBottom: "1px solid var(--line)" }}
                      >
                        <td style={{ padding: "8px 10px" }}>
                          <strong>{sub.display_name}</strong> ({sub.plugin_slug}
                          )
                        </td>
                        <td style={{ padding: "8px 10px" }}>v{sub.version}</td>
                        <td style={{ padding: "8px 10px" }}>
                          {protocolLabel(sub.protocol)}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span className="usr-badge">
                            {sub.validation_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
