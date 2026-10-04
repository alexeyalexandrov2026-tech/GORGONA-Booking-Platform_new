"use client";

import { useEffect, useState } from "react";
import { ManagementLayout } from "../../components/management-layout";
import { BusinessConfiguration } from "../../components/business-configuration";
import { BusinessGroups } from "../../components/business-groups";
import { Delegations } from "../../components/delegations";
import { Departments } from "../../components/departments";
import { LegalEntities } from "../../components/legal-entities";
import type {
  Business,
  BusinessFormat,
  IndustryCatalog,
  ProfileInput,
} from "../../lib/business-contracts";
import {
  fetchBusiness,
  fetchIndustryCatalog,
  ManagementApiError,
  saveBusinessProfile,
} from "../../lib/management-api";

const FORMAT_LABELS: Record<BusinessFormat, string> = {
  b2b: "Business customers (B2B)",
  b2c: "Individual customers (B2C)",
  marketplace: "Marketplace operator",
  franchise: "Franchise",
  holding: "Group of companies",
};

export default function BusinessPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => (
        <BusinessContent
          key={salonId}
          businessId={salonId}
          canManage={me.memberships.some(
            (m) =>
              m.salon_id === salonId &&
              m.location_id === null &&
              ["owner", "manager"].includes(m.role),
          )}
          canIssue={me.memberships.some(
            (m) =>
              m.salon_id === salonId &&
              m.location_id === null &&
              m.role === "owner",
          )}
        />
      )}
    </ManagementLayout>
  );
}

function BusinessContent({
  businessId,
  canManage,
  canIssue,
}: {
  businessId: string;
  canManage: boolean;
  canIssue: boolean;
}) {
  const [business, setBusiness] = useState<Business | null>(null);
  const [catalog, setCatalog] = useState<IndustryCatalog | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [formats, setFormats] = useState<BusinessFormat[]>([]);
  const [customName, setCustomName] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [conflict, setConflict] = useState(false);
  // Keep the exact command after an uncertain network result; retry cannot create a second version.
  const [pending, setPending] = useState<{
    key: string;
    body: ProfileInput;
  } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([fetchBusiness(businessId), fetchIndustryCatalog(businessId)])
      .then(([data, available]) => {
        if (!active) return;
        setBusiness(data);
        setCatalog(available);
        setSelected(data.profile?.industry_ids ?? []);
        setFormats(data.profile?.business_formats ?? []);
        setCustomName(data.profile?.custom_activity_name ?? "");
        setError(null);
        setConflict(false);
        setPending(null);
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load the business profile.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reload]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!business || !catalog || !canManage || !selected.length || conflict)
      return;
    const command = pending ?? {
      key: crypto.randomUUID(),
      body: {
        schema_version: 1 as const,
        catalog_version: catalog.catalog_version,
        expected_revision: business.profile?.revision ?? 0,
        industry_ids: [...selected].sort((a, b) => a - b),
        business_formats: [...formats].sort(),
        custom_activity_name: customName.trim() || null,
      },
    };
    setPending(command);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const profile = await saveBusinessProfile(
        businessId,
        command.body,
        command.key,
      );
      setBusiness({ ...business, profile });
      setPending(null);
      setMessage(`Business profile saved. Draft version ${profile.revision}.`);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Unable to save the profile.",
      );
      if (
        err instanceof ManagementApiError &&
        err.status &&
        err.status >= 400 &&
        err.status < 500
      ) {
        setPending(null);
        setConflict(err.status === 409);
      }
    } finally {
      setBusy(false);
    }
  }
  const visible =
    catalog?.industries.filter((item) =>
      `${item.name} ${item.examples}`
        .toLowerCase()
        .includes(query.toLowerCase().trim()),
    ) ?? [];
  const locked = !canManage || busy || Boolean(pending) || conflict;
  const refresh = () => {
    setLoading(true);
    setMessage(null);
    setReload((value) => value + 1);
  };
  return (
    <div>
      <div className="mgmt-section-header">
        <div>
          <h2>Business profile</h2>
          <p className="muted">
            Choose all the activities your business provides.
          </p>
        </div>
        <button
          type="button"
          className="secondary"
          onClick={refresh}
          disabled={busy || Boolean(pending)}
        >
          Reload saved profile
        </button>
      </div>
      {error && (
        <div className="mgmt-error-banner" role="alert">
          <p>{error}</p>
          {conflict && (
            <p>
              Your edits are still shown. Reload the saved profile before
              applying them again.
            </p>
          )}
          {!business && (
            <button type="button" onClick={refresh}>
              Retry loading
            </button>
          )}
        </div>
      )}
      {message && (
        <p role="status" className="hold-note">
          {message}
        </p>
      )}
      {loading ? (
        <p role="status">Loading business profile…</p>
      ) : (
        business &&
        catalog && (
          <>
            <p>
              <strong>{business.display_name}</strong> ·{" "}
              {business.profile
                ? `Draft version ${business.profile.revision}`
                : "No profile saved yet"}
            </p>
            <p className="muted">
              These choices prepare your business setup. Full industry workflows
              are being added in stages; choosing an activity does not activate
              them.
            </p>
            {!canManage && (
              <p className="hold-note">
                Your role can view this profile. A manager or owner can edit it.
              </p>
            )}
            {pending && !busy && (
              <p role="status">
                The save result is uncertain. Retry the same save to confirm it.
              </p>
            )}
            <form onSubmit={(event) => void save(event)}>
              <label htmlFor="industry-search">Find an activity</label>
              <input
                id="industry-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Beauty, trucking, construction, rentals…"
              />
              <p aria-live="polite">
                {selected.length} selected · {visible.length} matching
                activities
              </p>
              <fieldset disabled={locked}>
                <legend>Business activities</legend>
                <div className="business-activities">
                  {visible.map((item) => (
                    <label key={item.id} className="business-activity">
                      <input
                        type="checkbox"
                        checked={selected.includes(item.id)}
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, item.id]
                              : current.filter((id) => id !== item.id),
                          )
                        }
                      />
                      <span>
                        <strong>{item.name}</strong>
                        <span className="muted">{item.examples}</span>
                      </span>
                    </label>
                  ))}
                </div>
                {!visible.length && (
                  <p>
                    No matching activities. Try another search; previously
                    selected activities remain selected.
                  </p>
                )}
              </fieldset>
              <fieldset disabled={locked}>
                <legend>How your business works</legend>
                <div className="business-formats">
                  {catalog.business_formats.map((format) => (
                    <label key={format}>
                      <input
                        type="checkbox"
                        checked={formats.includes(format)}
                        onChange={(event) =>
                          setFormats((current) =>
                            event.target.checked
                              ? [...current, format]
                              : current.filter((value) => value !== format),
                          )
                        }
                      />{" "}
                      {FORMAT_LABELS[format]}
                    </label>
                  ))}
                </div>
                <label htmlFor="custom-activity">
                  Your activity name (optional)
                </label>
                <input
                  id="custom-activity"
                  value={customName}
                  maxLength={200}
                  onChange={(event) => setCustomName(event.target.value)}
                />
              </fieldset>
              {canManage && (
                <button
                  type="submit"
                  disabled={busy || conflict || selected.length === 0}
                >
                  {busy
                    ? "Saving…"
                    : pending
                      ? "Retry same save"
                      : "Save business profile"}
                </button>
              )}
            </form>
            <BusinessConfiguration
              businessId={businessId}
              canManage={canManage}
              profileRevision={business.profile?.revision ?? null}
              industryNames={Object.fromEntries(
                (catalog?.industries ?? []).map((item) => [item.id, item.name]),
              )}
            />
            <LegalEntities businessId={businessId} canManage={canManage} />
            <Departments
              businessId={businessId}
              canManage={canManage}
              locations={business.locations}
            />
            <BusinessGroups businessId={businessId} canManage={canManage} />
            {canManage && (
              <Delegations
                businessId={businessId}
                canIssue={canIssue}
                canManage={canManage}
                locations={business.locations}
              />
            )}
          </>
        )
      )}
    </div>
  );
}
