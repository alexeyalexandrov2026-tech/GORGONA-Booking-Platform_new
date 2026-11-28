"""AMARKAL v2.33.0: Low-Code / No-Code Visual BPMN Workflow & Approval Chain REST API.

Runs strictly under PostgreSQL 18 `ENABLE + FORCE ROW LEVEL SECURITY` with zero
dynamic code execution and immutable `gba.audit_events` logging on all mutations.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.workflow_bpmn import (
    BPMN_PRESET_TEMPLATES,
    BpmnNodeType,
    EdgeBranch,
    TriggerEntity,
    advance_bpmn_execution,
    export_bpmn_20_xml,
    generate_bpmn_from_prompt,
    validate_bpmn_graph,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/workflows", tags=["workflows-bpmn"])

WorkflowStatus = Literal["draft", "active", "paused", "archived"]
InstanceStatus = Literal["running", "awaiting_approval", "approved", "rejected", "cancelled"]
HumanDecision = Literal["approve", "reject"]

_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean(value: str) -> str:
    return _CTRL_RE.sub("", value).strip()


class BpmnNodePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    node_type: BpmnNodeType
    label: str = Field(min_length=1, max_length=120)
    x: int = Field(default=40, ge=0, le=3000)
    y: int = Field(default=100, ge=0, le=2000)
    config: dict[str, Any] = Field(default_factory=dict)


class BpmnEdgePayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    source_id: str = Field(min_length=1, max_length=64)
    target_id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=80)
    branch: EdgeBranch = "default"


class BpmnWorkflowView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    workflow_code: str
    display_name: str
    description: str
    trigger_entity: TriggerEntity
    version: int
    status: WorkflowStatus
    nodes: list[BpmnNodePayload]
    edges: list[BpmnEdgePayload]
    warnings: list[str]
    active_instance_count: int
    created_at: datetime
    updated_at: datetime


class BpmnInstanceView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    workflow_id: UUID
    workflow_code: str
    workflow_name: str
    reference_code: str
    entity_title: str
    amount_cents: int
    context: dict[str, Any]
    current_node_id: str
    current_node_label: str
    status: InstanceStatus
    trace: list[dict[str, Any]]
    started_at: datetime
    completed_at: datetime | None


class BpmnPresetView(BaseModel):
    model_config = ConfigDict(frozen=True)
    workflow_code: str
    display_name: str
    description: str
    trigger_entity: TriggerEntity
    node_count: int
    installed: bool


class WorkflowsOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    workflows: list[BpmnWorkflowView]
    instances: list[BpmnInstanceView]
    presets: list[BpmnPresetView]
    pending_approvals_count: int


class CreateWorkflowRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    workflow_code: str = Field(min_length=3, max_length=63)
    display_name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    trigger_entity: TriggerEntity = "contract"
    status: WorkflowStatus = "active"
    nodes: list[BpmnNodePayload] = Field(min_length=2, max_length=40)
    edges: list[BpmnEdgePayload] = Field(min_length=1, max_length=80)

    @field_validator("workflow_code")
    @classmethod
    def check_code(cls, v: str) -> str:
        code = v.strip().lower()
        if not _CODE_RE.fullmatch(code):
            raise ValueError("workflow_code must match ^[a-z0-9][a-z0-9_-]{2,62}$")
        return code


class UpdateWorkflowRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    status: WorkflowStatus | None = None
    nodes: list[BpmnNodePayload] | None = Field(default=None, min_length=2, max_length=40)
    edges: list[BpmnEdgePayload] | None = Field(default=None, min_length=1, max_length=80)


class GeneratePromptRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    prompt: str = Field(min_length=6, max_length=600)


class GeneratedDraftResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    workflow_code: str
    display_name: str
    description: str
    trigger_entity: TriggerEntity
    nodes: list[BpmnNodePayload]
    edges: list[BpmnEdgePayload]
    warnings: list[str]


class DryRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    amount_cents: int = Field(default=7_500_000, ge=0, le=100_000_000_000)
    context: dict[str, Any] = Field(
        default_factory=lambda: {"region": "Midwest", "currency": "USD", "risk_score": 15}
    )


class DryRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    workflow_code: str
    simulated_status: str
    visited_node_ids: list[str]
    trace: list[dict[str, Any]]


class StartInstanceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reference_code: str = Field(min_length=2, max_length=80)
    entity_title: str = Field(min_length=2, max_length=200)
    amount_cents: int = Field(ge=0, le=100_000_000_000)
    context: dict[str, Any] = Field(default_factory=dict)


class DecideInstanceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision: HumanDecision
    comment: str = Field(default="", max_length=500)


async def _fetch_all(
    conn: RuntimeConnection, sql: str, params: tuple[Any, ...]
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _fetch_one(
    conn: RuntimeConnection, sql: str, params: tuple[Any, ...]
) -> dict[str, Any] | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()
    return dict(row) if row is not None else None


def _row_to_workflow_view(row: dict[str, Any]) -> BpmnWorkflowView:
    raw_nodes = list(row.get("nodes_json") or [])
    raw_edges = list(row.get("edges_json") or [])
    validation = validate_bpmn_graph(
        raw_nodes, raw_edges, trigger_entity=str(row["trigger_entity"])
    )
    return BpmnWorkflowView(
        id=row["id"],
        workflow_code=str(row["workflow_code"]),
        display_name=str(row["display_name"]),
        description=str(row.get("description") or ""),
        trigger_entity=row["trigger_entity"],
        version=int(row["version"]),
        status=row["status"],
        nodes=[BpmnNodePayload.model_validate(n) for n in raw_nodes],
        edges=[BpmnEdgePayload.model_validate(e) for e in raw_edges],
        warnings=list(validation.warnings),
        active_instance_count=int(row.get("active_instance_count") or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_instance_view(row: dict[str, Any]) -> BpmnInstanceView:
    nodes = list(row.get("nodes_json") or [])
    cur_id = str(row.get("current_node_id") or "")
    cur_label = next(
        (str(n.get("label") or cur_id) for n in nodes if str(n.get("id")) == cur_id),
        cur_id or "Completed",
    )
    return BpmnInstanceView(
        id=row["id"],
        workflow_id=row["workflow_id"],
        workflow_code=str(row["workflow_code"]),
        workflow_name=str(row["workflow_name"]),
        reference_code=str(row["reference_code"]),
        entity_title=str(row["entity_title"]),
        amount_cents=int(row["amount_cents"]),
        context=dict(row.get("context_json") or {}),
        current_node_id=cur_id,
        current_node_label=cur_label,
        status=row["status"],
        trace=list(row.get("trace_json") or []),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


@router.get("/overview", response_model=WorkflowsOverviewResponse)
async def get_workflows_overview(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> WorkflowsOverviewResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        wf_rows = await _fetch_all(
            access.conn,
            """
            SELECT w.*,
                   (SELECT COUNT(*)
                      FROM gba.bpmn_workflow_instances i
                     WHERE i.tenant_id = w.tenant_id
                       AND i.workflow_id = w.id
                       AND i.status IN ('running', 'awaiting_approval')) AS active_instance_count
            FROM gba.bpmn_workflows w
            WHERE w.tenant_id = %s
            ORDER BY w.updated_at DESC
            """,
            (business_id,),
        )
        inst_rows = await _fetch_all(
            access.conn,
            """
            SELECT i.*,
                   w.workflow_code,
                   w.display_name AS workflow_name,
                   w.nodes_json
            FROM gba.bpmn_workflow_instances i
            JOIN gba.bpmn_workflows w
              ON w.id = i.workflow_id AND w.tenant_id = i.tenant_id
            WHERE i.tenant_id = %s
            ORDER BY i.updated_at DESC
            LIMIT 50
            """,
            (business_id,),
        )

    workflows = [_row_to_workflow_view(r) for r in wf_rows]
    instances = [_row_to_instance_view(r) for r in inst_rows]
    installed_codes = {w.workflow_code for w in workflows}
    presets = [
        BpmnPresetView(
            workflow_code=str(tpl["workflow_code"]),
            display_name=str(tpl["display_name"]),
            description=str(tpl["description"]),
            trigger_entity=tpl["trigger_entity"],
            node_count=len(tpl["nodes"]),
            installed=str(tpl["workflow_code"]) in installed_codes,
        )
        for tpl in BPMN_PRESET_TEMPLATES
    ]
    pending_count = sum(1 for i in instances if i.status == "awaiting_approval")
    return WorkflowsOverviewResponse(
        workflows=workflows,
        instances=instances,
        presets=presets,
        pending_approvals_count=pending_count,
    )


@router.post("", response_model=BpmnWorkflowView, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    business_id: UUID,
    body: CreateWorkflowRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BpmnWorkflowView:
    nodes_raw = [n.model_dump() for n in body.nodes]
    edges_raw = [e.model_dump() for e in body.edges]
    check = validate_bpmn_graph(nodes_raw, edges_raw, trigger_entity=body.trigger_entity)
    if not check.valid:
        raise HTTPException(status_code=422, detail="; ".join(check.errors))

    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        try:
            row = await _fetch_one(
                access.conn,
                """
                INSERT INTO gba.bpmn_workflows (
                    tenant_id, workflow_code, display_name, description,
                    trigger_entity, status, nodes_json, edges_json, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *, 0::bigint AS active_instance_count
                """,
                (
                    business_id,
                    body.workflow_code,
                    _clean(body.display_name),
                    _clean(body.description),
                    body.trigger_entity,
                    body.status,
                    Jsonb(nodes_raw),
                    Jsonb(edges_raw),
                    access.principal.user_id,
                ),
            )
        except pg_errors.UniqueViolation as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Workflow code '{body.workflow_code}' already exists.",
            ) from exc

        assert row is not None  # noqa: S101
        await access.conn.execute(
            """
            INSERT INTO gba.audit_events (
                tenant_id, actor, action, target_type, target_id, details, request_id
            )
            VALUES (
                %s, %s, 'bpmn.workflow_created', 'bpmn_workflow', %s, %s,
                nullif(pg_catalog.current_setting('gba.request_id', true), '')
            )
            """,
            (
                business_id,
                access.principal.actor,
                str(row["id"]),
                Jsonb(
                    {
                        "workflow_code": body.workflow_code,
                        "trigger_entity": body.trigger_entity,
                        "node_count": len(nodes_raw),
                    }
                ),
            ),
        )
        return _row_to_workflow_view(row)


@router.post("/presets/{preset_code}", response_model=BpmnWorkflowView, status_code=201)
async def install_workflow_preset(
    business_id: UUID,
    preset_code: str,
    request: Request,
    principal: CurrentPrincipal,
) -> BpmnWorkflowView:
    template = next(
        (tpl for tpl in BPMN_PRESET_TEMPLATES if tpl["workflow_code"] == preset_code),
        None,
    )
    if template is None:
        raise HTTPException(status_code=404, detail=f"Unknown BPMN preset '{preset_code}'.")
    req = CreateWorkflowRequest.model_validate(template)
    return await create_workflow(business_id, req, request, principal)


@router.post("/generate-from-prompt", response_model=GeneratedDraftResponse)
async def generate_workflow_from_prompt(
    business_id: UUID,
    body: GeneratePromptRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> GeneratedDraftResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ):
        draft = generate_bpmn_from_prompt(body.prompt)
        check = validate_bpmn_graph(
            draft["nodes"], draft["edges"], trigger_entity=draft["trigger_entity"]
        )
        return GeneratedDraftResponse(
            workflow_code=draft["workflow_code"],
            display_name=draft["display_name"],
            description=draft["description"],
            trigger_entity=draft["trigger_entity"],
            nodes=[BpmnNodePayload.model_validate(n) for n in draft["nodes"]],
            edges=[BpmnEdgePayload.model_validate(e) for e in draft["edges"]],
            warnings=list(check.warnings),
        )


@router.patch("/{workflow_id}", response_model=BpmnWorkflowView)
async def update_workflow(
    business_id: UUID,
    workflow_id: UUID,
    body: UpdateWorkflowRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BpmnWorkflowView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        existing = await _fetch_one(
            access.conn,
            "SELECT * FROM gba.bpmn_workflows WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (business_id, workflow_id),
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="Workflow not found.")

        next_nodes = (
            [n.model_dump() for n in body.nodes]
            if body.nodes is not None
            else list(existing["nodes_json"])
        )
        next_edges = (
            [e.model_dump() for e in body.edges]
            if body.edges is not None
            else list(existing["edges_json"])
        )
        check = validate_bpmn_graph(
            next_nodes, next_edges, trigger_entity=str(existing["trigger_entity"])
        )
        if not check.valid:
            raise HTTPException(status_code=422, detail="; ".join(check.errors))

        row = await _fetch_one(
            access.conn,
            """
            UPDATE gba.bpmn_workflows
            SET display_name = %s,
                description = %s,
                status = %s,
                nodes_json = %s,
                edges_json = %s,
                version = version + 1,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *,
                      (SELECT COUNT(*)
                         FROM gba.bpmn_workflow_instances i
                        WHERE i.tenant_id = gba.bpmn_workflows.tenant_id
                          AND i.workflow_id = gba.bpmn_workflows.id
                          AND i.status IN ('running', 'awaiting_approval'))
                      AS active_instance_count
            """,
            (
                _clean(body.display_name)
                if body.display_name is not None
                else existing["display_name"],
                _clean(body.description)
                if body.description is not None
                else existing["description"],
                body.status if body.status is not None else existing["status"],
                Jsonb(next_nodes),
                Jsonb(next_edges),
                business_id,
                workflow_id,
            ),
        )
        assert row is not None  # noqa: S101
        return _row_to_workflow_view(row)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    business_id: UUID,
    workflow_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> None:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        cur = await access.conn.execute(
            "DELETE FROM gba.bpmn_workflows WHERE tenant_id = %s AND id = %s",
            (business_id, workflow_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Workflow not found.")


@router.get("/{workflow_id}/bpmn-xml")
async def download_workflow_bpmn_xml(
    business_id: UUID,
    workflow_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        row = await _fetch_one(
            access.conn,
            "SELECT * FROM gba.bpmn_workflows WHERE tenant_id = %s AND id = %s",
            (business_id, workflow_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Workflow not found.")

    xml_text = export_bpmn_20_xml(
        workflow_code=str(row["workflow_code"]),
        display_name=str(row["display_name"]),
        nodes=list(row["nodes_json"] or []),
        edges=list(row["edges_json"] or []),
    )
    return Response(
        content=xml_text,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="{row["workflow_code"]}.bpmn.xml"',
        },
    )


@router.post("/{workflow_id}/dry-run", response_model=DryRunResponse)
async def dry_run_workflow(
    business_id: UUID,
    workflow_id: UUID,
    body: DryRunRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> DryRunResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        row = await _fetch_one(
            access.conn,
            "SELECT * FROM gba.bpmn_workflows WHERE tenant_id = %s AND id = %s",
            (business_id, workflow_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Workflow not found.")

    sim_status, _, trace, visited = advance_bpmn_execution(
        nodes=list(row["nodes_json"] or []),
        edges=list(row["edges_json"] or []),
        amount_cents=body.amount_cents,
        context=dict(body.context),
        dry_run=True,
    )
    return DryRunResponse(
        workflow_code=str(row["workflow_code"]),
        simulated_status=sim_status,
        visited_node_ids=visited,
        trace=trace,
    )


@router.post(
    "/{workflow_id}/instances",
    response_model=BpmnInstanceView,
    status_code=status.HTTP_201_CREATED,
)
async def start_workflow_instance(
    business_id: UUID,
    workflow_id: UUID,
    body: StartInstanceRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BpmnInstanceView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        wf = await _fetch_one(
            access.conn,
            "SELECT * FROM gba.bpmn_workflows WHERE tenant_id = %s AND id = %s",
            (business_id, workflow_id),
        )
        if wf is None:
            raise HTTPException(status_code=404, detail="Workflow not found.")
        if str(wf["status"]) != "active":
            raise HTTPException(
                status_code=409,
                detail="Only active workflows can launch new approval instances.",
            )

        inst_status, cur_node_id, trace, _ = advance_bpmn_execution(
            nodes=list(wf["nodes_json"] or []),
            edges=list(wf["edges_json"] or []),
            amount_cents=body.amount_cents,
            context=dict(body.context),
            dry_run=False,
        )
        completed_at = datetime.now(UTC) if inst_status in ("approved", "rejected") else None

        row = await _fetch_one(
            access.conn,
            """
            INSERT INTO gba.bpmn_workflow_instances (
                tenant_id, workflow_id, reference_code, entity_title,
                amount_cents, context_json, current_node_id, status,
                trace_json, started_by_user_id, completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                business_id,
                workflow_id,
                _clean(body.reference_code),
                _clean(body.entity_title),
                body.amount_cents,
                Jsonb(dict(body.context)),
                cur_node_id,
                inst_status,
                Jsonb(trace),
                access.principal.user_id,
                completed_at,
            ),
        )
        assert row is not None  # noqa: S101
        row["workflow_code"] = wf["workflow_code"]
        row["workflow_name"] = wf["display_name"]
        row["nodes_json"] = wf["nodes_json"]
        return _row_to_instance_view(row)


@router.post("/instances/{instance_id}/decide", response_model=BpmnInstanceView)
async def decide_workflow_instance(
    business_id: UUID,
    instance_id: UUID,
    body: DecideInstanceRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> BpmnInstanceView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        inst = await _fetch_one(
            access.conn,
            """
            SELECT i.*,
                   w.workflow_code,
                   w.display_name AS workflow_name,
                   w.nodes_json,
                   w.edges_json
            FROM gba.bpmn_workflow_instances i
            JOIN gba.bpmn_workflows w
              ON w.id = i.workflow_id AND w.tenant_id = i.tenant_id
            WHERE i.tenant_id = %s AND i.id = %s
            FOR UPDATE OF i
            """,
            (business_id, instance_id),
        )
        if inst is None:
            raise HTTPException(status_code=404, detail="Workflow instance not found.")
        if str(inst["status"]) != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail="Only instances awaiting human approval can receive a decision.",
            )

        nodes = list(inst["nodes_json"] or [])
        edges = list(inst["edges_json"] or [])
        trace = list(inst["trace_json"] or [])
        cur_node_id = str(inst["current_node_id"])
        cur_node = next((n for n in nodes if str(n.get("id")) == cur_node_id), None)
        cur_label = str(cur_node.get("label") or cur_node_id) if cur_node else cur_node_id
        now_iso = datetime.now(UTC).isoformat()

        trace.append(
            {
                "node_id": cur_node_id,
                "node_type": "human_approval",
                "label": cur_label,
                "outcome": f"human_{body.decision}d",
                "detail": (
                    f"{access.principal.actor} chose {body.decision.upper()}"
                    + (f": {_clean(body.comment)}" if body.comment.strip() else ".")
                ),
                "at": now_iso,
            }
        )

        if body.decision == "reject":
            next_status = "rejected"
            next_node_id = cur_node_id
            completed_at: datetime | None = datetime.now(UTC)
        else:
            outgoing = [e for e in edges if str(e.get("source_id")) == cur_node_id]
            next_edge = next(
                (e for e in outgoing if str(e.get("branch") or "default") in ("yes", "default")),
                outgoing[0] if outgoing else None,
            )
            if next_edge is None:
                next_status = "approved"
                next_node_id = cur_node_id
                completed_at = datetime.now(UTC)
            else:
                next_status, next_node_id, trace, _ = advance_bpmn_execution(
                    nodes=nodes,
                    edges=edges,
                    amount_cents=int(inst["amount_cents"]),
                    context=dict(inst.get("context_json") or {}),
                    start_node_id=str(next_edge["target_id"]),
                    existing_trace=trace,
                    dry_run=False,
                )
                completed_at = (
                    datetime.now(UTC) if next_status in ("approved", "rejected") else None
                )

        updated = await _fetch_one(
            access.conn,
            """
            UPDATE gba.bpmn_workflow_instances
            SET current_node_id = %s,
                status = %s,
                trace_json = %s,
                completed_at = %s,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *
            """,
            (
                next_node_id,
                next_status,
                Jsonb(trace),
                completed_at,
                business_id,
                instance_id,
            ),
        )
        assert updated is not None  # noqa: S101

        await access.conn.execute(
            """
            INSERT INTO gba.audit_events (
                tenant_id, actor, action, target_type, target_id, details, request_id
            )
            VALUES (
                %s, %s, 'bpmn.approval_decided', 'bpmn_workflow_instance', %s, %s,
                nullif(pg_catalog.current_setting('gba.request_id', true), '')
            )
            """,
            (
                business_id,
                access.principal.actor,
                str(instance_id),
                Jsonb(
                    {
                        "decision": body.decision,
                        "from_node": cur_node_id,
                        "next_status": next_status,
                    }
                ),
            ),
        )
        updated["workflow_code"] = inst["workflow_code"]
        updated["workflow_name"] = inst["workflow_name"]
        updated["nodes_json"] = nodes
        return _row_to_instance_view(updated)
