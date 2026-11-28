"""HTTP routes for AMARKAL v2.18.0: Enterprise MRP II (BOM Explosion, Stock Reservations &
Auto Draft PO) + Predictive EAM (Industrial Assets, IoT Telemetry Webhook & Auto Work Orders).
"""

from __future__ import annotations

from collections import deque
from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from psycopg import errors as pg_errors
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.api.self_service import (
    enforce_sliding_window_rate_limit,
    extract_client_ip,
)
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.industrial_mrp_eam import (
    AssetCategory,
    EamAssetStatus,
    EamAssetView,
    EamRuleView,
    EamTelemetryView,
    EamWorkOrderView,
    MaterialKind,
    MaterialUnit,
    MetricKey,
    MrpExplosionRequirement,
    MrpExplosionResult,
    MrpMaterialView,
    MrpProductionRunView,
    MrpRecipeLineView,
    MrpRecipeView,
    MrpReservationView,
    ProductionRunStatus,
    ReservationStatus,
    RuleOperator,
    TelemetrySource,
    WorkOrderPriority,
    WorkOrderStatus,
    WorkOrderTriggerKind,
    adjust_mrp_material_stock,
    create_eam_asset,
    create_eam_rule,
    create_mrp_material,
    create_mrp_production_run,
    create_mrp_recipe,
    delete_eam_rule,
    delete_mrp_recipe,
    generate_draft_po_for_run_shortages,
    ingest_eam_telemetry,
    list_eam_assets,
    list_eam_rules,
    list_eam_telemetry,
    list_eam_work_orders,
    list_mrp_materials,
    list_mrp_production_runs,
    list_mrp_recipes,
    preview_mrp_explosion,
    resolve_eam_asset_by_iot_token,
    rotate_eam_asset_iot_token,
    transition_mrp_production_run,
    update_eam_work_order_status,
)
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["industrial-mrp-eam"])

_IOT_INGEST_HITS: dict[str, deque[float]] = {}


# ── MRP II Schemas ───────────────────────────────────────────────────────────


class MrpMaterialResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    preferred_vendor_email: str | None = None
    created_at: datetime
    updated_at: datetime


class CreateMrpMaterialRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sku: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=2, max_length=160)
    material_kind: MaterialKind = "raw"
    unit: MaterialUnit = "ton"
    on_hand_milli: int = Field(default=0, ge=0, le=999_999_999_999)
    reorder_point_milli: int = Field(default=0, ge=0, le=999_999_999_999)
    unit_cost_cents: int = Field(default=0, ge=0, le=999_999_999_999)
    preferred_vendor_name: str = Field(default="", max_length=160)
    preferred_vendor_email: str | None = Field(default=None, max_length=160)


class AdjustMaterialStockRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    delta_milli: int = Field(ge=-999_999_999_999, le=999_999_999_999)


class MrpRecipeLineInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    component_material_id: UUID
    qty_per_batch_milli: int = Field(ge=1, le=999_999_999_999)
    scrap_bps: int = Field(default=0, ge=0, le=5000)
    notes: str = Field(default="", max_length=300)


class CreateMrpRecipeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=2, max_length=160)
    output_material_id: UUID
    output_qty_milli: int = Field(default=1000, ge=1, le=999_999_999_999)
    lead_time_days: int = Field(default=1, ge=0, le=365)
    notes: str = Field(default="", max_length=1000)
    lines: list[MrpRecipeLineInput] = Field(min_length=1, max_length=100)


class MrpRecipeLineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    recipe_id: UUID
    component_material_id: UUID
    component_sku: str
    component_name: str
    component_unit: MaterialUnit
    qty_per_batch_milli: int
    scrap_bps: int
    notes: str


class MrpRecipeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    lines: list[MrpRecipeLineResponse]
    created_at: datetime
    updated_at: datetime


class MrpExplosionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recipe_id: UUID
    target_qty_milli: int = Field(ge=1, le=999_999_999_999)


class MrpExplosionLineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    preferred_vendor_email: str | None = None


class MrpExplosionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    recipe_id: UUID
    recipe_code: str
    recipe_name: str
    output_material_id: UUID
    output_sku: str
    output_unit: MaterialUnit
    target_qty_milli: int
    requirements: list[MrpExplosionLineResponse]
    total_material_cost_cents: int
    shortage_count: int
    can_fully_reserve: bool


class CreateProductionRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recipe_id: UUID
    target_qty_milli: int = Field(ge=1, le=999_999_999_999)
    scheduled_date: date | None = None
    notes: str = Field(default="", max_length=1000)
    reserve_available: bool = True


class TransitionRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Literal["start", "complete", "cancel"]


class MrpReservationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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


class MrpProductionRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    run_number: str
    recipe_id: UUID
    recipe_code: str
    recipe_name: str
    output_sku: str
    output_unit: MaterialUnit
    target_qty_milli: int
    status: ProductionRunStatus
    scheduled_date: date | None = None
    estimated_material_cost_cents: int
    shortage_count: int
    draft_po_id: UUID | None = None
    notes: str
    reservations: list[MrpReservationResponse]
    completed_at: datetime | None = None
    created_at: datetime


class DraftPoResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    purchase_order_id: UUID
    po_number: str
    total_cents: int


# ── Predictive EAM Schemas ───────────────────────────────────────────────────


class EamAssetResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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
    iot_token_prefix: str | None = None
    last_telemetry_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EamAssetCreatedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    asset: EamAssetResponse
    iot_ingest_token: str


class CreateEamAssetRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_tag: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=2, max_length=160)
    category: AssetCategory = "fleet_vehicle"
    serial_number: str = Field(default="", max_length=120)
    location_label: str = Field(default="", max_length=160)
    engine_hours_milli: int = Field(default=0, ge=0, le=999_999_999_999)
    odometer_miles_milli: int = Field(default=0, ge=0, le=999_999_999_999)


class EamRuleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
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


class CreateEamRuleRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_id: UUID
    rule_name: str = Field(min_length=2, max_length=160)
    metric_key: MetricKey
    operator: RuleOperator
    threshold_milli: int = Field(ge=1, le=999_999_999_999)
    warning_lead_pct: int = Field(default=90, ge=50, le=100)
    priority: WorkOrderPriority = "high"
    wo_title_template: str = Field(min_length=2, max_length=240)
    wo_checklist: str = Field(default="", max_length=1000)
    auto_create_wo: bool = True


class EamTelemetryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    asset_id: UUID
    metric_key: MetricKey
    value_milli: int
    unit: str
    source: TelemetrySource
    anomaly_flagged: bool
    notes: str
    recorded_at: datetime


class EamWorkOrderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    wo_number: str
    asset_id: UUID
    asset_tag: str
    asset_name: str
    rule_id: UUID | None = None
    trigger_reading_id: UUID | None = None
    trigger_kind: WorkOrderTriggerKind
    priority: WorkOrderPriority
    status: WorkOrderStatus
    title: str
    diagnostic_summary: str
    estimated_cost_cents: int
    due_at: datetime | None = None
    completed_at: datetime | None = None
    completion_notes: str
    created_at: datetime
    updated_at: datetime


class IngestTelemetryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    asset_id: UUID
    metric_key: MetricKey
    value_milli: int = Field(ge=-1_000_000_000, le=999_999_999_999)
    source: TelemetrySource = "manual"
    notes: str = Field(default="", max_length=500)


class PublicIotTelemetryRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    metric_key: MetricKey
    value_milli: int = Field(ge=-1_000_000_000, le=999_999_999_999)
    notes: str = Field(default="", max_length=500)


class TelemetryIngestResultResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    reading: EamTelemetryResponse
    asset: EamAssetResponse
    auto_created_work_orders: list[EamWorkOrderResponse]


class UpdateWorkOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: WorkOrderStatus
    completion_notes: str = Field(default="", max_length=2000)
    estimated_cost_cents: int | None = Field(default=None, ge=0, le=999_999_999_999)


# ── View serializers ─────────────────────────────────────────────────────────


def _mat_resp(v: MrpMaterialView) -> MrpMaterialResponse:
    return MrpMaterialResponse(
        id=v.id,
        sku=v.sku,
        name=v.name,
        material_kind=v.material_kind,
        unit=v.unit,
        on_hand_milli=v.on_hand_milli,
        reserved_milli=v.reserved_milli,
        available_milli=v.available_milli,
        reorder_point_milli=v.reorder_point_milli,
        unit_cost_cents=v.unit_cost_cents,
        preferred_vendor_name=v.preferred_vendor_name,
        preferred_vendor_email=v.preferred_vendor_email,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _line_resp(v: MrpRecipeLineView) -> MrpRecipeLineResponse:
    return MrpRecipeLineResponse(
        id=v.id,
        recipe_id=v.recipe_id,
        component_material_id=v.component_material_id,
        component_sku=v.component_sku,
        component_name=v.component_name,
        component_unit=v.component_unit,
        qty_per_batch_milli=v.qty_per_batch_milli,
        scrap_bps=v.scrap_bps,
        notes=v.notes,
    )


def _recipe_resp(v: MrpRecipeView) -> MrpRecipeResponse:
    return MrpRecipeResponse(
        id=v.id,
        code=v.code,
        name=v.name,
        output_material_id=v.output_material_id,
        output_sku=v.output_sku,
        output_name=v.output_name,
        output_unit=v.output_unit,
        output_qty_milli=v.output_qty_milli,
        lead_time_days=v.lead_time_days,
        notes=v.notes,
        is_active=v.is_active,
        lines=[_line_resp(x) for x in v.lines],
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _explosion_line_resp(v: MrpExplosionRequirement) -> MrpExplosionLineResponse:
    return MrpExplosionLineResponse(
        material_id=v.material_id,
        sku=v.sku,
        name=v.name,
        unit=v.unit,
        required_milli=v.required_milli,
        on_hand_milli=v.on_hand_milli,
        already_reserved_milli=v.already_reserved_milli,
        available_milli=v.available_milli,
        reservable_milli=v.reservable_milli,
        shortage_milli=v.shortage_milli,
        unit_cost_cents=v.unit_cost_cents,
        estimated_cost_cents=v.estimated_cost_cents,
        preferred_vendor_name=v.preferred_vendor_name,
        preferred_vendor_email=v.preferred_vendor_email,
    )


def _explosion_resp(v: MrpExplosionResult) -> MrpExplosionResponse:
    return MrpExplosionResponse(
        recipe_id=v.recipe_id,
        recipe_code=v.recipe_code,
        recipe_name=v.recipe_name,
        output_material_id=v.output_material_id,
        output_sku=v.output_sku,
        output_unit=v.output_unit,
        target_qty_milli=v.target_qty_milli,
        requirements=[_explosion_line_resp(r) for r in v.requirements],
        total_material_cost_cents=v.total_material_cost_cents,
        shortage_count=v.shortage_count,
        can_fully_reserve=v.can_fully_reserve,
    )


def _res_resp(v: MrpReservationView) -> MrpReservationResponse:
    return MrpReservationResponse(
        id=v.id,
        run_id=v.run_id,
        material_id=v.material_id,
        material_sku=v.material_sku,
        material_name=v.material_name,
        material_unit=v.material_unit,
        required_milli=v.required_milli,
        reserved_milli=v.reserved_milli,
        shortage_milli=v.shortage_milli,
        unit_cost_cents=v.unit_cost_cents,
        status=v.status,
    )


def _run_resp(v: MrpProductionRunView) -> MrpProductionRunResponse:
    return MrpProductionRunResponse(
        id=v.id,
        run_number=v.run_number,
        recipe_id=v.recipe_id,
        recipe_code=v.recipe_code,
        recipe_name=v.recipe_name,
        output_sku=v.output_sku,
        output_unit=v.output_unit,
        target_qty_milli=v.target_qty_milli,
        status=v.status,
        scheduled_date=v.scheduled_date,
        estimated_material_cost_cents=v.estimated_material_cost_cents,
        shortage_count=v.shortage_count,
        draft_po_id=v.draft_po_id,
        notes=v.notes,
        reservations=[_res_resp(x) for x in v.reservations],
        completed_at=v.completed_at,
        created_at=v.created_at,
    )


def _asset_resp(v: EamAssetView) -> EamAssetResponse:
    return EamAssetResponse(
        id=v.id,
        asset_tag=v.asset_tag,
        name=v.name,
        category=v.category,
        serial_number=v.serial_number,
        location_label=v.location_label,
        status=v.status,
        engine_hours_milli=v.engine_hours_milli,
        odometer_miles_milli=v.odometer_miles_milli,
        health_score=v.health_score,
        iot_token_prefix=v.iot_token_prefix,
        last_telemetry_at=v.last_telemetry_at,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _rule_resp(v: EamRuleView) -> EamRuleResponse:
    return EamRuleResponse(
        id=v.id,
        asset_id=v.asset_id,
        rule_name=v.rule_name,
        metric_key=v.metric_key,
        operator=v.operator,
        threshold_milli=v.threshold_milli,
        warning_lead_pct=v.warning_lead_pct,
        priority=v.priority,
        wo_title_template=v.wo_title_template,
        wo_checklist=v.wo_checklist,
        auto_create_wo=v.auto_create_wo,
        last_triggered_milli=v.last_triggered_milli,
        is_active=v.is_active,
        created_at=v.created_at,
    )


def _tel_resp(v: EamTelemetryView) -> EamTelemetryResponse:
    return EamTelemetryResponse(
        id=v.id,
        asset_id=v.asset_id,
        metric_key=v.metric_key,
        value_milli=v.value_milli,
        unit=v.unit,
        source=v.source,
        anomaly_flagged=v.anomaly_flagged,
        notes=v.notes,
        recorded_at=v.recorded_at,
    )


def _wo_resp(v: EamWorkOrderView) -> EamWorkOrderResponse:
    return EamWorkOrderResponse(
        id=v.id,
        wo_number=v.wo_number,
        asset_id=v.asset_id,
        asset_tag=v.asset_tag,
        asset_name=v.asset_name,
        rule_id=v.rule_id,
        trigger_reading_id=v.trigger_reading_id,
        trigger_kind=v.trigger_kind,
        priority=v.priority,
        status=v.status,
        title=v.title,
        diagnostic_summary=v.diagnostic_summary,
        estimated_cost_cents=v.estimated_cost_cents,
        due_at=v.due_at,
        completed_at=v.completed_at,
        completion_notes=v.completion_notes,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


# ── MRP II Routes ────────────────────────────────────────────────────────────


@router.get(
    "/v1/businesses/{business_id}/industrial/mrp/materials",
    response_model=list[MrpMaterialResponse],
)
async def get_mrp_materials(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[MrpMaterialResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_mrp_materials(session.conn, tenant_id=business_id)
    return [_mat_resp(m) for m in items]


@router.post(
    "/v1/businesses/{business_id}/industrial/mrp/materials",
    response_model=MrpMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_mrp_material(
    business_id: UUID,
    body: CreateMrpMaterialRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> MrpMaterialResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await create_mrp_material(
                session.conn,
                tenant_id=business_id,
                sku=body.sku,
                name=body.name,
                material_kind=body.material_kind,
                unit=body.unit,
                on_hand_milli=body.on_hand_milli,
                reorder_point_milli=body.reorder_point_milli,
                unit_cost_cents=body.unit_cost_cents,
                preferred_vendor_name=body.preferred_vendor_name,
                preferred_vendor_email=body.preferred_vendor_email,
            )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A material with this SKU already exists.",
        ) from exc
    return _mat_resp(item)


@router.post(
    "/v1/businesses/{business_id}/industrial/mrp/materials/{material_id}/adjust",
    response_model=MrpMaterialResponse,
)
async def post_adjust_mrp_stock(
    business_id: UUID,
    material_id: UUID,
    body: AdjustMaterialStockRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> MrpMaterialResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await adjust_mrp_material_stock(
                session.conn,
                tenant_id=business_id,
                material_id=material_id,
                delta_milli=body.delta_milli,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _mat_resp(item)


@router.get(
    "/v1/businesses/{business_id}/industrial/mrp/recipes",
    response_model=list[MrpRecipeResponse],
)
async def get_mrp_recipes(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[MrpRecipeResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_mrp_recipes(session.conn, tenant_id=business_id)
    return [_recipe_resp(r) for r in items]


@router.post(
    "/v1/businesses/{business_id}/industrial/mrp/recipes",
    response_model=MrpRecipeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_mrp_recipe(
    business_id: UUID,
    body: CreateMrpRecipeRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> MrpRecipeResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            recipe = await create_mrp_recipe(
                session.conn,
                tenant_id=business_id,
                code=body.code,
                name=body.name,
                output_material_id=body.output_material_id,
                output_qty_milli=body.output_qty_milli,
                lead_time_days=body.lead_time_days,
                notes=body.notes,
                lines=[
                    (x.component_material_id, x.qty_per_batch_milli, x.scrap_bps, x.notes)
                    for x in body.lines
                ],
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A BOM recipe with this code already exists.",
        ) from exc
    except pg_errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referenced material was not found.",
        ) from exc
    return _recipe_resp(recipe)


@router.delete(
    "/v1/businesses/{business_id}/industrial/mrp/recipes/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_mrp_recipe_route(
    business_id: UUID,
    recipe_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> Response:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            deleted = await delete_mrp_recipe(
                session.conn, tenant_id=business_id, recipe_id=recipe_id
            )
    except pg_errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Recipe is referenced by existing production runs.",
        ) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/v1/businesses/{business_id}/industrial/mrp/explode",
    response_model=MrpExplosionResponse,
)
async def post_mrp_explode(
    business_id: UUID,
    body: MrpExplosionRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> MrpExplosionResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_READ,
            request_id=get_request_id(request),
        ) as session:
            res = await preview_mrp_explosion(
                session.conn,
                tenant_id=business_id,
                recipe_id=body.recipe_id,
                target_qty_milli=body.target_qty_milli,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _explosion_resp(res)


@router.get(
    "/v1/businesses/{business_id}/industrial/mrp/runs",
    response_model=list[MrpProductionRunResponse],
)
async def get_mrp_runs(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[MrpProductionRunResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_mrp_production_runs(session.conn, tenant_id=business_id)
    return [_run_resp(r) for r in items]


@router.post(
    "/v1/businesses/{business_id}/industrial/mrp/runs",
    response_model=MrpProductionRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_mrp_run(
    business_id: UUID,
    body: CreateProductionRunRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> MrpProductionRunResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            run = await create_mrp_production_run(
                session.conn,
                tenant_id=business_id,
                recipe_id=body.recipe_id,
                target_qty_milli=body.target_qty_milli,
                scheduled_date=body.scheduled_date,
                notes=body.notes,
                reserve_available=body.reserve_available,
                created_by_user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _run_resp(run)


@router.post(
    "/v1/businesses/{business_id}/industrial/mrp/runs/{run_id}/transition",
    response_model=MrpProductionRunResponse,
)
async def post_transition_mrp_run(
    business_id: UUID,
    run_id: UUID,
    body: TransitionRunRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> MrpProductionRunResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            run = await transition_mrp_production_run(
                session.conn, tenant_id=business_id, run_id=run_id, action=body.action
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _run_resp(run)


@router.post(
    "/v1/businesses/{business_id}/industrial/mrp/runs/{run_id}/draft-po",
    response_model=DraftPoResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_mrp_run_draft_po(
    business_id: UUID,
    run_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> DraftPoResultResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            po_id, po_number, total_cents = await generate_draft_po_for_run_shortages(
                session.conn,
                tenant_id=business_id,
                run_id=run_id,
                created_by_user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DraftPoResultResponse(
        purchase_order_id=po_id,
        po_number=po_number,
        total_cents=total_cents,
    )


# ── Predictive EAM & IoT Routes ──────────────────────────────────────────────


@router.get(
    "/v1/businesses/{business_id}/industrial/eam/assets",
    response_model=list[EamAssetResponse],
)
async def get_eam_assets(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[EamAssetResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_eam_assets(session.conn, tenant_id=business_id)
    return [_asset_resp(a) for a in items]


@router.post(
    "/v1/businesses/{business_id}/industrial/eam/assets",
    response_model=EamAssetCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_eam_asset(
    business_id: UUID,
    body: CreateEamAssetRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> EamAssetCreatedResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            asset, token = await create_eam_asset(
                session.conn,
                tenant_id=business_id,
                asset_tag=body.asset_tag,
                name=body.name,
                category=body.category,
                serial_number=body.serial_number,
                location_label=body.location_label,
                engine_hours_milli=body.engine_hours_milli,
                odometer_miles_milli=body.odometer_miles_milli,
            )
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An EAM asset with this asset tag already exists.",
        ) from exc
    return EamAssetCreatedResponse(asset=_asset_resp(asset), iot_ingest_token=token)


@router.post(
    "/v1/businesses/{business_id}/industrial/eam/assets/{asset_id}/rotate-token",
    response_model=EamAssetCreatedResponse,
)
async def post_rotate_iot_token(
    business_id: UUID,
    asset_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> EamAssetCreatedResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            asset, token = await rotate_eam_asset_iot_token(
                session.conn, tenant_id=business_id, asset_id=asset_id
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return EamAssetCreatedResponse(asset=_asset_resp(asset), iot_ingest_token=token)


@router.get(
    "/v1/businesses/{business_id}/industrial/eam/rules",
    response_model=list[EamRuleResponse],
)
async def get_eam_rules(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
    asset_id: Annotated[UUID | None, Query()] = None,
) -> list[EamRuleResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_eam_rules(session.conn, tenant_id=business_id, asset_id=asset_id)
    return [_rule_resp(r) for r in items]


@router.post(
    "/v1/businesses/{business_id}/industrial/eam/rules",
    response_model=EamRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_eam_rule(
    business_id: UUID,
    body: CreateEamRuleRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> EamRuleResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rule = await create_eam_rule(
                session.conn,
                tenant_id=business_id,
                asset_id=body.asset_id,
                rule_name=body.rule_name,
                metric_key=body.metric_key,
                operator=body.operator,
                threshold_milli=body.threshold_milli,
                warning_lead_pct=body.warning_lead_pct,
                priority=body.priority,
                wo_title_template=body.wo_title_template,
                wo_checklist=body.wo_checklist,
                auto_create_wo=body.auto_create_wo,
            )
    except pg_errors.ForeignKeyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Referenced asset not found."
        ) from exc
    return _rule_resp(rule)


@router.delete(
    "/v1/businesses/{business_id}/industrial/eam/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_eam_rule_route(
    business_id: UUID,
    rule_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> Response:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        deleted = await delete_eam_rule(session.conn, tenant_id=business_id, rule_id=rule_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/v1/businesses/{business_id}/industrial/eam/telemetry",
    response_model=list[EamTelemetryResponse],
)
async def get_eam_telemetry(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
    asset_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[EamTelemetryResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_eam_telemetry(
            session.conn, tenant_id=business_id, asset_id=asset_id, limit=limit
        )
    return [_tel_resp(t) for t in items]


@router.post(
    "/v1/businesses/{business_id}/industrial/eam/telemetry",
    response_model=TelemetryIngestResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_eam_telemetry(
    business_id: UUID,
    body: IngestTelemetryRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> TelemetryIngestResultResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            reading, asset, created_wos = await ingest_eam_telemetry(
                session.conn,
                tenant_id=business_id,
                asset_id=body.asset_id,
                metric_key=body.metric_key,
                value_milli=body.value_milli,
                source=body.source,
                notes=body.notes,
                created_by_user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TelemetryIngestResultResponse(
        reading=_tel_resp(reading),
        asset=_asset_resp(asset),
        auto_created_work_orders=[_wo_resp(w) for w in created_wos],
    )


@router.get(
    "/v1/businesses/{business_id}/industrial/eam/work-orders",
    response_model=list[EamWorkOrderResponse],
)
async def get_eam_work_orders(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[EamWorkOrderResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_eam_work_orders(session.conn, tenant_id=business_id)
    return [_wo_resp(w) for w in items]


@router.patch(
    "/v1/businesses/{business_id}/industrial/eam/work-orders/{wo_id}",
    response_model=EamWorkOrderResponse,
)
async def patch_eam_work_order(
    business_id: UUID,
    wo_id: UUID,
    body: UpdateWorkOrderRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> EamWorkOrderResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            wo = await update_eam_work_order_status(
                session.conn,
                tenant_id=business_id,
                wo_id=wo_id,
                status=body.status,
                completion_notes=body.completion_notes,
                estimated_cost_cents=body.estimated_cost_cents,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _wo_resp(wo)


@router.post(
    "/v1/public/iot/telemetry",
    response_model=TelemetryIngestResultResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_public_iot_telemetry(
    body: PublicIotTelemetryRequest,
    request: Request,
    iot_token: Annotated[str | None, Header(alias="X-AMARKAL-IoT-Token")] = None,
) -> TelemetryIngestResultResponse:
    """Rate-limited industrial IoT/PLC/Telematics webhook authenticated via X-AMARKAL-IoT-Token."""
    client_ip = extract_client_ip(request)
    enforce_sliding_window_rate_limit(
        _IOT_INGEST_HITS,
        key=f"iot:{client_ip}",
        window_seconds=60.0,
        max_requests=120,
        detail="IoT telemetry rate limit exceeded. Please retry shortly.",
    )
    if not iot_token or len(iot_token.strip()) < 16:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-AMARKAL-IoT-Token header.",
        )

    pool = runtime_pool(request)
    async with pool.connection() as conn, conn.transaction():
        resolved = await resolve_eam_asset_by_iot_token(conn, plaintext_token=iot_token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid IoT telemetry token.",
        )

    tenant_id, asset_id = resolved
    async with tenant_transaction(pool, tenant_id) as conn:
        reading, asset, created_wos = await ingest_eam_telemetry(
            conn,
            tenant_id=tenant_id,
            asset_id=asset_id,
            metric_key=body.metric_key,
            value_milli=body.value_milli,
            source="iot_webhook",
            notes=body.notes,
        )
    return TelemetryIngestResultResponse(
        reading=_tel_resp(reading),
        asset=_asset_resp(asset),
        auto_created_work_orders=[_wo_resp(w) for w in created_wos],
    )
