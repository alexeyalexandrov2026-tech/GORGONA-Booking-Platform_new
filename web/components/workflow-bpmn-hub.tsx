"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BpmnEdge,
  BpmnNode,
  BpmnWorkflowView,
  createWorkflow,
  decideWorkflowInstance,
  dryRunWorkflow,
  DryRunResponse,
  fetchWorkflowBpmnXml,
  fetchWorkflowsOverview,
  generateWorkflowFromPrompt,
  installWorkflowPreset,
  startWorkflowInstance,
  updateWorkflowGraph,
  WorkflowsOverviewResponse,
} from "../lib/workflow-bpmn-api";

type ActiveTab = "canvas" | "inbox" | "templates";

const NODE_WIDTH = 158;
const NODE_HEIGHT = 64;

const NODE_STYLE: Record<
  BpmnNode["node_type"],
  { bg: string; border: string; badge: string; text: string; badgeBg: string }
> = {
  start_trigger: {
    bg: "#ecfdf5",
    border: "#059669",
    badge: "START",
    text: "#064e3b",
    badgeBg: "#d1fae5",
  },
  exclusive_gateway: {
    bg: "#fffbeb",
    border: "#d97706",
    badge: "◇ GATEWAY",
    text: "#78350f",
    badgeBg: "#fef3c7",
  },
  human_approval: {
    bg: "#eff6ff",
    border: "#2563eb",
    badge: "HITL APPROVAL",
    text: "#1e3a8a",
    badgeBg: "#dbeafe",
  },
  ai_compliance_check: {
    bg: "#f5f3ff",
    border: "#7c3aed",
    badge: "AI AUDIT",
    text: "#4c1d95",
    badgeBg: "#ede9fe",
  },
  notify_or_webhook: {
    bg: "#f0f9ff",
    border: "#0284c7",
    badge: "NOTIFY",
    text: "#0c4a6e",
    badgeBg: "#e0f2fe",
  },
  end_approved: {
    bg: "#0f172a",
    border: "#0f172a",
    badge: "APPROVED",
    text: "#ffffff",
    badgeBg: "#16a34a",
  },
  end_rejected: {
    bg: "#fef2f2",
    border: "#dc2626",
    badge: "REJECTED",
    text: "#7f1d1d",
    badgeBg: "#fee2e2",
  },
};

function formatUsd(cents: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(cents / 100);
}

function getNodeSubtitle(node: BpmnNode): string {
  if (node.node_type === "human_approval") {
    const role = String(node.config.approver_role ?? "Approver");
    const sla = Number(node.config.sla_hours ?? 24);
    return `${role} · ${sla}h`;
  }
  if (node.node_type === "exclusive_gateway") {
    const field = String(node.config.field ?? "amount_cents");
    const op = String(node.config.operator ?? ">");
    const val = Number(node.config.value ?? 0);
    if (field === "amount_cents") {
      return `${op} ${formatUsd(val)}`;
    }
    return `${field} ${op} ${String(node.config.value ?? "")}`;
  }
  if (node.node_type === "ai_compliance_check") {
    return "Read-Only Audit";
  }
  if (node.node_type === "notify_or_webhook") {
    return String(node.config.channel ?? "Webhook");
  }
  if (node.node_type === "start_trigger") {
    return String(node.config.trigger_entity ?? "event");
  }
  return "Terminal Event";
}

export function WorkflowBpmnHub({ businessId }: { businessId: string }) {
  const [data, setData] = useState<WorkflowsOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("canvas");
  const [reloadTick, setReloadTick] = useState(0);

  // Active canvas draft state
  const [selectedWorkflowId, setSelectedWorkflowId] = useState<string>("");
  const [canvasNodes, setCanvasNodes] = useState<BpmnNode[]>([]);
  const [canvasEdges, setCanvasEdges] = useState<BpmnEdge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string>("");

  // AI prompt generator
  const [promptText, setPromptText] = useState(
    "If contract > $50k -> send to Legal Counsel -> then CFO -> then AI compliance check",
  );

  // Dry-run simulator
  const [simAmountUsd, setSimAmountUsd] = useState("75000");
  const [simRegion, setSimRegion] = useState("Midwest");
  const [simRisk, setSimRisk] = useState("15");
  const [dryRunResult, setDryRunResult] = useState<DryRunResponse | null>(null);

  // Start live instance form
  const [instRef, setInstRef] = useState("CNT-2026-0412");
  const [instTitle, setInstTitle] = useState(
    "Midwest Steel Annual Logistics Master Agreement",
  );
  const [instAmountUsd, setInstAmountUsd] = useState("75000");

  const syncSelectedWorkflow = useCallback(
    (wf: BpmnWorkflowView | undefined) => {
      if (!wf) return;
      setSelectedWorkflowId(wf.id);
      setCanvasNodes(wf.nodes);
      setCanvasEdges(wf.edges);
      const firstNode = wf.nodes[0];
      setSelectedNodeId(firstNode ? firstNode.id : "");
      setDryRunResult(null);
    },
    [],
  );

  useEffect(() => {
    let active = true;
    fetchWorkflowsOverview(businessId)
      .then((res) => {
        if (!active) return;
        setData(res);
        setError(null);
        const current =
          res.workflows.find((w) => w.id === selectedWorkflowId) ??
          res.workflows[0];
        if (current && (!selectedWorkflowId || canvasNodes.length === 0)) {
          setSelectedWorkflowId(current.id);
          setCanvasNodes(current.nodes);
          setCanvasEdges(current.edges);
          const first = current.nodes[0];
          if (first) setSelectedNodeId(first.id);
        }
      })
      .catch((err: unknown) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [businessId, reloadTick, selectedWorkflowId, canvasNodes.length]);

  const refresh = useCallback(() => {
    setLoading(true);
    setReloadTick((t) => t + 1);
  }, []);

  const selectedWorkflow = useMemo(
    () => data?.workflows.find((w) => w.id === selectedWorkflowId) ?? null,
    [data, selectedWorkflowId],
  );

  const selectedNode = useMemo(
    () => canvasNodes.find((n) => n.id === selectedNodeId) ?? null,
    [canvasNodes, selectedNodeId],
  );

  const visitedSet = useMemo(
    () => new Set(dryRunResult?.visited_node_ids ?? []),
    [dryRunResult],
  );

  const kpis = useMemo(() => {
    const workflows = data?.workflows ?? [];
    const totalNodes = workflows.reduce((acc, w) => acc + w.nodes.length, 0);
    return {
      activeWorkflows: workflows.filter((w) => w.status === "active").length,
      pendingApprovals: data?.pending_approvals_count ?? 0,
      totalNodes,
      completedInstances:
        data?.instances.filter((i) => i.status === "approved").length ?? 0,
    };
  }, [data]);

  const handleSelectWorkflow = (workflowId: string) => {
    const found = data?.workflows.find((w) => w.id === workflowId);
    syncSelectedWorkflow(found);
  };

  const handleInstallPreset = async (presetCode: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await installWorkflowPreset(businessId, presetCode);
      setNotice(`Installed BPMN workflow "${created.display_name}".`);
      syncSelectedWorkflow(created);
      setActiveTab("canvas");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleGenerateFromPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promptText.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const draft = await generateWorkflowFromPrompt(
        businessId,
        promptText.trim(),
      );
      const uniqueCode = `${draft.workflow_code.slice(0, 50)}-${Date.now().toString(36).slice(-4)}`;
      const saved = await createWorkflow(businessId, {
        workflow_code: uniqueCode,
        display_name: draft.display_name,
        description: draft.description,
        trigger_entity: draft.trigger_entity,
        status: "active",
        nodes: draft.nodes,
        edges: draft.edges,
      });
      setNotice(
        `AI generated & saved visual BPMN workflow "${saved.display_name}" (${saved.nodes.length} nodes).`,
      );
      syncSelectedWorkflow(saved);
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleUpdateSelectedNode = (patch: Partial<BpmnNode>) => {
    if (!selectedNodeId) return;
    setCanvasNodes((prev) =>
      prev.map((n) => (n.id === selectedNodeId ? { ...n, ...patch } : n)),
    );
  };

  const handleSaveCanvas = async () => {
    if (!selectedWorkflow) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await updateWorkflowGraph(
        businessId,
        selectedWorkflow.id,
        {
          nodes: canvasNodes,
          edges: canvasEdges,
        },
      );
      setNotice(
        `Saved "${updated.display_name}" (v${updated.version}) after DAG cycle validation.`,
      );
      syncSelectedWorkflow(updated);
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleExportXml = async () => {
    if (!selectedWorkflow) return;
    setBusy(true);
    setError(null);
    try {
      const xml = await fetchWorkflowBpmnXml(businessId, selectedWorkflow.id);
      const blob = new Blob([xml], { type: "application/xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${selectedWorkflow.workflow_code}.bpmn.xml`;
      a.click();
      URL.revokeObjectURL(url);
      setNotice(
        `Exported OMG BPMN 2.0 XML (${selectedWorkflow.workflow_code}.bpmn.xml).`,
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleDryRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedWorkflow) return;
    setBusy(true);
    setError(null);
    try {
      const usd = Number.parseFloat(simAmountUsd) || 0;
      const risk = Number.parseInt(simRisk, 10) || 0;
      const res = await dryRunWorkflow(businessId, selectedWorkflow.id, {
        amount_cents: Math.max(0, Math.round(usd * 100)),
        context: { region: simRegion.trim() || "Midwest", risk_score: risk },
      });
      setDryRunResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleStartInstance = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedWorkflow) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const usd = Number.parseFloat(instAmountUsd) || 0;
      const inst = await startWorkflowInstance(
        businessId,
        selectedWorkflow.id,
        {
          reference_code: instRef.trim(),
          entity_title: instTitle.trim(),
          amount_cents: Math.max(0, Math.round(usd * 100)),
          context: { region: "Midwest", risk_score: 14 },
        },
      );
      setNotice(
        `Launched ${inst.reference_code} -> paused at "${inst.current_node_label}" (${inst.status}).`,
      );
      setActiveTab("inbox");
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const handleDecide = async (
    instanceId: string,
    decision: "approve" | "reject",
  ) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await decideWorkflowInstance(businessId, instanceId, {
        decision,
        comment:
          decision === "approve"
            ? "Verified & approved in AMARKAL BPMN Inbox."
            : "Returned for revision.",
      });
      setNotice(
        `Recorded ${decision.toUpperCase()} for ${updated.reference_code} -> status: ${updated.status} (${updated.current_node_label}).`,
      );
      refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "22px" }}>
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
            Low-Code Orchestration · OMG BPMN 2.0 · $0.00 HITL Guardrail
          </span>
          <h2 style={{ margin: 0 }}>
            Visual BPMN Process &amp; Approval Designer
          </h2>
          <p
            style={{
              color: "var(--muted)",
              margin: "6px 0 0",
              fontSize: "0.92rem",
              maxWidth: "780px",
            }}
          >
            Visually design multi-stage document approval chains (e.g. Contract
            &gt; $50k → Legal Counsel → CFO → AI Compliance Check), generate
            flows from natural language, simulate branches with live path
            highlighting, and export standard BPMN 2.0 XML.
          </p>
        </div>
        <button
          type="button"
          className="secondary mgmt-action-btn"
          onClick={refresh}
          disabled={loading || busy}
        >
          {loading ? "Refreshing..." : "Refresh Flows"}
        </button>
      </div>

      {error && (
        <div className="mgmt-error-banner" role="alert">
          <strong>Workflow engine error:</strong> {error}
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
          <span className="mgmt-kpi-label">Active BPMN Workflows</span>
          <div
            style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.activeWorkflows}
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            Acyclic DAG validated · FORCE RLS
          </div>
        </div>
        <div className="mgmt-kpi-card" style={{ padding: "18px 20px" }}>
          <span className="mgmt-kpi-label">Pending Human Approvals</span>
          <div
            style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.pendingApprovals}
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            Paused at HITL sign-off gates
          </div>
        </div>
        <div className="mgmt-kpi-card" style={{ padding: "18px 20px" }}>
          <span className="mgmt-kpi-label">Configured Process Nodes</span>
          <div
            style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.totalNodes}
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            Gateways, Legal/CFO &amp; Read-Only AI
          </div>
        </div>
        <div className="mgmt-kpi-card" style={{ padding: "18px 20px" }}>
          <span className="mgmt-kpi-label">Completed Approvals</span>
          <div
            style={{ fontSize: "1.6rem", fontWeight: 700, marginTop: "6px" }}
          >
            {kpis.completedInstances}
          </div>
          <div
            style={{
              fontSize: "0.78rem",
              color: "var(--muted)",
              marginTop: "4px",
            }}
          >
            Immutable audit trail logged
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="BPMN workflow sections"
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
            { id: "canvas", label: "Visual BPMN Canvas & Dry-Run" },
            {
              id: "inbox",
              label: `Live Approvals Inbox (${data?.instances.length ?? 0})`,
            },
            { id: "templates", label: "Enterprise BPMN Templates" },
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

      {/* TAB 1: Visual BPMN Canvas & Dry-Run */}
      {data && activeTab === "canvas" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* AI Prompt-to-BPMN Bar */}
          <form
            onSubmit={handleGenerateFromPrompt}
            className="mgmt-kpi-card"
            style={{
              padding: "18px 20px",
              display: "flex",
              flexWrap: "wrap",
              alignItems: "flex-end",
              gap: "12px",
            }}
          >
            <div style={{ flex: "1 1 360px" }}>
              <label htmlFor="bpmn-ai-prompt" className="mgmt-kpi-label">
                AI Architect: Describe Approval Chain in Plain English or
                Russian
              </label>
              <input
                id="bpmn-ai-prompt"
                type="text"
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                style={{ width: "100%", marginTop: "6px", padding: "9px 12px" }}
              />
            </div>
            <button type="submit" className="mgmt-action-btn" disabled={busy}>
              Generate Visual BPMN Flow
            </button>
          </form>

          {/* Workflow Selector & Canvas Card */}
          <section className="mgmt-kpi-card" style={{ padding: "20px" }}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "12px",
                marginBottom: "14px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  flexWrap: "wrap",
                }}
              >
                <label
                  htmlFor="bpmn-wf-select"
                  className="mgmt-kpi-label"
                  style={{ margin: 0 }}
                >
                  Active Workflow:
                </label>
                <select
                  id="bpmn-wf-select"
                  value={selectedWorkflowId}
                  onChange={(e) => handleSelectWorkflow(e.target.value)}
                  style={{ padding: "7px 10px", minWidth: "260px" }}
                >
                  {data.workflows.length === 0 ? (
                    <option value="">No workflows installed yet</option>
                  ) : (
                    data.workflows.map((wf) => (
                      <option key={wf.id} value={wf.id}>
                        {wf.display_name} (v{wf.version})
                      </option>
                    ))
                  )}
                </select>
              </div>
              {selectedWorkflow && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                  <button
                    type="button"
                    className="secondary mgmt-btn-small"
                    disabled={busy}
                    onClick={handleExportXml}
                  >
                    Export BPMN 2.0 XML
                  </button>
                  <button
                    type="button"
                    className="mgmt-action-btn"
                    disabled={busy}
                    onClick={handleSaveCanvas}
                  >
                    Save Canvas Changes
                  </button>
                </div>
              )}
            </div>

            {canvasNodes.length === 0 ? (
              <div
                style={{
                  padding: "24px",
                  textAlign: "center",
                  color: "var(--muted)",
                }}
              >
                Install an Enterprise BPMN template or generate a workflow from
                a text prompt above to open the interactive visual canvas.
              </div>
            ) : (
              <div
                tabIndex={0}
                role="region"
                aria-label="Interactive visual BPMN workflow canvas"
                style={{
                  overflowX: "auto",
                  border: "1px solid #e2e8f0",
                  borderRadius: "12px",
                  background:
                    "radial-gradient(#cbd5e1 1px, transparent 1px), #f8fafc",
                  backgroundSize: "18px 18px",
                  padding: "12px",
                }}
              >
                <svg
                  viewBox="0 0 1140 330"
                  style={{
                    width: "100%",
                    minWidth: "920px",
                    height: "330px",
                    display: "block",
                  }}
                  role="img"
                  aria-label="Visual BPMN approval graph"
                >
                  <defs>
                    <marker
                      id="bpmn-arrow-default"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="7"
                      markerHeight="7"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748b" />
                    </marker>
                    <marker
                      id="bpmn-arrow-active"
                      viewBox="0 0 10 10"
                      refX="9"
                      refY="5"
                      markerWidth="7"
                      markerHeight="7"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 1 L 10 5 L 0 9 z" fill="#16a34a" />
                    </marker>
                  </defs>

                  {/* Directed Edges */}
                  {canvasEdges.map((edge) => {
                    const src = canvasNodes.find(
                      (n) => n.id === edge.source_id,
                    );
                    const tgt = canvasNodes.find(
                      (n) => n.id === edge.target_id,
                    );
                    if (!src || !tgt) return null;
                    const x1 = src.x + NODE_WIDTH;
                    const y1 = src.y + NODE_HEIGHT / 2;
                    const x2 = tgt.x;
                    const y2 = tgt.y + NODE_HEIGHT / 2;
                    const cx = (x1 + x2) / 2;
                    const isTraversed =
                      visitedSet.has(src.id) && visitedSet.has(tgt.id);
                    const midX = (x1 + x2) / 2;
                    const isHorizontal = Math.abs(y1 - y2) < 12;
                    const midY = isHorizontal ? y1 - 18 : (y1 + y2) / 2 - 8;
                    return (
                      <g key={edge.id}>
                        <path
                          d={`M ${x1} ${y1} C ${cx} ${y1}, ${cx} ${y2}, ${x2} ${y2}`}
                          fill="none"
                          stroke={isTraversed ? "#16a34a" : "#64748b"}
                          strokeWidth={isTraversed ? 3 : 2}
                          markerEnd={
                            isTraversed
                              ? "url(#bpmn-arrow-active)"
                              : "url(#bpmn-arrow-default)"
                          }
                        />
                        {edge.label && (
                          <g>
                            <rect
                              x={midX - 28}
                              y={midY - 9}
                              width={56}
                              height={17}
                              rx={8}
                              fill={isTraversed ? "#dcfce7" : "#ffffff"}
                              stroke={isTraversed ? "#16a34a" : "#cbd5e1"}
                              strokeWidth={1}
                            />
                            <text
                              x={midX}
                              y={midY + 3}
                              textAnchor="middle"
                              fontSize="9.5"
                              fontWeight="600"
                              fill={isTraversed ? "#166534" : "#334155"}
                            >
                              {edge.label}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}

                  {/* Interactive BPMN Nodes */}
                  {canvasNodes.map((node) => {
                    const st = NODE_STYLE[node.node_type];
                    const isSelected = node.id === selectedNodeId;
                    const isVisited = visitedSet.has(node.id);
                    return (
                      <g
                        key={node.id}
                        transform={`translate(${node.x}, ${node.y})`}
                        onClick={() => setSelectedNodeId(node.id)}
                        style={{ cursor: "pointer" }}
                      >
                        {isVisited && (
                          <rect
                            x={-4}
                            y={-4}
                            width={NODE_WIDTH + 8}
                            height={NODE_HEIGHT + 8}
                            rx={14}
                            fill="none"
                            stroke="#16a34a"
                            strokeWidth={2.5}
                            strokeDasharray="4 2"
                          />
                        )}
                        <rect
                          x={0}
                          y={0}
                          width={NODE_WIDTH}
                          height={NODE_HEIGHT}
                          rx={11}
                          fill={st.bg}
                          stroke={isSelected ? "#0f172a" : st.border}
                          strokeWidth={isSelected ? 2.5 : 1.5}
                        />
                        <rect
                          x={8}
                          y={7}
                          width={84}
                          height={15}
                          rx={4}
                          fill={st.badgeBg}
                        />
                        <text
                          x={13}
                          y={18}
                          fontSize="9"
                          fontWeight="700"
                          fill={
                            node.node_type === "end_approved"
                              ? "#ffffff"
                              : st.text
                          }
                        >
                          {st.badge}
                        </text>
                        <text
                          x={8}
                          y={38}
                          fontSize="11.2"
                          fontWeight="700"
                          fill={st.text}
                        >
                          {node.label.slice(0, 23)}
                        </text>
                        <text
                          x={8}
                          y={54}
                          fontSize="10"
                          fill={
                            node.node_type === "end_approved"
                              ? "#cbd5e1"
                              : "#475569"
                          }
                        >
                          {getNodeSubtitle(node).slice(0, 24)}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            )}

            {/* Selected Node Inspector + Dry-Run Simulator side-by-side */}
            {selectedWorkflow && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns:
                    "repeat(auto-fit, minmax(min(360px, 100%), 1fr))",
                  gap: "18px",
                  marginTop: "18px",
                }}
              >
                {/* Node Inspector */}
                <div
                  style={{
                    border: "1px solid #e2e8f0",
                    borderRadius: "10px",
                    padding: "16px",
                    background: "#ffffff",
                  }}
                >
                  <h3 style={{ margin: "0 0 10px", fontSize: "0.96rem" }}>
                    Node Properties Inspector
                  </h3>
                  {selectedNode ? (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "10px",
                      }}
                    >
                      <div>
                        <label
                          htmlFor="node-label-inp"
                          className="mgmt-kpi-label"
                        >
                          Node Label ({selectedNode.node_type})
                        </label>
                        <input
                          id="node-label-inp"
                          type="text"
                          value={selectedNode.label}
                          onChange={(e) =>
                            handleUpdateSelectedNode({ label: e.target.value })
                          }
                          style={{
                            width: "100%",
                            marginTop: "4px",
                            padding: "8px 10px",
                          }}
                        />
                      </div>

                      {selectedNode.node_type === "human_approval" && (
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "1fr 110px",
                            gap: "10px",
                          }}
                        >
                          <div>
                            <label
                              htmlFor="node-role-inp"
                              className="mgmt-kpi-label"
                            >
                              Approver Role
                            </label>
                            <input
                              id="node-role-inp"
                              type="text"
                              value={String(
                                selectedNode.config.approver_role ?? "",
                              )}
                              onChange={(e) =>
                                handleUpdateSelectedNode({
                                  config: {
                                    ...selectedNode.config,
                                    approver_role: e.target.value,
                                  },
                                })
                              }
                              style={{
                                width: "100%",
                                marginTop: "4px",
                                padding: "8px 10px",
                              }}
                            />
                          </div>
                          <div>
                            <label
                              htmlFor="node-sla-inp"
                              className="mgmt-kpi-label"
                            >
                              SLA (hrs)
                            </label>
                            <input
                              id="node-sla-inp"
                              type="number"
                              min={1}
                              value={Number(
                                selectedNode.config.sla_hours ?? 24,
                              )}
                              onChange={(e) =>
                                handleUpdateSelectedNode({
                                  config: {
                                    ...selectedNode.config,
                                    sla_hours: Number(e.target.value) || 24,
                                  },
                                })
                              }
                              style={{
                                width: "100%",
                                marginTop: "4px",
                                padding: "8px 10px",
                              }}
                            />
                          </div>
                        </div>
                      )}

                      {selectedNode.node_type === "exclusive_gateway" && (
                        <div>
                          <label
                            htmlFor="node-thresh-inp"
                            className="mgmt-kpi-label"
                          >
                            Threshold Amount (USD)
                          </label>
                          <input
                            id="node-thresh-inp"
                            type="number"
                            min={0}
                            value={Math.round(
                              Number(selectedNode.config.value ?? 5000000) /
                                100,
                            )}
                            onChange={(e) => {
                              const usd = Number(e.target.value) || 0;
                              handleUpdateSelectedNode({
                                config: {
                                  ...selectedNode.config,
                                  value: Math.round(usd * 100),
                                },
                              });
                            }}
                            style={{
                              width: "100%",
                              marginTop: "4px",
                              padding: "8px 10px",
                            }}
                          />
                        </div>
                      )}
                    </div>
                  ) : (
                    <p
                      style={{
                        color: "var(--muted)",
                        margin: 0,
                        fontSize: "0.86rem",
                      }}
                    >
                      Click any BPMN node on the canvas to inspect or edit its
                      properties.
                    </p>
                  )}
                </div>

                {/* Live Dry-Run Path Simulator */}
                <form
                  onSubmit={handleDryRun}
                  style={{
                    border: "1px solid #e2e8f0",
                    borderRadius: "10px",
                    padding: "16px",
                    background: "#ffffff",
                    display: "flex",
                    flexDirection: "column",
                    gap: "12px",
                  }}
                >
                  <h3 style={{ margin: 0, fontSize: "0.96rem" }}>
                    Live Path Dry-Run Simulator
                  </h3>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns:
                        "repeat(auto-fit, minmax(110px, 1fr))",
                      gap: "10px",
                    }}
                  >
                    <div>
                      <label htmlFor="sim-wf-amt" className="mgmt-kpi-label">
                        Amount (USD)
                      </label>
                      <input
                        id="sim-wf-amt"
                        type="number"
                        min={0}
                        value={simAmountUsd}
                        onChange={(e) => setSimAmountUsd(e.target.value)}
                        style={{
                          width: "100%",
                          marginTop: "4px",
                          padding: "8px 10px",
                        }}
                      />
                    </div>
                    <div>
                      <label htmlFor="sim-wf-reg" className="mgmt-kpi-label">
                        Region
                      </label>
                      <input
                        id="sim-wf-reg"
                        type="text"
                        value={simRegion}
                        onChange={(e) => setSimRegion(e.target.value)}
                        style={{
                          width: "100%",
                          marginTop: "4px",
                          padding: "8px 10px",
                        }}
                      />
                    </div>
                    <div>
                      <label htmlFor="sim-wf-risk" className="mgmt-kpi-label">
                        AI Risk (0–100)
                      </label>
                      <input
                        id="sim-wf-risk"
                        type="number"
                        min={0}
                        max={100}
                        value={simRisk}
                        onChange={(e) => setSimRisk(e.target.value)}
                        style={{
                          width: "100%",
                          marginTop: "4px",
                          padding: "8px 10px",
                        }}
                      />
                    </div>
                  </div>
                  <div>
                    <button
                      type="submit"
                      className="mgmt-action-btn"
                      disabled={busy}
                    >
                      Simulate Path on Canvas
                    </button>
                  </div>

                  {dryRunResult && (
                    <div
                      style={{
                        padding: "10px 12px",
                        borderRadius: "8px",
                        background: "#f0fdf4",
                        border: "1px solid #86efac",
                        fontSize: "0.82rem",
                        color: "#14532d",
                      }}
                    >
                      <strong>
                        Simulated Outcome:{" "}
                        {dryRunResult.simulated_status.toUpperCase()}
                      </strong>{" "}
                      ({dryRunResult.trace.length} steps highlighted on canvas)
                      <ol style={{ margin: "6px 0 0", paddingLeft: "18px" }}>
                        {dryRunResult.trace.map((step, idx) => (
                          <li key={`${step.node_id}-${idx}`}>
                            <strong>{step.label}:</strong> {step.detail}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </form>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 2: Live Approvals Inbox */}
      {data && activeTab === "inbox" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {selectedWorkflow && (
            <form
              onSubmit={handleStartInstance}
              className="mgmt-kpi-card"
              style={{
                padding: "20px",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
              }}
            >
              <h3 style={{ margin: 0, fontSize: "1rem" }}>
                Launch Live Approval Instance ({selectedWorkflow.display_name})
              </h3>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: "12px",
                }}
              >
                <div>
                  <label htmlFor="inst-ref" className="mgmt-kpi-label">
                    Document Reference
                  </label>
                  <input
                    id="inst-ref"
                    type="text"
                    required
                    value={instRef}
                    onChange={(e) => setInstRef(e.target.value)}
                    style={{
                      width: "100%",
                      marginTop: "4px",
                      padding: "8px 10px",
                    }}
                  />
                </div>
                <div>
                  <label htmlFor="inst-title" className="mgmt-kpi-label">
                    Contract / PO Title
                  </label>
                  <input
                    id="inst-title"
                    type="text"
                    required
                    value={instTitle}
                    onChange={(e) => setInstTitle(e.target.value)}
                    style={{
                      width: "100%",
                      marginTop: "4px",
                      padding: "8px 10px",
                    }}
                  />
                </div>
                <div>
                  <label htmlFor="inst-amt" className="mgmt-kpi-label">
                    Value (USD)
                  </label>
                  <input
                    id="inst-amt"
                    type="number"
                    min={0}
                    required
                    value={instAmountUsd}
                    onChange={(e) => setInstAmountUsd(e.target.value)}
                    style={{
                      width: "100%",
                      marginTop: "4px",
                      padding: "8px 10px",
                    }}
                  />
                </div>
              </div>
              <div>
                <button
                  type="submit"
                  className="mgmt-action-btn"
                  disabled={busy}
                >
                  Submit into Approval Chain
                </button>
              </div>
            </form>
          )}

          <section className="mgmt-kpi-card" style={{ padding: "20px" }}>
            <h3 style={{ margin: "0 0 12px" }}>Approval Execution Queue</h3>
            {data.instances.length === 0 ? (
              <p style={{ color: "var(--muted)", margin: 0 }}>
                No workflow instances have been launched yet.
              </p>
            ) : (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px",
                }}
              >
                {data.instances.map((inst) => (
                  <div
                    key={inst.id}
                    style={{
                      border: "1px solid #e2e8f0",
                      borderRadius: "10px",
                      padding: "16px",
                      background: "#ffffff",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "12px",
                      }}
                    >
                      <div>
                        <strong
                          style={{ fontSize: "0.96rem", color: "#0f172a" }}
                        >
                          {inst.reference_code} · {inst.entity_title}
                        </strong>
                        <div
                          style={{
                            fontSize: "0.84rem",
                            color: "#475569",
                            marginTop: "3px",
                          }}
                        >
                          {inst.workflow_name} · Value:{" "}
                          <strong>{formatUsd(inst.amount_cents)}</strong> ·
                          Current Stage:{" "}
                          <strong>{inst.current_node_label}</strong>
                        </div>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <span className="mgmt-status-pill">{inst.status}</span>
                        {inst.status === "awaiting_approval" && (
                          <>
                            <button
                              type="button"
                              className="mgmt-action-btn"
                              disabled={busy}
                              onClick={() => handleDecide(inst.id, "approve")}
                            >
                              Approve Step
                            </button>
                            <button
                              type="button"
                              className="secondary mgmt-btn-small"
                              disabled={busy}
                              onClick={() => handleDecide(inst.id, "reject")}
                            >
                              Reject
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    {inst.trace.length > 0 && (
                      <ol
                        style={{
                          margin: "10px 0 0",
                          paddingLeft: "18px",
                          fontSize: "0.82rem",
                          color: "#334155",
                        }}
                      >
                        {inst.trace.map((step, idx) => (
                          <li key={`${inst.id}-${step.node_id}-${idx}`}>
                            <strong>{step.label}</strong> ({step.outcome}):{" "}
                            {step.detail}
                          </li>
                        ))}
                      </ol>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 3: Enterprise Templates */}
      {data && activeTab === "templates" && (
        <section className="mgmt-kpi-card" style={{ padding: "22px" }}>
          <h3 style={{ margin: "0 0 6px" }}>
            1-Click Enterprise BPMN Blueprints
          </h3>
          <p
            style={{
              margin: "0 0 16px",
              color: "var(--muted)",
              fontSize: "0.88rem",
            }}
          >
            Install pre-validated corporate approval chains with built-in $0.00
            Human-in-the-Loop gates and read-only AI compliance checks.
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit, minmax(min(300px, 100%), 1fr))",
              gap: "16px",
            }}
          >
            {data.presets.map((preset) => (
              <div
                key={preset.workflow_code}
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
                      {preset.installed
                        ? "Installed"
                        : `${preset.node_count} nodes`}
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
                </div>
                <button
                  type="button"
                  className={
                    preset.installed
                      ? "secondary mgmt-btn-small"
                      : "mgmt-action-btn"
                  }
                  disabled={busy || preset.installed}
                  onClick={() => handleInstallPreset(preset.workflow_code)}
                  style={{ alignSelf: "flex-start" }}
                >
                  {preset.installed
                    ? "Template Installed"
                    : "Install Blueprint"}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
