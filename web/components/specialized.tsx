"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { fetchWorkspace, managementFetch } from "../lib/management-api";
import {
  createSpecialEnrollment,
  fetchAssetIncidents,
  fetchCareConsents,
  fetchCareEncounters,
  fetchCareSubjects,
  fetchCivicAllocations,
  fetchCivicCases,
  fetchCivicPrograms,
  fetchManagedAssets,
  fetchSpecialPrograms,
  recordCareEncounter,
  saveAssetIncident,
  saveCareConsent,
  saveCareSubject,
  saveCivicAllocation,
  saveCivicCase,
  saveCivicProgram,
  saveManagedAsset,
  saveSpecialProgram,
  specializedError,
} from "../lib/specialized-api";
import {
  type AssetIncidentView,
  type CareConsentView,
  type CareEncounterView,
  type CareSubjectView,
  type CivicAllocationView,
  type CivicCaseView,
  type CivicProgramView,
  type ManagedAssetView,
  type SpecialProgramView,
} from "../lib/specialized-contracts";

type TabId = "venues" | "care" | "assets" | "civic";

const TABS: { id: TabId; label: string }[] = [
  { id: "venues", label: "Venues & Programs" },
  { id: "care", label: "Care & Consents" },
  { id: "assets", label: "Assets & Field Safety" },
  { id: "civic", label: "Civic & Dual-Review" },
];

type LocationRef = { id: string; name: string; timezone: string };
type CounterpartyRef = { counterparty_id: string; display_name: string };

function newId(): string {
  return crypto.randomUUID();
}

export function SpecializedScreen({
  businessId,
  canManage,
}: {
  businessId: string;
  canManage: boolean;
}) {
  const [tab, setTab] = useState<TabId>("venues");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [locations, setLocations] = useState<LocationRef[]>([]);
  const [counterparties, setCounterparties] = useState<CounterpartyRef[]>([]);
  const [locId, setLocId] = useState("");
  const [cpId, setCpId] = useState("");

  // Tab 1: Venues & Programs (SPECIAL-01)
  const [programs, setPrograms] = useState<SpecialProgramView[]>([]);
  const [vCode, setVCode] = useState("");
  const [vTitle, setVTitle] = useState("");
  const [vKind, setVKind] = useState<
    "education_cohort" | "fitness_membership" | "club_pass"
  >("fitness_membership");
  const [vCap, setVCap] = useState("10");
  const [vProgId, setVProgId] = useState("");

  // Tab 2: Care & Consents (SPECIAL-02)
  const [subjects, setSubjects] = useState<CareSubjectView[]>([]);
  const [consents, setConsents] = useState<CareConsentView[]>([]);
  const [encounters, setEncounters] = useState<CareEncounterView[]>([]);
  const [cCode, setCCode] = useState("");
  const [cName, setCName] = useState("");
  const [cSubjId, setCSubjId] = useState("");
  const [cGrantor, setCGrantor] = useState("");
  const [cConsId, setCConsId] = useState("");
  const [cSummary, setCSummary] = useState("");
  const [cNotes, setCNotes] = useState("");

  // Tab 3: Assets & Safety Incidents (SPECIAL-03)
  const [assets, setAssets] = useState<ManagedAssetView[]>([]);
  const [incidents, setIncidents] = useState<AssetIncidentView[]>([]);
  const [aCode, setACode] = useState("");
  const [aName, setAName] = useState("");
  const [aDomain, setADomain] = useState<
    | "agriculture_plot"
    | "utility_infrastructure"
    | "mining_equipment"
    | "security_post"
    | "facility_system"
    | "environmental_site"
  >("utility_infrastructure");
  const [aAssetId, setAAssetId] = useState("");
  const [aIncSeverity, setAIncSeverity] = useState<
    "low" | "medium" | "high" | "critical"
  >("critical");
  const [aIncDesc, setAIncDesc] = useState("");

  // Tab 4: Civic & Dual-Review (SPECIAL-04)
  const [civicPrograms, setCivicPrograms] = useState<CivicProgramView[]>([]);
  const [civicCases, setCivicCases] = useState<CivicCaseView[]>([]);
  const [allocations, setAllocations] = useState<CivicAllocationView[]>([]);
  const [pCode, setPCode] = useState("");
  const [pTitle, setPTitle] = useState("");
  const [pDual, setPDual] = useState(true);
  const [pProgId, setPProgId] = useState("");
  const [caseNum, setCaseNum] = useState("");
  const [caseSummary, setCaseSummary] = useState("");
  const [pCaseId, setPCaseId] = useState("");
  const [allocRef, setAllocRef] = useState("");

  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const reloadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ws = await fetchWorkspace(businessId);
      setLocations(ws.locations);
      const firstLoc = ws.locations[0];
      if (firstLoc) setLocId((p) => p || firstLoc.id);

      try {
        const cps = await managementFetch<{ items: CounterpartyRef[] }>(
          `/v1/businesses/${businessId}/counterparties`,
        );
        const cpList = cps.items ?? [];
        setCounterparties(cpList);
        const firstCp = cpList[0];
        if (firstCp) setCpId((p) => p || firstCp.counterparty_id);
      } catch {
        // Optional secondary list
      }

      const [
        progRes,
        subjRes,
        consRes,
        encRes,
        assetRes,
        incRes,
        civProgRes,
        civCaseRes,
        allocRes,
      ] = await Promise.allSettled([
        fetchSpecialPrograms(businessId),
        fetchCareSubjects(businessId),
        fetchCareConsents(businessId),
        fetchCareEncounters(businessId),
        fetchManagedAssets(businessId),
        fetchAssetIncidents(businessId),
        fetchCivicPrograms(businessId),
        fetchCivicCases(businessId),
        fetchCivicAllocations(businessId),
      ]);

      if (progRes.status === "fulfilled") {
        setPrograms(progRes.value);
        const firstP = progRes.value[0];
        if (firstP) setVProgId((p) => p || firstP.program_id);
      }
      if (subjRes.status === "fulfilled") {
        setSubjects(subjRes.value);
        const firstS = subjRes.value[0];
        if (firstS) setCSubjId((p) => p || firstS.subject_id);
      }
      if (consRes.status === "fulfilled") {
        setConsents(consRes.value);
        const firstC = consRes.value[0];
        if (firstC) setCConsId((p) => p || firstC.consent_id);
      }
      if (encRes.status === "fulfilled") setEncounters(encRes.value);
      if (assetRes.status === "fulfilled") {
        setAssets(assetRes.value);
        const firstA = assetRes.value[0];
        if (firstA) setAAssetId((p) => p || firstA.asset_id);
      }
      if (incRes.status === "fulfilled") setIncidents(incRes.value);
      if (civProgRes.status === "fulfilled") {
        setCivicPrograms(civProgRes.value);
        const firstCp = civProgRes.value[0];
        if (firstCp) setPProgId((p) => p || firstCp.program_id);
      }
      if (civCaseRes.status === "fulfilled") {
        setCivicCases(civCaseRes.value);
        const firstCs = civCaseRes.value[0];
        if (firstCs) setPCaseId((p) => p || firstCs.case_id);
      }
      if (allocRes.status === "fulfilled") setAllocations(allocRes.value);
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setLoading(false);
    }
  }, [businessId]);

  const initializedRef = useRef(false);
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    const t = window.setTimeout(() => {
      void reloadAll();
    }, 0);
    return () => window.clearTimeout(t);
  }, [reloadAll]);

  function onTabKeyDown(e: KeyboardEvent<HTMLButtonElement>, idx: number) {
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

  // --- Handlers: Tab 1 (Venues & Programs) ---
  async function handleSaveSpecialProgram(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !locId || !vCode.trim() || !vTitle.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveSpecialProgram(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        code: vCode.trim().toUpperCase(),
        title: vTitle.trim(),
        program_kind: vKind,
        capacity: Number(vCap) || 10,
        included_sessions: 8,
        price_minor: 5000,
        currency: "USD",
      });
      setVCode("");
      setVTitle("");
      setVProgId(saved.program_id);
      setNotice(`Saved specialized program ${saved.code}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleEnrollParticipant(e: FormEvent) {
    e.preventDefault();
    if (!locId || !vProgId || !cpId) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await createSpecialEnrollment(businessId, newId(), newId(), {
        location_id: locId,
        program_id: vProgId,
        participant_counterparty_id: cpId,
      });
      setNotice("Enrolled participant in specialized program");
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  // --- Handlers: Tab 2 (Care & Consents) ---
  async function handleSaveSubject(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !locId || !cpId || !cCode.trim() || !cName.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveCareSubject(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        guardian_counterparty_id: cpId,
        subject_kind: "human_patient",
        code: cCode.trim().toUpperCase(),
        display_name: cName.trim(),
      });
      setCCode("");
      setCName("");
      setCSubjId(saved.subject_id);
      setNotice(`Saved care subject ${saved.code}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveConsent(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !locId || !cSubjId || !cGrantor.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveCareConsent(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        subject_id: cSubjId,
        scope: "care_records",
        status: "active",
        granted_by_name: cGrantor.trim(),
      });
      setCGrantor("");
      setCConsId(saved.consent_id);
      setNotice(`Granted care consent (${saved.scope})`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevokeConsent(consent: CareConsentView) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await saveCareConsent(businessId, consent.consent_id, newId(), {
        expected_revision: consent.revision,
        location_id: consent.location_id,
        subject_id: consent.subject_id,
        scope: consent.scope,
        status: "revoked",
        granted_by_name: consent.granted_by_name,
      });
      setNotice(`Revoked consent for subject ${consent.subject_id}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRecordEncounter(e: FormEvent) {
    e.preventDefault();
    if (!locId || !cSubjId || !cConsId || !cSummary.trim() || !cNotes.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await recordCareEncounter(businessId, newId(), newId(), {
        location_id: locId,
        subject_id: cSubjId,
        consent_id: cConsId,
        encounter_date: "2026-11-22",
        summary: cSummary.trim(),
        clinical_notes: cNotes.trim(),
      });
      setCSummary("");
      setCNotes("");
      setNotice("Recorded consent-gated care encounter");
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  // --- Handlers: Tab 3 (Assets & Field Safety) ---
  async function handleSaveAsset(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !locId || !aCode.trim() || !aName.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveManagedAsset(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        asset_domain: aDomain,
        code: aCode.trim().toUpperCase(),
        name: aName.trim(),
        status: "active",
      });
      setACode("");
      setAName("");
      setAAssetId(saved.asset_id);
      setNotice(`Registered asset ${saved.code}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleLogIncident(e: FormEvent) {
    e.preventDefault();
    if (!locId || !aAssetId || !aIncDesc.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveAssetIncident(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        asset_id: aAssetId,
        incident_kind: "environmental_spill",
        severity: aIncSeverity,
        status: "open",
        description: aIncDesc.trim(),
      });
      setAIncDesc("");
      setNotice(`Logged ${saved.severity} safety incident`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAttemptReactivateAsset(asset: ManagedAssetView) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await saveManagedAsset(businessId, asset.asset_id, newId(), {
        expected_revision: asset.revision,
        location_id: asset.location_id,
        asset_domain: asset.asset_domain,
        code: asset.code,
        name: asset.name,
        status: "active",
      });
      setNotice(`Reactivated asset ${asset.code}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  // --- Handlers: Tab 4 (Civic & Dual-Review) ---
  async function handleSaveCivicProgram(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !locId || !pCode.trim() || !pTitle.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveCivicProgram(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        program_domain: "public_service_program",
        code: pCode.trim().toUpperCase(),
        title: pTitle.trim(),
        status: "active",
        requires_dual_review: pDual,
      });
      setPCode("");
      setPTitle("");
      setPProgId(saved.program_id);
      setNotice(`Saved civic program ${saved.code}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmitCivicCase(e: FormEvent) {
    e.preventDefault();
    if (!locId || !pProgId || !cpId || !caseNum.trim() || !caseSummary.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveCivicCase(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        program_id: pProgId,
        subject_counterparty_id: cpId,
        case_number: caseNum.trim().toUpperCase(),
        status: "submitted",
        summary: caseSummary.trim(),
      });
      setCaseNum("");
      setCaseSummary("");
      setPCaseId(saved.case_id);
      setNotice(`Submitted civic case ${saved.case_number}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleAttemptSelfApprove(c: CivicCaseView) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await saveCivicCase(businessId, c.case_id, newId(), {
        expected_revision: c.revision,
        location_id: c.location_id,
        program_id: c.program_id,
        subject_counterparty_id: c.subject_counterparty_id,
        case_number: c.case_number,
        status: "approved",
        summary: c.summary,
        decision_notes: "Self-approval attempt",
      });
      setNotice(`Approved case ${c.case_number}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleIssueAllocation(e: FormEvent) {
    e.preventDefault();
    if (!canManage || !locId || !pCaseId || !allocRef.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await saveCivicAllocation(businessId, newId(), newId(), {
        expected_revision: 0,
        location_id: locId,
        case_id: pCaseId,
        allocation_kind: "public_permit",
        reference_code: allocRef.trim().toUpperCase(),
        status: "active",
        effective_from: "2026-12-01",
      });
      setAllocRef("");
      setNotice(`Issued allocation ${saved.reference_code}`);
      await reloadAll();
    } catch (err) {
      setError(specializedError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="spec-shell"
      aria-label="Specialized Industry Operations"
    >
      <header>
        <h1>Specialized Industries (Stage 8 — Profiles 12–39)</h1>
        <p>
          Branch-scoped specialized modules: Education &amp; Hospitality,
          Consent-Gated Clinical/Vet/Social Care, Assets &amp; Field Safety, and
          Staffing/Advisory/Civic Dual-Review.
        </p>
      </header>

      <div className="spec-card">
        <div className="spec-form-grid">
          <label>
            Active branch
            <select value={locId} onChange={(e) => setLocId(e.target.value)}>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Counterparty
            <select value={cpId} onChange={(e) => setCpId(e.target.value)}>
              {counterparties.map((c) => (
                <option key={c.counterparty_id} value={c.counterparty_id}>
                  {c.display_name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {error ? (
        <div className="mgmt-error" role="alert">
          {error}
        </div>
      ) : null}
      {notice ? (
        <div className="mgmt-notice" role="status">
          {notice}
        </div>
      ) : null}

      <div
        className="spec-tabs"
        role="tablist"
        aria-label="Specialized modules"
      >
        {TABS.map((t, idx) => (
          <button
            key={t.id}
            ref={(el) => {
              tabRefs.current[idx] = el;
            }}
            id={`tab-${t.id}`}
            type="button"
            role="tab"
            className="spec-tab"
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKeyDown(e, idx)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? <p>Loading specialized records…</p> : null}

      {tab === "venues" ? (
        <div
          id="panel-venues"
          role="tabpanel"
          aria-labelledby="tab-venues"
          className="spec-panel"
        >
          <form className="spec-card" onSubmit={handleSaveSpecialProgram}>
            <h2>New Cohort / Fitness Program</h2>
            <div className="spec-form-grid">
              <label>
                Program code
                <input
                  value={vCode}
                  onChange={(e) => setVCode(e.target.value)}
                  placeholder="YOGA_2026"
                  required
                />
              </label>
              <label>
                Program title
                <input
                  value={vTitle}
                  onChange={(e) => setVTitle(e.target.value)}
                  placeholder="Morning Reformer Cohort"
                  required
                />
              </label>
              <label>
                Program kind
                <select
                  value={vKind}
                  onChange={(e) =>
                    setVKind(
                      e.target.value as
                        "education_cohort" | "fitness_membership" | "club_pass",
                    )
                  }
                >
                  <option value="fitness_membership">fitness_membership</option>
                  <option value="education_cohort">education_cohort</option>
                  <option value="club_pass">club_pass</option>
                </select>
              </label>
              <label>
                Program capacity
                <input
                  type="number"
                  min={1}
                  value={vCap}
                  onChange={(e) => setVCap(e.target.value)}
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy || !canManage}>
                Save specialized program
              </button>
            </div>
          </form>

          <form className="spec-card" onSubmit={handleEnrollParticipant}>
            <h2>Enroll Counterparty</h2>
            <div className="spec-form-grid">
              <label>
                Target program
                <select
                  value={vProgId}
                  onChange={(e) => setVProgId(e.target.value)}
                >
                  {programs.map((p) => (
                    <option key={p.program_id} value={p.program_id}>
                      {p.code} — {p.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy}>
                Enroll participant
              </button>
            </div>
          </form>

          <div className="spec-card">
            <h2>Registered Programs ({programs.length})</h2>
            <div className="spec-table-wrap">
              <table className="spec-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Title</th>
                    <th>Kind</th>
                    <th>Enrolled / Cap</th>
                  </tr>
                </thead>
                <tbody>
                  {programs.map((p) => (
                    <tr key={p.program_id}>
                      <td>{p.code}</td>
                      <td>{p.title}</td>
                      <td>{p.program_kind}</td>
                      <td>
                        {p.enrolled_count} / {p.capacity}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {tab === "care" ? (
        <div
          id="panel-care"
          role="tabpanel"
          aria-labelledby="tab-care"
          className="spec-panel"
        >
          <form className="spec-card" onSubmit={handleSaveSubject}>
            <h2>Care Subject</h2>
            <div className="spec-form-grid">
              <label>
                Subject code
                <input
                  value={cCode}
                  onChange={(e) => setCCode(e.target.value)}
                  placeholder="PAT_101"
                  required
                />
              </label>
              <label>
                Subject display name
                <input
                  value={cName}
                  onChange={(e) => setCName(e.target.value)}
                  placeholder="Jordan Patient"
                  required
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy || !canManage}>
                Save care subject
              </button>
            </div>
          </form>

          <form className="spec-card" onSubmit={handleSaveConsent}>
            <h2>Grant Consent</h2>
            <div className="spec-form-grid">
              <label>
                Care subject
                <select
                  value={cSubjId}
                  onChange={(e) => setCSubjId(e.target.value)}
                >
                  {subjects.map((s) => (
                    <option key={s.subject_id} value={s.subject_id}>
                      {s.code} — {s.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Granted by name
                <input
                  value={cGrantor}
                  onChange={(e) => setCGrantor(e.target.value)}
                  placeholder="Guardian Morgan"
                  required
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy || !canManage}>
                Grant active consent
              </button>
            </div>
          </form>

          <form className="spec-card" onSubmit={handleRecordEncounter}>
            <h2>Record Consent-Gated Encounter</h2>
            <div className="spec-form-grid">
              <label>
                Governing consent
                <select
                  value={cConsId}
                  onChange={(e) => setCConsId(e.target.value)}
                >
                  {consents.map((c) => (
                    <option key={c.consent_id} value={c.consent_id}>
                      {c.scope} ({c.status}) — {c.granted_by_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Encounter summary
                <input
                  value={cSummary}
                  onChange={(e) => setCSummary(e.target.value)}
                  placeholder="Initial physiotherapy assessment"
                  required
                />
              </label>
              <label>
                Clinical notes
                <input
                  value={cNotes}
                  onChange={(e) => setCNotes(e.target.value)}
                  placeholder="CONFIDENTIAL-CARE-NOTE"
                  required
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy}>
                Record encounter
              </button>
            </div>
          </form>

          <div className="spec-card">
            <h2>
              Consents ({consents.length}) &amp; Encounters ({encounters.length}
              )
            </h2>
            <div className="spec-table-wrap">
              <table className="spec-table">
                <thead>
                  <tr>
                    <th>Grantor</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {consents.map((c) => (
                    <tr key={c.consent_id}>
                      <td>{c.granted_by_name}</td>
                      <td>{c.status}</td>
                      <td>
                        <button
                          type="button"
                          disabled={
                            busy || !canManage || c.status === "revoked"
                          }
                          onClick={() => void handleRevokeConsent(c)}
                        >
                          Revoke consent {c.granted_by_name}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="spec-table-wrap">
              <table className="spec-table">
                <thead>
                  <tr>
                    <th>Summary</th>
                    <th>Consent Active</th>
                    <th>Clinical Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {encounters.map((enc) => (
                    <tr key={enc.encounter_id}>
                      <td>{enc.summary}</td>
                      <td>{String(enc.consent_active)}</td>
                      <td>{enc.clinical_notes ?? "[REDACTED BY CONSENT]"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {tab === "assets" ? (
        <div
          id="panel-assets"
          role="tabpanel"
          aria-labelledby="tab-assets"
          className="spec-panel"
        >
          <form className="spec-card" onSubmit={handleSaveAsset}>
            <h2>Register Field Asset</h2>
            <div className="spec-form-grid">
              <label>
                Asset domain
                <select
                  value={aDomain}
                  onChange={(e) =>
                    setADomain(
                      e.target.value as ManagedAssetView["asset_domain"],
                    )
                  }
                >
                  <option value="utility_infrastructure">
                    utility_infrastructure
                  </option>
                  <option value="agriculture_plot">agriculture_plot</option>
                  <option value="mining_equipment">mining_equipment</option>
                  <option value="security_post">security_post</option>
                  <option value="facility_system">facility_system</option>
                  <option value="environmental_site">environmental_site</option>
                </select>
              </label>
              <label>
                Asset code
                <input
                  value={aCode}
                  onChange={(e) => setACode(e.target.value)}
                  placeholder="SUB-NORTH-1"
                  required
                />
              </label>
              <label>
                Asset name
                <input
                  value={aName}
                  onChange={(e) => setAName(e.target.value)}
                  placeholder="North Pump Station"
                  required
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy || !canManage}>
                Save managed asset
              </button>
            </div>
          </form>

          <form className="spec-card" onSubmit={handleLogIncident}>
            <h2>Log Safety Incident</h2>
            <div className="spec-form-grid">
              <label>
                Incident asset
                <select
                  value={aAssetId}
                  onChange={(e) => setAAssetId(e.target.value)}
                >
                  {assets.map((a) => (
                    <option key={a.asset_id} value={a.asset_id}>
                      {a.code} — {a.status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Incident severity
                <select
                  value={aIncSeverity}
                  onChange={(e) =>
                    setAIncSeverity(
                      e.target.value as AssetIncidentView["severity"],
                    )
                  }
                >
                  <option value="critical">critical</option>
                  <option value="high">high</option>
                  <option value="medium">medium</option>
                  <option value="low">low</option>
                </select>
              </label>
              <label>
                Incident description
                <input
                  value={aIncDesc}
                  onChange={(e) => setAIncDesc(e.target.value)}
                  placeholder="Coolant manifold pressure breach"
                  required
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy}>
                Log incident
              </button>
            </div>
          </form>

          <div className="spec-card">
            <h2>
              Managed Assets ({assets.length}) &amp; Incidents (
              {incidents.length})
            </h2>
            <div className="spec-table-wrap">
              <table className="spec-table">
                <thead>
                  <tr>
                    <th>Code</th>
                    <th>Domain</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map((a) => (
                    <tr key={a.asset_id}>
                      <td>{a.code}</td>
                      <td>{a.asset_domain}</td>
                      <td>{a.status}</td>
                      <td>
                        <button
                          type="button"
                          disabled={busy || !canManage}
                          onClick={() => void handleAttemptReactivateAsset(a)}
                        >
                          Attempt reactivate {a.code}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {tab === "civic" ? (
        <div
          id="panel-civic"
          role="tabpanel"
          aria-labelledby="tab-civic"
          className="spec-panel"
        >
          <form className="spec-card" onSubmit={handleSaveCivicProgram}>
            <h2>New Dual-Review Civic / Staffing Program</h2>
            <div className="spec-form-grid">
              <label>
                Civic program code
                <input
                  value={pCode}
                  onChange={(e) => setPCode(e.target.value)}
                  placeholder="GRANT-2026"
                  required
                />
              </label>
              <label>
                Civic program title
                <input
                  value={pTitle}
                  onChange={(e) => setPTitle(e.target.value)}
                  placeholder="Municipal Grant Review"
                  required
                />
              </label>
            </div>
            <label className="spec-check-inline">
              <input
                type="checkbox"
                checked={pDual}
                onChange={(e) => setPDual(e.target.checked)}
              />
              Require dual-review (four-eyes approval)
            </label>
            <div className="spec-actions">
              <button type="submit" disabled={busy || !canManage}>
                Save civic program
              </button>
            </div>
          </form>

          <form className="spec-card" onSubmit={handleSubmitCivicCase}>
            <h2>Submit Case</h2>
            <div className="spec-form-grid">
              <label>
                Target civic program
                <select
                  value={pProgId}
                  onChange={(e) => setPProgId(e.target.value)}
                >
                  {civicPrograms.map((p) => (
                    <option key={p.program_id} value={p.program_id}>
                      {p.code} — {p.title}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Case number
                <input
                  value={caseNum}
                  onChange={(e) => setCaseNum(e.target.value)}
                  placeholder="CASE-2026-01"
                  required
                />
              </label>
              <label>
                Case summary
                <input
                  value={caseSummary}
                  onChange={(e) => setCaseSummary(e.target.value)}
                  placeholder="Public permit request"
                  required
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy}>
                Submit civic case
              </button>
            </div>
          </form>

          <form className="spec-card" onSubmit={handleIssueAllocation}>
            <h2>Issue Permit / Allocation</h2>
            <div className="spec-form-grid">
              <label>
                Target civic case
                <select
                  value={pCaseId}
                  onChange={(e) => setPCaseId(e.target.value)}
                >
                  {civicCases.map((c) => (
                    <option key={c.case_id} value={c.case_id}>
                      {c.case_number} — {c.status}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Allocation reference
                <input
                  value={allocRef}
                  onChange={(e) => setAllocRef(e.target.value)}
                  placeholder="PRM-2026-1"
                  required
                />
              </label>
            </div>
            <div className="spec-actions">
              <button type="submit" disabled={busy || !canManage}>
                Issue allocation
              </button>
            </div>
          </form>

          <div className="spec-card">
            <h2>
              Civic Cases ({civicCases.length}) &amp; Allocations (
              {allocations.length})
            </h2>
            <div className="spec-table-wrap">
              <table className="spec-table">
                <thead>
                  <tr>
                    <th>Case Number</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {civicCases.map((c) => (
                    <tr key={c.case_id}>
                      <td>{c.case_number}</td>
                      <td>{c.status}</td>
                      <td>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void handleAttemptSelfApprove(c)}
                        >
                          Attempt self-approve {c.case_number}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
