"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { type BusinessGroup } from "../lib/group-contracts";
import {
  fetchGroups,
  fetchMembers,
  managementFetch,
  type MemberView,
} from "../lib/management-api";
import {
  enterpriseError,
  fetchConsolidatedGroupReport,
  fetchDirectoryLinks,
  fetchGroupReportGrants,
  fetchLifecycleEvents,
  fetchSsoProviders,
  postDeprovisionLink,
  publishGroupReportSnapshot,
  saveDirectoryLink,
  saveGroupReportGrant,
  saveSsoProvider,
} from "../lib/enterprise-api";
import {
  ALL_REPORT_SETS,
  formatEnterpriseMinor,
  type ConsolidatedGroupReportView,
  type DirectoryLinkView,
  type GroupReportGrantView,
  type LifecycleEventView,
  type ReportSet,
  type SsoProtocol,
  type SsoProviderView,
} from "../lib/enterprise-contracts";

type TabId = "sso" | "consents" | "analytics";

const TABS: { id: TabId; label: string }[] = [
  { id: "sso", label: "Corporate SSO & Lifecycle" },
  { id: "consents", label: "Group Reporting Consents" },
  { id: "analytics", label: "Consolidated Group Analytics" },
];

type LegalEntityRef = {
  legal_entity_id: string;
  code: string;
  legal_name: string;
};

function newId(): string {
  return crypto.randomUUID();
}

export function EnterpriseScreen({
  businessId,
  canManage,
}: {
  businessId: string;
  canManage: boolean;
}) {
  const [tab, setTab] = useState<TabId>("sso");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [members, setMembers] = useState<MemberView[]>([]);
  const [groups, setGroups] = useState<BusinessGroup[]>([]);
  const [legalEntities, setLegalEntities] = useState<LegalEntityRef[]>([]);

  const [providers, setProviders] = useState<SsoProviderView[]>([]);
  const [links, setLinks] = useState<DirectoryLinkView[]>([]);
  const [events, setEvents] = useState<LifecycleEventView[]>([]);
  const [grants, setGrants] = useState<GroupReportGrantView[]>([]);
  const [report, setReport] = useState<ConsolidatedGroupReportView | null>(
    null,
  );

  // Tab 1: SSO Provider & Directory Link
  const [provCode, setProvCode] = useState("");
  const [provName, setProvName] = useState("");
  const [provProto, setProvProto] = useState<SsoProtocol>("oidc");
  const [provIssuer, setProvIssuer] = useState(
    "https://corp.okta.com/oauth2/default",
  );
  const [provDomain, setProvDomain] = useState("");

  const [lnkProvId, setLnkProvId] = useState("");
  const [lnkUserId, setLnkUserId] = useState("");
  const [lnkSub, setLnkSub] = useState("");
  const [lnkEmpCode, setLnkEmpCode] = useState("");

  // Tab 2: Member Group Consents & Snapshot Publishing
  const [grtGroupId, setGrtGroupId] = useState("");
  const [grtSets, setGrtSets] = useState<ReportSet[]>(["revenue_by_currency"]);

  const [snapGroupId, setSnapGroupId] = useState("");
  const [snapLeId, setSnapLeId] = useState("");
  const [snapPeriod, setSnapPeriod] = useState("2026-10");
  const [snapCurrency, setSnapCurrency] = useState("USD");
  const [snapSet, setSnapSet] = useState<ReportSet>("revenue_by_currency");
  const [snapCount, setSnapCount] = useState("10");
  const [snapAmount, setSnapAmount] = useState("50000");
  const [snapNotes, setSnapNotes] = useState("Monthly aggregate");

  // Tab 3: Organizer Consolidated Report
  const [repGroupId, setRepGroupId] = useState("");
  const [repPeriod, setRepPeriod] = useState("2026-10");

  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const memberGroups = useMemo(
    () => groups.filter((g) => g.role === "member"),
    [groups],
  );
  const organizerGroups = useMemo(
    () => groups.filter((g) => g.role === "organizer"),
    [groups],
  );

  const reloadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [provList, lnkList, evList, grtList] = await Promise.all([
        fetchSsoProviders(businessId),
        fetchDirectoryLinks(businessId),
        fetchLifecycleEvents(businessId),
        fetchGroupReportGrants(businessId),
      ]);
      setProviders(provList);
      setLinks(lnkList);
      setEvents(evList);
      setGrants(grtList);
      const firstProv = provList[0];
      if (firstProv) setLnkProvId((p) => p || firstProv.provider_id);

      try {
        const [memList, grpPage, leRes] = await Promise.all([
          fetchMembers(businessId),
          fetchGroups(businessId),
          managementFetch<{ items: LegalEntityRef[] }>(
            `/v1/businesses/${businessId}/ledger`,
          ),
        ]);
        setMembers(memList);
        const grpList = grpPage.items ?? [];
        setGroups(grpList);
        const leList = leRes.items ?? [];
        setLegalEntities(leList);

        const nonOwner = memList.find(
          (m) => m.status === "active" && m.role !== "owner",
        );
        const firstMem = nonOwner ?? memList[0];
        if (firstMem) setLnkUserId((p) => p || firstMem.user_id);

        const firstMemGrp = grpList.find((g) => g.role === "member");
        if (firstMemGrp) {
          setGrtGroupId((p) => p || firstMemGrp.group_id);
          setSnapGroupId((p) => p || firstMemGrp.group_id);
        }
        const firstOrgGrp = grpList.find((g) => g.role === "organizer");
        if (firstOrgGrp) {
          setRepGroupId((p) => p || firstOrgGrp.group_id);
        }
        const firstLe = leList[0];
        if (firstLe) {
          setSnapLeId((p) => p || firstLe.legal_entity_id);
        }
      } catch {
        // Optional secondary endpoints
      }
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    const timer = window.setTimeout(() => {
      if (!initializedRef.current) {
        initializedRef.current = true;
        void reloadAll();
      }
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [reloadAll]);

  function onTabKeyDown(idx: number, e: KeyboardEvent<HTMLButtonElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const nextIdx =
      e.key === "ArrowRight"
        ? (idx + 1) % TABS.length
        : (idx - 1 + TABS.length) % TABS.length;
    const nextTab = TABS[nextIdx];
    if (nextTab) {
      setTab(nextTab.id);
      tabRefs.current[nextIdx]?.focus();
    }
  }

  function toggleReportSet(rset: ReportSet) {
    if (grtSets.includes(rset)) {
      if (grtSets.length <= 1) return;
      setGrtSets(grtSets.filter((x) => x !== rset));
    } else {
      setGrtSets([...grtSets, rset]);
    }
  }

  async function handleSaveProvider(e: FormEvent) {
    e.preventDefault();
    if (
      !canManage ||
      !provCode.trim() ||
      !provName.trim() ||
      !provDomain.trim()
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveSsoProvider(businessId, newId(), newId(), {
        expected_revision: 0,
        code: provCode.trim().toUpperCase(),
        display_name: provName.trim(),
        protocol: provProto,
        issuer_url: provIssuer.trim(),
        email_domain: provDomain.trim().toLowerCase(),
        status: "active",
      });
      setProvCode("");
      setProvName("");
      setProvDomain("");
      setLnkProvId(created.provider_id);
      setNotice(`Saved SSO provider ${created.code}`);
      await reloadAll();
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveLink(e: FormEvent) {
    e.preventDefault();
    if (
      !canManage ||
      !lnkProvId ||
      !lnkUserId ||
      !lnkSub.trim() ||
      !lnkEmpCode.trim()
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await saveDirectoryLink(businessId, newId(), newId(), {
        expected_revision: 0,
        provider_id: lnkProvId,
        user_id: lnkUserId,
        external_subject: lnkSub.trim(),
        employee_code: lnkEmpCode.trim().toUpperCase(),
      });
      setLnkSub("");
      setLnkEmpCode("");
      setNotice(`Linked directory employee ${created.employee_code}`);
      await reloadAll();
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDeprovision(link: DirectoryLinkView) {
    if (!canManage) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await postDeprovisionLink(businessId, link.link_id, newId(), {
        reason: `SCIM offboarding ${link.employee_code}`,
      });
      setNotice(
        `Deprovisioned ${res.link.employee_code} (${res.event.memberships_suspended} membership suspended)`,
      );
      await reloadAll();
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveGrant(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !grtGroupId || grtSets.length === 0) return;
    const grp = memberGroups.find((g) => g.group_id === grtGroupId);
    if (!grp) return;
    const existing = grants.find(
      (g) => g.owner_business_id === businessId && g.group_id === grtGroupId,
    );
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveGroupReportGrant(
        businessId,
        existing ? existing.grant_id : newId(),
        newId(),
        {
          expected_revision: existing ? existing.revision : 0,
          organizer_business_id: grp.organizer_business_id,
          group_id: grp.group_id,
          allowed_report_sets: grtSets,
          status: "active",
        },
      );
      setNotice(
        `Saved active report consent for ${grp.code} (${saved.allowed_report_sets.join(", ")})`,
      );
      await reloadAll();
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevokeGrant(grant: GroupReportGrantView) {
    if (!canManage) return;
    const grp = groups.find((g) => g.group_id === grant.group_id);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await saveGroupReportGrant(businessId, grant.grant_id, newId(), {
        expected_revision: grant.revision,
        organizer_business_id: grant.organizer_business_id,
        group_id: grant.group_id,
        allowed_report_sets: grant.allowed_report_sets,
        status: "revoked",
      });
      setNotice(`Revoked report consent for ${grp?.code ?? grant.group_id}`);
      await reloadAll();
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handlePublishSnapshot(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !snapGroupId || !snapLeId || !snapPeriod.trim()) return;
    const grp = memberGroups.find((g) => g.group_id === snapGroupId);
    if (!grp) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await publishGroupReportSnapshot(
        businessId,
        newId(),
        newId(),
        {
          organizer_business_id: grp.organizer_business_id,
          group_id: grp.group_id,
          legal_entity_id: snapLeId,
          period_key: snapPeriod.trim(),
          currency: snapCurrency.trim().toUpperCase(),
          report_set: snapSet,
          metric_count: Number(snapCount) || 0,
          metric_amount_minor: Number(snapAmount) || 0,
          notes: snapNotes.trim() || null,
        },
      );
      setNotice(
        `Published ${saved.report_set} snapshot (${saved.period_key}, ${formatEnterpriseMinor(saved.metric_amount_minor, saved.currency)})`,
      );
      await reloadAll();
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleLoadConsolidatedReport() {
    if (!repGroupId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const data = await fetchConsolidatedGroupReport(
        businessId,
        repGroupId,
        repPeriod.trim() || undefined,
      );
      setReport(data);
      setNotice(
        `Loaded consolidated group report (${data.entries.length} attributed member entries)`,
      );
    } catch (err) {
      setError(enterpriseError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="ent-shell">
      <header>
        <h1>Enterprise SSO, Lifecycle &amp; Group Reporting</h1>
        <p>
          Corporate SSO directory deprovisioning with immediate access
          revocation, and consent-based consolidated group analytics preserving
          Stage 1 ownership boundaries.
        </p>
      </header>

      {error ? (
        <div role="alert" className="mgmt-error">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div role="status" className="mgmt-notice">
          {notice}
        </div>
      ) : null}
      {loading ? <p>Loading enterprise governance workspace…</p> : null}

      <div
        className="ent-tabs"
        role="tablist"
        aria-label="Enterprise governance sections"
      >
        {TABS.map((t, idx) => (
          <button
            key={t.id}
            ref={(el) => {
              tabRefs.current[idx] = el;
            }}
            id={`ent-tab-${t.id}`}
            type="button"
            role="tab"
            className="ent-tab"
            aria-selected={tab === t.id}
            aria-controls={`ent-panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKeyDown(idx, e)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "sso" ? (
        <section
          id="ent-panel-sso"
          role="tabpanel"
          aria-labelledby="ent-tab-sso"
          className="ent-panel"
        >
          <div className="ent-card">
            <h2>Corporate SSO Identity Providers</h2>
            <form onSubmit={handleSaveProvider}>
              <div className="ent-form-grid">
                <label>
                  Provider code
                  <input
                    value={provCode}
                    onChange={(e) => setProvCode(e.target.value)}
                    placeholder="OKTA_CORP"
                  />
                </label>
                <label>
                  Provider display name
                  <input
                    value={provName}
                    onChange={(e) => setProvName(e.target.value)}
                    placeholder="Okta Corporate SSO"
                  />
                </label>
                <label>
                  Protocol
                  <select
                    value={provProto}
                    onChange={(e) =>
                      setProvProto(e.target.value as SsoProtocol)
                    }
                  >
                    <option value="oidc">oidc</option>
                    <option value="saml">saml</option>
                  </select>
                </label>
                <label>
                  Issuer URL
                  <input
                    value={provIssuer}
                    onChange={(e) => setProvIssuer(e.target.value)}
                  />
                </label>
                <label>
                  Corporate email domain
                  <input
                    value={provDomain}
                    onChange={(e) => setProvDomain(e.target.value)}
                    placeholder="acme-corp.example"
                  />
                </label>
              </div>
              <div className="ent-actions">
                <button type="submit" disabled={busy || !canManage}>
                  Save SSO provider
                </button>
              </div>
            </form>
            <div
              className="ent-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="SSO providers table"
            >
              <table className="ent-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Name</th>
                    <th>Protocol</th>
                    <th>Domain</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((p) => (
                    <tr key={p.provider_id}>
                      <td>{p.code}</td>
                      <td>{p.display_name}</td>
                      <td>{p.protocol}</td>
                      <td>{p.email_domain}</td>
                      <td>{p.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="ent-card">
            <h2>Directory Employee Links &amp; Atomic Deprovisioning</h2>
            <form onSubmit={handleSaveLink}>
              <div className="ent-form-grid">
                <label>
                  Directory provider
                  <select
                    value={lnkProvId}
                    onChange={(e) => setLnkProvId(e.target.value)}
                  >
                    {providers.map((p) => (
                      <option key={p.provider_id} value={p.provider_id}>
                        {p.code} — {p.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Business member
                  <select
                    value={lnkUserId}
                    onChange={(e) => setLnkUserId(e.target.value)}
                  >
                    {members.map((m) => (
                      <option key={m.user_id} value={m.user_id}>
                        {m.display_name ?? m.user_id} ({m.role} / {m.status})
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  External subject
                  <input
                    value={lnkSub}
                    onChange={(e) => setLnkSub(e.target.value)}
                    placeholder="okta|emp-001"
                  />
                </label>
                <label>
                  Employee code
                  <input
                    value={lnkEmpCode}
                    onChange={(e) => setLnkEmpCode(e.target.value)}
                    placeholder="EMP-001"
                  />
                </label>
              </div>
              <div className="ent-actions">
                <button
                  type="submit"
                  disabled={busy || !canManage || !lnkProvId}
                >
                  Save directory link
                </button>
              </div>
            </form>
            <div
              className="ent-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Directory links table"
            >
              <table className="ent-table">
                <thead>
                  <tr>
                    <th>Employee</th>
                    <th>External Subject</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {links.map((l) => (
                    <tr key={l.link_id}>
                      <td>{l.employee_code}</td>
                      <td>{l.external_subject}</td>
                      <td>{l.status}</td>
                      <td>
                        {l.status === "active" ? (
                          <button
                            type="button"
                            disabled={busy || !canManage}
                            onClick={() => void handleDeprovision(l)}
                          >
                            Deprovision {l.employee_code}
                          </button>
                        ) : (
                          <span>Deprovisioned</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="ent-card">
            <h2>Lifecycle Audit Events</h2>
            <div
              className="ent-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Lifecycle events table"
            >
              <table className="ent-table">
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Reason</th>
                    <th>Memberships Suspended</th>
                    <th>Delegations Removed</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.event_id}>
                      <td>{ev.event_kind}</td>
                      <td>{ev.reason ?? "—"}</td>
                      <td>{ev.memberships_suspended}</td>
                      <td>{ev.delegations_removed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      ) : null}

      {tab === "consents" ? (
        <section
          id="ent-panel-consents"
          role="tabpanel"
          aria-labelledby="ent-tab-consents"
          className="ent-panel"
        >
          <div className="ent-card">
            <h2>Member Group Reporting Consent Grants</h2>
            <form onSubmit={handleSaveGrant}>
              <div className="ent-form-grid">
                <label>
                  Consent target group
                  <select
                    value={grtGroupId}
                    onChange={(e) => setGrtGroupId(e.target.value)}
                  >
                    {memberGroups.map((g) => (
                      <option key={g.group_id} value={g.group_id}>
                        {g.code} — {g.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <fieldset className="ent-fieldset">
                <legend>Allowed report sets</legend>
                <div className="ent-check-grid">
                  {ALL_REPORT_SETS.map((rset) => (
                    <label key={rset}>
                      <input
                        type="checkbox"
                        checked={grtSets.includes(rset)}
                        onChange={() => toggleReportSet(rset)}
                      />
                      <span>{rset}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <div className="ent-actions">
                <button
                  type="submit"
                  disabled={busy || !canManage || !grtGroupId}
                >
                  Save report consent
                </button>
              </div>
            </form>
            <div
              className="ent-table-wrap"
              tabIndex={0}
              role="region"
              aria-label="Report grants table"
            >
              <table className="ent-table">
                <thead>
                  <tr>
                    <th>Group</th>
                    <th>Allowed Report Sets</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {grants
                    .filter((g) => g.owner_business_id === businessId)
                    .map((g) => {
                      const grp = groups.find((x) => x.group_id === g.group_id);
                      const label = grp?.code ?? g.group_id;
                      return (
                        <tr key={g.grant_id}>
                          <td>{label}</td>
                          <td>{g.allowed_report_sets.join(", ")}</td>
                          <td>{g.status}</td>
                          <td>
                            {g.status === "active" ? (
                              <button
                                type="button"
                                disabled={busy || !canManage}
                                onClick={() => void handleRevokeGrant(g)}
                              >
                                Revoke consent {label}
                              </button>
                            ) : (
                              <span>Revoked</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="ent-card">
            <h2>Publish Legal-Entity Aggregate Snapshot</h2>
            <form onSubmit={handlePublishSnapshot}>
              <div className="ent-form-grid">
                <label>
                  Snapshot group
                  <select
                    value={snapGroupId}
                    onChange={(e) => setSnapGroupId(e.target.value)}
                  >
                    {memberGroups.map((g) => (
                      <option key={g.group_id} value={g.group_id}>
                        {g.code} — {g.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Snapshot legal entity
                  <select
                    value={snapLeId}
                    onChange={(e) => setSnapLeId(e.target.value)}
                  >
                    {legalEntities.map((le) => (
                      <option
                        key={le.legal_entity_id}
                        value={le.legal_entity_id}
                      >
                        {le.code} — {le.legal_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Period (YYYY-MM)
                  <input
                    value={snapPeriod}
                    onChange={(e) => setSnapPeriod(e.target.value)}
                  />
                </label>
                <label>
                  Currency
                  <input
                    value={snapCurrency}
                    onChange={(e) => setSnapCurrency(e.target.value)}
                  />
                </label>
                <label>
                  Report set
                  <select
                    value={snapSet}
                    onChange={(e) => setSnapSet(e.target.value as ReportSet)}
                  >
                    {ALL_REPORT_SETS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Metric count
                  <input
                    type="number"
                    value={snapCount}
                    onChange={(e) => setSnapCount(e.target.value)}
                  />
                </label>
                <label>
                  Metric amount minor
                  <input
                    type="number"
                    value={snapAmount}
                    onChange={(e) => setSnapAmount(e.target.value)}
                  />
                </label>
                <label>
                  Snapshot notes
                  <input
                    value={snapNotes}
                    onChange={(e) => setSnapNotes(e.target.value)}
                  />
                </label>
              </div>
              <div className="ent-actions">
                <button
                  type="submit"
                  disabled={busy || !canManage || !snapGroupId || !snapLeId}
                >
                  Publish report snapshot
                </button>
              </div>
            </form>
          </div>
        </section>
      ) : null}

      {tab === "analytics" ? (
        <section
          id="ent-panel-analytics"
          role="tabpanel"
          aria-labelledby="ent-tab-analytics"
          className="ent-panel"
        >
          <div className="ent-card">
            <h2>Consolidated Group Analytics (Currency-Separated)</h2>
            <div className="ent-form-grid">
              <label>
                Organizer group
                <select
                  value={repGroupId}
                  onChange={(e) => setRepGroupId(e.target.value)}
                >
                  {organizerGroups.map((g) => (
                    <option key={g.group_id} value={g.group_id}>
                      {g.code} — {g.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Report period (YYYY-MM)
                <input
                  value={repPeriod}
                  onChange={(e) => setRepPeriod(e.target.value)}
                />
              </label>
            </div>
            <div className="ent-actions">
              <button
                type="button"
                disabled={busy || !repGroupId}
                onClick={() => void handleLoadConsolidatedReport()}
              >
                Load consolidated report
              </button>
            </div>

            {report ? (
              <div data-testid="consolidated-report-result">
                <h3>Totals by Currency &amp; Report Set</h3>
                <div
                  className="ent-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Consolidated totals table"
                >
                  <table className="ent-table">
                    <thead>
                      <tr>
                        <th>Currency</th>
                        <th>Report Set</th>
                        <th>Total Count</th>
                        <th>Total Amount</th>
                        <th>Businesses</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.totals_by_currency.map((t) => (
                        <tr key={`${t.currency}:${t.report_set}`}>
                          <td>{t.currency}</td>
                          <td>{t.report_set}</td>
                          <td>{t.total_count}</td>
                          <td>
                            {formatEnterpriseMinor(
                              t.total_amount_minor,
                              t.currency,
                            )}
                          </td>
                          <td>{t.contributing_businesses}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <h3>Attributed Member Entries ({report.entries.length})</h3>
                <div
                  className="ent-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Attributed member entries table"
                >
                  <table className="ent-table">
                    <thead>
                      <tr>
                        <th>Owner Business</th>
                        <th>Legal Entity</th>
                        <th>Report Set</th>
                        <th>Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.entries.map((e) => (
                        <tr key={e.snapshot_id}>
                          <td>{e.owner_business_id.slice(0, 8)}</td>
                          <td>{e.legal_entity_id.slice(0, 8)}</td>
                          <td>{e.report_set}</td>
                          <td>
                            {formatEnterpriseMinor(
                              e.metric_amount_minor,
                              e.currency,
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
