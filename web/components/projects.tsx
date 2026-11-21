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
import {
  fetchWorkspace,
  managementFetch,
  type LocationItem,
} from "../lib/management-api";
import {
  createMatterInvoice,
  decideStage,
  decideTimeEntry,
  fetchConflictChecks,
  fetchExports,
  fetchMatterFiles,
  fetchMatterInvoices,
  fetchMatterMembers,
  fetchMatters,
  fetchRecurringRuns,
  fetchRecurringSchedules,
  fetchStages,
  fetchTasks,
  fetchTimeEntries,
  grantMatterMember,
  projectsError,
  recordConflictCheck,
  revokeMatterMember,
  runMatterExport,
  runPortfolioExport,
  saveMatter,
  saveRecurringSchedule,
  saveStage,
  saveTask,
  saveTimeEntry,
  searchProjects,
  submitStage,
  triggerRecurringRun,
  uploadMatterFile,
} from "../lib/projects-api";
import {
  formatMinor,
  parseMajorToMinor,
  type ConflictCheckView,
  type ConflictDecision,
  type FileCategory,
  type MatterAccessMode,
  type MatterFileView,
  type MatterInvoiceView,
  type MatterKind,
  type MatterMemberView,
  type MatterRole,
  type MatterStatus,
  type MatterView,
  type ProjectExportRecord,
  type ProjectSearchResult,
  type RecurringCadence,
  type RecurringRunView,
  type RecurringScheduleView,
  type StageView,
  type TaskPriority,
  type TaskStatus,
  type TaskView,
  type TimeEntryView,
} from "../lib/projects-contracts";

type TabId = "matters" | "work" | "time" | "billing";

const TABS: { id: TabId; label: string }[] = [
  { id: "matters", label: "Matters & Ethical Wall" },
  { id: "work", label: "Stages, Tasks, Files & Search" },
  { id: "time", label: "Time & Recurring" },
  { id: "billing", label: "Billing & Exports" },
];

type CounterpartyRef = { counterparty_id: string; display_name: string };
type BookRef = { book_id: string; base_currency: string };
type AccountRef = {
  account_id: string;
  code: string;
  name: string;
  type: string;
};
type MemberRef = {
  user_id: string;
  display_name?: string;
  email?: string;
  role: string;
};

function newId(): string {
  return crypto.randomUUID();
}

export function ProjectsScreen({
  businessId,
  assignedLocationId,
  canWork,
  canManage,
  canBill,
}: {
  businessId: string;
  assignedLocationId: string | null;
  canWork: boolean;
  canManage: boolean;
  canBill: boolean;
}) {
  const [tab, setTab] = useState<TabId>("matters");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [matters, setMatters] = useState<MatterView[]>([]);
  const [exportsList, setExportsList] = useState<ProjectExportRecord[]>([]);
  const [counterparties, setCounterparties] = useState<CounterpartyRef[]>([]);
  const [books, setBooks] = useState<BookRef[]>([]);
  const [accounts, setAccounts] = useState<AccountRef[]>([]);
  const [bizMembers, setBizMembers] = useState<MemberRef[]>([]);

  const [selectedMatterId, setSelectedMatterId] = useState("");
  const [conflictChecks, setConflictChecks] = useState<ConflictCheckView[]>([]);
  const [matterMembers, setMatterMembers] = useState<MatterMemberView[]>([]);
  const [stages, setStages] = useState<StageView[]>([]);
  const [tasks, setTasks] = useState<TaskView[]>([]);
  const [files, setFiles] = useState<MatterFileView[]>([]);
  const [timeEntries, setTimeEntries] = useState<TimeEntryView[]>([]);
  const [schedules, setSchedules] = useState<RecurringScheduleView[]>([]);
  const [runs, setRuns] = useState<RecurringRunView[]>([]);
  const [invoices, setInvoices] = useState<MatterInvoiceView[]>([]);

  // Matter create form
  const [mLoc, setMLoc] = useState("");
  const [mCode, setMCode] = useState("");
  const [mTitle, setMTitle] = useState("");
  const [mKind, setMKind] = useState<MatterKind>("legal_case");
  const [mStatus, setMStatus] = useState<MatterStatus>("intake");
  const [mAccess, setMAccess] = useState<MatterAccessMode>("restricted");
  const [mClient, setMClient] = useState("");
  const [mCurrency, setMCurrency] = useState("USD");
  const [mBudget, setMBudget] = useState("2500.00");
  const [mOpenedOn, setMOpenedOn] = useState("2026-11-21");

  // Conflict check form
  const [ccParties, setCcParties] = useState("");
  const [ccDecision, setCcDecision] = useState<ConflictDecision>("clear");
  const [ccRationale, setCcRationale] = useState("");

  // ACL member form
  const [aclUserId, setAclUserId] = useState("");
  const [aclRole, setAclRole] = useState<MatterRole>("contributor");

  // Search
  const [searchQ, setSearchQ] = useState("");
  const [searchRes, setSearchRes] = useState<ProjectSearchResult | null>(null);

  // Stage form
  const [stNo, setStNo] = useState("1");
  const [stTitle, setStTitle] = useState("");
  const [stFee, setStFee] = useState("1200.00");

  // Task form
  const [tTitle, setTTitle] = useState("");
  const [tPriority, setTPriority] = useState<TaskPriority>("high");
  const [tStatus, setTStatus] = useState<TaskStatus>("in_progress");

  // File upload form
  const [fTitle, setFTitle] = useState("");
  const [fCat, setFCat] = useState<FileCategory>("evidence");
  const [fFile, setFFile] = useState<File | null>(null);

  // Time entry form
  const [teDate, setTeDate] = useState("2026-11-21");
  const [teMinutes, setTeMinutes] = useState("90");
  const [teRate, setTeRate] = useState("300.00");
  const [teDesc, setTeDesc] = useState("");

  // Recurring schedule form
  const [scTitle, setScTitle] = useState("");
  const [scTaskTitle, setScTaskTitle] = useState("");
  const [scCadence, setScCadence] = useState<RecurringCadence>("monthly");
  const [scNextDate, setScNextDate] = useState("2026-11-01");
  const [scFee, setScFee] = useState("2000.00");

  // Billing form
  const [invBookId, setInvBookId] = useState("");
  const [invArId, setInvArId] = useState("");
  const [invRevId, setInvRevId] = useState("");
  const [invTitle, setInvTitle] = useState("Legal Services Invoice");
  const [invNumber, setInvNumber] = useState("PRO-UI-001");
  const [lastExportSummary, setLastExportSummary] = useState<string | null>(
    null,
  );

  const keys = useRef<Record<string, string>>({});
  const keyFor = (slot: string) => {
    if (!keys.current[slot]) keys.current[slot] = `pro-ui-${newId()}`;
    return keys.current[slot];
  };
  const clearKey = (slot: string) => {
    delete keys.current[slot];
  };

  const defaultLocation = useMemo(
    () => assignedLocationId ?? locations[0]?.id ?? "",
    [assignedLocationId, locations],
  );
  const effLoc = mLoc || defaultLocation;
  const effClient = mClient || counterparties[0]?.counterparty_id || "";
  const effAclUser = aclUserId || bizMembers[0]?.user_id || "";
  const effMatterId = selectedMatterId || matters[0]?.matter_id || "";
  const selectedMatter = useMemo(
    () => matters.find((m) => m.matter_id === effMatterId) ?? null,
    [matters, effMatterId],
  );
  const effBookId = invBookId || books[0]?.book_id || "";
  const effArId =
    invArId ||
    accounts.find((a) => a.code === "1200")?.account_id ||
    accounts.find((a) => a.type === "asset")?.account_id ||
    "";
  const effRevId =
    invRevId ||
    accounts.find((a) => a.code === "4000")?.account_id ||
    accounts.find((a) => a.type === "revenue")?.account_id ||
    "";

  const detailSeq = useRef(0);

  const loadMatterDetails = useCallback(
    async (matterId: string) => {
      const seq = ++detailSeq.current;
      if (!matterId) {
        setConflictChecks([]);
        setMatterMembers([]);
        setStages([]);
        setTasks([]);
        setFiles([]);
        setTimeEntries([]);
        setSchedules([]);
        setRuns([]);
        setInvoices([]);
        return;
      }
      try {
        const [cc, mm, st, tk, fl, te, sc, rn, inv] = await Promise.all([
          fetchConflictChecks(businessId, matterId),
          fetchMatterMembers(businessId, matterId),
          fetchStages(businessId, matterId),
          fetchTasks(businessId, matterId),
          fetchMatterFiles(businessId, matterId),
          fetchTimeEntries(businessId, matterId),
          fetchRecurringSchedules(businessId, matterId),
          fetchRecurringRuns(businessId, matterId),
          fetchMatterInvoices(businessId, matterId),
        ]);
        if (detailSeq.current !== seq) return;
        setConflictChecks(cc);
        setMatterMembers(mm);
        setStages(st);
        setTasks(tk);
        setFiles(fl);
        setTimeEntries(te);
        setSchedules(sc);
        setRuns(rn);
        setInvoices(inv);
      } catch (err) {
        if (detailSeq.current !== seq) return;
        setError(projectsError(err));
      }
    },
    [businessId],
  );

  const loadAll = useCallback(async () => {
    try {
      const [ws, ms, ex] = await Promise.all([
        fetchWorkspace(businessId),
        fetchMatters(businessId),
        fetchExports(businessId),
      ]);
      setLocations(ws.locations);
      setMatters(ms);
      setExportsList(ex);
      setError(null);

      if (canManage) {
        try {
          const mems = await managementFetch<MemberRef[]>(
            `/v1/salons/${businessId}/members`,
          );
          setBizMembers(mems ?? []);
        } catch {
          setBizMembers([]);
        }
      }
      if (canBill) {
        try {
          const [cps, bks] = await Promise.all([
            managementFetch<{ items: CounterpartyRef[] }>(
              `/v1/businesses/${businessId}/counterparties`,
            ),
            managementFetch<{ items: { book: BookRef | null }[] }>(
              `/v1/businesses/${businessId}/ledger`,
            ),
          ]);
          setCounterparties(cps.items ?? []);
          const bList = (bks.items ?? []).flatMap((i) =>
            i.book ? [i.book] : [],
          );
          setBooks(bList);
          const firstBook = bList[0]?.book_id;
          if (firstBook) {
            const acc = await managementFetch<{ items: AccountRef[] }>(
              `/v1/businesses/${businessId}/ledger/books/${firstBook}/accounts`,
            );
            setAccounts(acc.items ?? []);
          }
        } catch {
          setCounterparties([]);
          setBooks([]);
          setAccounts([]);
        }
      }
    } catch (err) {
      setError(projectsError(err));
    } finally {
      setLoading(false);
    }
  }, [businessId, canManage, canBill]);

  useEffect(() => {
    let alive = true;
    void Promise.resolve().then(() => {
      if (alive) return loadAll();
      return undefined;
    });
    return () => {
      alive = false;
    };
  }, [loadAll]);

  useEffect(() => {
    let alive = true;
    void Promise.resolve().then(() => {
      if (alive) return loadMatterDetails(effMatterId);
      return undefined;
    });
    return () => {
      alive = false;
    };
  }, [effMatterId, loadMatterDetails]);

  const onTabKeyDown = (e: KeyboardEvent<HTMLButtonElement>, idx: number) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = TABS[(idx + 1) % TABS.length];
      if (next) setTab(next.id);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = TABS[(idx - 1 + TABS.length) % TABS.length];
      if (prev) setTab(prev.id);
    }
  };

  async function runAction(
    slot: string,
    fn: () => Promise<string | { message: string; nextMatterId?: string }>,
  ) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fn();
      const msg = typeof res === "string" ? res : res.message;
      const targetId =
        typeof res === "string"
          ? effMatterId
          : (res.nextMatterId ?? effMatterId);
      clearKey(slot);
      setNotice(msg);
      await loadAll();
      if (targetId) await loadMatterDetails(targetId);
    } catch (err) {
      setError(projectsError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveMatter(e: FormEvent) {
    e.preventDefault();
    const budget = mBudget.trim() ? parseMajorToMinor(mBudget) : null;
    if (mBudget.trim() && budget === null) {
      setError("Enter budget as a non-negative amount (e.g. 2500.00).");
      return;
    }
    await runAction("save-matter", async () => {
      const id = newId();
      const saved = await saveMatter(businessId, id, keyFor("save-matter"), {
        expected_revision: 0,
        location_id: effLoc,
        code: mCode,
        title: mTitle,
        kind: mKind,
        status: mStatus,
        access_mode: mAccess,
        client_counterparty_id: effClient,
        currency: mCurrency,
        budget_minor: budget,
        opened_on: mOpenedOn,
      });
      setMCode("");
      setMTitle("");
      setConflictChecks([]);
      setMatterMembers([]);
      setStages([]);
      setTasks([]);
      setFiles([]);
      setTimeEntries([]);
      setSchedules([]);
      setRuns([]);
      setInvoices([]);
      setSelectedMatterId(saved.matter_id);
      return {
        message: `Matter ${saved.code} saved (${saved.access_mode}).`,
        nextMatterId: saved.matter_id,
      };
    });
  }

  async function handleActivateMatter() {
    if (!selectedMatter) return;
    await runAction("activate-matter", async () => {
      const updated = await saveMatter(
        businessId,
        selectedMatter.matter_id,
        keyFor("activate-matter"),
        {
          expected_revision: selectedMatter.revision,
          location_id: selectedMatter.location_id,
          code: selectedMatter.code,
          title: selectedMatter.title,
          description: selectedMatter.description,
          kind: selectedMatter.kind,
          status: "active",
          access_mode: selectedMatter.access_mode,
          client_counterparty_id: selectedMatter.client_counterparty_id,
          currency: selectedMatter.currency,
          budget_minor: selectedMatter.budget_minor,
          opened_on: selectedMatter.opened_on,
          due_on: selectedMatter.due_on,
        },
      );
      return `Matter ${updated.code} activated (rev ${updated.revision}).`;
    });
  }

  async function handleConflictCheck(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter) return;
    await runAction("conflict-check", async () => {
      const c = await recordConflictCheck(
        businessId,
        selectedMatter.matter_id,
        keyFor("conflict-check"),
        {
          checked_parties: ccParties,
          decision: ccDecision,
          rationale: ccRationale,
        },
      );
      setCcParties("");
      setCcRationale("");
      return `Conflict check recorded (${c.decision}).`;
    });
  }

  async function handleGrantMember(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter) return;
    await runAction("grant-member", async () => {
      await grantMatterMember(
        businessId,
        selectedMatter.matter_id,
        keyFor("grant-member"),
        { user_id: effAclUser, matter_role: aclRole },
      );
      return `Ethical-wall membership updated (${aclRole}).`;
    });
  }

  async function handleRevokeMember(memberId: string) {
    if (!selectedMatter) return;
    await runAction(`revoke-${memberId}`, async () => {
      await revokeMatterMember(
        businessId,
        selectedMatter.matter_id,
        memberId,
        keyFor(`revoke-${memberId}`),
      );
      return "Ethical-wall membership revoked.";
    });
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault();
    if (!searchQ.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await searchProjects(businessId, searchQ.trim());
      setSearchRes(res);
    } catch (err) {
      setError(projectsError(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveStage(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter) return;
    const fee = stFee.trim() ? parseMajorToMinor(stFee) : null;
    if (stFee.trim() && fee === null) {
      setError("Enter stage fee as a non-negative amount.");
      return;
    }
    await runAction("save-stage", async () => {
      const st = await saveStage(
        businessId,
        selectedMatter.matter_id,
        newId(),
        keyFor("save-stage"),
        {
          expected_revision: 0,
          stage_no: Number(stNo),
          title: stTitle,
          fixed_fee_minor: fee,
        },
      );
      setStTitle("");
      setStNo(String(st.stage_no + 1));
      return `Stage ${st.stage_no} (${st.title}) saved.`;
    });
  }

  async function handleStageSubmit(stage: StageView) {
    if (!selectedMatter) return;
    await runAction(`submit-stage-${stage.stage_id}`, async () => {
      await submitStage(
        businessId,
        selectedMatter.matter_id,
        stage.stage_id,
        keyFor(`submit-stage-${stage.stage_id}`),
        {
          expected_revision: stage.revision,
          deliverable_summary: `Deliverable submitted for ${stage.title}`,
        },
      );
      return `Stage ${stage.stage_no} submitted for acceptance.`;
    });
  }

  async function handleStageAccept(stage: StageView) {
    if (!selectedMatter) return;
    await runAction(`accept-stage-${stage.stage_id}`, async () => {
      await decideStage(
        businessId,
        selectedMatter.matter_id,
        stage.stage_id,
        keyFor(`accept-stage-${stage.stage_id}`),
        { expected_revision: stage.revision, decision: "accept" },
      );
      return `Stage ${stage.stage_no} accepted.`;
    });
  }

  async function handleSaveTask(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter) return;
    await runAction("save-task", async () => {
      const tk = await saveTask(
        businessId,
        selectedMatter.matter_id,
        newId(),
        keyFor("save-task"),
        {
          expected_revision: 0,
          stage_id: stages[0]?.stage_id ?? null,
          title: tTitle,
          priority: tPriority,
          status: tStatus,
        },
      );
      setTTitle("");
      return `Task ${tk.title} saved.`;
    });
  }

  async function handleUploadFile(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter || !fFile) {
      setError("Choose a PDF, PNG, or JPEG file to upload.");
      return;
    }
    const mediaType = fFile.type;
    if (
      mediaType !== "application/pdf" &&
      mediaType !== "image/png" &&
      mediaType !== "image/jpeg"
    ) {
      setError("Only PDF, PNG, and JPEG files are supported.");
      return;
    }
    const bytes = new Uint8Array(await fFile.arrayBuffer());
    await runAction("upload-file", async () => {
      const uploaded = await uploadMatterFile(
        businessId,
        selectedMatter.matter_id,
        newId(),
        keyFor("upload-file"),
        {
          title: fTitle,
          category: fCat,
          fileName: fFile.name,
          mediaType,
          bytes,
        },
      );
      setFTitle("");
      setFFile(null);
      return `File ${uploaded.title} uploaded (${uploaded.byte_size} bytes).`;
    });
  }

  async function handleSaveTime(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter) return;
    const rate = parseMajorToMinor(teRate);
    if (rate === null) {
      setError("Enter hourly rate as a valid amount.");
      return;
    }
    await runAction("save-time", async () => {
      const te = await saveTimeEntry(
        businessId,
        selectedMatter.matter_id,
        newId(),
        keyFor("save-time"),
        {
          expected_revision: 0,
          work_date: teDate,
          duration_minutes: Number(teMinutes),
          hourly_rate_minor: rate,
          billable: true,
          description: teDesc,
          submit: true,
        },
      );
      setTeDesc("");
      return `Time entry submitted (${formatMinor(te.amount_minor, te.currency)}).`;
    });
  }

  async function handleApproveTime(te: TimeEntryView) {
    if (!selectedMatter) return;
    await runAction(`approve-time-${te.time_entry_id}`, async () => {
      await decideTimeEntry(
        businessId,
        selectedMatter.matter_id,
        te.time_entry_id,
        keyFor(`approve-time-${te.time_entry_id}`),
        { expected_revision: te.revision, decision: "approve" },
      );
      return "Time entry approved for billing.";
    });
  }

  async function handleSaveSchedule(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter) return;
    const fee = parseMajorToMinor(scFee);
    if (fee === null) {
      setError("Enter recurring fee as a valid amount.");
      return;
    }
    await runAction("save-schedule", async () => {
      const sc = await saveRecurringSchedule(
        businessId,
        selectedMatter.matter_id,
        newId(),
        keyFor("save-schedule"),
        {
          expected_revision: 0,
          title: scTitle,
          task_template_title: scTaskTitle,
          cadence: scCadence,
          next_run_date: scNextDate,
          fixed_fee_minor: fee,
          status: "active",
        },
      );
      setScTitle("");
      setScTaskTitle("");
      return `Recurring schedule ${sc.title} saved.`;
    });
  }

  async function handleRunSchedule(sc: RecurringScheduleView) {
    if (!selectedMatter) return;
    await runAction(`run-sched-${sc.schedule_id}`, async () => {
      const rn = await triggerRecurringRun(
        businessId,
        selectedMatter.matter_id,
        sc.schedule_id,
        keyFor(`run-sched-${sc.schedule_id}`),
        sc.revision,
      );
      return `Recurring cycle ${rn.period_start}..${rn.period_end} materialized.`;
    });
  }

  async function handleCreateInvoice(e: FormEvent) {
    e.preventDefault();
    if (!selectedMatter) return;
    const approvedTimeIds = timeEntries
      .filter(
        (t) => t.status === "approved" && t.billable && t.amount_minor > 0,
      )
      .map((t) => t.time_entry_id);
    const billedStageIds = new Set(
      invoices.flatMap((inv) =>
        inv.items.map((i) => i.stage_id).filter((s): s is string => s !== null),
      ),
    );
    const billableStageIds = stages
      .filter(
        (s) =>
          s.status === "accepted" &&
          s.fixed_fee_minor !== null &&
          s.fixed_fee_minor > 0 &&
          !billedStageIds.has(s.stage_id),
      )
      .map((s) => s.stage_id);
    const unbilledRunIds = runs
      .filter((r) => r.billing_status === "unbilled" && r.fee_minor > 0)
      .map((r) => r.run_id);

    if (
      approvedTimeIds.length === 0 &&
      billableStageIds.length === 0 &&
      unbilledRunIds.length === 0
    ) {
      setError(
        "No approved time, accepted fixed-fee stages, or unbilled runs ready to invoice.",
      );
      return;
    }

    await runAction("create-invoice", async () => {
      const inv = await createMatterInvoice(
        businessId,
        selectedMatter.matter_id,
        keyFor("create-invoice"),
        {
          book_id: effBookId,
          receivable_account_id: effArId,
          revenue_account_id: effRevId,
          invoice_date: "2026-11-21",
          due_date: "2026-12-21",
          title: invTitle,
          number: invNumber.trim() || null,
          time_entry_ids: approvedTimeIds,
          stage_ids: billableStageIds,
          recurring_run_ids: unbilledRunIds,
        },
      );
      return `FIN-03 invoice created (${formatMinor(inv.total_minor, inv.currency)}).`;
    });
  }

  async function handleMatterExport() {
    if (!selectedMatter) return;
    await runAction("export-matter", async () => {
      const exp = await runMatterExport(
        businessId,
        selectedMatter.matter_id,
        keyFor("export-matter"),
      );
      setLastExportSummary(
        `Matter export: ${exp.export.matter_count} matter, ${exp.export.stage_count} stage(s), ${exp.export.task_count} task(s), ${exp.export.file_count} file(s), ${exp.export.invoice_count} invoice(s).`,
      );
      return `Matter export recorded (${exp.export.invoice_count} invoice(s)).`;
    });
  }

  async function handlePortfolioExport() {
    await runAction("export-portfolio", async () => {
      const exp = await runPortfolioExport(
        businessId,
        effLoc,
        keyFor("export-portfolio"),
      );
      setLastExportSummary(
        `Portfolio export: ${exp.export.matter_count} visible matter(s), ${exp.export.invoice_count} invoice(s).`,
      );
      return `Portfolio export recorded (${exp.export.matter_count} visible matter(s), ${exp.export.invoice_count} invoice(s)).`;
    });
  }

  return (
    <section className="projects-shell" aria-label="Projects and Legal Matters">
      <header>
        <h1>Projects &amp; Legal Matters</h1>
        <p>
          Manage legal cases with conflict checks, ethical-wall access controls,
          stages, tasks, restricted files, billable time, recurring engagements,
          FIN-03 invoicing, and audited exports.
        </p>
      </header>

      <div className="projects-tabs" role="tablist" aria-label="Projects views">
        {TABS.map((t, idx) => (
          <button
            key={t.id}
            id={`pro-tab-${t.id}`}
            type="button"
            role="tab"
            className="projects-tab"
            aria-selected={tab === t.id}
            aria-controls={
              !loading && tab === t.id ? `pro-panel-${t.id}` : undefined
            }
            onClick={() => setTab(t.id)}
            onKeyDown={(e) => onTabKeyDown(e, idx)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {notice && (
        <div role="status" className="mgmt-notice">
          {notice}
        </div>
      )}
      {error && (
        <div role="alert" className="mgmt-error">
          {error}
        </div>
      )}

      {loading ? (
        <p>Loading projects workspace…</p>
      ) : (
        <>
          {tab === "matters" && (
            <div
              id="pro-panel-matters"
              role="tabpanel"
              aria-labelledby="pro-tab-matters"
              className="projects-panel"
            >
              {canManage && (
                <div className="projects-card">
                  <h2>New Matter / Project</h2>
                  <form onSubmit={handleSaveMatter}>
                    <div className="projects-form-grid">
                      <label>
                        Branch
                        <select
                          value={effLoc}
                          onChange={(e) => setMLoc(e.target.value)}
                          disabled={assignedLocationId !== null}
                        >
                          {locations.map((l) => (
                            <option key={l.id} value={l.id}>
                              {l.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Matter code
                        <input
                          value={mCode}
                          onChange={(e) => setMCode(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Matter title
                        <input
                          value={mTitle}
                          onChange={(e) => setMTitle(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Kind
                        <select
                          value={mKind}
                          onChange={(e) =>
                            setMKind(e.target.value as MatterKind)
                          }
                        >
                          <option value="legal_case">Legal case</option>
                          <option value="project">Project</option>
                          <option value="recurring_engagement">
                            Recurring engagement
                          </option>
                        </select>
                      </label>
                      <label>
                        Initial status
                        <select
                          value={mStatus}
                          onChange={(e) =>
                            setMStatus(e.target.value as MatterStatus)
                          }
                        >
                          <option value="intake">Intake</option>
                          <option value="conflict_check">Conflict check</option>
                          <option value="active">Active</option>
                        </select>
                      </label>
                      <label>
                        Access mode
                        <select
                          value={mAccess}
                          onChange={(e) =>
                            setMAccess(e.target.value as MatterAccessMode)
                          }
                        >
                          <option value="restricted">
                            Restricted (Ethical Wall)
                          </option>
                          <option value="branch">Branch-wide</option>
                        </select>
                      </label>
                      <label>
                        Client counterparty
                        <select
                          value={effClient}
                          onChange={(e) => setMClient(e.target.value)}
                          required
                        >
                          {counterparties.map((c) => (
                            <option
                              key={c.counterparty_id}
                              value={c.counterparty_id}
                            >
                              {c.display_name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Currency
                        <input
                          value={mCurrency}
                          onChange={(e) =>
                            setMCurrency(e.target.value.toUpperCase())
                          }
                          maxLength={3}
                          required
                        />
                      </label>
                      <label>
                        Budget
                        <input
                          value={mBudget}
                          onChange={(e) => setMBudget(e.target.value)}
                        />
                      </label>
                      <label>
                        Opened on
                        <input
                          type="date"
                          value={mOpenedOn}
                          onChange={(e) => setMOpenedOn(e.target.value)}
                          required
                        />
                      </label>
                    </div>
                    <div className="projects-actions">
                      <button type="submit" disabled={busy || !effClient}>
                        Save matter
                      </button>
                    </div>
                  </form>
                </div>
              )}

              <div className="projects-card">
                <h2>Authorized Matters &amp; Projects</h2>
                <div
                  className="projects-table-wrap"
                  tabIndex={0}
                  role="region"
                  aria-label="Authorized matters table"
                >
                  <table
                    className="projects-table"
                    aria-label="Project matters"
                  >
                    <thead>
                      <tr>
                        <th>Code</th>
                        <th>Title</th>
                        <th>Kind</th>
                        <th>Status</th>
                        <th>Access</th>
                        <th>Select</th>
                      </tr>
                    </thead>
                    <tbody>
                      {matters.length === 0 ? (
                        <tr>
                          <td colSpan={6}>No authorized matters visible.</td>
                        </tr>
                      ) : (
                        matters.map((m) => (
                          <tr key={m.matter_id}>
                            <td>{m.code}</td>
                            <td>{m.title}</td>
                            <td>{m.kind}</td>
                            <td>{m.status}</td>
                            <td>{m.access_mode}</td>
                            <td>
                              <button
                                type="button"
                                onClick={() => {
                                  if (m.matter_id !== effMatterId) {
                                    setConflictChecks([]);
                                    setMatterMembers([]);
                                    setStages([]);
                                    setTasks([]);
                                    setFiles([]);
                                    setTimeEntries([]);
                                    setSchedules([]);
                                    setRuns([]);
                                    setInvoices([]);
                                  }
                                  setSelectedMatterId(m.matter_id);
                                }}
                              >
                                {m.matter_id === effMatterId
                                  ? "Selected"
                                  : "Inspect"}
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {selectedMatter && (
                <div className="projects-card">
                  <h2>
                    Selected Matter: {selectedMatter.code} —{" "}
                    {selectedMatter.title} ({selectedMatter.status})
                  </h2>
                  {canManage &&
                    selectedMatter.status !== "active" &&
                    selectedMatter.status !== "closed" && (
                      <div className="projects-actions">
                        <button
                          type="button"
                          onClick={handleActivateMatter}
                          disabled={busy}
                        >
                          Activate matter
                        </button>
                      </div>
                    )}

                  <h3>Conflict-of-Interest Checks ({conflictChecks.length})</h3>
                  {canManage && (
                    <form onSubmit={handleConflictCheck}>
                      <div className="projects-form-grid">
                        <label>
                          Checked parties
                          <input
                            value={ccParties}
                            onChange={(e) => setCcParties(e.target.value)}
                            required
                          />
                        </label>
                        <label>
                          Conflict decision
                          <select
                            value={ccDecision}
                            onChange={(e) =>
                              setCcDecision(e.target.value as ConflictDecision)
                            }
                          >
                            <option value="clear">Clear</option>
                            <option value="waived">Waived</option>
                            <option value="blocked">Blocked</option>
                          </select>
                        </label>
                        <label>
                          Rationale
                          <input
                            value={ccRationale}
                            onChange={(e) => setCcRationale(e.target.value)}
                            required
                          />
                        </label>
                      </div>
                      <div className="projects-actions">
                        <button type="submit" disabled={busy}>
                          Record conflict check
                        </button>
                      </div>
                    </form>
                  )}

                  <h3>Ethical-Wall Members ({matterMembers.length})</h3>
                  {canManage && bizMembers.length > 0 && (
                    <form onSubmit={handleGrantMember}>
                      <div className="projects-form-grid">
                        <label>
                          Staff member
                          <select
                            value={effAclUser}
                            onChange={(e) => setAclUserId(e.target.value)}
                          >
                            {bizMembers.map((u) => (
                              <option key={u.user_id} value={u.user_id}>
                                {u.display_name || u.email || u.user_id} (
                                {u.role})
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Matter role
                          <select
                            value={aclRole}
                            onChange={(e) =>
                              setAclRole(e.target.value as MatterRole)
                            }
                          >
                            <option value="lead">Lead</option>
                            <option value="contributor">Contributor</option>
                            <option value="billing">Billing</option>
                            <option value="viewer">Viewer</option>
                          </select>
                        </label>
                      </div>
                      <div className="projects-actions">
                        <button type="submit" disabled={busy}>
                          Grant matter access
                        </button>
                      </div>
                    </form>
                  )}
                  <div
                    className="projects-table-wrap"
                    tabIndex={0}
                    role="region"
                    aria-label="Ethical wall members table"
                  >
                    <table
                      className="projects-table"
                      aria-label="Matter members"
                    >
                      <thead>
                        <tr>
                          <th>User</th>
                          <th>Role</th>
                          <th>State</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {matterMembers.map((mm) => (
                          <tr key={mm.member_id}>
                            <td>{mm.user_id}</td>
                            <td>{mm.matter_role}</td>
                            <td>{mm.revoked_at ? "Revoked" : "Active"}</td>
                            <td>
                              {canManage && !mm.revoked_at && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    handleRevokeMember(mm.member_id)
                                  }
                                  disabled={busy}
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
                </div>
              )}
            </div>
          )}

          {tab === "work" && (
            <div
              id="pro-panel-work"
              role="tabpanel"
              aria-labelledby="pro-tab-work"
              className="projects-panel"
            >
              <div className="projects-card">
                <h2>ACL-Enforced Project Search</h2>
                <form onSubmit={handleSearch}>
                  <div className="projects-form-grid">
                    <label>
                      Search query
                      <input
                        value={searchQ}
                        onChange={(e) => setSearchQ(e.target.value)}
                        placeholder="Search matters, stages, tasks, files"
                        required
                      />
                    </label>
                  </div>
                  <div className="projects-actions">
                    <button type="submit" disabled={busy}>
                      Search projects
                    </button>
                  </div>
                </form>
                {searchRes && (
                  <p data-testid="projects-search-summary">
                    Search &ldquo;{searchRes.query}&rdquo;:{" "}
                    {searchRes.matters.length} matter(s),{" "}
                    {searchRes.stages.length} stage(s), {searchRes.tasks.length}{" "}
                    task(s), {searchRes.files.length} file(s).
                  </p>
                )}
              </div>

              {selectedMatter && (
                <>
                  <div className="projects-card">
                    <h2>Stages &amp; Deliverable Acceptance</h2>
                    {canManage && (
                      <form onSubmit={handleSaveStage}>
                        <div className="projects-form-grid">
                          <label>
                            Stage number
                            <input
                              type="number"
                              min={1}
                              value={stNo}
                              onChange={(e) => setStNo(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Stage title
                            <input
                              value={stTitle}
                              onChange={(e) => setStTitle(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Fixed fee
                            <input
                              value={stFee}
                              onChange={(e) => setStFee(e.target.value)}
                            />
                          </label>
                        </div>
                        <div className="projects-actions">
                          <button type="submit" disabled={busy}>
                            Save stage
                          </button>
                        </div>
                      </form>
                    )}
                    <div
                      className="projects-table-wrap"
                      tabIndex={0}
                      role="region"
                      aria-label="Project stages table"
                    >
                      <table
                        className="projects-table"
                        aria-label="Project stages"
                      >
                        <thead>
                          <tr>
                            <th>#</th>
                            <th>Title</th>
                            <th>Fee</th>
                            <th>Status</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stages.map((s) => (
                            <tr key={s.stage_id}>
                              <td>{s.stage_no}</td>
                              <td>{s.title}</td>
                              <td>
                                {s.fixed_fee_minor !== null
                                  ? formatMinor(
                                      s.fixed_fee_minor,
                                      selectedMatter.currency,
                                    )
                                  : "—"}
                              </td>
                              <td>{s.status}</td>
                              <td>
                                {canWork &&
                                  (s.status === "open" ||
                                    s.status === "rejected") && (
                                    <button
                                      type="button"
                                      onClick={() => handleStageSubmit(s)}
                                      disabled={busy}
                                    >
                                      Submit deliverable
                                    </button>
                                  )}
                                {canManage && s.status === "submitted" && (
                                  <button
                                    type="button"
                                    onClick={() => handleStageAccept(s)}
                                    disabled={busy}
                                  >
                                    Accept stage
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="projects-card">
                    <h2>Tasks ({tasks.length})</h2>
                    {canWork && (
                      <form onSubmit={handleSaveTask}>
                        <div className="projects-form-grid">
                          <label>
                            Task title
                            <input
                              value={tTitle}
                              onChange={(e) => setTTitle(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Priority
                            <select
                              value={tPriority}
                              onChange={(e) =>
                                setTPriority(e.target.value as TaskPriority)
                              }
                            >
                              <option value="low">Low</option>
                              <option value="normal">Normal</option>
                              <option value="high">High</option>
                              <option value="urgent">Urgent</option>
                            </select>
                          </label>
                          <label>
                            Task status
                            <select
                              value={tStatus}
                              onChange={(e) =>
                                setTStatus(e.target.value as TaskStatus)
                              }
                            >
                              <option value="todo">To do</option>
                              <option value="in_progress">In progress</option>
                              <option value="blocked">Blocked</option>
                              <option value="done">Done</option>
                            </select>
                          </label>
                        </div>
                        <div className="projects-actions">
                          <button type="submit" disabled={busy}>
                            Save task
                          </button>
                        </div>
                      </form>
                    )}
                    <div
                      className="projects-table-wrap"
                      tabIndex={0}
                      role="region"
                      aria-label="Project tasks table"
                    >
                      <table
                        className="projects-table"
                        aria-label="Project tasks"
                      >
                        <thead>
                          <tr>
                            <th>Title</th>
                            <th>Priority</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {tasks.map((tk) => (
                            <tr key={tk.task_id}>
                              <td>{tk.title}</td>
                              <td>{tk.priority}</td>
                              <td>{tk.status}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="projects-card">
                    <h2>Restricted Matter Files ({files.length})</h2>
                    {canWork && (
                      <form onSubmit={handleUploadFile}>
                        <div className="projects-form-grid">
                          <label>
                            File title
                            <input
                              value={fTitle}
                              onChange={(e) => setFTitle(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            File category
                            <select
                              value={fCat}
                              onChange={(e) =>
                                setFCat(e.target.value as FileCategory)
                              }
                            >
                              <option value="evidence">Evidence</option>
                              <option value="pleading">Pleading</option>
                              <option value="contract">Contract</option>
                              <option value="deliverable">Deliverable</option>
                              <option value="correspondence">
                                Correspondence
                              </option>
                              <option value="other">Other</option>
                            </select>
                          </label>
                          <label>
                            PDF/PNG/JPEG file
                            <input
                              type="file"
                              accept="application/pdf,image/png,image/jpeg"
                              onChange={(e) =>
                                setFFile(e.target.files?.[0] ?? null)
                              }
                            />
                          </label>
                        </div>
                        <div className="projects-actions">
                          <button type="submit" disabled={busy}>
                            Upload matter file
                          </button>
                        </div>
                      </form>
                    )}
                    <div
                      className="projects-table-wrap"
                      tabIndex={0}
                      role="region"
                      aria-label="Matter files table"
                    >
                      <table
                        className="projects-table"
                        aria-label="Matter files"
                      >
                        <thead>
                          <tr>
                            <th>Title</th>
                            <th>File name</th>
                            <th>Category</th>
                            <th>Size</th>
                          </tr>
                        </thead>
                        <tbody>
                          {files.map((fl) => (
                            <tr key={fl.file_id}>
                              <td>{fl.title}</td>
                              <td>{fl.file_name}</td>
                              <td>{fl.category}</td>
                              <td>{fl.byte_size} B</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {tab === "time" && (
            <div
              id="pro-panel-time"
              role="tabpanel"
              aria-labelledby="pro-tab-time"
              className="projects-panel"
            >
              {selectedMatter && (
                <>
                  <div className="projects-card">
                    <h2>Billable Time Entries ({timeEntries.length})</h2>
                    {canWork && (
                      <form onSubmit={handleSaveTime}>
                        <div className="projects-form-grid">
                          <label>
                            Work date
                            <input
                              type="date"
                              value={teDate}
                              onChange={(e) => setTeDate(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Duration (minutes)
                            <input
                              type="number"
                              min={1}
                              max={1440}
                              value={teMinutes}
                              onChange={(e) => setTeMinutes(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Hourly rate
                            <input
                              value={teRate}
                              onChange={(e) => setTeRate(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Work description
                            <input
                              value={teDesc}
                              onChange={(e) => setTeDesc(e.target.value)}
                              required
                            />
                          </label>
                        </div>
                        <div className="projects-actions">
                          <button type="submit" disabled={busy}>
                            Submit time entry
                          </button>
                        </div>
                      </form>
                    )}
                    <div
                      className="projects-table-wrap"
                      tabIndex={0}
                      role="region"
                      aria-label="Time entries table"
                    >
                      <table
                        className="projects-table"
                        aria-label="Time entries"
                      >
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Minutes</th>
                            <th>Amount</th>
                            <th>Status</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {timeEntries.map((te) => (
                            <tr key={te.time_entry_id}>
                              <td>{te.work_date}</td>
                              <td>{te.duration_minutes}</td>
                              <td>
                                {formatMinor(te.amount_minor, te.currency)}
                              </td>
                              <td>{te.status}</td>
                              <td>
                                {canManage && te.status === "submitted" && (
                                  <button
                                    type="button"
                                    onClick={() => handleApproveTime(te)}
                                    disabled={busy}
                                  >
                                    Approve time
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className="projects-card">
                    <h2>Recurring Service Schedules ({schedules.length})</h2>
                    {canManage && (
                      <form onSubmit={handleSaveSchedule}>
                        <div className="projects-form-grid">
                          <label>
                            Schedule title
                            <input
                              value={scTitle}
                              onChange={(e) => setScTitle(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Cycle task title
                            <input
                              value={scTaskTitle}
                              onChange={(e) => setScTaskTitle(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Cadence
                            <select
                              value={scCadence}
                              onChange={(e) =>
                                setScCadence(e.target.value as RecurringCadence)
                              }
                            >
                              <option value="weekly">Weekly</option>
                              <option value="biweekly">Biweekly</option>
                              <option value="monthly">Monthly</option>
                              <option value="quarterly">Quarterly</option>
                            </select>
                          </label>
                          <label>
                            Next run date
                            <input
                              type="date"
                              value={scNextDate}
                              onChange={(e) => setScNextDate(e.target.value)}
                              required
                            />
                          </label>
                          <label>
                            Cycle fee
                            <input
                              value={scFee}
                              onChange={(e) => setScFee(e.target.value)}
                              required
                            />
                          </label>
                        </div>
                        <div className="projects-actions">
                          <button type="submit" disabled={busy}>
                            Save recurring schedule
                          </button>
                        </div>
                      </form>
                    )}
                    <div
                      className="projects-table-wrap"
                      tabIndex={0}
                      role="region"
                      aria-label="Recurring schedules table"
                    >
                      <table
                        className="projects-table"
                        aria-label="Recurring schedules"
                      >
                        <thead>
                          <tr>
                            <th>Title</th>
                            <th>Cadence</th>
                            <th>Next run</th>
                            <th>Fee</th>
                            <th>Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {schedules.map((sc) => (
                            <tr key={sc.schedule_id}>
                              <td>{sc.title}</td>
                              <td>{sc.cadence}</td>
                              <td>{sc.next_run_date}</td>
                              <td>
                                {formatMinor(sc.fixed_fee_minor, sc.currency)}
                              </td>
                              <td>
                                {canManage && sc.status === "active" && (
                                  <button
                                    type="button"
                                    onClick={() => handleRunSchedule(sc)}
                                    disabled={busy}
                                  >
                                    Run cycle
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <p>Materialized cycles: {runs.length}</p>
                  </div>
                </>
              )}
            </div>
          )}

          {tab === "billing" && (
            <div
              id="pro-panel-billing"
              role="tabpanel"
              aria-labelledby="pro-tab-billing"
              className="projects-panel"
            >
              {selectedMatter && canBill && (
                <div className="projects-card">
                  <h2>Issue FIN-03 Matter Invoice</h2>
                  <form onSubmit={handleCreateInvoice}>
                    <div className="projects-form-grid">
                      <label>
                        Ledger book
                        <select
                          value={effBookId}
                          onChange={(e) => setInvBookId(e.target.value)}
                        >
                          {books.map((b) => (
                            <option key={b.book_id} value={b.book_id}>
                              {b.book_id.slice(0, 8)} ({b.base_currency})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Receivable account
                        <select
                          value={effArId}
                          onChange={(e) => setInvArId(e.target.value)}
                        >
                          {accounts.map((a) => (
                            <option key={a.account_id} value={a.account_id}>
                              {a.code} {a.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Revenue account
                        <select
                          value={effRevId}
                          onChange={(e) => setInvRevId(e.target.value)}
                        >
                          {accounts.map((a) => (
                            <option key={a.account_id} value={a.account_id}>
                              {a.code} {a.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Invoice title
                        <input
                          value={invTitle}
                          onChange={(e) => setInvTitle(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Invoice number
                        <input
                          value={invNumber}
                          onChange={(e) => setInvNumber(e.target.value)}
                        />
                      </label>
                    </div>
                    <div className="projects-actions">
                      <button
                        type="submit"
                        disabled={busy || !effBookId || !effArId || !effRevId}
                      >
                        Issue FIN-03 invoice
                      </button>
                    </div>
                  </form>
                </div>
              )}

              {selectedMatter && (
                <div className="projects-card">
                  <h2>Matter Invoices ({invoices.length})</h2>
                  <div
                    className="projects-table-wrap"
                    tabIndex={0}
                    role="region"
                    aria-label="Matter invoices table"
                  >
                    <table
                      className="projects-table"
                      aria-label="Matter invoices"
                    >
                      <thead>
                        <tr>
                          <th>Title</th>
                          <th>Number</th>
                          <th>Total</th>
                          <th>Items</th>
                        </tr>
                      </thead>
                      <tbody>
                        {invoices.map((inv) => (
                          <tr key={inv.matter_invoice_id}>
                            <td>{inv.title}</td>
                            <td>{inv.number ?? "—"}</td>
                            <td>
                              {formatMinor(inv.total_minor, inv.currency)}
                            </td>
                            <td>{inv.items.length}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="projects-card">
                <h2>ACL-Enforced Audited Exports ({exportsList.length})</h2>
                <div className="projects-actions">
                  {selectedMatter && (
                    <button
                      type="button"
                      onClick={handleMatterExport}
                      disabled={busy}
                    >
                      Export selected matter
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handlePortfolioExport}
                    disabled={busy || !effLoc}
                  >
                    Export branch portfolio
                  </button>
                </div>
                {lastExportSummary && (
                  <p data-testid="projects-export-summary">
                    {lastExportSummary}
                  </p>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
