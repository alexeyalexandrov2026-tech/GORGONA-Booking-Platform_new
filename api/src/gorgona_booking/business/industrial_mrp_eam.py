"""AMARKAL v2.18.0: Enterprise MRP II (BOM Explosion, Stock Reservations & Auto Draft PO)
and Predictive EAM (IoT Telemetry Ingestion, Rule Engine & Automated Work Orders).
"""

from __future__ import annotations

import hashlib
import json
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

MaterialKind = Literal["raw", "subassembly", "finished"]
MaterialUnit = Literal["ton", "kg", "lb", "liter", "gallon", "meter", "unit", "box"]
ProductionRunStatus = Literal["planned", "reserved", "in_progress", "completed", "cancelled"]
ReservationStatus = Literal["active", "consumed", "released"]

AssetCategory = Literal[
    "fleet_vehicle",
    "heavy_machinery",
    "cnc_industrial",
    "hvac_facility",
    "power_generator",
    "iot_sensor_node",
]
EamAssetStatus = Literal["operational", "warning", "maintenance_due", "out_of_service"]
MetricKey = Literal[
    "engine_hours",
    "odometer_miles",
    "temperature_c",
    "vibration_mm_s",
    "oil_pressure_psi",
    "battery_voltage",
    "fuel_mpg",
]
RuleOperator = Literal["gte", "lte", "interval_every"]
WorkOrderPriority = Literal["low", "normal", "high", "critical"]
WorkOrderStatus = Literal["open", "scheduled", "in_progress", "completed", "cancelled"]
WorkOrderTriggerKind = Literal["predictive_iot", "preventive_interval", "manual"]
TelemetrySource = Literal["iot_webhook", "manual", "telematics"]

METRIC_DEFAULT_UNITS: dict[MetricKey, str] = {
    "engine_hours": "hrs",
    "odometer_miles": "mi",
    "temperature_c": "C",
    "vibration_mm_s": "mm/s",
    "oil_pressure_psi": "psi",
    "battery_voltage": "V",
    "fuel_mpg": "mpg",
}

MAX_BOM_DEPTH = 8


def generate_iot_ingest_token() -> tuple[str, str, str]:
    """Return (plaintext_token, prefix, sha256_hex)."""
    raw = f"amk_iot_{secrets.token_urlsafe(24)}"
    prefix = raw[:14]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, prefix, digest


def hash_iot_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MrpMaterialView:
    id: UUID
    sku: str
    name: str
    material_kind: MaterialKind
    unit: MaterialUnit
    on_hand_milli: int
    reserved_milli: int
    available_milli: int
    reorder_point_milli: int
    unit_cost_cents: int
    preferred_vendor_name: str
    preferred_vendor_email: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MrpRecipeLineView:
    id: UUID
    recipe_id: UUID
    component_material_id: UUID
    component_sku: str
    component_name: str
    component_unit: MaterialUnit
    qty_per_batch_milli: int
    scrap_bps: int
    notes: str


@dataclass(frozen=True, slots=True)
class MrpRecipeView:
    id: UUID
    code: str
    name: str
    output_material_id: UUID
    output_sku: str
    output_name: str
    output_unit: MaterialUnit
    output_qty_milli: int
    lead_time_days: int
    notes: str
    is_active: bool
    lines: list[MrpRecipeLineView]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MrpExplosionRequirement:
    material_id: UUID
    sku: str
    name: str
    unit: MaterialUnit
    required_milli: int
    on_hand_milli: int
    already_reserved_milli: int
    available_milli: int
    reservable_milli: int
    shortage_milli: int
    unit_cost_cents: int
    estimated_cost_cents: int
    preferred_vendor_name: str
    preferred_vendor_email: str | None


@dataclass(frozen=True, slots=True)
class MrpExplosionResult:
    recipe_id: UUID
    recipe_code: str
    recipe_name: str
    output_material_id: UUID
    output_sku: str
    output_unit: MaterialUnit
    target_qty_milli: int
    requirements: list[MrpExplosionRequirement]
    total_material_cost_cents: int
    shortage_count: int
    can_fully_reserve: bool


@dataclass(frozen=True, slots=True)
class MrpReservationView:
    id: UUID
    run_id: UUID
    material_id: UUID
    material_sku: str
    material_name: str
    material_unit: MaterialUnit
    required_milli: int
    reserved_milli: int
    shortage_milli: int
    unit_cost_cents: int
    status: ReservationStatus


@dataclass(frozen=True, slots=True)
class MrpProductionRunView:
    id: UUID
    run_number: str
    recipe_id: UUID
    recipe_code: str
    recipe_name: str
    output_sku: str
    output_unit: MaterialUnit
    target_qty_milli: int
    status: ProductionRunStatus
    scheduled_date: date | None
    estimated_material_cost_cents: int
    shortage_count: int
    draft_po_id: UUID | None
    notes: str
    reservations: list[MrpReservationView]
    completed_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EamAssetView:
    id: UUID
    asset_tag: str
    name: str
    category: AssetCategory
    serial_number: str
    location_label: str
    status: EamAssetStatus
    engine_hours_milli: int
    odometer_miles_milli: int
    health_score: int
    iot_token_prefix: str | None
    last_telemetry_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EamRuleView:
    id: UUID
    asset_id: UUID
    rule_name: str
    metric_key: MetricKey
    operator: RuleOperator
    threshold_milli: int
    warning_lead_pct: int
    priority: WorkOrderPriority
    wo_title_template: str
    wo_checklist: str
    auto_create_wo: bool
    last_triggered_milli: int
    is_active: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EamTelemetryView:
    id: UUID
    asset_id: UUID
    metric_key: MetricKey
    value_milli: int
    unit: str
    source: TelemetrySource
    anomaly_flagged: bool
    notes: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class EamWorkOrderView:
    id: UUID
    wo_number: str
    asset_id: UUID
    asset_tag: str
    asset_name: str
    rule_id: UUID | None
    trigger_reading_id: UUID | None
    trigger_kind: WorkOrderTriggerKind
    priority: WorkOrderPriority
    status: WorkOrderStatus
    title: str
    diagnostic_summary: str
    estimated_cost_cents: int
    due_at: datetime | None
    completed_at: datetime | None
    completion_notes: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    outcome: Literal["ok", "warning", "triggered"]
    reason: str
    health_penalty: int


def compute_bom_explosion(
    *,
    root_recipe: MrpRecipeView,
    target_qty_milli: int,
    materials_by_id: dict[UUID, MrpMaterialView],
    recipes_by_output_id: dict[UUID, MrpRecipeView],
) -> MrpExplosionResult:
    """Deterministic multi-level BOM explosion in exact integer thousandths (milli-units).

    Explodes sub-assemblies recursively up to MAX_BOM_DEPTH while preventing circular BOM cycles.
    Applies per-line scrap_bps using ceiling integer division so raw stock is never under-reserved.
    """
    if target_qty_milli <= 0:
        raise ValueError("Target production quantity must be positive.")

    required_by_mat: dict[UUID, int] = {}

    def _walk(recipe: MrpRecipeView, need_milli: int, depth: int, path: frozenset[UUID]) -> None:
        if depth > MAX_BOM_DEPTH:
            raise ValueError(f"BOM depth exceeds maximum limit ({MAX_BOM_DEPTH}).")
        if recipe.output_material_id in path:
            raise ValueError(f"Circular BOM reference detected on SKU {recipe.output_sku}.")
        next_path = path | {recipe.output_material_id}
        batch_out = max(1, recipe.output_qty_milli)

        for line in recipe.lines:
            # Exact ceiling scaling: ceil(need_milli * qty_per_batch_milli / output_qty_milli)
            base_req = (need_milli * line.qty_per_batch_milli + batch_out - 1) // batch_out
            # Apply scrap allowance in basis points: ceil(base_req * (10000 + scrap_bps) / 10000)
            gross_req = (base_req * (10_000 + line.scrap_bps) + 9_999) // 10_000
            comp_mat = materials_by_id.get(line.component_material_id)
            sub_recipe = recipes_by_output_id.get(line.component_material_id)
            if (
                comp_mat is not None
                and comp_mat.material_kind == "subassembly"
                and sub_recipe is not None
                and sub_recipe.is_active
                and sub_recipe.id != recipe.id
            ):
                _walk(sub_recipe, gross_req, depth + 1, next_path)
            else:
                required_by_mat[line.component_material_id] = (
                    required_by_mat.get(line.component_material_id, 0) + gross_req
                )

    _walk(root_recipe, target_qty_milli, 0, frozenset())

    requirements: list[MrpExplosionRequirement] = []
    total_cost_cents = 0
    shortage_count = 0

    for mat_id, req_milli in required_by_mat.items():
        mat = materials_by_id[mat_id]
        available = max(0, mat.on_hand_milli - mat.reserved_milli)
        reservable = min(req_milli, available)
        shortage = max(0, req_milli - available)
        # Cost in exact integer cents: ceil(req_milli * unit_cost_cents / 1000)
        est_cost = (req_milli * mat.unit_cost_cents + 999) // 1000
        total_cost_cents += est_cost
        if shortage > 0:
            shortage_count += 1
        requirements.append(
            MrpExplosionRequirement(
                material_id=mat.id,
                sku=mat.sku,
                name=mat.name,
                unit=mat.unit,
                required_milli=req_milli,
                on_hand_milli=mat.on_hand_milli,
                already_reserved_milli=mat.reserved_milli,
                available_milli=available,
                reservable_milli=reservable,
                shortage_milli=shortage,
                unit_cost_cents=mat.unit_cost_cents,
                estimated_cost_cents=est_cost,
                preferred_vendor_name=mat.preferred_vendor_name,
                preferred_vendor_email=mat.preferred_vendor_email,
            )
        )

    requirements.sort(key=lambda r: (r.shortage_milli == 0, r.sku))
    return MrpExplosionResult(
        recipe_id=root_recipe.id,
        recipe_code=root_recipe.code,
        recipe_name=root_recipe.name,
        output_material_id=root_recipe.output_material_id,
        output_sku=root_recipe.output_sku,
        output_unit=root_recipe.output_unit,
        target_qty_milli=target_qty_milli,
        requirements=requirements,
        total_material_cost_cents=total_cost_cents,
        shortage_count=shortage_count,
        can_fully_reserve=(shortage_count == 0),
    )


def evaluate_predictive_rule(
    *,
    operator: RuleOperator,
    threshold_milli: int,
    warning_lead_pct: int,
    value_milli: int,
    last_triggered_milli: int,
    metric_key: MetricKey,
) -> RuleEvaluation:
    """Evaluate an IoT sensor reading against a predictive maintenance rule.

    - `gte`: triggers when value >= threshold; warns when value >= threshold * warning_lead_pct%.
    - `lte`: triggers when value <= threshold (e.g. low oil pressure or battery voltage);
      warns within the lead band above threshold.
    - `interval_every`: tracks delta since `last_triggered_milli` (e.g. every 500 engine hours
      or 10,000 miles); warns at `warning_lead_pct%` (e.g. 450h) and triggers predictive WO at
      >= warning_lead_pct% so repairs are scheduled BEFORE mechanical failure!
    """
    unit = METRIC_DEFAULT_UNITS.get(metric_key, "")
    val_disp = f"{value_milli / 1000:.2f} {unit}".strip()
    thr_disp = f"{threshold_milli / 1000:.2f} {unit}".strip()

    if operator == "gte":
        warn_at = (threshold_milli * warning_lead_pct) // 100
        if value_milli >= threshold_milli:
            return RuleEvaluation(
                outcome="triggered",
                reason=f"{metric_key} reached {val_disp} (threshold >= {thr_disp}).",
                health_penalty=30,
            )
        if value_milli >= warn_at:
            return RuleEvaluation(
                outcome="warning",
                reason=(
                    f"{metric_key} at {val_disp} ({warning_lead_pct}% predictive warning "
                    f"before {thr_disp})."
                ),
                health_penalty=12,
            )
        return RuleEvaluation(outcome="ok", reason="Within nominal range.", health_penalty=0)

    if operator == "lte":
        # e.g., threshold 25 psi, lead 90% => warn at <= 25 / 0.9 = 27.78 psi
        warn_at = math.ceil((threshold_milli * 100) / max(50, warning_lead_pct))
        if value_milli <= threshold_milli:
            return RuleEvaluation(
                outcome="triggered",
                reason=f"{metric_key} dropped to {val_disp} (threshold <= {thr_disp}).",
                health_penalty=30,
            )
        if value_milli <= warn_at:
            return RuleEvaluation(
                outcome="warning",
                reason=f"{metric_key} approaching low limit ({val_disp} vs {thr_disp}).",
                health_penalty=12,
            )
        return RuleEvaluation(outcome="ok", reason="Within nominal range.", health_penalty=0)

    # operator == "interval_every"
    delta = max(0, value_milli - last_triggered_milli)
    lead_trigger = (threshold_milli * warning_lead_pct) // 100
    if delta >= threshold_milli:
        return RuleEvaluation(
            outcome="triggered",
            reason=(
                f"{metric_key} accrued {delta / 1000:.1f} {unit} since last service "
                f"(interval {thr_disp} reached at {val_disp})."
            ),
            health_penalty=25,
        )
    if delta >= lead_trigger:
        remaining = max(0, threshold_milli - delta)
        accrued_str = f"{delta / 1000:.1f}/{threshold_milli / 1000:.1f}"
        return RuleEvaluation(
            outcome="triggered",
            reason=(
                f"Predictive service window reached: {accrued_str} {unit} "
                f"({remaining / 1000:.1f} {unit} remaining before overhaul)."
            ),
            health_penalty=15,
        )
    return RuleEvaluation(outcome="ok", reason="Service interval nominal.", health_penalty=0)


# ── Row mappers ──────────────────────────────────────────────────────────────


def _require_row(row: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if row is None:
        raise RuntimeError(f"Expected RETURNING row for {label}.")
    return row


def _row_to_material(r: dict[str, object]) -> MrpMaterialView:
    on_hand = int(r["on_hand_milli"])  # type: ignore[call-overload]
    reserved = int(r["reserved_milli"])  # type: ignore[call-overload]
    return MrpMaterialView(
        id=r["id"],  # type: ignore[arg-type]
        sku=str(r["sku"]),
        name=str(r["name"]),
        material_kind=r["material_kind"],  # type: ignore[arg-type]
        unit=r["unit"],  # type: ignore[arg-type]
        on_hand_milli=on_hand,
        reserved_milli=reserved,
        available_milli=max(0, on_hand - reserved),
        reorder_point_milli=int(r["reorder_point_milli"]),  # type: ignore[call-overload]
        unit_cost_cents=int(r["unit_cost_cents"]),  # type: ignore[call-overload]
        preferred_vendor_name=str(r["preferred_vendor_name"] or ""),
        preferred_vendor_email=(
            str(r["preferred_vendor_email"]) if r["preferred_vendor_email"] else None
        ),
        created_at=r["created_at"],  # type: ignore[arg-type]
        updated_at=r["updated_at"],  # type: ignore[arg-type]
    )


def _row_to_asset(r: dict[str, object]) -> EamAssetView:
    return EamAssetView(
        id=r["id"],  # type: ignore[arg-type]
        asset_tag=str(r["asset_tag"]),
        name=str(r["name"]),
        category=r["category"],  # type: ignore[arg-type]
        serial_number=str(r["serial_number"] or ""),
        location_label=str(r["location_label"] or ""),
        status=r["status"],  # type: ignore[arg-type]
        engine_hours_milli=int(r["engine_hours_milli"]),  # type: ignore[call-overload]
        odometer_miles_milli=int(r["odometer_miles_milli"]),  # type: ignore[call-overload]
        health_score=int(r["health_score"]),  # type: ignore[call-overload]
        iot_token_prefix=str(r["iot_token_prefix"]) if r["iot_token_prefix"] else None,
        last_telemetry_at=r["last_telemetry_at"],  # type: ignore[arg-type]
        created_at=r["created_at"],  # type: ignore[arg-type]
        updated_at=r["updated_at"],  # type: ignore[arg-type]
    )


def _row_to_rule(r: dict[str, object]) -> EamRuleView:
    return EamRuleView(
        id=r["id"],  # type: ignore[arg-type]
        asset_id=r["asset_id"],  # type: ignore[arg-type]
        rule_name=str(r["rule_name"]),
        metric_key=r["metric_key"],  # type: ignore[arg-type]
        operator=r["operator"],  # type: ignore[arg-type]
        threshold_milli=int(r["threshold_milli"]),  # type: ignore[call-overload]
        warning_lead_pct=int(r["warning_lead_pct"]),  # type: ignore[call-overload]
        priority=r["priority"],  # type: ignore[arg-type]
        wo_title_template=str(r["wo_title_template"]),
        wo_checklist=str(r["wo_checklist"] or ""),
        auto_create_wo=bool(r["auto_create_wo"]),
        last_triggered_milli=int(r["last_triggered_milli"]),  # type: ignore[call-overload]
        is_active=bool(r["is_active"]),
        created_at=r["created_at"],  # type: ignore[arg-type]
    )


def _row_to_telemetry(r: dict[str, object]) -> EamTelemetryView:
    return EamTelemetryView(
        id=r["id"],  # type: ignore[arg-type]
        asset_id=r["asset_id"],  # type: ignore[arg-type]
        metric_key=r["metric_key"],  # type: ignore[arg-type]
        value_milli=int(r["value_milli"]),  # type: ignore[call-overload]
        unit=str(r["unit"] or ""),
        source=r["source"],  # type: ignore[arg-type]
        anomaly_flagged=bool(r["anomaly_flagged"]),
        notes=str(r["notes"] or ""),
        recorded_at=r["recorded_at"],  # type: ignore[arg-type]
    )


def _row_to_wo(r: dict[str, object]) -> EamWorkOrderView:
    return EamWorkOrderView(
        id=r["id"],  # type: ignore[arg-type]
        wo_number=str(r["wo_number"]),
        asset_id=r["asset_id"],  # type: ignore[arg-type]
        asset_tag=str(r["asset_tag"]),
        asset_name=str(r["asset_name"]),
        rule_id=r["rule_id"],  # type: ignore[arg-type]
        trigger_reading_id=r["trigger_reading_id"],  # type: ignore[arg-type]
        trigger_kind=r["trigger_kind"],  # type: ignore[arg-type]
        priority=r["priority"],  # type: ignore[arg-type]
        status=r["status"],  # type: ignore[arg-type]
        title=str(r["title"]),
        diagnostic_summary=str(r["diagnostic_summary"] or ""),
        estimated_cost_cents=int(r["estimated_cost_cents"]),  # type: ignore[call-overload]
        due_at=r["due_at"],  # type: ignore[arg-type]
        completed_at=r["completed_at"],  # type: ignore[arg-type]
        completion_notes=str(r["completion_notes"] or ""),
        created_at=r["created_at"],  # type: ignore[arg-type]
        updated_at=r["updated_at"],  # type: ignore[arg-type]
    )


# ── MRP II Persistence ───────────────────────────────────────────────────────


async def list_mrp_materials(conn: AsyncConnection, *, tenant_id: UUID) -> list[MrpMaterialView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, sku, name, material_kind, unit, on_hand_milli, reserved_milli,
                   reorder_point_milli, unit_cost_cents, preferred_vendor_name,
                   preferred_vendor_email, created_at, updated_at
            FROM gba.mrp_materials
            WHERE tenant_id = %s
            ORDER BY material_kind ASC, sku ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_material(dict(r)) for r in rows]


async def create_mrp_material(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    sku: str,
    name: str,
    material_kind: MaterialKind,
    unit: MaterialUnit,
    on_hand_milli: int,
    reorder_point_milli: int,
    unit_cost_cents: int,
    preferred_vendor_name: str,
    preferred_vendor_email: str | None,
) -> MrpMaterialView:
    clean_sku = sku.strip().upper()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.mrp_materials (
                tenant_id, sku, name, material_kind, unit, on_hand_milli, reserved_milli,
                reorder_point_milli, unit_cost_cents, preferred_vendor_name,
                preferred_vendor_email
            )
            VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, %s, %s)
            RETURNING id, sku, name, material_kind, unit, on_hand_milli, reserved_milli,
                      reorder_point_milli, unit_cost_cents, preferred_vendor_name,
                      preferred_vendor_email, created_at, updated_at
            """,
            (
                tenant_id,
                clean_sku,
                name.strip(),
                material_kind,
                unit,
                on_hand_milli,
                reorder_point_milli,
                unit_cost_cents,
                preferred_vendor_name.strip(),
                preferred_vendor_email.strip() if preferred_vendor_email else None,
            ),
        )
        row = await cur.fetchone()
    return _row_to_material(dict(_require_row(row, "mrp_materials insert")))


async def adjust_mrp_material_stock(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    material_id: UUID,
    delta_milli: int,
) -> MrpMaterialView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT on_hand_milli, reserved_milli
            FROM gba.mrp_materials
            WHERE tenant_id = %s AND id = %s
            FOR UPDATE
            """,
            (tenant_id, material_id),
        )
        cur_row = await cur.fetchone()
        if cur_row is None:
            raise LookupError("Material not found.")
        new_on_hand = int(cur_row["on_hand_milli"]) + delta_milli
        reserved = int(cur_row["reserved_milli"])
        if new_on_hand < reserved:
            raise ValueError(
                f"Cannot reduce on-hand stock below active reserved quantity "
                f"({reserved / 1000:.3f})."
            )
        await cur.execute(
            """
            UPDATE gba.mrp_materials
            SET on_hand_milli = %s, updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, sku, name, material_kind, unit, on_hand_milli, reserved_milli,
                      reorder_point_milli, unit_cost_cents, preferred_vendor_name,
                      preferred_vendor_email, created_at, updated_at
            """,
            (new_on_hand, tenant_id, material_id),
        )
        row = await cur.fetchone()
    return _row_to_material(dict(_require_row(row, "mrp_materials insert")))


async def list_mrp_recipes(conn: AsyncConnection, *, tenant_id: UUID) -> list[MrpRecipeView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT r.id, r.code, r.name, r.output_material_id, m.sku AS output_sku,
                   m.name AS output_name, m.unit AS output_unit, r.output_qty_milli,
                   r.lead_time_days, r.notes, r.is_active, r.created_at, r.updated_at
            FROM gba.mrp_recipes r
            JOIN gba.mrp_materials m
              ON m.tenant_id = r.tenant_id AND m.id = r.output_material_id
            WHERE r.tenant_id = %s
            ORDER BY r.code ASC
            """,
            (tenant_id,),
        )
        recipe_rows = await cur.fetchall()
        await cur.execute(
            """
            SELECT l.id, l.recipe_id, l.component_material_id, m.sku AS component_sku,
                   m.name AS component_name, m.unit AS component_unit,
                   l.qty_per_batch_milli, l.scrap_bps, l.notes
            FROM gba.mrp_recipe_lines l
            JOIN gba.mrp_materials m
              ON m.tenant_id = l.tenant_id AND m.id = l.component_material_id
            WHERE l.tenant_id = %s
            ORDER BY m.sku ASC
            """,
            (tenant_id,),
        )
        line_rows = await cur.fetchall()

    lines_by_recipe: dict[UUID, list[MrpRecipeLineView]] = {}
    for lr in line_rows:
        rid: UUID = lr["recipe_id"]
        lines_by_recipe.setdefault(rid, []).append(
            MrpRecipeLineView(
                id=lr["id"],
                recipe_id=rid,
                component_material_id=lr["component_material_id"],
                component_sku=str(lr["component_sku"]),
                component_name=str(lr["component_name"]),
                component_unit=lr["component_unit"],
                qty_per_batch_milli=int(lr["qty_per_batch_milli"]),
                scrap_bps=int(lr["scrap_bps"]),
                notes=str(lr["notes"] or ""),
            )
        )

    out: list[MrpRecipeView] = []
    for rr in recipe_rows:
        rid = rr["id"]
        out.append(
            MrpRecipeView(
                id=rid,
                code=str(rr["code"]),
                name=str(rr["name"]),
                output_material_id=rr["output_material_id"],
                output_sku=str(rr["output_sku"]),
                output_name=str(rr["output_name"]),
                output_unit=rr["output_unit"],
                output_qty_milli=int(rr["output_qty_milli"]),
                lead_time_days=int(rr["lead_time_days"]),
                notes=str(rr["notes"] or ""),
                is_active=bool(rr["is_active"]),
                lines=lines_by_recipe.get(rid, []),
                created_at=rr["created_at"],
                updated_at=rr["updated_at"],
            )
        )
    return out


async def create_mrp_recipe(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    code: str,
    name: str,
    output_material_id: UUID,
    output_qty_milli: int,
    lead_time_days: int,
    notes: str,
    lines: list[tuple[UUID, int, int, str]],
) -> MrpRecipeView:
    if not lines:
        raise ValueError("BOM recipe must include at least one component line.")
    comp_ids = [c[0] for c in lines]
    if len(set(comp_ids)) != len(comp_ids):
        raise ValueError("Duplicate component materials in BOM recipe.")
    if output_material_id in comp_ids:
        raise ValueError("Output material cannot be its own direct component.")

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.mrp_recipes (
                tenant_id, code, name, output_material_id, output_qty_milli,
                lead_time_days, notes, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, true)
            RETURNING id
            """,
            (
                tenant_id,
                code.strip().upper(),
                name.strip(),
                output_material_id,
                output_qty_milli,
                lead_time_days,
                notes.strip(),
            ),
        )
        rec_row = await cur.fetchone()
        recipe_id: UUID = _require_row(rec_row, "mrp_recipes insert")["id"]
        for comp_id, qty_milli, scrap_bps, line_notes in lines:
            await cur.execute(
                """
                INSERT INTO gba.mrp_recipe_lines (
                    tenant_id, recipe_id, component_material_id,
                    qty_per_batch_milli, scrap_bps, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, recipe_id, comp_id, qty_milli, scrap_bps, line_notes.strip()),
            )

    recipes = await list_mrp_recipes(conn, tenant_id=tenant_id)
    for r in recipes:
        if r.id == recipe_id:
            return r
    raise LookupError("Created BOM recipe could not be loaded.")


async def delete_mrp_recipe(conn: AsyncConnection, *, tenant_id: UUID, recipe_id: UUID) -> bool:
    async with conn.cursor() as cur:
        res = await cur.execute(
            "DELETE FROM gba.mrp_recipes WHERE tenant_id = %s AND id = %s",
            (tenant_id, recipe_id),
        )
        return res.rowcount > 0


async def preview_mrp_explosion(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    recipe_id: UUID,
    target_qty_milli: int,
) -> MrpExplosionResult:
    materials = await list_mrp_materials(conn, tenant_id=tenant_id)
    recipes = await list_mrp_recipes(conn, tenant_id=tenant_id)
    root = next((r for r in recipes if r.id == recipe_id), None)
    if root is None:
        raise LookupError("BOM recipe not found.")
    return compute_bom_explosion(
        root_recipe=root,
        target_qty_milli=target_qty_milli,
        materials_by_id={m.id: m for m in materials},
        recipes_by_output_id={r.output_material_id: r for r in recipes if r.is_active},
    )


async def list_mrp_production_runs(
    conn: AsyncConnection, *, tenant_id: UUID
) -> list[MrpProductionRunView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT pr.id, pr.run_number, pr.recipe_id, r.code AS recipe_code,
                   r.name AS recipe_name, m.sku AS output_sku, m.unit AS output_unit,
                   pr.target_qty_milli, pr.status, pr.scheduled_date,
                   pr.estimated_material_cost_cents, pr.shortage_count,
                   pr.draft_po_id, pr.notes, pr.completed_at, pr.created_at
            FROM gba.mrp_production_runs pr
            JOIN gba.mrp_recipes r
              ON r.tenant_id = pr.tenant_id AND r.id = pr.recipe_id
            JOIN gba.mrp_materials m
              ON m.tenant_id = r.tenant_id AND m.id = r.output_material_id
            WHERE pr.tenant_id = %s
            ORDER BY pr.created_at DESC
            LIMIT 100
            """,
            (tenant_id,),
        )
        run_rows = await cur.fetchall()
        await cur.execute(
            """
            SELECT res.id, res.run_id, res.material_id, m.sku AS material_sku,
                   m.name AS material_name, m.unit AS material_unit,
                   res.required_milli, res.reserved_milli, res.shortage_milli,
                   res.unit_cost_cents, res.status
            FROM gba.mrp_material_reservations res
            JOIN gba.mrp_materials m
              ON m.tenant_id = res.tenant_id AND m.id = res.material_id
            WHERE res.tenant_id = %s
            ORDER BY m.sku ASC
            """,
            (tenant_id,),
        )
        res_rows = await cur.fetchall()

    res_by_run: dict[UUID, list[MrpReservationView]] = {}
    for rr in res_rows:
        run_id: UUID = rr["run_id"]
        res_by_run.setdefault(run_id, []).append(
            MrpReservationView(
                id=rr["id"],
                run_id=run_id,
                material_id=rr["material_id"],
                material_sku=str(rr["material_sku"]),
                material_name=str(rr["material_name"]),
                material_unit=rr["material_unit"],
                required_milli=int(rr["required_milli"]),
                reserved_milli=int(rr["reserved_milli"]),
                shortage_milli=int(rr["shortage_milli"]),
                unit_cost_cents=int(rr["unit_cost_cents"]),
                status=rr["status"],
            )
        )

    return [
        MrpProductionRunView(
            id=r["id"],
            run_number=str(r["run_number"]),
            recipe_id=r["recipe_id"],
            recipe_code=str(r["recipe_code"]),
            recipe_name=str(r["recipe_name"]),
            output_sku=str(r["output_sku"]),
            output_unit=r["output_unit"],
            target_qty_milli=int(r["target_qty_milli"]),
            status=r["status"],
            scheduled_date=r["scheduled_date"],
            estimated_material_cost_cents=int(r["estimated_material_cost_cents"]),
            shortage_count=int(r["shortage_count"]),
            draft_po_id=r["draft_po_id"],
            notes=str(r["notes"] or ""),
            reservations=res_by_run.get(r["id"], []),
            completed_at=r["completed_at"],
            created_at=r["created_at"],
        )
        for r in run_rows
    ]


async def create_mrp_production_run(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    recipe_id: UUID,
    target_qty_milli: int,
    scheduled_date: date | None,
    notes: str,
    reserve_available: bool,
    created_by_user_id: UUID | None,
) -> MrpProductionRunView:
    explosion = await preview_mrp_explosion(
        conn, tenant_id=tenant_id, recipe_id=recipe_id, target_qty_milli=target_qty_milli
    )
    run_number = f"MRP-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

    # Lock involved materials in deterministic UUID order to prevent deadlocks
    req_mat_ids = sorted({req.material_id for req in explosion.requirements})
    locked_avail: dict[UUID, tuple[int, int]] = {}
    async with conn.cursor(row_factory=dict_row) as cur:
        for mid in req_mat_ids:
            await cur.execute(
                """
                SELECT on_hand_milli, reserved_milli
                FROM gba.mrp_materials
                WHERE tenant_id = %s AND id = %s
                FOR UPDATE
                """,
                (tenant_id, mid),
            )
            mrow = await cur.fetchone()
            if mrow is not None:
                locked_avail[mid] = (int(mrow["on_hand_milli"]), int(mrow["reserved_milli"]))

        actual_shortages = 0
        reservation_plan: list[tuple[UUID, int, int, int, int]] = []
        for req in explosion.requirements:
            on_hand, reserved = locked_avail.get(req.material_id, (0, 0))
            avail = max(0, on_hand - reserved)
            to_reserve = min(req.required_milli, avail) if reserve_available else 0
            shortage = max(0, req.required_milli - avail)
            if shortage > 0:
                actual_shortages += 1
            reservation_plan.append(
                (req.material_id, req.required_milli, to_reserve, shortage, req.unit_cost_cents)
            )
            if to_reserve > 0:
                await cur.execute(
                    """
                    UPDATE gba.mrp_materials
                    SET reserved_milli = reserved_milli + %s, updated_at = now()
                    WHERE tenant_id = %s AND id = %s
                    """,
                    (to_reserve, tenant_id, req.material_id),
                )

        run_status: ProductionRunStatus = (
            "reserved" if (reserve_available and actual_shortages == 0) else "planned"
        )
        await cur.execute(
            """
            INSERT INTO gba.mrp_production_runs (
                tenant_id, run_number, recipe_id, target_qty_milli, status,
                scheduled_date, estimated_material_cost_cents, shortage_count,
                notes, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                run_number,
                recipe_id,
                target_qty_milli,
                run_status,
                scheduled_date,
                explosion.total_material_cost_cents,
                actual_shortages,
                notes.strip(),
                created_by_user_id,
            ),
        )
        run_row = await cur.fetchone()
        run_id: UUID = _require_row(run_row, "mrp_production_runs insert")["id"]

        for mat_id, req_milli, res_milli, short_milli, unit_cost in reservation_plan:
            await cur.execute(
                """
                INSERT INTO gba.mrp_material_reservations (
                    tenant_id, run_id, material_id, required_milli,
                    reserved_milli, shortage_milli, unit_cost_cents, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
                """,
                (tenant_id, run_id, mat_id, req_milli, res_milli, short_milli, unit_cost),
            )

    runs = await list_mrp_production_runs(conn, tenant_id=tenant_id)
    for run in runs:
        if run.id == run_id:
            return run
    raise LookupError("Created production run could not be loaded.")


async def transition_mrp_production_run(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    run_id: UUID,
    action: Literal["start", "complete", "cancel"],
) -> MrpProductionRunView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT pr.id, pr.status, pr.target_qty_milli, r.output_material_id
            FROM gba.mrp_production_runs pr
            JOIN gba.mrp_recipes r
              ON r.tenant_id = pr.tenant_id AND r.id = pr.recipe_id
            WHERE pr.tenant_id = %s AND pr.id = %s
            FOR UPDATE OF pr
            """,
            (tenant_id, run_id),
        )
        run_row = await cur.fetchone()
        if run_row is None:
            raise LookupError("Production run not found.")
        cur_status = str(run_row["status"])
        if cur_status in ("completed", "cancelled"):
            raise ValueError(f"Production run is already {cur_status}.")

        if action == "start":
            await cur.execute(
                """
                UPDATE gba.mrp_production_runs
                SET status = 'in_progress', updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, run_id),
            )
        elif action == "cancel":
            await cur.execute(
                """
                SELECT id, material_id, reserved_milli
                FROM gba.mrp_material_reservations
                WHERE tenant_id = %s AND run_id = %s AND status = 'active'
                ORDER BY material_id ASC
                FOR UPDATE
                """,
                (tenant_id, run_id),
            )
            active_res = await cur.fetchall()
            for r in active_res:
                res_milli = int(r["reserved_milli"])
                if res_milli > 0:
                    await cur.execute(
                        """
                        UPDATE gba.mrp_materials
                        SET reserved_milli = GREATEST(0, reserved_milli - %s), updated_at = now()
                        WHERE tenant_id = %s AND id = %s
                        """,
                        (res_milli, tenant_id, r["material_id"]),
                    )
            await cur.execute(
                """
                UPDATE gba.mrp_material_reservations
                SET status = 'released', reserved_milli = 0, updated_at = now()
                WHERE tenant_id = %s AND run_id = %s AND status = 'active'
                """,
                (tenant_id, run_id),
            )
            await cur.execute(
                """
                UPDATE gba.mrp_production_runs
                SET status = 'cancelled', updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, run_id),
            )
        else:  # complete
            await cur.execute(
                """
                SELECT id, material_id, reserved_milli
                FROM gba.mrp_material_reservations
                WHERE tenant_id = %s AND run_id = %s AND status = 'active'
                ORDER BY material_id ASC
                FOR UPDATE
                """,
                (tenant_id, run_id),
            )
            active_res = await cur.fetchall()
            for r in active_res:
                res_milli = int(r["reserved_milli"])
                if res_milli > 0:
                    await cur.execute(
                        """
                        UPDATE gba.mrp_materials
                        SET on_hand_milli = GREATEST(0, on_hand_milli - %s),
                            reserved_milli = GREATEST(0, reserved_milli - %s),
                            updated_at = now()
                        WHERE tenant_id = %s AND id = %s
                        """,
                        (res_milli, res_milli, tenant_id, r["material_id"]),
                    )
            await cur.execute(
                """
                UPDATE gba.mrp_material_reservations
                SET status = 'consumed', updated_at = now()
                WHERE tenant_id = %s AND run_id = %s AND status = 'active'
                """,
                (tenant_id, run_id),
            )
            # Credit finished goods output to warehouse on_hand_milli
            await cur.execute(
                """
                UPDATE gba.mrp_materials
                SET on_hand_milli = on_hand_milli + %s, updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (int(run_row["target_qty_milli"]), tenant_id, run_row["output_material_id"]),
            )
            await cur.execute(
                """
                UPDATE gba.mrp_production_runs
                SET status = 'completed', completed_at = now(), updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, run_id),
            )

    runs = await list_mrp_production_runs(conn, tenant_id=tenant_id)
    for run in runs:
        if run.id == run_id:
            return run
    raise LookupError("Updated production run could not be loaded.")


async def generate_draft_po_for_run_shortages(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    run_id: UUID,
    created_by_user_id: UUID | None,
) -> tuple[UUID, str, int]:
    """Create a real Draft Purchase Order in gba.purchase_orders for all shortage lines."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT pr.id, pr.run_number, pr.draft_po_id, r.name AS recipe_name
            FROM gba.mrp_production_runs pr
            JOIN gba.mrp_recipes r ON r.tenant_id = pr.tenant_id AND r.id = pr.recipe_id
            WHERE pr.tenant_id = %s AND pr.id = %s
            FOR UPDATE OF pr
            """,
            (tenant_id, run_id),
        )
        run_row = await cur.fetchone()
        if run_row is None:
            raise LookupError("Production run not found.")
        if run_row["draft_po_id"] is not None:
            raise ValueError("A Draft Purchase Order has already been generated for this run.")

        await cur.execute(
            """
            SELECT res.material_id, m.sku, m.name, m.unit, res.shortage_milli,
                   res.unit_cost_cents, m.preferred_vendor_name, m.preferred_vendor_email
            FROM gba.mrp_material_reservations res
            JOIN gba.mrp_materials m
              ON m.tenant_id = res.tenant_id AND m.id = res.material_id
            WHERE res.tenant_id = %s AND res.run_id = %s AND res.shortage_milli > 0
            ORDER BY m.sku ASC
            """,
            (tenant_id, run_id),
        )
        shortages = await cur.fetchall()
        if not shortages:
            raise ValueError("This production run has zero material shortages.")

        vendor_name = str(shortages[0]["preferred_vendor_name"] or "").strip() or (
            "MRP Raw Material Supplier"
        )
        vendor_email = (
            str(shortages[0]["preferred_vendor_email"]).strip()
            if shortages[0]["preferred_vendor_email"]
            else None
        )
        items_payload: list[dict[str, object]] = []
        total_cents = 0
        for s in shortages:
            short_milli = int(s["shortage_milli"])
            unit_cost = int(s["unit_cost_cents"])
            line_total = (short_milli * unit_cost + 999) // 1000
            total_cents += line_total
            items_payload.append(
                {
                    "sku": str(s["sku"]),
                    "description": (
                        f"{s['name']} ({short_milli / 1000:.3f} {s['unit']} shortage "
                        f"for {run_row['run_number']})"
                    ),
                    "quantity": round(short_milli / 1000, 3),
                    "unit_price_cents": unit_cost,
                    "line_total_cents": line_total,
                }
            )

        po_number = f"PO-MRP-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
        await cur.execute(
            """
            INSERT INTO gba.purchase_orders (
                tenant_id, po_number, title, vendor_name, vendor_email, currency,
                items, total_cents, payment_terms, notes, status, approval_required,
                created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, 'USD', %s::jsonb, %s, 'Net 30', %s, 'draft', true, %s)
            RETURNING id
            """,
            (
                tenant_id,
                po_number,
                f"MRP II Replenishment for {run_row['run_number']} ({run_row['recipe_name']})",
                vendor_name,
                vendor_email,
                json.dumps(items_payload),
                total_cents,
                (
                    f"Auto-drafted by AMARKAL MRP II Engine from production run "
                    f"{run_row['run_number']}. Human approval required before issue."
                ),
                created_by_user_id,
            ),
        )
        po_row = await cur.fetchone()
        po_id: UUID = _require_row(po_row, "purchase_orders insert")["id"]
        await cur.execute(
            """
            UPDATE gba.mrp_production_runs
            SET draft_po_id = %s, updated_at = now()
            WHERE tenant_id = %s AND id = %s
            """,
            (po_id, tenant_id, run_id),
        )
    return po_id, po_number, total_cents


# ── Predictive EAM & IoT Persistence ─────────────────────────────────────────


async def list_eam_assets(conn: AsyncConnection, *, tenant_id: UUID) -> list[EamAssetView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, asset_tag, name, category, serial_number, location_label, status,
                   engine_hours_milli, odometer_miles_milli, health_score,
                   iot_token_prefix, last_telemetry_at, created_at, updated_at
            FROM gba.eam_assets
            WHERE tenant_id = %s
            ORDER BY health_score ASC, asset_tag ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_asset(dict(r)) for r in rows]


async def create_eam_asset(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    asset_tag: str,
    name: str,
    category: AssetCategory,
    serial_number: str,
    location_label: str,
    engine_hours_milli: int,
    odometer_miles_milli: int,
) -> tuple[EamAssetView, str]:
    plaintext, prefix, digest = generate_iot_ingest_token()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.eam_assets (
                tenant_id, asset_tag, name, category, serial_number, location_label,
                status, engine_hours_milli, odometer_miles_milli, health_score,
                iot_token_prefix, iot_token_hash
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'operational', %s, %s, 100, %s, %s)
            RETURNING id, asset_tag, name, category, serial_number, location_label, status,
                      engine_hours_milli, odometer_miles_milli, health_score,
                      iot_token_prefix, last_telemetry_at, created_at, updated_at
            """,
            (
                tenant_id,
                asset_tag.strip().upper(),
                name.strip(),
                category,
                serial_number.strip(),
                location_label.strip(),
                engine_hours_milli,
                odometer_miles_milli,
                prefix,
                digest,
            ),
        )
        row = await cur.fetchone()
    return _row_to_asset(dict(_require_row(row, "eam_assets insert"))), plaintext


async def rotate_eam_asset_iot_token(
    conn: AsyncConnection, *, tenant_id: UUID, asset_id: UUID
) -> tuple[EamAssetView, str]:
    plaintext, prefix, digest = generate_iot_ingest_token()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.eam_assets
            SET iot_token_prefix = %s, iot_token_hash = %s, updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, asset_tag, name, category, serial_number, location_label, status,
                      engine_hours_milli, odometer_miles_milli, health_score,
                      iot_token_prefix, last_telemetry_at, created_at, updated_at
            """,
            (prefix, digest, tenant_id, asset_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise LookupError("EAM asset not found.")
    return _row_to_asset(dict(row)), plaintext


async def list_eam_rules(
    conn: AsyncConnection, *, tenant_id: UUID, asset_id: UUID | None = None
) -> list[EamRuleView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        if asset_id is not None:
            await cur.execute(
                """
                SELECT id, asset_id, rule_name, metric_key, operator, threshold_milli,
                       warning_lead_pct, priority, wo_title_template, wo_checklist,
                       auto_create_wo, last_triggered_milli, is_active, created_at
                FROM gba.eam_maintenance_rules
                WHERE tenant_id = %s AND asset_id = %s
                ORDER BY created_at DESC
                """,
                (tenant_id, asset_id),
            )
        else:
            await cur.execute(
                """
                SELECT id, asset_id, rule_name, metric_key, operator, threshold_milli,
                       warning_lead_pct, priority, wo_title_template, wo_checklist,
                       auto_create_wo, last_triggered_milli, is_active, created_at
                FROM gba.eam_maintenance_rules
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                """,
                (tenant_id,),
            )
        rows = await cur.fetchall()
    return [_row_to_rule(dict(r)) for r in rows]


async def create_eam_rule(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    asset_id: UUID,
    rule_name: str,
    metric_key: MetricKey,
    operator: RuleOperator,
    threshold_milli: int,
    warning_lead_pct: int,
    priority: WorkOrderPriority,
    wo_title_template: str,
    wo_checklist: str,
    auto_create_wo: bool,
) -> EamRuleView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.eam_maintenance_rules (
                tenant_id, asset_id, rule_name, metric_key, operator, threshold_milli,
                warning_lead_pct, priority, wo_title_template, wo_checklist,
                auto_create_wo, last_triggered_milli, is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, true)
            RETURNING id, asset_id, rule_name, metric_key, operator, threshold_milli,
                      warning_lead_pct, priority, wo_title_template, wo_checklist,
                      auto_create_wo, last_triggered_milli, is_active, created_at
            """,
            (
                tenant_id,
                asset_id,
                rule_name.strip(),
                metric_key,
                operator,
                threshold_milli,
                warning_lead_pct,
                priority,
                wo_title_template.strip(),
                wo_checklist.strip(),
                auto_create_wo,
            ),
        )
        row = await cur.fetchone()
    return _row_to_rule(dict(_require_row(row, "eam_maintenance_rules insert")))


async def delete_eam_rule(conn: AsyncConnection, *, tenant_id: UUID, rule_id: UUID) -> bool:
    async with conn.cursor() as cur:
        res = await cur.execute(
            "DELETE FROM gba.eam_maintenance_rules WHERE tenant_id = %s AND id = %s",
            (tenant_id, rule_id),
        )
        return res.rowcount > 0


async def list_eam_telemetry(
    conn: AsyncConnection, *, tenant_id: UUID, asset_id: UUID | None = None, limit: int = 50
) -> list[EamTelemetryView]:
    clamped = max(1, min(200, limit))
    async with conn.cursor(row_factory=dict_row) as cur:
        if asset_id is not None:
            await cur.execute(
                """
                SELECT id, asset_id, metric_key, value_milli, unit, source,
                       anomaly_flagged, notes, recorded_at
                FROM gba.eam_telemetry_readings
                WHERE tenant_id = %s AND asset_id = %s
                ORDER BY recorded_at DESC
                LIMIT %s
                """,
                (tenant_id, asset_id, clamped),
            )
        else:
            await cur.execute(
                """
                SELECT id, asset_id, metric_key, value_milli, unit, source,
                       anomaly_flagged, notes, recorded_at
                FROM gba.eam_telemetry_readings
                WHERE tenant_id = %s
                ORDER BY recorded_at DESC
                LIMIT %s
                """,
                (tenant_id, clamped),
            )
        rows = await cur.fetchall()
    return [_row_to_telemetry(dict(r)) for r in rows]


async def list_eam_work_orders(conn: AsyncConnection, *, tenant_id: UUID) -> list[EamWorkOrderView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT wo.id, wo.wo_number, wo.asset_id, a.asset_tag, a.name AS asset_name,
                   wo.rule_id, wo.trigger_reading_id, wo.trigger_kind, wo.priority,
                   wo.status, wo.title, wo.diagnostic_summary, wo.estimated_cost_cents,
                   wo.due_at, wo.completed_at, wo.completion_notes, wo.created_at,
                   wo.updated_at
            FROM gba.eam_predictive_work_orders wo
            JOIN gba.eam_assets a
              ON a.tenant_id = wo.tenant_id AND a.id = wo.asset_id
            WHERE wo.tenant_id = %s
            ORDER BY
                CASE wo.status
                    WHEN 'open' THEN 0
                    WHEN 'in_progress' THEN 1
                    WHEN 'scheduled' THEN 2
                    ELSE 3
                END,
                wo.created_at DESC
            LIMIT 100
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_wo(dict(r)) for r in rows]


async def resolve_eam_asset_by_iot_token(
    conn: AsyncConnection, *, plaintext_token: str
) -> tuple[UUID, UUID] | None:
    """Resolve (tenant_id, asset_id) via invoker-only RLS setting gba.iot_token_hash."""
    digest = hash_iot_token(plaintext_token)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT set_config('gba.iot_token_hash', %s, true)",
            (digest,),
        )
        await cur.execute(
            """
            SELECT tenant_id, id
            FROM gba.eam_assets
            WHERE iot_token_hash = %s
            LIMIT 1
            """,
            (digest,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return row["tenant_id"], row["id"]


async def ingest_eam_telemetry(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    asset_id: UUID,
    metric_key: MetricKey,
    value_milli: int,
    source: TelemetrySource,
    notes: str,
    created_by_user_id: UUID | None = None,
) -> tuple[EamTelemetryView, EamAssetView, list[EamWorkOrderView]]:
    """Record IoT telemetry, evaluate predictive rules, and auto-open Work Orders before failure."""
    unit = METRIC_DEFAULT_UNITS.get(metric_key, "")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, asset_tag, name, status, engine_hours_milli,
                   odometer_miles_milli, health_score
            FROM gba.eam_assets
            WHERE tenant_id = %s AND id = %s
            FOR UPDATE
            """,
            (tenant_id, asset_id),
        )
        asset_row = await cur.fetchone()
        if asset_row is None:
            raise LookupError("EAM asset not found.")

        await cur.execute(
            """
            SELECT id, asset_id, rule_name, metric_key, operator, threshold_milli,
                   warning_lead_pct, priority, wo_title_template, wo_checklist,
                   auto_create_wo, last_triggered_milli, is_active, created_at
            FROM gba.eam_maintenance_rules
            WHERE tenant_id = %s AND asset_id = %s AND metric_key = %s AND is_active = true
            ORDER BY created_at ASC
            """,
            (tenant_id, asset_id, metric_key),
        )
        rule_rows = await cur.fetchall()

        anomaly = False
        max_penalty = 0
        triggered_rules: list[tuple[EamRuleView, RuleEvaluation]] = []
        warning_only = False

        for rr in rule_rows:
            rule = _row_to_rule(dict(rr))
            ev = evaluate_predictive_rule(
                operator=rule.operator,
                threshold_milli=rule.threshold_milli,
                warning_lead_pct=rule.warning_lead_pct,
                value_milli=value_milli,
                last_triggered_milli=rule.last_triggered_milli,
                metric_key=metric_key,
            )
            if ev.outcome == "triggered":
                anomaly = True
                max_penalty = max(max_penalty, ev.health_penalty)
                triggered_rules.append((rule, ev))
            elif ev.outcome == "warning":
                anomaly = True
                warning_only = True
                max_penalty = max(max_penalty, ev.health_penalty)

        await cur.execute(
            """
            INSERT INTO gba.eam_telemetry_readings (
                tenant_id, asset_id, metric_key, value_milli, unit, source,
                anomaly_flagged, notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, asset_id, metric_key, value_milli, unit, source,
                      anomaly_flagged, notes, recorded_at
            """,
            (
                tenant_id,
                asset_id,
                metric_key,
                value_milli,
                unit,
                source,
                anomaly,
                notes.strip(),
            ),
        )
        reading_row = await cur.fetchone()
        reading = _row_to_telemetry(dict(_require_row(reading_row, "eam_telemetry insert")))

        # Update asset meter counters, health score, and predictive status
        new_hours = (
            max(int(asset_row["engine_hours_milli"]), value_milli)
            if metric_key == "engine_hours"
            else int(asset_row["engine_hours_milli"])
        )
        new_odo = (
            max(int(asset_row["odometer_miles_milli"]), value_milli)
            if metric_key == "odometer_miles"
            else int(asset_row["odometer_miles_milli"])
        )
        cur_health = int(asset_row["health_score"])
        new_health = (
            max(10, cur_health - max_penalty) if max_penalty > 0 else min(100, cur_health + 2)
        )
        new_status: EamAssetStatus = asset_row["status"]
        if triggered_rules:
            new_status = "maintenance_due"
        elif warning_only and new_status == "operational":
            new_status = "warning"

        await cur.execute(
            """
            UPDATE gba.eam_assets
            SET engine_hours_milli = %s,
                odometer_miles_milli = %s,
                health_score = %s,
                status = %s,
                last_telemetry_at = now(),
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, asset_tag, name, category, serial_number, location_label, status,
                      engine_hours_milli, odometer_miles_milli, health_score,
                      iot_token_prefix, last_telemetry_at, created_at, updated_at
            """,
            (new_hours, new_odo, new_health, new_status, tenant_id, asset_id),
        )
        updated_asset_row = await cur.fetchone()
        updated_asset = _row_to_asset(dict(_require_row(updated_asset_row, "eam_assets update")))

        created_wos: list[EamWorkOrderView] = []
        for rule, ev in triggered_rules:
            if not rule.auto_create_wo:
                continue
            # Deduplicate: skip if an active open/scheduled/in_progress WO already exists for rule
            await cur.execute(
                """
                SELECT id
                FROM gba.eam_predictive_work_orders
                WHERE tenant_id = %s AND asset_id = %s AND rule_id = %s
                  AND status IN ('open', 'scheduled', 'in_progress')
                LIMIT 1
                """,
                (tenant_id, asset_id, rule.id),
            )
            existing = await cur.fetchone()
            if existing is not None:
                continue

            wo_number = f"EAM-{datetime.now(UTC).strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
            trigger_kind: WorkOrderTriggerKind = (
                "preventive_interval" if rule.operator == "interval_every" else "predictive_iot"
            )
            diag = ev.reason
            if rule.wo_checklist:
                diag = f"{diag}\nChecklist: {rule.wo_checklist}"
            due_days = 1 if rule.priority == "critical" else (3 if rule.priority == "high" else 7)
            due_at = datetime.now(UTC) + timedelta(days=due_days)

            await cur.execute(
                """
                INSERT INTO gba.eam_predictive_work_orders (
                    tenant_id, wo_number, asset_id, rule_id, trigger_reading_id,
                    trigger_kind, priority, status, title, diagnostic_summary,
                    estimated_cost_cents, due_at, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s, %s, 0, %s, %s)
                RETURNING id, wo_number, asset_id, rule_id, trigger_reading_id,
                          trigger_kind, priority, status, title, diagnostic_summary,
                          estimated_cost_cents, due_at, completed_at, completion_notes,
                          created_at, updated_at
                """,
                (
                    tenant_id,
                    wo_number,
                    asset_id,
                    rule.id,
                    reading.id,
                    trigger_kind,
                    rule.priority,
                    rule.wo_title_template,
                    diag[:2000],
                    due_at,
                    created_by_user_id,
                ),
            )
            wo_row = await cur.fetchone()
            enriched = dict(_require_row(wo_row, "eam_predictive_work_orders insert"))
            enriched["asset_tag"] = updated_asset.asset_tag
            enriched["asset_name"] = updated_asset.name
            created_wos.append(_row_to_wo(enriched))

            if rule.operator == "interval_every":
                await cur.execute(
                    """
                    UPDATE gba.eam_maintenance_rules
                    SET last_triggered_milli = %s, updated_at = now()
                    WHERE tenant_id = %s AND id = %s
                    """,
                    (value_milli, tenant_id, rule.id),
                )

    return reading, updated_asset, created_wos


async def update_eam_work_order_status(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    wo_id: UUID,
    status: WorkOrderStatus,
    completion_notes: str,
    estimated_cost_cents: int | None,
) -> EamWorkOrderView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.eam_predictive_work_orders
            SET status = %s,
                completion_notes = CASE WHEN %s <> '' THEN %s ELSE completion_notes END,
                estimated_cost_cents = COALESCE(%s, estimated_cost_cents),
                completed_at = CASE WHEN %s = 'completed' THEN now() ELSE completed_at END,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, asset_id
            """,
            (
                status,
                completion_notes.strip(),
                completion_notes.strip(),
                estimated_cost_cents,
                status,
                tenant_id,
                wo_id,
            ),
        )
        row = await cur.fetchone()
        if row is None:
            raise LookupError("Predictive Work Order not found.")

        if status == "completed":
            # Restore asset health & operational status if no other open WOs remain
            await cur.execute(
                """
                SELECT COUNT(*)::int AS open_cnt
                FROM gba.eam_predictive_work_orders
                WHERE tenant_id = %s AND asset_id = %s
                  AND status IN ('open', 'scheduled', 'in_progress')
                """,
                (tenant_id, row["asset_id"]),
            )
            cnt_row = await cur.fetchone()
            if cnt_row is not None and int(cnt_row["open_cnt"]) == 0:
                await cur.execute(
                    """
                    UPDATE gba.eam_assets
                    SET status = 'operational', health_score = GREATEST(health_score, 95),
                        updated_at = now()
                    WHERE tenant_id = %s AND id = %s
                    """,
                    (tenant_id, row["asset_id"]),
                )

    wos = await list_eam_work_orders(conn, tenant_id=tenant_id)
    for wo in wos:
        if wo.id == wo_id:
            return wo
    raise LookupError("Updated Work Order could not be loaded.")
