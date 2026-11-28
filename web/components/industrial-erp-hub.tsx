"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import {
  adjustMrpMaterialStock,
  createEamAsset,
  createEamRule,
  createMrpMaterial,
  createMrpRecipe,
  createMrpRun,
  deleteEamRule,
  explodeMrpBom,
  fetchEamAssets,
  fetchEamRules,
  fetchEamTelemetry,
  fetchEamWorkOrders,
  fetchMrpMaterials,
  fetchMrpRecipes,
  fetchMrpRuns,
  generateDraftPoForRun,
  ingestEamTelemetry,
  rotateEamToken,
  transitionMrpRun,
  updateEamWorkOrder,
  type AssetCategory,
  type EamAsset,
  type EamRule,
  type EamTelemetry,
  type EamWorkOrder,
  type MaterialKind,
  type MaterialUnit,
  type MetricKey,
  type MrpExplosion,
  type MrpMaterial,
  type MrpProductionRun,
  type MrpRecipe,
  type RuleOperator,
  type WoPriority,
} from "../lib/industrial-api";

type TabId = "mrp_bom" | "mrp_runs" | "eam_iot" | "eam_wos";

function fmtQty(milli: number, unit?: string): string {
  const v = (milli / 1000).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 3,
  });
  return unit ? `${v} ${unit}` : v;
}

function fmtUsd(cents: number): string {
  return `$${(cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : "Operation failed.";
}

const METRIC_LABELS: Record<MetricKey, string> = {
  engine_hours: "Engine Hours (hrs)",
  odometer_miles: "Odometer (miles)",
  temperature_c: "Temperature (°C)",
  vibration_mm_s: "Vibration (mm/s)",
  oil_pressure_psi: "Oil Pressure (psi)",
  battery_voltage: "Battery Voltage (V)",
  fuel_mpg: "Fuel Economy (mpg)",
};

const CATEGORY_LABELS: Record<AssetCategory, string> = {
  fleet_vehicle: "Fleet Vehicle / Truck",
  heavy_machinery: "Heavy Machinery",
  cnc_industrial: "CNC / Production Line",
  hvac_facility: "HVAC / Facility Unit",
  power_generator: "Power Generator",
  iot_sensor_node: "Industrial IoT Gateway",
};

export function IndustrialErpHub({ businessId }: { businessId: string }) {
  const [activeTab, setActiveTab] = useState<TabId>("mrp_bom");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [materials, setMaterials] = useState<MrpMaterial[]>([]);
  const [recipes, setRecipes] = useState<MrpRecipe[]>([]);
  const [runs, setRuns] = useState<MrpProductionRun[]>([]);
  const [assets, setAssets] = useState<EamAsset[]>([]);
  const [rules, setRules] = useState<EamRule[]>([]);
  const [telemetry, setTelemetry] = useState<EamTelemetry[]>([]);
  const [workOrders, setWorkOrders] = useState<EamWorkOrder[]>([]);

  // Material form state
  const [matSku, setMatSku] = useState("");
  const [matName, setMatName] = useState("");
  const [matKind, setMatKind] = useState<MaterialKind>("raw");
  const [matUnit, setMatUnit] = useState<MaterialUnit>("ton");
  const [matOnHand, setMatOnHand] = useState("10");
  const [matUnitCost, setMatUnitCost] = useState("450");
  const [matVendor, setMatVendor] = useState("");
  const [savingMat, setSavingMat] = useState(false);

  // BOM recipe form state
  const [recCode, setRecCode] = useState("");
  const [recName, setRecName] = useState("");
  const [recOutputId, setRecOutputId] = useState("");
  const [recOutQty, setRecOutQty] = useState("1");
  const [recCompAId, setRecCompAId] = useState("");
  const [recCompAQty, setRecCompAQty] = useState("0.6");
  const [recCompAScrap, setRecCompAScrap] = useState("2");
  const [recCompBId, setRecCompBId] = useState("");
  const [recCompBQty, setRecCompBQty] = useState("0.4");
  const [savingRec, setSavingRec] = useState(false);

  // BOM explosion + run state
  const [expRecipeId, setExpRecipeId] = useState("");
  const [expTargetQty, setExpTargetQty] = useState("2.5");
  const [explosion, setExplosion] = useState<MrpExplosion | null>(null);
  const [runNotes, setRunNotes] = useState("");
  const [launchingRun, setLaunchingRun] = useState(false);

  // EAM Asset form state
  const [assetTag, setAssetTag] = useState("");
  const [assetName, setAssetName] = useState("");
  const [assetCategory, setAssetCategory] =
    useState<AssetCategory>("fleet_vehicle");
  const [assetSerial, setAssetSerial] = useState("");
  const [assetLocation, setAssetLocation] = useState("");
  const [assetHours, setAssetHours] = useState("1200");
  const [latestToken, setLatestToken] = useState<{
    tag: string;
    token: string;
  } | null>(null);
  const [copiedIotKind, setCopiedIotKind] = useState<"token" | "curl" | null>(
    null,
  );
  const [savingAsset, setSavingAsset] = useState(false);

  // EAM Rule form state
  const [ruleAssetId, setRuleAssetId] = useState("");
  const [ruleName, setRuleName] = useState("");
  const [ruleMetric, setRuleMetric] = useState<MetricKey>("engine_hours");
  const [ruleOp, setRuleOp] = useState<RuleOperator>("interval_every");
  const [ruleThreshold, setRuleThreshold] = useState("500");
  const [ruleLeadPct, setRuleLeadPct] = useState("90");
  const [rulePriority, setRulePriority] = useState<WoPriority>("high");
  const [ruleWoTitle, setRuleWoTitle] = useState("");
  const [savingRule, setSavingRule] = useState(false);

  // EAM Telemetry form state
  const [telAssetId, setTelAssetId] = useState("");
  const [telMetric, setTelMetric] = useState<MetricKey>("engine_hours");
  const [telValue, setTelValue] = useState("1460");
  const [telNotes, setTelNotes] = useState("");
  const [sendingTel, setSendingTel] = useState(false);

  // Unique input IDs for WCAG labels
  const matSkuId = useId();
  const matNameId = useId();
  const matKindId = useId();
  const matUnitId = useId();
  const matOnHandId = useId();
  const matCostId = useId();
  const matVendorId = useId();

  const recCodeId = useId();
  const recNameId = useId();
  const recOutId = useId();
  const recOutQtyId = useId();
  const recCompAInputId = useId();
  const recCompAQtyId = useId();
  const recCompAScrapId = useId();
  const recCompBInputId = useId();
  const recCompBQtyId = useId();

  const expRecId = useId();
  const expQtyId = useId();
  const runNotesId = useId();

  const assetTagId = useId();
  const assetNameId = useId();
  const assetCatId = useId();
  const assetSerialId = useId();
  const assetLocId = useId();
  const assetHoursId = useId();

  const ruleAssetInputId = useId();
  const ruleNameId = useId();
  const ruleMetricId = useId();
  const ruleOpId = useId();
  const ruleThrId = useId();
  const ruleLeadId = useId();
  const rulePriId = useId();
  const ruleTitleId = useId();

  const telAssetInputId = useId();
  const telMetricId = useId();
  const telValId = useId();
  const telNotesId = useId();

  const reloadAll = useCallback(async () => {
    const [m, r, pr, a, ru, t, wo] = await Promise.all([
      fetchMrpMaterials(businessId),
      fetchMrpRecipes(businessId),
      fetchMrpRuns(businessId),
      fetchEamAssets(businessId),
      fetchEamRules(businessId),
      fetchEamTelemetry(businessId),
      fetchEamWorkOrders(businessId),
    ]);
    setMaterials(m);
    setRecipes(r);
    setRuns(pr);
    setAssets(a);
    setRules(ru);
    setTelemetry(t);
    setWorkOrders(wo);
    const firstRecipe = r[0];
    if (firstRecipe) setExpRecipeId((cur) => cur || firstRecipe.id);
    const firstAsset = a[0];
    if (firstAsset) {
      setRuleAssetId((cur) => cur || firstAsset.id);
      setTelAssetId((cur) => cur || firstAsset.id);
    }
  }, [businessId]);

  useEffect(() => {
    let active = true;
    async function init() {
      try {
        await reloadAll();
      } catch (err) {
        if (active) setError(errText(err));
      } finally {
        if (active) setLoading(false);
      }
    }
    void init();
    return () => {
      active = false;
    };
  }, [reloadAll]);

  async function onCreateMaterial(e: React.FormEvent) {
    e.preventDefault();
    setSavingMat(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createMrpMaterial(businessId, {
        sku: matSku.trim().toUpperCase(),
        name: matName.trim(),
        material_kind: matKind,
        unit: matUnit,
        on_hand_milli: Math.max(0, Math.round(Number(matOnHand || "0") * 1000)),
        reorder_point_milli: 0,
        unit_cost_cents: Math.max(
          0,
          Math.round(Number(matUnitCost || "0") * 100),
        ),
        preferred_vendor_name: matVendor.trim(),
      });
      setMaterials((prev) => [...prev, created]);
      setMatSku("");
      setMatName("");
      setMatVendor("");
      setNotice(`Material ${created.sku} (${created.name}) added.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingMat(false);
    }
  }

  async function onQuickReceive(material: MrpMaterial) {
    setError(null);
    setNotice(null);
    try {
      const updated = await adjustMrpMaterialStock(
        businessId,
        material.id,
        1000,
      );
      setMaterials((prev) =>
        prev.map((m) => (m.id === updated.id ? updated : m)),
      );
      setNotice(
        `Received +1.00 ${updated.unit} into ${updated.sku} (On hand: ${fmtQty(updated.on_hand_milli, updated.unit)}).`,
      );
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onCreateRecipe(e: React.FormEvent) {
    e.preventDefault();
    if (!recOutputId || !recCompAId) {
      setError("Select an output product and at least one raw material.");
      return;
    }
    setSavingRec(true);
    setError(null);
    setNotice(null);
    try {
      const lines = [
        {
          component_material_id: recCompAId,
          qty_per_batch_milli: Math.max(
            1,
            Math.round(Number(recCompAQty || "0.5") * 1000),
          ),
          scrap_bps: Math.max(
            0,
            Math.min(5000, Math.round(Number(recCompAScrap || "0") * 100)),
          ),
          notes: "",
        },
      ];
      if (recCompBId && recCompBId !== recCompAId) {
        lines.push({
          component_material_id: recCompBId,
          qty_per_batch_milli: Math.max(
            1,
            Math.round(Number(recCompBQty || "0.25") * 1000),
          ),
          scrap_bps: 0,
          notes: "",
        });
      }
      const created = await createMrpRecipe(businessId, {
        code: recCode.trim().toUpperCase(),
        name: recName.trim(),
        output_material_id: recOutputId,
        output_qty_milli: Math.max(
          1,
          Math.round(Number(recOutQty || "1") * 1000),
        ),
        lead_time_days: 1,
        notes: "",
        lines,
      });
      setRecipes((prev) => [...prev, created]);
      setExpRecipeId(created.id);
      setRecCode("");
      setRecName("");
      setNotice(
        `BOM recipe ${created.code} created (${created.lines.length} component line(s)).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingRec(false);
    }
  }

  async function onPreviewExplosion(e: React.FormEvent) {
    e.preventDefault();
    if (!expRecipeId) return;
    setError(null);
    setNotice(null);
    try {
      const res = await explodeMrpBom(
        businessId,
        expRecipeId,
        Math.max(1, Math.round(Number(expTargetQty || "1") * 1000)),
      );
      setExplosion(res);
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onLaunchRun() {
    if (!expRecipeId) return;
    setLaunchingRun(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createMrpRun(businessId, {
        recipe_id: expRecipeId,
        target_qty_milli: Math.max(
          1,
          Math.round(Number(expTargetQty || "1") * 1000),
        ),
        notes: runNotes.trim(),
        reserve_available: true,
      });
      await reloadAll();
      setExplosion(null);
      setRunNotes("");
      setActiveTab("mrp_runs");
      setNotice(
        `Production run ${created.run_number} created — available raw materials atomically reserved (${created.shortage_count} shortage line(s)).`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setLaunchingRun(false);
    }
  }

  async function onTransitionRun(
    runId: string,
    action: "start" | "complete" | "cancel",
  ) {
    setError(null);
    setNotice(null);
    try {
      const updated = await transitionMrpRun(businessId, runId, action);
      await reloadAll();
      setNotice(`Run ${updated.run_number} -> ${updated.status}.`);
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onDraftPo(runId: string) {
    setError(null);
    setNotice(null);
    try {
      const po = await generateDraftPoForRun(businessId, runId);
      await reloadAll();
      setNotice(
        `Draft Purchase Order ${po.po_number} created (${fmtUsd(po.total_cents)}) in Commercial & PO for human approval.`,
      );
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onCreateAsset(e: React.FormEvent) {
    e.preventDefault();
    setSavingAsset(true);
    setError(null);
    setNotice(null);
    try {
      const res = await createEamAsset(businessId, {
        asset_tag: assetTag.trim().toUpperCase(),
        name: assetName.trim(),
        category: assetCategory,
        serial_number: assetSerial.trim(),
        location_label: assetLocation.trim(),
        engine_hours_milli: Math.max(
          0,
          Math.round(Number(assetHours || "0") * 1000),
        ),
        odometer_miles_milli: 0,
      });
      setAssets((prev) => [res.asset, ...prev]);
      setRuleAssetId(res.asset.id);
      setTelAssetId(res.asset.id);
      setLatestToken({ tag: res.asset.asset_tag, token: res.iot_ingest_token });
      setCopiedIotKind(null);
      setAssetTag("");
      setAssetName("");
      setAssetSerial("");
      setAssetLocation("");
      setNotice(
        `Asset ${res.asset.asset_tag} registered with dedicated IoT ingest token.`,
      );
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingAsset(false);
    }
  }

  async function onRotateToken(asset: EamAsset) {
    setError(null);
    setNotice(null);
    try {
      const res = await rotateEamToken(businessId, asset.id);
      setAssets((prev) =>
        prev.map((a) => (a.id === res.asset.id ? res.asset : a)),
      );
      setLatestToken({ tag: res.asset.asset_tag, token: res.iot_ingest_token });
      setCopiedIotKind(null);
      setNotice(
        `Rotated IoT telemetry token for ${res.asset.asset_tag}. Copy it now — shown once.`,
      );
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onCopyIotSnippet(kind: "token" | "curl") {
    if (!latestToken) return;
    const origin =
      typeof window !== "undefined"
        ? window.location.origin
        : "https://www.amarkal-platform.com";
    const text =
      kind === "token"
        ? latestToken.token
        : `curl -X POST "${origin}/v1/public/iot/telemetry" -H "Content-Type: application/json" -H "X-AMARKAL-IoT-Token: ${latestToken.token}" -d '{"metric_key":"engine_hours","value_milli":1460000,"notes":"PLC gateway heartbeat"}'`;
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIotKind(kind);
      setNotice(
        kind === "token"
          ? `Copied IoT token for ${latestToken.tag} to clipboard.`
          : `Copied ready-to-run IoT telemetry cURL command for ${latestToken.tag}.`,
      );
    } catch {
      setError("Clipboard access was blocked by the browser.");
    }
  }

  async function onCreateRule(e: React.FormEvent) {
    e.preventDefault();
    if (!ruleAssetId) return;
    setSavingRule(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createEamRule(businessId, {
        asset_id: ruleAssetId,
        rule_name: ruleName.trim(),
        metric_key: ruleMetric,
        operator: ruleOp,
        threshold_milli: Math.max(
          1,
          Math.round(Number(ruleThreshold || "1") * 1000),
        ),
        warning_lead_pct: Math.max(
          50,
          Math.min(100, Math.round(Number(ruleLeadPct || "90"))),
        ),
        priority: rulePriority,
        wo_title_template: ruleWoTitle.trim(),
        wo_checklist:
          "Inspect wear components, log meter reading, verify safety.",
        auto_create_wo: true,
      });
      setRules((prev) => [created, ...prev]);
      setRuleName("");
      setRuleWoTitle("");
      setNotice(`Predictive rule "${created.rule_name}" activated.`);
    } catch (err) {
      setError(errText(err));
    } finally {
      setSavingRule(false);
    }
  }

  async function onDeleteRule(ruleId: string) {
    setError(null);
    try {
      await deleteEamRule(businessId, ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      setNotice("Predictive rule removed.");
    } catch (err) {
      setError(errText(err));
    }
  }

  async function onIngestTelemetry(e: React.FormEvent) {
    e.preventDefault();
    if (!telAssetId) return;
    setSendingTel(true);
    setError(null);
    setNotice(null);
    try {
      const res = await ingestEamTelemetry(businessId, {
        asset_id: telAssetId,
        metric_key: telMetric,
        value_milli: Math.round(Number(telValue || "0") * 1000),
        source: "telematics",
        notes: telNotes.trim(),
      });
      await reloadAll();
      setTelNotes("");
      if (res.auto_created_work_orders.length > 0) {
        const woNums = res.auto_created_work_orders
          .map((w) => w.wo_number)
          .join(", ");
        setNotice(
          `Telemetry anomaly detected on ${res.asset.asset_tag}! Auto-created predictive Work Order(s): ${woNums}.`,
        );
      } else {
        setNotice(
          `Telemetry recorded for ${res.asset.asset_tag} (Health Score: ${res.asset.health_score}/100).`,
        );
      }
    } catch (err) {
      setError(errText(err));
    } finally {
      setSendingTel(false);
    }
  }

  async function onUpdateWo(
    woId: string,
    status: "scheduled" | "in_progress" | "completed" | "cancelled",
  ) {
    setError(null);
    setNotice(null);
    try {
      const updated = await updateEamWorkOrder(businessId, woId, {
        status,
        completion_notes:
          status === "completed"
            ? "Predictive service completed on schedule."
            : "",
      });
      await reloadAll();
      setNotice(`Work Order ${updated.wo_number} marked ${updated.status}.`);
    } catch (err) {
      setError(errText(err));
    }
  }

  const openWoCount = workOrders.filter(
    (w) => w.status === "open" || w.status === "in_progress",
  ).length;
  const shortageRuns = runs.filter(
    (r) =>
      r.shortage_count > 0 &&
      r.status !== "cancelled" &&
      r.status !== "completed",
  ).length;

  return (
    <div className="usr-stack">
      <div className="mgmt-section-header">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.6rem" }}>
            Enterprise MRP II &amp; Predictive EAM (IoT)
          </h1>
          <p className="usr-muted" style={{ margin: "4px 0 0" }}>
            Multi-level Bill of Materials (BOM) explosion with atomic warehouse
            reservations, 1-click shortage Draft POs, and industrial IoT sensor
            telemetry with automated predictive maintenance Work Orders.
          </p>
        </div>
      </div>

      {/* Executive KPI Strip */}
      <div className="usr-grid">
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            BOM Recipes &amp; Materials
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {recipes.length} BOMs · {materials.length} SKUs
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Active Production Runs
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {
              runs.filter(
                (r) => r.status !== "completed" && r.status !== "cancelled",
              ).length
            }
            {shortageRuns > 0 ? ` (${shortageRuns} w/ shortage)` : ""}
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Monitored IoT Assets
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {assets.length} ·{" "}
            {assets.filter((a) => a.status === "maintenance_due").length} due
          </div>
        </div>
        <div className="usr-card">
          <div className="usr-muted" style={{ fontSize: "0.8rem" }}>
            Open Predictive Work Orders
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700, marginTop: 4 }}>
            {openWoCount}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="Industrial ERP sections"
        className="usr-inline"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "mrp_bom"}
          className={
            activeTab === "mrp_bom"
              ? "usr-small-btn"
              : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("mrp_bom")}
        >
          MRP II &amp; BOM Recipes ({recipes.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "mrp_runs"}
          className={
            activeTab === "mrp_runs"
              ? "usr-small-btn"
              : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("mrp_runs")}
        >
          Production Runs &amp; Reservations ({runs.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "eam_iot"}
          className={
            activeTab === "eam_iot"
              ? "usr-small-btn"
              : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("eam_iot")}
        >
          Predictive EAM &amp; IoT Sensors ({assets.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "eam_wos"}
          className={
            activeTab === "eam_wos"
              ? "usr-small-btn"
              : "secondary usr-small-btn"
          }
          onClick={() => setActiveTab("eam_wos")}
        >
          Predictive Work Orders ({openWoCount})
        </button>
      </div>

      {error && (
        <p className="usr-field-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="hold-note" style={{ margin: 0 }}>
          {notice}
        </p>
      )}
      {loading && (
        <p className="mgmt-loading" aria-live="polite">
          Loading MRP II &amp; Predictive EAM…
        </p>
      )}

      {/* TAB 1: MRP II & BOM Recipes */}
      {!loading && activeTab === "mrp_bom" && (
        <div className="usr-stack">
          <section className="usr-card" aria-labelledby="mrp-explosion-heading">
            <h2 id="mrp-explosion-heading" style={{ margin: "0 0 8px" }}>
              MRP II Net Requirements Explosion &amp; Atomic Reservation
            </h2>
            <p className="usr-muted" style={{ margin: "0 0 12px" }}>
              Calculate exact multi-level raw material needs (including scrap
              factor), inspect real-time warehouse availability, and launch a
              Production Run that atomically reserves stock.
            </p>
            <form
              onSubmit={(e) => void onPreviewExplosion(e)}
              className="usr-grid"
            >
              <label htmlFor={expRecId}>
                BOM Recipe
                <select
                  id={expRecId}
                  value={expRecipeId}
                  onChange={(e) => setExpRecipeId(e.target.value)}
                >
                  <option value="">Select BOM recipe…</option>
                  {recipes.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.code} — {r.name} (Batch:{" "}
                      {fmtQty(r.output_qty_milli, r.output_unit)})
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={expQtyId}>
                Target Output Quantity
                <input
                  id={expQtyId}
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={expTargetQty}
                  onChange={(e) => setExpTargetQty(e.target.value)}
                />
              </label>
              <label htmlFor={runNotesId}>
                Production Notes (optional)
                <input
                  id={runNotesId}
                  type="text"
                  value={runNotes}
                  onChange={(e) => setRunNotes(e.target.value)}
                  placeholder="Shift A batch / customer lot ref"
                />
              </label>
              <div
                className="usr-inline"
                style={{ alignSelf: "end", gap: 8, flexWrap: "wrap" }}
              >
                <button
                  type="submit"
                  className="secondary usr-small-btn"
                  disabled={!expRecipeId}
                >
                  Preview BOM Explosion
                </button>
                <button
                  type="button"
                  className="usr-small-btn"
                  disabled={!expRecipeId || launchingRun}
                  onClick={() => void onLaunchRun()}
                >
                  {launchingRun ? "Reserving…" : "Launch Run & Reserve Stock"}
                </button>
              </div>
            </form>

            {explosion && (
              <div style={{ marginTop: 16 }}>
                <div
                  className="usr-inline"
                  style={{
                    justifyContent: "space-between",
                    gap: 12,
                    marginBottom: 8,
                    flexWrap: "wrap",
                  }}
                >
                  <strong>
                    Explosion for {explosion.recipe_code} →{" "}
                    {fmtQty(explosion.target_qty_milli, explosion.output_unit)}
                  </strong>
                  <span>
                    Est. Material Cost:{" "}
                    <strong>
                      {fmtUsd(explosion.total_material_cost_cents)}
                    </strong>{" "}
                    ·{" "}
                    {explosion.can_fully_reserve
                      ? "100% Ready to Reserve"
                      : `${explosion.shortage_count} Shortage Line(s)`}
                  </span>
                </div>
                <div
                  style={{ overflowX: "auto" }}
                  tabIndex={0}
                  role="region"
                  aria-label="Scrollable industrial data table"
                >
                  <table className="mgmt-table">
                    <thead>
                      <tr>
                        <th>SKU</th>
                        <th>Material</th>
                        <th>Required</th>
                        <th>Available</th>
                        <th>Will Reserve</th>
                        <th>Shortage</th>
                        <th>Est. Cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {explosion.requirements.map((req) => (
                        <tr key={req.material_id}>
                          <td>
                            <code>{req.sku}</code>
                          </td>
                          <td>{req.name}</td>
                          <td>{fmtQty(req.required_milli, req.unit)}</td>
                          <td>{fmtQty(req.available_milli, req.unit)}</td>
                          <td>{fmtQty(req.reservable_milli, req.unit)}</td>
                          <td
                            style={{
                              fontWeight: req.shortage_milli > 0 ? 700 : 400,
                              color:
                                req.shortage_milli > 0 ? "#b91c1c" : "#15803d",
                            }}
                          >
                            {req.shortage_milli > 0
                              ? fmtQty(req.shortage_milli, req.unit)
                              : "0.00"}
                          </td>
                          <td>{fmtUsd(req.estimated_cost_cents)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </section>

          <section className="usr-card" aria-labelledby="mrp-materials-heading">
            <h2 id="mrp-materials-heading" style={{ margin: "0 0 10px" }}>
              Raw Materials, Sub-Assemblies &amp; Finished Goods (
              {materials.length})
            </h2>
            <form
              onSubmit={(e) => void onCreateMaterial(e)}
              className="usr-grid"
              style={{ marginBottom: 14 }}
            >
              <label htmlFor={matSkuId}>
                SKU
                <input
                  id={matSkuId}
                  required
                  value={matSku}
                  onChange={(e) => setMatSku(e.target.value)}
                  placeholder="RAW-STEEL-A"
                />
              </label>
              <label htmlFor={matNameId}>
                Material Name
                <input
                  id={matNameId}
                  required
                  value={matName}
                  onChange={(e) => setMatName(e.target.value)}
                  placeholder="Cold-Rolled Steel Coil"
                />
              </label>
              <label htmlFor={matKindId}>
                Kind
                <select
                  id={matKindId}
                  value={matKind}
                  onChange={(e) => setMatKind(e.target.value as MaterialKind)}
                >
                  <option value="raw">Raw Material</option>
                  <option value="subassembly">Sub-Assembly</option>
                  <option value="finished">Finished Good</option>
                </select>
              </label>
              <label htmlFor={matUnitId}>
                Unit
                <select
                  id={matUnitId}
                  value={matUnit}
                  onChange={(e) => setMatUnit(e.target.value as MaterialUnit)}
                >
                  <option value="ton">ton</option>
                  <option value="kg">kg</option>
                  <option value="lb">lb</option>
                  <option value="liter">liter</option>
                  <option value="gallon">gallon</option>
                  <option value="meter">meter</option>
                  <option value="unit">unit</option>
                  <option value="box">box</option>
                </select>
              </label>
              <label htmlFor={matOnHandId}>
                Initial On-Hand
                <input
                  id={matOnHandId}
                  type="number"
                  step="0.01"
                  min="0"
                  value={matOnHand}
                  onChange={(e) => setMatOnHand(e.target.value)}
                />
              </label>
              <label htmlFor={matCostId}>
                Unit Cost (USD)
                <input
                  id={matCostId}
                  type="number"
                  step="0.01"
                  min="0"
                  value={matUnitCost}
                  onChange={(e) => setMatUnitCost(e.target.value)}
                />
              </label>
              <label htmlFor={matVendorId}>
                Preferred Vendor (for Auto Draft PO)
                <input
                  id={matVendorId}
                  value={matVendor}
                  onChange={(e) => setMatVendor(e.target.value)}
                  placeholder="US Midwest Alloy Corp"
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingMat}
                >
                  {savingMat ? "Adding…" : "+ Add Material SKU"}
                </button>
              </div>
            </form>

            {materials.length > 0 && (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Scrollable industrial data table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      <th>SKU</th>
                      <th>Name</th>
                      <th>Kind</th>
                      <th>On Hand</th>
                      <th>Reserved</th>
                      <th>Available</th>
                      <th>Unit Cost</th>
                      <th>Stock</th>
                    </tr>
                  </thead>
                  <tbody>
                    {materials.map((m) => (
                      <tr key={m.id}>
                        <td>
                          <code>{m.sku}</code>
                        </td>
                        <td>{m.name}</td>
                        <td>{m.material_kind}</td>
                        <td>{fmtQty(m.on_hand_milli, m.unit)}</td>
                        <td>{fmtQty(m.reserved_milli, m.unit)}</td>
                        <td>
                          <strong>{fmtQty(m.available_milli, m.unit)}</strong>
                        </td>
                        <td>{fmtUsd(m.unit_cost_cents)}</td>
                        <td>
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            onClick={() => void onQuickReceive(m)}
                          >
                            +1 {m.unit}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="usr-card" aria-labelledby="mrp-recipe-create">
            <h2 id="mrp-recipe-create" style={{ margin: "0 0 10px" }}>
              Create Bill of Materials (BOM) Recipe
            </h2>
            <form onSubmit={(e) => void onCreateRecipe(e)} className="usr-grid">
              <label htmlFor={recCodeId}>
                BOM Code
                <input
                  id={recCodeId}
                  required
                  value={recCode}
                  onChange={(e) => setRecCode(e.target.value)}
                  placeholder="BOM-BEAM-1T"
                />
              </label>
              <label htmlFor={recNameId}>
                Recipe Name
                <input
                  id={recNameId}
                  required
                  value={recName}
                  onChange={(e) => setRecName(e.target.value)}
                  placeholder="Structural I-Beam (1 Ton Batch)"
                />
              </label>
              <label htmlFor={recOutId}>
                Finished / Output Material
                <select
                  id={recOutId}
                  required
                  value={recOutputId}
                  onChange={(e) => setRecOutputId(e.target.value)}
                >
                  <option value="">Select output SKU…</option>
                  {materials.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.sku} — {m.name} ({m.unit})
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={recOutQtyId}>
                Batch Output Qty
                <input
                  id={recOutQtyId}
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={recOutQty}
                  onChange={(e) => setRecOutQty(e.target.value)}
                />
              </label>
              <label htmlFor={recCompAInputId}>
                Component #1 (Raw / Sub-Assembly)
                <select
                  id={recCompAInputId}
                  required
                  value={recCompAId}
                  onChange={(e) => setRecCompAId(e.target.value)}
                >
                  <option value="">Select component…</option>
                  {materials.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.sku} — {m.name} ({m.unit})
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={recCompAQtyId}>
                Component #1 Qty / Batch
                <input
                  id={recCompAQtyId}
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={recCompAQty}
                  onChange={(e) => setRecCompAQty(e.target.value)}
                />
              </label>
              <label htmlFor={recCompAScrapId}>
                Component #1 Scrap %
                <input
                  id={recCompAScrapId}
                  type="number"
                  step="0.5"
                  min="0"
                  max="50"
                  value={recCompAScrap}
                  onChange={(e) => setRecCompAScrap(e.target.value)}
                />
              </label>
              <label htmlFor={recCompBInputId}>
                Component #2 (optional)
                <select
                  id={recCompBInputId}
                  value={recCompBId}
                  onChange={(e) => setRecCompBId(e.target.value)}
                >
                  <option value="">None</option>
                  {materials.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.sku} — {m.name} ({m.unit})
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={recCompBQtyId}>
                Component #2 Qty / Batch
                <input
                  id={recCompBQtyId}
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={recCompBQty}
                  onChange={(e) => setRecCompBQty(e.target.value)}
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingRec}
                >
                  {savingRec ? "Saving…" : "+ Save BOM Recipe"}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {/* TAB 2: Production Runs & Reservations */}
      {!loading && activeTab === "mrp_runs" && (
        <div className="usr-stack">
          <section className="usr-card" aria-labelledby="mrp-runs-heading">
            <h2 id="mrp-runs-heading" style={{ margin: "0 0 10px" }}>
              Production Runs, Warehouse Reservations &amp; Auto-Draft POs (
              {runs.length})
            </h2>
            {runs.length === 0 ? (
              <p className="usr-muted">
                No production runs yet. Open the MRP II &amp; BOM Recipes tab to
                explode a BOM and reserve raw materials.
              </p>
            ) : (
              <div className="usr-stack">
                {runs.map((run) => (
                  <article
                    key={run.id}
                    className="usr-card"
                    style={{ background: "#fafafa" }}
                  >
                    <div
                      className="usr-inline"
                      style={{
                        justifyContent: "space-between",
                        flexWrap: "wrap",
                        gap: 8,
                      }}
                    >
                      <div>
                        <strong>{run.run_number}</strong> · {run.recipe_code} (
                        {run.recipe_name}) →{" "}
                        <strong>
                          {fmtQty(run.target_qty_milli, run.output_unit)}
                        </strong>
                        <div
                          className="usr-muted"
                          style={{ fontSize: "0.85rem" }}
                        >
                          Status: <strong>{run.status}</strong> · Est. Material
                          Cost: {fmtUsd(run.estimated_material_cost_cents)} ·
                          Shortages: {run.shortage_count}
                        </div>
                      </div>
                      <div
                        className="usr-inline"
                        style={{ gap: 6, flexWrap: "wrap" }}
                      >
                        {run.shortage_count > 0 && !run.draft_po_id && (
                          <button
                            type="button"
                            className="usr-small-btn"
                            onClick={() => void onDraftPo(run.id)}
                          >
                            1-Click Draft PO for Shortages
                          </button>
                        )}
                        {run.draft_po_id && (
                          <Link
                            href="/commercial/"
                            className="button secondary usr-small-btn"
                          >
                            View Draft PO in Commercial ↗
                          </Link>
                        )}
                        {run.status === "reserved" && (
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            onClick={() =>
                              void onTransitionRun(run.id, "start")
                            }
                          >
                            Start Production
                          </button>
                        )}
                        {(run.status === "reserved" ||
                          run.status === "in_progress" ||
                          run.status === "planned") && (
                          <>
                            <button
                              type="button"
                              className="usr-small-btn"
                              onClick={() =>
                                void onTransitionRun(run.id, "complete")
                              }
                            >
                              Complete &amp; Output Stock
                            </button>
                            <button
                              type="button"
                              className="secondary usr-small-btn"
                              onClick={() =>
                                void onTransitionRun(run.id, "cancel")
                              }
                            >
                              Cancel &amp; Release
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    {run.reservations.length > 0 && (
                      <div
                        style={{ overflowX: "auto", marginTop: 10 }}
                        tabIndex={0}
                        role="region"
                        aria-label="Material reservations table"
                      >
                        <table className="mgmt-table">
                          <thead>
                            <tr>
                              <th>SKU</th>
                              <th>Material</th>
                              <th>Required</th>
                              <th>Reserved</th>
                              <th>Shortage</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {run.reservations.map((res) => (
                              <tr key={res.id}>
                                <td>
                                  <code>{res.material_sku}</code>
                                </td>
                                <td>{res.material_name}</td>
                                <td>
                                  {fmtQty(
                                    res.required_milli,
                                    res.material_unit,
                                  )}
                                </td>
                                <td>
                                  {fmtQty(
                                    res.reserved_milli,
                                    res.material_unit,
                                  )}
                                </td>
                                <td
                                  style={{
                                    color:
                                      res.shortage_milli > 0
                                        ? "#b91c1c"
                                        : "#15803d",
                                    fontWeight:
                                      res.shortage_milli > 0 ? 700 : 400,
                                  }}
                                >
                                  {fmtQty(
                                    res.shortage_milli,
                                    res.material_unit,
                                  )}
                                </td>
                                <td>{res.status}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 3: Predictive EAM & IoT Sensors */}
      {!loading && activeTab === "eam_iot" && (
        <div className="usr-stack">
          {latestToken && (
            <section
              className="usr-card"
              role="status"
              style={{ borderColor: "#111111", background: "#f8fafc" }}
            >
              <strong>
                One-Time IoT Device Webhook Token for {latestToken.tag}
              </strong>
              <p className="usr-muted" style={{ margin: "4px 0 8px" }}>
                Send live sensor readings from any industrial PLC, telematics
                hub, or IoT gateway to{" "}
                <code>POST /v1/public/iot/telemetry</code> with header{" "}
                <code>X-AMARKAL-IoT-Token</code>:
              </p>
              <code
                style={{
                  display: "block",
                  padding: "8px 10px",
                  background: "#ffffff",
                  border: "1px solid #cbd5e1",
                  borderRadius: 6,
                  wordBreak: "break-all",
                }}
              >
                {latestToken.token}
              </code>
              <div className="usr-inline" style={{ marginTop: 10, gap: 8 }}>
                <button
                  type="button"
                  className="secondary usr-small-btn"
                  onClick={() => void onCopyIotSnippet("token")}
                >
                  {copiedIotKind === "token" ? "Token Copied ✓" : "Copy Token"}
                </button>
                <button
                  type="button"
                  className="usr-small-btn"
                  onClick={() => void onCopyIotSnippet("curl")}
                >
                  {copiedIotKind === "curl"
                    ? "cURL Copied ✓"
                    : "Copy cURL Snippet"}
                </button>
              </div>
            </section>
          )}

          <section className="usr-card" aria-labelledby="eam-assets-heading">
            <h2 id="eam-assets-heading" style={{ margin: "0 0 10px" }}>
              Industrial Assets &amp; IoT Fleet Registry ({assets.length})
            </h2>
            <form
              onSubmit={(e) => void onCreateAsset(e)}
              className="usr-grid"
              style={{ marginBottom: 14 }}
            >
              <label htmlFor={assetTagId}>
                Asset Tag
                <input
                  id={assetTagId}
                  required
                  value={assetTag}
                  onChange={(e) => setAssetTag(e.target.value)}
                  placeholder="TRK-104"
                />
              </label>
              <label htmlFor={assetNameId}>
                Asset Name
                <input
                  id={assetNameId}
                  required
                  value={assetName}
                  onChange={(e) => setAssetName(e.target.value)}
                  placeholder="Freightliner Cascadia #104"
                />
              </label>
              <label htmlFor={assetCatId}>
                Category
                <select
                  id={assetCatId}
                  value={assetCategory}
                  onChange={(e) =>
                    setAssetCategory(e.target.value as AssetCategory)
                  }
                >
                  {Object.entries(CATEGORY_LABELS).map(([k, lbl]) => (
                    <option key={k} value={k}>
                      {lbl}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={assetSerialId}>
                Serial / VIN
                <input
                  id={assetSerialId}
                  value={assetSerial}
                  onChange={(e) => setAssetSerial(e.target.value)}
                  placeholder="1FUJGLDR5HL..."
                />
              </label>
              <label htmlFor={assetLocId}>
                Yard / Plant Location
                <input
                  id={assetLocId}
                  value={assetLocation}
                  onChange={(e) => setAssetLocation(e.target.value)}
                  placeholder="Chicago Hub Bay 3"
                />
              </label>
              <label htmlFor={assetHoursId}>
                Current Engine Hours
                <input
                  id={assetHoursId}
                  type="number"
                  step="1"
                  min="0"
                  value={assetHours}
                  onChange={(e) => setAssetHours(e.target.value)}
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingAsset}
                >
                  {savingAsset ? "Registering…" : "+ Register Asset & IoT Key"}
                </button>
              </div>
            </form>

            {assets.length > 0 && (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Scrollable industrial data table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      <th>Tag</th>
                      <th>Asset</th>
                      <th>Status</th>
                      <th>Health</th>
                      <th>Engine Hours</th>
                      <th>IoT Token</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assets.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <code>{a.asset_tag}</code>
                        </td>
                        <td>
                          <strong>{a.name}</strong>
                          <div
                            className="usr-muted"
                            style={{ fontSize: "0.8rem" }}
                          >
                            {CATEGORY_LABELS[a.category]}
                            {a.location_label ? ` · ${a.location_label}` : ""}
                          </div>
                        </td>
                        <td>
                          <strong
                            style={{
                              color:
                                a.status === "maintenance_due"
                                  ? "#b91c1c"
                                  : a.status === "warning"
                                    ? "#b45309"
                                    : "#15803d",
                            }}
                          >
                            {a.status}
                          </strong>
                        </td>
                        <td>{a.health_score}/100</td>
                        <td>{fmtQty(a.engine_hours_milli, "hrs")}</td>
                        <td>
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            onClick={() => void onRotateToken(a)}
                          >
                            Rotate Key ({a.iot_token_prefix ?? "none"}…)
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="usr-card" aria-labelledby="eam-rules-heading">
            <h2 id="eam-rules-heading" style={{ margin: "0 0 10px" }}>
              Predictive Maintenance Rules ({rules.length})
            </h2>
            <form
              onSubmit={(e) => void onCreateRule(e)}
              className="usr-grid"
              style={{ marginBottom: 14 }}
            >
              <label htmlFor={ruleAssetInputId}>
                Asset
                <select
                  id={ruleAssetInputId}
                  required
                  value={ruleAssetId}
                  onChange={(e) => setRuleAssetId(e.target.value)}
                >
                  <option value="">Select asset…</option>
                  {assets.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.asset_tag} — {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={ruleNameId}>
                Rule Name
                <input
                  id={ruleNameId}
                  required
                  value={ruleName}
                  onChange={(e) => setRuleName(e.target.value)}
                  placeholder="500h Diesel PM Service"
                />
              </label>
              <label htmlFor={ruleMetricId}>
                Sensor Metric
                <select
                  id={ruleMetricId}
                  value={ruleMetric}
                  onChange={(e) => setRuleMetric(e.target.value as MetricKey)}
                >
                  {Object.entries(METRIC_LABELS).map(([k, lbl]) => (
                    <option key={k} value={k}>
                      {lbl}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={ruleOpId}>
                Trigger Mode
                <select
                  id={ruleOpId}
                  value={ruleOp}
                  onChange={(e) => setRuleOp(e.target.value as RuleOperator)}
                >
                  <option value="interval_every">
                    Every N Units (Interval)
                  </option>
                  <option value="gte">At or Above Threshold (&gt;=)</option>
                  <option value="lte">At or Below Threshold (&lt;=)</option>
                </select>
              </label>
              <label htmlFor={ruleThrId}>
                Threshold Value
                <input
                  id={ruleThrId}
                  type="number"
                  step="0.1"
                  min="0.1"
                  value={ruleThreshold}
                  onChange={(e) => setRuleThreshold(e.target.value)}
                />
              </label>
              <label htmlFor={ruleLeadId}>
                Predictive Lead % (50–100)
                <input
                  id={ruleLeadId}
                  type="number"
                  min="50"
                  max="100"
                  value={ruleLeadPct}
                  onChange={(e) => setRuleLeadPct(e.target.value)}
                />
              </label>
              <label htmlFor={rulePriId}>
                Work Order Priority
                <select
                  id={rulePriId}
                  value={rulePriority}
                  onChange={(e) =>
                    setRulePriority(e.target.value as WoPriority)
                  }
                >
                  <option value="normal">Normal</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                  <option value="low">Low</option>
                </select>
              </label>
              <label htmlFor={ruleTitleId}>
                Auto Work Order Title
                <input
                  id={ruleTitleId}
                  required
                  value={ruleWoTitle}
                  onChange={(e) => setRuleWoTitle(e.target.value)}
                  placeholder="Predictive 500h Oil, Filter & Bearing Inspection"
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={savingRule || !ruleAssetId}
                >
                  {savingRule ? "Saving…" : "+ Add Predictive Rule"}
                </button>
              </div>
            </form>

            {rules.length > 0 && (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Scrollable industrial data table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      <th>Rule</th>
                      <th>Metric</th>
                      <th>Trigger</th>
                      <th>Priority</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((r) => (
                      <tr key={r.id}>
                        <td>
                          <strong>{r.rule_name}</strong>
                          <div
                            className="usr-muted"
                            style={{ fontSize: "0.8rem" }}
                          >
                            WO: {r.wo_title_template}
                          </div>
                        </td>
                        <td>{METRIC_LABELS[r.metric_key]}</td>
                        <td>
                          {r.operator} {fmtQty(r.threshold_milli)} (lead{" "}
                          {r.warning_lead_pct}%)
                        </td>
                        <td>{r.priority}</td>
                        <td>
                          <button
                            type="button"
                            className="secondary usr-small-btn"
                            onClick={() => void onDeleteRule(r.id)}
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="usr-card" aria-labelledby="eam-telemetry-heading">
            <h2 id="eam-telemetry-heading" style={{ margin: "0 0 10px" }}>
              Ingest Sensor Telemetry &amp; Trigger Predictive Check
            </h2>
            <form
              onSubmit={(e) => void onIngestTelemetry(e)}
              className="usr-grid"
              style={{ marginBottom: 14 }}
            >
              <label htmlFor={telAssetInputId}>
                Asset
                <select
                  id={telAssetInputId}
                  required
                  value={telAssetId}
                  onChange={(e) => setTelAssetId(e.target.value)}
                >
                  <option value="">Select asset…</option>
                  {assets.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.asset_tag} — {a.name}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={telMetricId}>
                Metric
                <select
                  id={telMetricId}
                  value={telMetric}
                  onChange={(e) => setTelMetric(e.target.value as MetricKey)}
                >
                  {Object.entries(METRIC_LABELS).map(([k, lbl]) => (
                    <option key={k} value={k}>
                      {lbl}
                    </option>
                  ))}
                </select>
              </label>
              <label htmlFor={telValId}>
                Sensor Reading Value
                <input
                  id={telValId}
                  type="number"
                  step="0.1"
                  value={telValue}
                  onChange={(e) => setTelValue(e.target.value)}
                />
              </label>
              <label htmlFor={telNotesId}>
                Gateway / Operator Note
                <input
                  id={telNotesId}
                  value={telNotes}
                  onChange={(e) => setTelNotes(e.target.value)}
                  placeholder="CAN-bus OBD-II ping"
                />
              </label>
              <div style={{ alignSelf: "end" }}>
                <button
                  type="submit"
                  className="usr-small-btn"
                  disabled={sendingTel || !telAssetId}
                >
                  {sendingTel ? "Evaluating…" : "Send Telemetry Reading"}
                </button>
              </div>
            </form>

            {telemetry.length > 0 && (
              <div
                style={{ overflowX: "auto" }}
                tabIndex={0}
                role="region"
                aria-label="Scrollable industrial data table"
              >
                <table className="mgmt-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Reading</th>
                      <th>Source</th>
                      <th>Anomaly</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {telemetry.slice(0, 12).map((t) => (
                      <tr key={t.id}>
                        <td>{METRIC_LABELS[t.metric_key]}</td>
                        <td>
                          <strong>{fmtQty(t.value_milli, t.unit)}</strong>
                        </td>
                        <td>{t.source}</td>
                        <td
                          style={{
                            color: t.anomaly_flagged ? "#b91c1c" : "#15803d",
                            fontWeight: t.anomaly_flagged ? 700 : 400,
                          }}
                        >
                          {t.anomaly_flagged ? "Flagged" : "Normal"}
                        </td>
                        <td>{t.notes || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}

      {/* TAB 4: Predictive Work Orders */}
      {!loading && activeTab === "eam_wos" && (
        <section className="usr-card" aria-labelledby="eam-wos-heading">
          <h2 id="eam-wos-heading" style={{ margin: "0 0 10px" }}>
            Predictive &amp; Preventive Maintenance Work Orders (
            {workOrders.length})
          </h2>
          {workOrders.length === 0 ? (
            <p className="usr-muted">
              No predictive Work Orders triggered yet. Register an asset, add a
              rule, and send telemetry above the lead threshold to see automatic
              pre-failure Work Order generation.
            </p>
          ) : (
            <div className="usr-stack">
              {workOrders.map((wo) => (
                <article
                  key={wo.id}
                  className="usr-card"
                  style={{ background: "#fafafa" }}
                >
                  <div
                    className="usr-inline"
                    style={{
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: 8,
                    }}
                  >
                    <div>
                      <strong>{wo.wo_number}</strong> ·{" "}
                      <code>{wo.asset_tag}</code> ({wo.asset_name})
                      <div style={{ fontWeight: 600, marginTop: 2 }}>
                        {wo.title}
                      </div>
                      <p
                        className="usr-muted"
                        style={{
                          margin: "4px 0 0",
                          fontSize: "0.85rem",
                          whiteSpace: "pre-line",
                        }}
                      >
                        {wo.diagnostic_summary}
                      </p>
                      <div
                        className="usr-muted"
                        style={{ fontSize: "0.8rem", marginTop: 4 }}
                      >
                        Trigger: {wo.trigger_kind} · Priority:{" "}
                        <strong>{wo.priority}</strong> · Status:{" "}
                        <strong>{wo.status}</strong>
                      </div>
                    </div>
                    <div
                      className="usr-inline"
                      style={{ gap: 6, flexWrap: "wrap" }}
                    >
                      {wo.status === "open" && (
                        <button
                          type="button"
                          className="secondary usr-small-btn"
                          onClick={() => void onUpdateWo(wo.id, "in_progress")}
                        >
                          Start Repair
                        </button>
                      )}
                      {(wo.status === "open" ||
                        wo.status === "scheduled" ||
                        wo.status === "in_progress") && (
                        <button
                          type="button"
                          className="usr-small-btn"
                          onClick={() => void onUpdateWo(wo.id, "completed")}
                        >
                          Complete &amp; Restore Health
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
