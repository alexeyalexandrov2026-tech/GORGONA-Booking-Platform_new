"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { accessToken, authManager, signIn } from "../lib/auth";
import { setActiveSalonId } from "../lib/management-api";
import {
  fetchOnboardingPresets,
  fetchOnboardingStatus,
  registerSelfServiceBusiness,
  type IndustryPreset,
  type OnboardingStatus,
  type RegisterBusinessResult,
} from "../lib/onboarding-api";

const COMMON_TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "America/Anchorage",
  "Pacific/Honolulu",
  "UTC",
];

const FORMAT_OPTIONS = [
  { id: "b2c", label: "B2C (Consumers)" },
  { id: "b2b", label: "B2B (Businesses)" },
  { id: "marketplace", label: "Marketplace" },
  { id: "franchise", label: "Franchise / Network" },
  { id: "holding", label: "Holding / Multi-entity" },
];

function slugify(input: string): string {
  return input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50);
}

export function SelfServiceOnboarding() {
  const router = useRouter();
  const [configured, setConfigured] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [status, setStatus] = useState<OnboardingStatus | null>(null);
  const [presets, setPresets] = useState<IndustryPreset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [created, setCreated] = useState<RegisterBusinessResult | null>(null);

  const [businessName, setBusinessName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [locationName, setLocationName] = useState("Main Location");
  const [timezone, setTimezone] = useState("America/New_York");
  const [query, setQuery] = useState("");
  const [selectedIndustries, setSelectedIndustries] = useState<number[]>([1]);
  const [formats, setFormats] = useState<string[]>(["b2c"]);
  const [idempotencyKey] = useState(() =>
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `ss-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const [manager, list] = await Promise.all([
          authManager(),
          fetchOnboardingPresets(),
        ]);
        if (!active) return;
        setConfigured(Boolean(manager));
        setPresets(list);
        const tok = await accessToken();
        if (!active) return;
        if (tok) {
          setSignedIn(true);
          const st = await fetchOnboardingStatus();
          if (active) setStatus(st);
        }
      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not initialize business registration.",
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const filteredPresets = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return presets;
    return presets.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.examples.toLowerCase().includes(q) ||
        p.code.toLowerCase().includes(q) ||
        p.naics_sectors.some((s) => s.includes(q)),
    );
  }, [presets, query]);

  const modulePreview = useMemo(() => {
    const enableable = new Set<string>();
    const pending = new Set<string>();
    for (const id of selectedIndustries) {
      const p = presets.find((item) => item.id === id);
      if (!p) continue;
      for (const m of p.enableable_module_ids) enableable.add(m);
      for (const m of p.pending_module_ids) pending.add(m);
    }
    return {
      enableable: Array.from(enableable).sort(),
      pending: Array.from(pending).sort(),
    };
  }, [presets, selectedIndustries]);

  const toggleIndustry = (id: number) => {
    setSelectedIndustries((prev) =>
      prev.includes(id)
        ? prev.length > 1
          ? prev.filter((x) => x !== id)
          : prev
        : [...prev, id].sort((a, b) => a - b),
    );
  };

  const toggleFormat = (id: string) => {
    setFormats((prev) =>
      prev.includes(id)
        ? prev.length > 1
          ? prev.filter((x) => x !== id)
          : prev
        : [...prev, id],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const effectiveSlug = slug.trim() || slugify(businessName);
    if (!businessName.trim() || effectiveSlug.length < 2) {
      setError("Enter a business name and valid URL slug (at least 2 chars).");
      return;
    }
    setSubmitting(true);
    try {
      const res = await registerSelfServiceBusiness(
        {
          business_name: businessName.trim(),
          slug: effectiveSlug,
          location_name: locationName.trim() || "Main Location",
          timezone,
          industry_ids: selectedIndustries,
          business_formats: formats,
        },
        idempotencyKey,
      );
      setActiveSalonId(res.business_id);
      setCreated(res);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Business registration failed.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="management-shell">
      <header className="mgmt-header">
        <div className="mgmt-brand-area">
          <Link href="/overview/" className="mgmt-brand">
            GORGONA <span>Self-Service Onboarding</span>
          </Link>
        </div>
        <div className="mgmt-header-actions">
          {status?.businesses.length ? (
            <Link href="/overview/" className="mgmt-nav-link">
              Back to workspace
            </Link>
          ) : null}
          <Link href="/legal/terms/" className="mgmt-nav-link">
            Terms
          </Link>
          <Link href="/legal/privacy/" className="mgmt-nav-link">
            Privacy
          </Link>
        </div>
      </header>
      <main className="mgmt-main" id="main-content">
        <h1>Create your GORGONA business workspace</h1>
        <p>
          Register your company, select one or more of the 39 supported
          industries, and launch your management cabinet immediately without
          waiting for administrator approval.
        </p>

        {error && (
          <div className="mgmt-error-banner" role="alert">
            <p>{error}</p>
          </div>
        )}

        {loading ? (
          <div className="mgmt-loading" aria-live="polite">
            <p>Loading industry catalog and session…</p>
          </div>
        ) : !signedIn ? (
          <section className="mgmt-auth-gate">
            <h2>Sign in to register your business</h2>
            <p>
              {configured
                ? "Sign in with your Microsoft account to create your company workspace and become its initial owner."
                : "Sign-in is not configured in this environment yet."}
            </p>
            {configured && (
              <button onClick={() => void signIn("/onboarding/")}>
                Sign in to continue
              </button>
            )}
          </section>
        ) : created ? (
          <section className="mgmt-card" aria-live="polite">
            <h2>Workspace ready: {created.business_name}</h2>
            <p>
              Your company (<code>{created.slug}</code>) is active with{" "}
              <strong>{created.effective_module_ids.length}</strong> verified
              modules enabled on configuration v{created.configuration_version}.
            </p>
            <p>
              <strong>Enabled modules:</strong>{" "}
              {created.effective_module_ids.join(", ")}
            </p>
            {created.pending_module_ids.length > 0 && (
              <p className="hold-note">
                Additional specialized modules (
                {created.pending_module_ids.join(", ")}) are listed in Business
                Profile and can be enabled once their industry acceptance is
                recorded.
              </p>
            )}
            <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
              <button onClick={() => router.push("/overview/")}>
                Open workspace overview
              </button>
              <Link href="/business/" className="secondary">
                Configure business profile
              </Link>
            </div>
          </section>
        ) : (
          <form onSubmit={(e) => void handleSubmit(e)} className="mgmt-card">
            <h2>1. Company & primary location</h2>
            <div className="form-grid">
              <label>
                Business name
                <input
                  type="text"
                  required
                  maxLength={200}
                  value={businessName}
                  onChange={(e) => {
                    const next = e.target.value;
                    setBusinessName(next);
                    if (!slugEdited) setSlug(slugify(next));
                  }}
                  placeholder="Acme Studio LLC"
                />
              </label>
              <label>
                URL slug (lowercase letters, digits, hyphens)
                <input
                  type="text"
                  required
                  minLength={2}
                  maxLength={63}
                  pattern="^[a-z0-9]+(-[a-z0-9]+)*$"
                  value={slug}
                  onChange={(e) => {
                    setSlugEdited(true);
                    setSlug(e.target.value.toLowerCase());
                  }}
                  placeholder="acme-studio"
                />
              </label>
              <label>
                Primary location name
                <input
                  type="text"
                  required
                  maxLength={200}
                  value={locationName}
                  onChange={(e) => setLocationName(e.target.value)}
                />
              </label>
              <label>
                Location IANA time zone
                <select
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                >
                  {COMMON_TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <h2 style={{ marginTop: "1.5rem" }}>2. Business formats</h2>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
              {FORMAT_OPTIONS.map((f) => (
                <label key={f.id} style={{ display: "flex", gap: "0.4rem" }}>
                  <input
                    type="checkbox"
                    checked={formats.includes(f.id)}
                    onChange={() => toggleFormat(f.id)}
                  />
                  {f.label}
                </label>
              ))}
            </div>

            <h2 style={{ marginTop: "1.5rem" }}>
              3. Industries ({selectedIndustries.length} of {presets.length}{" "}
              selected)
            </h2>
            <label>
              Search 39 industries by name, activity, or NAICS sector
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search beauty, construction, rental, healthcare, 54…"
              />
            </label>
            <div
              tabIndex={0}
              className="mgmt-table-container"
              style={{
                maxHeight: "320px",
                overflowY: "auto",
                marginTop: "0.75rem",
                border: "1px solid var(--line, #d0d7de)",
                padding: "0.75rem",
              }}
            >
              {filteredPresets.map((ind) => (
                <label
                  key={ind.id}
                  style={{
                    display: "block",
                    padding: "0.4rem 0",
                    borderBottom: "1px solid rgba(0,0,0,0.06)",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={selectedIndustries.includes(ind.id)}
                    onChange={() => toggleIndustry(ind.id)}
                    style={{ marginRight: "0.5rem" }}
                  />
                  <strong>
                    #{ind.id} {ind.name}
                  </strong>{" "}
                  <span>(NAICS {ind.naics_sectors.join(", ")})</span>
                  <div style={{ fontSize: "0.85rem", color: "#3f3832" }}>
                    {ind.examples}
                  </div>
                </label>
              ))}
            </div>

            <section style={{ marginTop: "1.25rem" }}>
              <h3>Modules activated on creation</h3>
              <p>
                <strong>Core + verified modules:</strong> organization,
                users_access, {modulePreview.enableable.join(", ")}
              </p>
              {modulePreview.pending.length > 0 && (
                <p className="hold-note">
                  Specialized modules awaiting acceptance (not auto-enabled):{" "}
                  {modulePreview.pending.join(", ")}
                </p>
              )}
            </section>

            <p style={{ fontSize: "0.85rem", marginTop: "1rem" }}>
              By creating a workspace, you agree to the{" "}
              <Link href="/legal/terms/">Terms of Service</Link> and{" "}
              <Link href="/legal/privacy/">Privacy Policy</Link>.
            </p>
            <button type="submit" disabled={submitting}>
              {submitting ? "Creating workspace…" : "Create business workspace"}
            </button>
          </form>
        )}
      </main>
    </div>
  );
}
