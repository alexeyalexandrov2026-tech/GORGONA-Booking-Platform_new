"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AbacOverviewResponse,
  assignAbacPolicy,
  BaseRole,
  createAbacPolicy,
  deleteAbacPolicy,
  fetchAbacOverview,
  formatUsdCents,
  installAbacPreset,
  revokeAbacAssignment,
  simulateAbacPolicy,
  SimulateAbacResponse,
  toggleAbacPolicyActive,
} from "../lib/abac-policies-api";

type ActiveTab = "policies" | "builder" | "assignments" | "simulator";

const TIMEZONE_OPTIONS = [
  "America/Chicago",
  "America/New_York",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "UTC",
] as const;

const WEEKDAYS = [
  { id: 1, label: "Mon" },
  { id: 2, label: "Tue" },
  { id: 3, label: "Wed" },
  { id: 4, label: "Thu" },
  { id: 5, label: "Fri" },
  { id: 6, label: "Sat" },
  { id: 7, label: "Sun" },
] as const;

const FIELD_MASK_LABELS: Record<string, { label: string; sample: string }> = {
  phone: { label: "Phone Numbers", sample: "***-***-4821" },
  email: { label: "Email Addresses", sample: "c***@acme.us" },
  tax_id: { label: "Tax ID / EIN / SSN", sample: "**-***9104" },
  bank_account: { label: "Bank Account / IBAN", sample: "••••4321" },
  compensation: { label: "Payroll & Salaries", sample: "[REDACTED]" },
  unit_cost: { label: "Unit Cost & COGS", sample: "[REDACTED]" },
  contract_value: { label: "Contract Values", sample: "[REDACTED]" },
};

const QUICK_DENY_GROUPS: readonly {
  group: string;
  perms: readonly string[];
}[] = [
  {
    group: "Finance & Ledger",
    perms: ["finance.manage", "finance.close", "documents.manage"],
  },
  {
    group: "CRM & Contracts",
    perms: ["counterparties.manage", "booking.write", "catalog.manage"],
  },
  {
    group: "Operations & Supply",
    perms: [
      "inventory.manage",
      "supply.manage",
      "workforce.manage",
      "transport.manage",
    ],
  },
  {
    group: "Governance & Admin",
    perms: [
      "members.manage",
      "members.manage_admins",
      "settings.manage",
      "enterprise.manage",
    ],
  },
];

function hhmmToMinutes(hhmm: string): number {
  const parts = hhmm.split(":");
  const h = Number(parts[0] ?? 9);
  const m = Number(parts[1] ?? 0);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return 540;
  return Math.max(0, Math.min(1440, h * 60 + m));
}

function parseCsvList(raw: string): string[] {
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function AbacAccessControlHub({ businessId }: { businessId: string }) {
  const [data, setData] = useState<AbacOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("policies");
  const [reloadTick, setReloadTick] = useState(0);

  // Builder state
  const [policyCode, setPolicyCode] = useState("regional-contracts-guard");
  const [displayName, setDisplayName] = useState(
    "Regional Account Manager (Masked Phone · 09:00–18:00)",
  );
  const [description, setDescription] = useState(
    "Restricts client records to assigned US region, masks phone & tax IDs, and locks contract edits after 18:00 local time.",
  );
  const [baseRole, setBaseRole] = useState<BaseRole>("manager");
  const [deniedPerms, setDeniedPerms] = useState<string[]>([
    "finance.close",
    "settings.manage",
  ]);
  const [regionsInput, setRegionsInput] = useState("Midwest, IL, OH, WI");
  const [maskedFields, setMaskedFields] = useState<string[]>([
    "phone",
    "tax_id",
  ]);
  const [windowEnabled, setWindowEnabled] = useState(true);
  const [windowTz, setWindowTz] = useState("America/Chicago");
  const [windowStart, setWindowStart] = useState("09:00");
  const [windowEnd, setWindowEnd] = useState("18:00");
  const [windowDays, setWindowDays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [windowPerms, setWindowPerms] = useState<string[]>([
    "counterparties.manage",
    "documents.manage",
  ]);
  const [limitUsd, setLimitUsd] = useState("50000");

  // Assignment state
  const [assignPolicyId, setAssignPolicyId] = useState("");
  const [assignUserId, setAssignUserId] = useState("");
  const [assignRegionsOverride, setAssignRegionsOverride] = useState("");

  // Simulator state
  const [simPolicyId, setSimPolicyId] = useState("");
  const [simPermission, setSimPermission] = useState("counterparties.manage");
  const [simLocalUtc, setSimLocalUtc] = useState("2026-11-26T00:30:00Z"); // 18:30 CST
  const [simRegion, setSimRegion] = useState("Midwest");
  const [simAmountUsd, setSimAmountUsd] = useState("42000");
  const [simResult, setSimResult] = useState<SimulateAbacResponse | null>(null);

  useEffect(() => {
    let mounted = true;
    fetchAbacOverview(businessId)
      .then((res) => {
        if (!mounted) return;
        setData(res);
        setError(null);
        const firstPolicy = res.policies[0];
        if (firstPolicy) {
          setAssignPolicyId((prev) => prev || firstPolicy.id);
          setSimPolicyId((prev) => prev || firstPolicy.id);
        }
        const firstMember = res.members[0];
        if (firstMember) {
          setAssignUserId((prev) => prev || firstMember.user_id);
        }
      })
      .catch((err: unknown) => {
        if (!mounted) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [businessId, reloadTick]);

  const refresh = useCallback(() => {
    setLoading(true);
    setReloadTick((t) => t + 1);
  }, []);

  const kpis = useMemo(() => {
    const policies = data?.policies ?? [];
    const activePolicies = policies.filter((p) => p.is_active);
    return {
      activePolicies: activePolicies.length,
      totalPolicies: policies.length,
      assignments: data?.assignments.filter((a) => a.is_active).length ?? 0,
      maskingPolicies: activePolicies.filter((p) => p.masked_fields.length > 0)
        .length,
      timeLockPolicies: activePolicies.filter((p) => p.write_window_enabled)
        .length,
    };
  }, [data]);

  const toggleListValue = (
    current: string[],
    value: string,
    setter: React.Dispatch<React.SetStateAction<string[]>>,
  ) => {
    setter(
      current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    );
  };

  const toggleWeekday = (dayId: number) => {
    setWindowDays((prev) =>
      prev.includes(dayId)
        ? prev.filter((d) => d !== dayId)
        : [...prev, dayId].sort((a, b) => a - b),
    );
  };

  async function handleInstallPreset(presetCode: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await installAbacPreset(businessId, presetCode);
      setNotice(`Preset "${created.display_name}" installed and active.`);
      setSimPolicyId(created.id);
      setAssignPolicyId(created.id);
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleCreatePolicy(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const parsedUsd = limitUsd.trim() ? Number(limitUsd.trim()) : null;
      const maxCents =
        parsedUsd !== null && Number.isFinite(parsedUsd) && parsedUsd >= 0
          ? Math.round(parsedUsd * 100)
          : null;
      const created = await createAbacPolicy(businessId, {
        policy_code: policyCode.trim().toLowerCase(),
        display_name: displayName.trim(),
        description: description.trim(),
        base_role: baseRole,
        is_active: true,
        denied_permissions: deniedPerms,
        allowed_regions: parseCsvList(regionsInput),
        masked_fields: maskedFields,
        write_window_enabled: windowEnabled,
        write_window_timezone: windowTz,
        write_window_start_minute: hhmmToMinutes(windowStart),
        write_window_end_minute: hhmmToMinutes(windowEnd),
        write_window_days: windowDays,
        write_window_permissions: windowPerms,
        max_financial_amount_cents: maxCents,
      });
      setNotice(`Custom ABAC policy "${created.display_name}" created.`);
      setSimPolicyId(created.id);
      setAssignPolicyId(created.id);
      setActiveTab("policies");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleToggleActive(policyId: string, nextActive: boolean) {
    setBusy(true);
    setError(null);
    try {
      await toggleAbacPolicyActive(businessId, policyId, nextActive);
      setNotice(nextActive ? "Policy re-activated." : "Policy paused.");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeletePolicy(policyId: string) {
    setBusy(true);
    setError(null);
    try {
      await deleteAbacPolicy(businessId, policyId);
      setNotice("ABAC policy deleted.");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAssignPolicy(e: React.FormEvent) {
    e.preventDefault();
    if (!assignPolicyId || !assignUserId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const assigned = await assignAbacPolicy(businessId, {
        policy_id: assignPolicyId,
        user_id: assignUserId,
        assigned_regions_override: parseCsvList(assignRegionsOverride),
      });
      setNotice(
        `Assigned "${assigned.policy_name}" to ${assigned.member_name}.`,
      );
      setAssignRegionsOverride("");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevokeAssignment(assignmentId: string) {
    setBusy(true);
    setError(null);
    try {
      await revokeAbacAssignment(businessId, assignmentId);
      setNotice("Assignment revoked.");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRunSimulation(e: React.FormEvent) {
    e.preventDefault();
    if (!simPolicyId) return;
    setBusy(true);
    setError(null);
    try {
      const amtNum = simAmountUsd.trim() ? Number(simAmountUsd.trim()) : null;
      const result = await simulateAbacPolicy(businessId, {
        policy_id: simPolicyId,
        permission: simPermission,
        simulated_at_utc: simLocalUtc.trim() || undefined,
        record_region: simRegion.trim() || null,
        amount_cents:
          amtNum !== null && Number.isFinite(amtNum)
            ? Math.round(amtNum * 100)
            : null,
      });
      setSimResult(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      <div className="mgmt-section-header">
        <div>
          <span
            style={{
              display: "inline-block",
              fontSize: "0.75rem",
              fontWeight: 600,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "#334155",
              marginBottom: "4px",
            }}
          >
            Enterprise Governance · ABAC Restrictive Overlay
          </span>
          <h2 style={{ margin: 0 }}>Matrix Access Control & PII Masking</h2>
          <p
            style={{
              color: "var(--muted)",
              margin: "6px 0 0",
              fontSize: "0.92rem",
              maxWidth: "740px",
            }}
          >
            Layer granular regional scopes, automatic phone/email/EIN field
            masking, local-timezone write locks (e.g. contract edits only until
            18:00), and financial approval ceilings on top of PostgreSQL 18
            FORCE RLS without modifying core roles.
          </p>
        </div>
        <button
          type="button"
          className="secondary mgmt-action-btn"
          onClick={refresh}
          disabled={loading || busy}
        >
          {loading ? "Refreshing..." : "Refresh Matrix"}
        </button>
      </div>

      {error && (
        <div className="mgmt-error-banner" role="alert">
          <strong>Access control error:</strong> {error}
        </div>
      )}

      {notice && (
        <div
          role="status"
          style={{
            padding: "12px 16px",
            borderRadius: "10px",
            border: "1px solid #bbf7d0",
            background: "#f0fdf4",
            color: "#166534",
            fontSize: "0.9rem",
            fontWeight: 500,
          }}
        >
          {notice}
        </div>
      )}

      {/* KPI Strip */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
          gap: "16px",
        }}
      >
        <div className="mgmt-kpi-card" style={{ padding: "18px 20px" }}>
          <span className="mgmt-kpi-label">Active ABAC Policies</span>
          <div
            style={{ fontSize: "1.65rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.activePolicies}{" "}
            <span
              style={{
                fontSize: "0.85rem",
                fontWeight: 400,
                color: "var(--muted)",
              }}
            >
              / {kpis.totalPolicies} total
            </span>
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            Least-privilege overlay · FORCE RLS
          </div>
        </div>
        <div className="mgmt-kpi-card" style={{ padding: "18px 20px" }}>
          <span className="mgmt-kpi-label">Protected Assignments</span>
          <div
            style={{ fontSize: "1.65rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.assignments}
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            Active member-policy bindings
          </div>
        </div>
        <div className="mgmt-kpi-card" style={{ padding: "18px 20px" }}>
          <span className="mgmt-kpi-label">PII Field Masking</span>
          <div
            style={{ fontSize: "1.65rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.maskingPolicies}
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            Phone, Email, Tax ID & Payroll redaction
          </div>
        </div>
        <div className="mgmt-kpi-card" style={{ padding: "18px 20px" }}>
          <span className="mgmt-kpi-label">Time-Window Write Locks</span>
          <div
            style={{ fontSize: "1.65rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.timeLockPolicies}
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            IANA timezone shift enforcement
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div
        role="tablist"
        aria-label="Matrix access control views"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px",
          borderBottom: "1px solid var(--border, #e5e7eb)",
          paddingBottom: "12px",
        }}
      >
        {(
          [
            { id: "policies", label: "Policies & Enterprise Presets" },
            { id: "builder", label: "Create Custom Policy" },
            { id: "assignments", label: "Team Assignments" },
            { id: "simulator", label: "Live Policy Simulator" },
          ] as const
        ).map((tab) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: "9px 16px",
                borderRadius: "8px",
                border: selected ? "1px solid #0f172a" : "1px solid #d1d5db",
                background: selected ? "#0f172a" : "#ffffff",
                color: selected ? "#ffffff" : "#111827",
                fontWeight: 600,
                fontSize: "0.88rem",
                cursor: "pointer",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {loading && !data ? (
        <div className="mgmt-loading" aria-live="polite">
          Loading ABAC matrix policies...
        </div>
      ) : null}

      {/* TAB 1: Policies & Enterprise Presets */}
      {data && activeTab === "policies" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          <section className="mgmt-kpi-card" style={{ padding: "22px" }}>
            <h3 style={{ margin: "0 0 6px" }}>Active Custom Policies</h3>
            <p
              style={{
                margin: "0 0 16px",
                color: "var(--muted)",
                fontSize: "0.88rem",
              }}
            >
              Evaluated inside every PostgreSQL authorization transaction. Base
              membership roles establish the ceiling; policies only narrow
              permissions, mask PII, or lock after-hours edits.
            </p>
            {data.policies.length === 0 ? (
              <p style={{ color: "var(--muted)", margin: 0 }}>
                No custom ABAC policies yet. Install one of the enterprise
                presets below or build your own rule matrix.
              </p>
            ) : (
              <div
                tabIndex={0}
                role="region"
                aria-label="Active ABAC policies table"
                style={{ overflowX: "auto" }}
              >
                <table
                  style={{
                    width: "100%",
                    minWidth: "920px",
                    borderCollapse: "collapse",
                    fontSize: "0.86rem",
                  }}
                >
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid #e5e7eb",
                        textAlign: "left",
                        color: "#374151",
                      }}
                    >
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Policy
                      </th>
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Base Ceiling
                      </th>
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Regions
                      </th>
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Masked PII
                      </th>
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Write Window
                      </th>
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Deal Cap
                      </th>
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Members
                      </th>
                      <th style={{ padding: "10px 8px", whiteSpace: "nowrap" }}>
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.policies.map((policy) => (
                      <tr
                        key={policy.id}
                        style={{ borderBottom: "1px solid #f1f5f9" }}
                      >
                        <td style={{ padding: "12px 8px" }}>
                          <div style={{ fontWeight: 600, color: "#0f172a" }}>
                            {policy.display_name}
                          </div>
                          <div
                            style={{ fontSize: "0.78rem", color: "#475569" }}
                          >
                            <code>{policy.policy_code}</code> ·{" "}
                            {policy.denied_permissions.length} denied perms
                          </div>
                        </td>
                        <td
                          style={{ padding: "12px 8px", whiteSpace: "nowrap" }}
                        >
                          <span className="mgmt-status-pill">
                            {policy.base_role}
                          </span>
                        </td>
                        <td style={{ padding: "12px 8px" }}>
                          {policy.allowed_regions.length > 0
                            ? policy.allowed_regions.join(", ")
                            : "All regions"}
                        </td>
                        <td style={{ padding: "12px 8px" }}>
                          {policy.masked_fields.length > 0
                            ? policy.masked_fields.join(", ")
                            : "None"}
                        </td>
                        <td
                          style={{ padding: "12px 8px", whiteSpace: "nowrap" }}
                        >
                          {policy.write_window_summary}
                        </td>
                        <td
                          style={{ padding: "12px 8px", whiteSpace: "nowrap" }}
                        >
                          {formatUsdCents(policy.max_financial_amount_cents)}
                        </td>
                        <td
                          style={{ padding: "12px 8px", whiteSpace: "nowrap" }}
                        >
                          {policy.assigned_member_count}
                        </td>
                        <td
                          style={{ padding: "12px 8px", whiteSpace: "nowrap" }}
                        >
                          <div style={{ display: "flex", gap: "6px" }}>
                            <button
                              type="button"
                              className="secondary mgmt-btn-small"
                              disabled={busy}
                              onClick={() => {
                                setSimPolicyId(policy.id);
                                setActiveTab("simulator");
                              }}
                            >
                              Test
                            </button>
                            <button
                              type="button"
                              className="secondary mgmt-btn-small"
                              disabled={busy}
                              onClick={() =>
                                handleToggleActive(policy.id, !policy.is_active)
                              }
                            >
                              {policy.is_active ? "Pause" : "Resume"}
                            </button>
                            <button
                              type="button"
                              className="secondary mgmt-btn-small"
                              disabled={busy}
                              onClick={() => handleDeletePolicy(policy.id)}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="mgmt-kpi-card" style={{ padding: "22px" }}>
            <h3 style={{ margin: "0 0 6px" }}>
              1-Click Enterprise Policy Presets
            </h3>
            <p
              style={{
                margin: "0 0 16px",
                color: "var(--muted)",
                fontSize: "0.88rem",
              }}
            >
              Pre-built corporate governance templates for regional sales, dual
              AP control, fleet dispatch, and external CPA audits.
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(auto-fit, minmax(min(440px, 100%), 1fr))",
                gap: "16px",
              }}
            >
              {data.presets.map((preset) => (
                <div
                  key={preset.policy_code}
                  style={{
                    border: "1px solid #e2e8f0",
                    borderRadius: "12px",
                    padding: "16px",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    gap: "12px",
                    background: "#ffffff",
                  }}
                >
                  <div>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "8px",
                      }}
                    >
                      <strong style={{ fontSize: "0.95rem", color: "#0f172a" }}>
                        {preset.display_name}
                      </strong>
                      <span className="mgmt-status-pill">
                        {preset.installed ? "Installed" : preset.base_role}
                      </span>
                    </div>
                    <p
                      style={{
                        margin: "8px 0 0",
                        fontSize: "0.84rem",
                        color: "#475569",
                        lineHeight: 1.5,
                      }}
                    >
                      {preset.description}
                    </p>
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "6px",
                        marginTop: "10px",
                        fontSize: "0.76rem",
                      }}
                    >
                      {preset.masked_fields.map((f) => (
                        <span
                          key={f}
                          style={{
                            padding: "3px 8px",
                            borderRadius: "999px",
                            background: "#f1f5f9",
                            color: "#1e293b",
                            fontWeight: 500,
                          }}
                        >
                          Mask: {f}
                        </span>
                      ))}
                      {preset.allowed_regions.length > 0 && (
                        <span
                          style={{
                            padding: "3px 8px",
                            borderRadius: "999px",
                            background: "#eff6ff",
                            color: "#1d4ed8",
                            fontWeight: 500,
                          }}
                        >
                          Regions: {preset.allowed_regions.join(", ")}
                        </span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    className={
                      preset.installed
                        ? "secondary mgmt-btn-small"
                        : "mgmt-action-btn"
                    }
                    disabled={busy || preset.installed}
                    onClick={() => handleInstallPreset(preset.policy_code)}
                    style={{ alignSelf: "flex-start" }}
                  >
                    {preset.installed ? "Preset Installed" : "Install Preset"}
                  </button>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* TAB 2: Create Custom Policy */}
      {data && activeTab === "builder" && (
        <form
          onSubmit={handleCreatePolicy}
          className="mgmt-kpi-card"
          style={{
            padding: "24px",
            display: "flex",
            flexDirection: "column",
            gap: "20px",
          }}
        >
          <div>
            <h3 style={{ margin: "0 0 4px" }}>Build Custom ABAC Policy</h3>
            <p
              style={{ margin: 0, color: "var(--muted)", fontSize: "0.88rem" }}
            >
              Define exactly what a custom role can see, mask, and edit — down
              to specific hours and dollar caps.
            </p>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: "16px",
            }}
          >
            <div>
              <label htmlFor="abac-code" className="mgmt-kpi-label">
                Policy Code (slug)
              </label>
              <input
                id="abac-code"
                type="text"
                required
                value={policyCode}
                onChange={(e) => setPolicyCode(e.target.value)}
                style={{ width: "100%", marginTop: "6px", padding: "9px 10px" }}
              />
            </div>
            <div>
              <label htmlFor="abac-name" className="mgmt-kpi-label">
                Display Name
              </label>
              <input
                id="abac-name"
                type="text"
                required
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                style={{ width: "100%", marginTop: "6px", padding: "9px 10px" }}
              />
            </div>
            <div>
              <label htmlFor="abac-role" className="mgmt-kpi-label">
                Base Role Ceiling
              </label>
              <select
                id="abac-role"
                value={baseRole}
                onChange={(e) => setBaseRole(e.target.value as BaseRole)}
                style={{ width: "100%", marginTop: "6px", padding: "9px 10px" }}
              >
                <option value="manager">Manager (full ops ceiling)</option>
                <option value="front_desk">Front Desk</option>
                <option value="artist">Staff / Specialist</option>
                <option value="owner">Owner</option>
              </select>
            </div>
            <div>
              <label htmlFor="abac-limit" className="mgmt-kpi-label">
                Max Financial Amount (USD, optional)
              </label>
              <input
                id="abac-limit"
                type="number"
                min={0}
                value={limitUsd}
                onChange={(e) => setLimitUsd(e.target.value)}
                placeholder="e.g. 50000"
                style={{ width: "100%", marginTop: "6px", padding: "9px 10px" }}
              />
            </div>
          </div>

          <div>
            <label htmlFor="abac-desc" className="mgmt-kpi-label">
              Governance Description
            </label>
            <input
              id="abac-desc"
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              style={{ width: "100%", marginTop: "6px", padding: "9px 10px" }}
            />
          </div>

          <div>
            <label htmlFor="abac-regions" className="mgmt-kpi-label">
              Allowed Regions / States (comma-separated, leave blank for all)
            </label>
            <input
              id="abac-regions"
              type="text"
              value={regionsInput}
              onChange={(e) => setRegionsInput(e.target.value)}
              placeholder="Midwest, IL, OH, WI"
              style={{ width: "100%", marginTop: "6px", padding: "9px 10px" }}
            />
          </div>

          {/* Field-Level PII Masking */}
          <fieldset
            style={{
              border: "1px solid #e2e8f0",
              borderRadius: "10px",
              padding: "16px",
            }}
          >
            <legend style={{ fontWeight: 600, padding: "0 6px" }}>
              Field-Level PII & Sensitive Data Masking
            </legend>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
                gap: "10px",
                marginTop: "6px",
              }}
            >
              {data.available_masked_fields.map((fieldKey) => {
                const meta = FIELD_MASK_LABELS[fieldKey] ?? {
                  label: fieldKey,
                  sample: "[REDACTED]",
                };
                const checked = maskedFields.includes(fieldKey);
                return (
                  <label
                    key={fieldKey}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "8px 10px",
                      borderRadius: "8px",
                      border: checked
                        ? "1px solid #0f172a"
                        : "1px solid #e2e8f0",
                      background: checked ? "#f8fafc" : "#ffffff",
                      cursor: "pointer",
                      fontSize: "0.86rem",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() =>
                        toggleListValue(maskedFields, fieldKey, setMaskedFields)
                      }
                    />
                    <span>
                      <strong>{meta.label}</strong>{" "}
                      <code style={{ fontSize: "0.75rem", color: "#475569" }}>
                        {meta.sample}
                      </code>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {/* Denied Permissions Matrix */}
          <fieldset
            style={{
              border: "1px solid #e2e8f0",
              borderRadius: "10px",
              padding: "16px",
            }}
          >
            <legend style={{ fontWeight: 600, padding: "0 6px" }}>
              Denied Permissions (Subtracted from Base Role)
            </legend>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "14px",
                marginTop: "6px",
              }}
            >
              {QUICK_DENY_GROUPS.map((grp) => (
                <div key={grp.group}>
                  <div
                    style={{
                      fontSize: "0.8rem",
                      fontWeight: 700,
                      color: "#334155",
                      marginBottom: "6px",
                    }}
                  >
                    {grp.group}
                  </div>
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "6px",
                    }}
                  >
                    {grp.perms.map((perm) => (
                      <label
                        key={perm}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                          fontSize: "0.84rem",
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={deniedPerms.includes(perm)}
                          onChange={() =>
                            toggleListValue(deniedPerms, perm, setDeniedPerms)
                          }
                        />
                        <code>{perm}</code>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </fieldset>

          {/* Time-Window Write Lock */}
          <fieldset
            style={{
              border: "1px solid #e2e8f0",
              borderRadius: "10px",
              padding: "16px",
            }}
          >
            <legend style={{ fontWeight: 600, padding: "0 6px" }}>
              Business-Hours Write Window Guard
            </legend>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                fontWeight: 600,
                fontSize: "0.9rem",
                marginBottom: "12px",
              }}
            >
              <input
                type="checkbox"
                checked={windowEnabled}
                onChange={(e) => setWindowEnabled(e.target.checked)}
              />
              Restrict write/edit operations outside approved local working
              hours
            </label>

            {windowEnabled && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px",
                }}
              >
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                    gap: "12px",
                  }}
                >
                  <div>
                    <label htmlFor="abac-tz" className="mgmt-kpi-label">
                      Timezone (IANA)
                    </label>
                    <select
                      id="abac-tz"
                      value={windowTz}
                      onChange={(e) => setWindowTz(e.target.value)}
                      style={{
                        width: "100%",
                        marginTop: "4px",
                        padding: "8px",
                      }}
                    >
                      {TIMEZONE_OPTIONS.map((tz) => (
                        <option key={tz} value={tz}>
                          {tz}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="abac-start" className="mgmt-kpi-label">
                      Allow Writes From
                    </label>
                    <input
                      id="abac-start"
                      type="time"
                      value={windowStart}
                      onChange={(e) => setWindowStart(e.target.value)}
                      style={{
                        width: "100%",
                        marginTop: "4px",
                        padding: "8px",
                      }}
                    />
                  </div>
                  <div>
                    <label htmlFor="abac-end" className="mgmt-kpi-label">
                      Allow Writes Until
                    </label>
                    <input
                      id="abac-end"
                      type="time"
                      value={windowEnd}
                      onChange={(e) => setWindowEnd(e.target.value)}
                      style={{
                        width: "100%",
                        marginTop: "4px",
                        padding: "8px",
                      }}
                    />
                  </div>
                </div>

                <div>
                  <span className="mgmt-kpi-label">Allowed Weekdays</span>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                      marginTop: "6px",
                    }}
                  >
                    {WEEKDAYS.map((day) => {
                      const active = windowDays.includes(day.id);
                      return (
                        <button
                          key={day.id}
                          type="button"
                          aria-pressed={active}
                          onClick={() => toggleWeekday(day.id)}
                          style={{
                            padding: "6px 12px",
                            borderRadius: "6px",
                            border: active
                              ? "1px solid #0f172a"
                              : "1px solid #cbd5e1",
                            background: active ? "#0f172a" : "#ffffff",
                            color: active ? "#ffffff" : "#111827",
                            fontSize: "0.82rem",
                            fontWeight: 600,
                            cursor: "pointer",
                          }}
                        >
                          {day.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <span className="mgmt-kpi-label">
                    Gated Write Permissions (leave empty to gate ALL write
                    permissions)
                  </span>
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "8px",
                      marginTop: "6px",
                    }}
                  >
                    {[
                      "counterparties.manage",
                      "documents.manage",
                      "finance.manage",
                      "inventory.manage",
                      "booking.write",
                    ].map((perm) => (
                      <label
                        key={perm}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "5px 10px",
                          borderRadius: "6px",
                          border: "1px solid #cbd5e1",
                          fontSize: "0.82rem",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={windowPerms.includes(perm)}
                          onChange={() =>
                            toggleListValue(windowPerms, perm, setWindowPerms)
                          }
                        />
                        <code>{perm}</code>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </fieldset>

          <div>
            <button type="submit" className="mgmt-action-btn" disabled={busy}>
              {busy ? "Saving Policy..." : "Save ABAC Policy"}
            </button>
          </div>
        </form>
      )}

      {/* TAB 3: Team Assignments */}
      {data && activeTab === "assignments" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <form
            onSubmit={handleAssignPolicy}
            className="mgmt-kpi-card"
            style={{
              padding: "22px",
              display: "flex",
              flexDirection: "column",
              gap: "14px",
            }}
          >
            <div>
              <h3 style={{ margin: "0 0 4px" }}>
                Assign ABAC Policy to Team Member
              </h3>
              <p
                style={{
                  margin: 0,
                  color: "var(--muted)",
                  fontSize: "0.86rem",
                }}
              >
                Built-in owner self-lockout protection guarantees business
                owners can never accidentally block their own access-recovery
                rights.
              </p>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "12px",
              }}
            >
              <div>
                <label htmlFor="assign-member" className="mgmt-kpi-label">
                  Team Member
                </label>
                <select
                  id="assign-member"
                  value={assignUserId}
                  onChange={(e) => setAssignUserId(e.target.value)}
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                >
                  {data.members.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.display_name} ({m.role})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="assign-policy" className="mgmt-kpi-label">
                  ABAC Policy
                </label>
                <select
                  id="assign-policy"
                  value={assignPolicyId}
                  onChange={(e) => setAssignPolicyId(e.target.value)}
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                >
                  <option value="">Select policy...</option>
                  {data.policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="assign-regions" className="mgmt-kpi-label">
                  Optional Member Region Override
                </label>
                <input
                  id="assign-regions"
                  type="text"
                  value={assignRegionsOverride}
                  onChange={(e) => setAssignRegionsOverride(e.target.value)}
                  placeholder="e.g. TX, OK (overrides policy regions)"
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                />
              </div>
            </div>
            <div>
              <button
                type="submit"
                className="mgmt-action-btn"
                disabled={busy || !assignPolicyId || !assignUserId}
              >
                {busy ? "Assigning..." : "Bind Policy to Member"}
              </button>
            </div>
          </form>

          <section className="mgmt-kpi-card" style={{ padding: "22px" }}>
            <h3 style={{ margin: "0 0 12px" }}>
              Active Member Policy Bindings
            </h3>
            {data.assignments.length === 0 ? (
              <p style={{ color: "var(--muted)", margin: 0 }}>
                No team members are currently bound to an ABAC overlay (all
                members use their standard base role permissions).
              </p>
            ) : (
              <div
                tabIndex={0}
                role="region"
                aria-label="Active ABAC assignments"
                style={{ overflowX: "auto" }}
              >
                <table
                  style={{
                    width: "100%",
                    minWidth: "700px",
                    borderCollapse: "collapse",
                    fontSize: "0.86rem",
                  }}
                >
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid #e5e7eb",
                        textAlign: "left",
                      }}
                    >
                      <th style={{ padding: "10px 8px" }}>Member</th>
                      <th style={{ padding: "10px 8px" }}>Base Role</th>
                      <th style={{ padding: "10px 8px" }}>Policy</th>
                      <th style={{ padding: "10px 8px" }}>Region Override</th>
                      <th style={{ padding: "10px 8px" }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.assignments.map((a) => (
                      <tr
                        key={a.id}
                        style={{ borderBottom: "1px solid #f1f5f9" }}
                      >
                        <td style={{ padding: "10px 8px" }}>
                          <strong>{a.member_name}</strong>
                          {a.member_email_masked && (
                            <div
                              style={{ fontSize: "0.78rem", color: "#475569" }}
                            >
                              {a.member_email_masked}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "10px 8px" }}>{a.member_role}</td>
                        <td style={{ padding: "10px 8px" }}>
                          {a.policy_name} (<code>{a.policy_code}</code>)
                        </td>
                        <td style={{ padding: "10px 8px" }}>
                          {a.assigned_regions_override.length > 0
                            ? a.assigned_regions_override.join(", ")
                            : "Inherited from policy"}
                        </td>
                        <td style={{ padding: "10px 8px" }}>
                          <button
                            type="button"
                            className="secondary mgmt-btn-small"
                            disabled={busy}
                            onClick={() => handleRevokeAssignment(a.id)}
                          >
                            Revoke
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 4: Live Policy Simulator */}
      {data && activeTab === "simulator" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <form
            onSubmit={handleRunSimulation}
            className="mgmt-kpi-card"
            style={{
              padding: "22px",
              display: "flex",
              flexDirection: "column",
              gap: "16px",
            }}
          >
            <div>
              <h3 style={{ margin: "0 0 4px" }}>
                Live ABAC & PII Masking Simulator
              </h3>
              <p
                style={{
                  margin: 0,
                  color: "var(--muted)",
                  fontSize: "0.86rem",
                }}
              >
                Verify regional boundaries, after-hours contract edit blocks
                (e.g. 18:30 CST), financial limits, and real-time PII redaction
                before binding policies to your staff.
              </p>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                gap: "12px",
              }}
            >
              <div>
                <label htmlFor="sim-policy" className="mgmt-kpi-label">
                  Policy to Test
                </label>
                <select
                  id="sim-policy"
                  value={simPolicyId}
                  onChange={(e) => setSimPolicyId(e.target.value)}
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                >
                  <option value="">Select policy...</option>
                  {data.policies.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.display_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="sim-perm" className="mgmt-kpi-label">
                  Requested Permission
                </label>
                <select
                  id="sim-perm"
                  value={simPermission}
                  onChange={(e) => setSimPermission(e.target.value)}
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                >
                  {data.available_permissions.map((perm) => (
                    <option key={perm} value={perm}>
                      {perm}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="sim-time" className="mgmt-kpi-label">
                  Simulated Timestamp (ISO UTC)
                </label>
                <input
                  id="sim-time"
                  type="text"
                  value={simLocalUtc}
                  onChange={(e) => setSimLocalUtc(e.target.value)}
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                />
              </div>
              <div>
                <label htmlFor="sim-region" className="mgmt-kpi-label">
                  Target Record Region
                </label>
                <input
                  id="sim-region"
                  type="text"
                  value={simRegion}
                  onChange={(e) => setSimRegion(e.target.value)}
                  placeholder="Midwest or California"
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                />
              </div>
              <div>
                <label htmlFor="sim-amt" className="mgmt-kpi-label">
                  Transaction Amount (USD)
                </label>
                <input
                  id="sim-amt"
                  type="number"
                  min={0}
                  value={simAmountUsd}
                  onChange={(e) => setSimAmountUsd(e.target.value)}
                  style={{
                    width: "100%",
                    marginTop: "6px",
                    padding: "9px 10px",
                  }}
                />
              </div>
            </div>
            <div>
              <button
                type="submit"
                className="mgmt-action-btn"
                disabled={busy || !simPolicyId}
              >
                {busy ? "Evaluating..." : "Run Access Simulation"}
              </button>
            </div>
          </form>

          {simResult && (
            <div className="mgmt-kpi-card" style={{ padding: "22px" }}>
              <div
                style={{
                  padding: "14px 16px",
                  borderRadius: "10px",
                  border: simResult.allowed
                    ? "1px solid #86efac"
                    : "1px solid #fca5a5",
                  background: simResult.allowed ? "#f0fdf4" : "#fef2f2",
                  color: simResult.allowed ? "#14532d" : "#7f1d1d",
                  marginBottom: "18px",
                }}
              >
                <div style={{ fontWeight: 700, fontSize: "1rem" }}>
                  {simResult.allowed ? "ACCESS ALLOWED" : "ACCESS DENIED"}{" "}
                  {simResult.blocked_by ? `(${simResult.blocked_by})` : ""}
                </div>
                <div style={{ marginTop: "4px", fontSize: "0.9rem" }}>
                  {simResult.reason}
                </div>
                <div
                  style={{ marginTop: "4px", fontSize: "0.8rem", opacity: 0.9 }}
                >
                  Evaluated clock: {simResult.evaluated_local_time} · Base role:{" "}
                  <code>{simResult.base_role}</code>
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                  gap: "16px",
                }}
              >
                <div>
                  <h4 style={{ margin: "0 0 8px", fontSize: "0.9rem" }}>
                    Raw Database Record
                  </h4>
                  <pre
                    tabIndex={0}
                    role="region"
                    aria-label="Raw database record JSON preview"
                    style={{
                      margin: 0,
                      padding: "12px",
                      borderRadius: "8px",
                      background: "#f8fafc",
                      border: "1px solid #e2e8f0",
                      fontSize: "0.8rem",
                      overflowX: "auto",
                    }}
                  >
                    {JSON.stringify(simResult.raw_preview, null, 2)}
                  </pre>
                </div>
                <div>
                  <h4 style={{ margin: "0 0 8px", fontSize: "0.9rem" }}>
                    Masked API Response Preview
                  </h4>
                  <pre
                    tabIndex={0}
                    role="region"
                    aria-label="Masked API response JSON preview"
                    style={{
                      margin: 0,
                      padding: "12px",
                      borderRadius: "8px",
                      background: "#0f172a",
                      color: "#f8fafc",
                      fontSize: "0.8rem",
                      overflowX: "auto",
                    }}
                  >
                    {JSON.stringify(simResult.masked_preview, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
