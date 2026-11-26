"""HTTP routes for GORGONA App Hub (Connectors, Scoped API Keys, Signed Webhooks, Native MCP)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.ai_assistant.service import ask_owner_copilot
from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.connectors.service import (
    ALLOWED_SCOPES,
    ALLOWED_WEBHOOK_EVENTS,
    CONNECTOR_CATALOG,
    create_api_key,
    create_webhook,
    delete_connector_installation,
    delete_webhook,
    enqueue_webhook_test_delivery,
    list_api_keys,
    list_connector_installations,
    list_webhook_deliveries,
    list_webhooks,
    resolve_api_key,
    revoke_api_key,
    upsert_connector_installation,
)
from gorgona_booking.db.pool import set_tenant_context
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["connectors"])


class ConnectorCatalogEntryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    category: str
    summary: str
    auth_mode: str
    fields: list[str]
    us_highlight: str
    installed: bool
    status: str | None = None
    config_masked: dict[str, Any] = {}
    updated_at: datetime | None = None


class ConnectorInstallRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["installed", "paused"] = "installed"
    config: dict[str, str] = Field(default_factory=dict)


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["mcp:read", "catalog:read", "bookings:read"])


class ApiKeyItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    status: str
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class ApiKeyCreatedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: ApiKeyItemResponse
    secret_token: str


class WebhookCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    url: str = Field(min_length=12, max_length=500)
    description: str = Field(default="", max_length=240)
    events: list[str] = Field(default_factory=lambda: ["booking.created", "invoice.issued"])


class WebhookEndpointResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    url: str
    description: str
    events: list[str]
    signing_secret_prefix: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class WebhookCreatedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    endpoint: WebhookEndpointResponse
    signing_secret: str


class WebhookDeliveryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    endpoint_id: UUID
    event_type: str
    signature_header: str
    status: str
    http_status: int | None
    attempts: int
    last_error: str | None = None
    created_at: datetime
    delivered_at: datetime | None


class McpJsonRpcRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")
    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/v1/businesses/{business_id}/connectors/catalog",
    response_model=list[ConnectorCatalogEntryResponse],
)
@router.get(
    "/v1/salons/{business_id}/connectors/catalog",
    response_model=list[ConnectorCatalogEntryResponse],
)
async def get_connectors_catalog(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[ConnectorCatalogEntryResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        installed = await list_connector_installations(session.conn, tenant_id=business_id)
    by_id = {row["connector_id"]: row for row in installed}
    result: list[ConnectorCatalogEntryResponse] = []
    for spec in CONNECTOR_CATALOG:
        inst = by_id.get(spec.id)
        result.append(
            ConnectorCatalogEntryResponse(
                id=spec.id,
                name=spec.name,
                category=spec.category,
                summary=spec.summary,
                auth_mode=spec.auth_mode,
                fields=list(spec.fields),
                us_highlight=spec.us_highlight,
                installed=inst is not None,
                status=str(inst["status"]) if inst else None,
                config_masked=dict(inst["config_masked"]) if inst else {},
                updated_at=inst["updated_at"] if inst else None,
            )
        )
    return result


@router.put("/v1/businesses/{business_id}/connectors/{connector_id}")
@router.put("/v1/salons/{business_id}/connectors/{connector_id}")
async def put_connector_installation(
    business_id: UUID,
    connector_id: str,
    body: ConnectorInstallRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            return await upsert_connector_installation(
                session.conn,
                tenant_id=business_id,
                connector_id=connector_id,
                status=body.status,
                config=body.config,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete(
    "/v1/businesses/{business_id}/connectors/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/v1/salons/{business_id}/connectors/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_connector_installation(
    business_id: UUID,
    connector_id: str,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        await delete_connector_installation(
            session.conn, tenant_id=business_id, connector_id=connector_id
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/v1/businesses/{business_id}/connectors/api-keys",
    response_model=list[ApiKeyItemResponse],
)
async def get_business_api_keys(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[ApiKeyItemResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_api_keys(session.conn, tenant_id=business_id)
    return [ApiKeyItemResponse(**r) for r in rows]


@router.post(
    "/v1/businesses/{business_id}/connectors/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_business_api_key(
    business_id: UUID,
    body: ApiKeyCreateRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> ApiKeyCreatedResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            row, raw_secret = await create_api_key(
                session.conn,
                tenant_id=business_id,
                name=body.name,
                scopes=body.scopes,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return ApiKeyCreatedResponse(key=ApiKeyItemResponse(**row), secret_token=raw_secret)


@router.delete(
    "/v1/businesses/{business_id}/connectors/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_business_api_key(
    business_id: UUID,
    key_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        await revoke_api_key(session.conn, tenant_id=business_id, key_id=key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/v1/businesses/{business_id}/connectors/webhooks",
    response_model=list[WebhookEndpointResponse],
)
async def get_business_webhooks(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[WebhookEndpointResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_webhooks(session.conn, tenant_id=business_id)
    return [WebhookEndpointResponse(**r) for r in rows]


@router.post(
    "/v1/businesses/{business_id}/connectors/webhooks",
    response_model=WebhookCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_business_webhook(
    business_id: UUID,
    body: WebhookCreateRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> WebhookCreatedResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            row, secret = await create_webhook(
                session.conn,
                tenant_id=business_id,
                url=body.url,
                description=body.description,
                events=body.events,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return WebhookCreatedResponse(endpoint=WebhookEndpointResponse(**row), signing_secret=secret)


@router.delete(
    "/v1/businesses/{business_id}/connectors/webhooks/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_business_webhook(
    business_id: UUID,
    endpoint_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        await delete_webhook(session.conn, tenant_id=business_id, endpoint_id=endpoint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/v1/businesses/{business_id}/connectors/webhooks/{endpoint_id}/test",
    response_model=WebhookDeliveryResponse,
)
async def post_business_webhook_test(
    business_id: UUID,
    endpoint_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> WebhookDeliveryResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            row = await enqueue_webhook_test_delivery(
                session.conn, tenant_id=business_id, endpoint_id=endpoint_id
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return WebhookDeliveryResponse(**row)


@router.get(
    "/v1/businesses/{business_id}/connectors/webhooks/deliveries",
    response_model=list[WebhookDeliveryResponse],
)
async def get_business_webhook_deliveries(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[WebhookDeliveryResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_webhook_deliveries(session.conn, tenant_id=business_id)
    return [WebhookDeliveryResponse(**r) for r in rows]


@router.get("/v1/businesses/{business_id}/connectors/meta")
async def get_connector_meta(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ):
        pass
    return {
        "allowed_scopes": sorted(ALLOWED_SCOPES),
        "allowed_webhook_events": sorted(ALLOWED_WEBHOOK_EVENTS),
        "mcp_endpoint": "/v1/mcp",
    }


@router.post("/v1/mcp")
async def post_native_mcp(
    body: McpJsonRpcRequest,
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """GORGONA Native MCP Server (JSON-RPC 2.0) secured by Scoped API Keys & FORCE RLS."""
    response.headers["Cache-Control"] = "no-store"
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer gorg_live_* API key required",
        )
    raw_token = authorization.removeprefix("Bearer ").strip()

    async with runtime_pool(request).connection() as conn, conn.transaction():
        resolved = await resolve_api_key(conn, raw_token)
        if resolved is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API key",
            )
        key_id, tenant_id, scopes = resolved
        if "mcp:read" not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key lacks mcp:read scope",
            )
        await set_tenant_context(conn, tenant_id)
        await conn.execute(
            "UPDATE gba.api_keys SET last_used_at = now() WHERE tenant_id = %s AND id = %s",
            (tenant_id, key_id),
        )

        if body.method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": body.id,
                "result": {
                    "protocolVersion": "2025-03-26",
                    "serverInfo": {"name": "gorgona-business-os-mcp", "version": "2.0.0"},
                    "capabilities": {"tools": {}},
                },
            }

        if body.method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": body.id,
                "result": {
                    "tools": [
                        {
                            "name": "get_business_summary",
                            "description": (
                                "Return tenant business name, booking state, and active counts."
                            ),
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "list_services",
                            "description": (
                                "List published bookable services with USD prices and durations."
                            ),
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "ask_business_copilot",
                            "description": (
                                "Ask the read-only grounded GORGONA AI Business Copilot."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {"question": {"type": "string"}},
                            },
                        },
                    ]
                },
            }

        if body.method == "tools/call":
            tool_name = str(body.params.get("name") or "")
            args = body.params.get("arguments") or {}
            if tool_name == "get_business_summary":
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT id, slug, display_name, status, booking_state "
                        "FROM gba.tenants WHERE id = %s",
                        (tenant_id,),
                    )
                    trow = await cur.fetchone()
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": str(dict(trow)) if trow else "{}",
                            }
                        ],
                        "structuredContent": {
                            "business_id": str(tenant_id),
                            "slug": str(trow["slug"]) if trow else "",
                            "display_name": str(trow["display_name"]) if trow else "",
                            "booking_state": str(trow["booking_state"]) if trow else "",
                        },
                    },
                }
            if tool_name == "list_services":
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        SELECT s.code AS service_code, s.name AS service_name,
                               v.id AS variant_id, v.name AS variant_name,
                               v.price_cents, v.currency, v.booking_duration_minutes
                        FROM gba.service_variants v
                        JOIN gba.services s ON s.tenant_id = v.tenant_id AND s.id = v.service_id
                        WHERE v.tenant_id = %s AND v.status = 'published' AND v.is_bookable
                        ORDER BY s.name, v.name
                        LIMIT 50
                        """,
                        (tenant_id,),
                    )
                    items = [
                        {
                            "service_code": r["service_code"],
                            "service_name": r["service_name"],
                            "variant_id": str(r["variant_id"]),
                            "variant_name": r["variant_name"],
                            "price_cents": int(r["price_cents"]),
                            "currency": str(r["currency"]),
                            "duration_minutes": r["booking_duration_minutes"],
                        }
                        for r in await cur.fetchall()
                    ]
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {"type": "text", "text": f"Found {len(items)} bookable services."}
                        ],
                        "structuredContent": {"services": items},
                    },
                }
            if tool_name == "ask_business_copilot":
                question = str(args.get("question") or "")[:500]
                cp = await ask_owner_copilot(conn, tenant_id=tenant_id, question=question or None)
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [{"type": "text", "text": cp.reply}],
                        "structuredContent": {
                            "engine": cp.engine,
                            "business_name": cp.business_name,
                            "metrics": cp.metrics,
                        },
                    },
                }
            return {
                "jsonrpc": "2.0",
                "id": body.id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        return {
            "jsonrpc": "2.0",
            "id": body.id,
            "error": {"code": -32601, "message": f"Method not found: {body.method}"},
        }
