"""HTTP routes for GORGONA App Hub (Connectors, Scoped API Keys, Signed Webhooks, Native MCP)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.ai_assistant.service import (
    CopilotContext,
    gather_owner_copilot_context,
    synthesize_owner_copilot,
)
from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.api.search import search_business_records
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.connectors.dispatcher import dispatch_business_event
from gorgona_booking.connectors.service import (
    ALLOWED_SCOPES,
    ALLOWED_WEBHOOK_EVENTS,
    CONNECTOR_CATALOG,
    WebhookProbeOutcome,
    create_api_key,
    create_webhook,
    delete_connector_installation,
    delete_webhook,
    list_api_keys,
    list_connector_installations,
    list_webhook_deliveries,
    list_webhooks,
    prepare_webhook_test_delivery,
    record_webhook_test_delivery,
    resolve_api_key,
    revoke_api_key,
    send_webhook_http_probe,
    upsert_connector_installation,
)
from gorgona_booking.db.pool import set_tenant_context
from gorgona_booking.growth.service import (
    get_launch_readiness,
    get_unit_economics,
)
from gorgona_booking.payments.stripe_service import StripeRuntimeConfig, list_payment_sessions
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
            prepared = await prepare_webhook_test_delivery(
                session.conn, tenant_id=business_id, endpoint_id=endpoint_id
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    settings = getattr(request.app.state, "settings", None)
    if settings is not None and settings.environment in ("staging", "production"):
        outcome = await send_webhook_http_probe(prepared)
    else:
        outcome = WebhookProbeOutcome(
            status="queued",
            http_status=None,
            last_error="Outbound webhook HTTP delivery is disabled in local/test environment.",
        )

    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        row = await record_webhook_test_delivery(
            session.conn,
            tenant_id=business_id,
            endpoint_id=endpoint_id,
            prepared=prepared,
            outcome=outcome,
        )
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


class WebhookDispatchEventRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    event_type: str = Field(min_length=3, max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/.well-known/agent.json", include_in_schema=False)
async def get_a2a_agent_card(response: Response) -> dict[str, Any]:
    """Open A2A / Agentic Discovery Card for AMARKAL Business OS (zero unapproved writes)."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "schema_version": "1.0",
        "name": "AMARKAL Platform Business OS",
        "operator": "Alexey AAA Logistics LLC",
        "url": "https://www.amarkal-platform.com",
        "description": (
            "Multi-tenant US Business Operating System across 39 NAICS industries with "
            "PostgreSQL 18 FORCE RLS isolation, double-entry USD finance (FIN-03), "
            "and governed Human-in-the-Loop AI operations."
        ),
        "protocols": {
            "mcp": {
                "endpoint": "https://www.amarkal-platform.com/v1/mcp",
                "transport": "jsonrpc-2.0-http",
                "protocol_version": "2025-03-26",
                "authentication": "Bearer scoped API key (mcp:read)",
            }
        },
        "governance": {
            "tenant_isolation": "postgresql_force_rls",
            "human_in_the_loop": True,
            "zero_unapproved_writes": True,
            "platform_transaction_commission_bps": 0,
        },
        "capabilities": [
            "get_business_summary",
            "list_services",
            "ask_business_copilot",
            "get_unit_economics",
            "list_upcoming_bookings",
            "list_payment_sessions",
            "get_launch_readiness",
            "search_business_records",
            "draft_payment_proposal",
        ],
    }


@router.post(
    "/v1/businesses/{business_id}/connectors/webhooks/dispatch",
    response_model=list[WebhookDeliveryResponse],
)
async def post_dispatch_webhook_event(
    business_id: UUID,
    body: WebhookDispatchEventRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> list[WebhookDeliveryResponse]:
    """Trigger real outbound HMAC-signed webhook delivery to all subscribed active endpoints."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ):
        pass
    settings = getattr(request.app.state, "settings", None)
    env_name = settings.environment if settings is not None else "local"
    try:
        rows = await dispatch_business_event(
            runtime_pool(request),
            tenant_id=business_id,
            event_type=body.event_type,
            data=body.data,
            environment=env_name,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
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
    break_for_copilot = False
    copilot_ctx: CopilotContext | None = None
    copilot_question = ""

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
                    "serverInfo": {
                        "name": "gorgona-business-os-mcp",
                        "title": "AMARKAL Platform Business OS MCP",
                        "version": "2.1.0",
                    },
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
                                "Ask the read-only grounded AMARKAL AI Business Copilot."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {"question": {"type": "string"}},
                            },
                        },
                        {
                            "name": "get_unit_economics",
                            "description": (
                                "Return live trailing-30-day USD revenue, material COGS, "
                                "net margin, and average ticket."
                            ),
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "list_upcoming_bookings",
                            "description": (
                                "List confirmed upcoming bookings over the next 14 days with "
                                "USD values and masked contacts."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "limit": {"type": "integer", "minimum": 1, "maximum": 50}
                                },
                            },
                        },
                        {
                            "name": "list_payment_sessions",
                            "description": (
                                "List recent Stripe US payment checkout sessions and statuses."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "limit": {"type": "integer", "minimum": 1, "maximum": 50}
                                },
                            },
                        },
                        {
                            "name": "get_launch_readiness",
                            "description": (
                                "Return live 0-100% Go-Live operational readiness score, "
                                "milestones, and 0% commission savings."
                            ),
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "search_business_records",
                            "description": (
                                "Search tenant counterparties, documents, FIN-03 invoices, "
                                "catalog items, and Stripe payment sessions under FORCE RLS."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "required": ["query"],
                                "properties": {
                                    "query": {"type": "string", "minLength": 2, "maxLength": 120},
                                    "limit_per_kind": {
                                        "type": "integer",
                                        "minimum": 1,
                                        "maximum": 10,
                                    },
                                },
                            },
                        },
                        {
                            "name": "draft_payment_proposal",
                            "description": (
                                "Prepare a Human-in-the-Loop USD Stripe payment link proposal for "
                                "owner approval (performs zero unapproved writes)."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "required": ["amount_cents", "description"],
                                "properties": {
                                    "amount_cents": {
                                        "type": "integer",
                                        "minimum": 50,
                                        "maximum": 99999999,
                                    },
                                    "description": {"type": "string", "minLength": 2},
                                    "reference_id": {"type": "string"},
                                },
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
            if tool_name == "get_unit_economics":
                ue = await get_unit_economics(conn, tenant_id=tenant_id)
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"30d gross revenue ${ue.gross_revenue_cents / 100:,.2f}, "
                                    f"net margin ${ue.net_margin_cents / 100:,.2f} "
                                    f"({ue.margin_percent:.1f}%)."
                                ),
                            }
                        ],
                        "structuredContent": {
                            "window_days": ue.window_days,
                            "currency": ue.currency,
                            "bookings_count_30d": ue.bookings_count_30d,
                            "gross_revenue_cents": ue.gross_revenue_cents,
                            "material_cogs_cents": ue.material_cogs_cents,
                            "net_margin_cents": ue.net_margin_cents,
                            "margin_percent": ue.margin_percent,
                            "average_ticket_cents": ue.average_ticket_cents,
                        },
                    },
                }
            if tool_name == "list_upcoming_bookings":
                lim = max(1, min(int(args.get("limit") or 20), 50))
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        SELECT b.id, b.starts_at, b.ends_at, b.status,
                               b.total_cents, b.currency,
                               s.name AS service_name, r.display_name AS resource_name
                        FROM gba.bookings b
                        LEFT JOIN gba.service_variants v
                          ON v.tenant_id = b.tenant_id AND v.id = b.variant_id
                        LEFT JOIN gba.services s
                          ON s.tenant_id = v.tenant_id AND s.id = v.service_id
                        LEFT JOIN gba.resources r
                          ON r.tenant_id = b.tenant_id AND r.id = b.resource_id
                        WHERE b.tenant_id = %s
                          AND b.status = 'CONFIRMED'
                          AND b.starts_at >= now()
                          AND b.starts_at < now() + interval '14 days'
                        ORDER BY b.starts_at ASC
                        LIMIT %s
                        """,
                        (tenant_id, lim),
                    )
                    rows = [
                        {
                            "booking_id": str(r["id"]),
                            "starts_at": r["starts_at"].isoformat(),
                            "ends_at": r["ends_at"].isoformat(),
                            "status": str(r["status"]),
                            "total_cents": int(r["total_cents"]),
                            "currency": str(r["currency"]),
                            "service_name": str(r["service_name"] or ""),
                            "resource_name": str(r["resource_name"] or ""),
                        }
                        for r in await cur.fetchall()
                    ]
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Found {len(rows)} upcoming confirmed booking(s).",
                            }
                        ],
                        "structuredContent": {"bookings": rows},
                    },
                }
            if tool_name == "list_payment_sessions":
                lim = max(1, min(int(args.get("limit") or 20), 50))
                sessions = await list_payment_sessions(conn, tenant_id=tenant_id, limit=lim)
                items = [
                    {
                        "id": str(s.id),
                        "status": s.status,
                        "livemode": s.livemode,
                        "amount_cents": s.amount_cents,
                        "currency": s.currency,
                        "description": s.description,
                        "reference_kind": s.reference_kind,
                        "created_at": s.created_at.isoformat(),
                    }
                    for s in sessions
                ]
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Found {len(items)} Stripe payment session(s).",
                            }
                        ],
                        "structuredContent": {"sessions": items},
                    },
                }
            if tool_name == "get_launch_readiness":
                scfg = StripeRuntimeConfig.from_env()
                rd = await get_launch_readiness(
                    conn,
                    tenant_id=tenant_id,
                    stripe_configured=scfg.configured,
                    stripe_livemode=scfg.livemode,
                )
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"{rd.business_name} Go-Live readiness: {rd.score_percent}% "
                                    f"({rd.completed_steps}/{rd.total_steps} milestones)."
                                ),
                            }
                        ],
                        "structuredContent": {
                            "business_name": rd.business_name,
                            "score_percent": rd.score_percent,
                            "completed_steps": rd.completed_steps,
                            "total_steps": rd.total_steps,
                            "stripe_live_ready": rd.stripe_live_ready,
                            "commission_saved_vs_5pct_cents": rd.commission_saved_vs_5pct_cents,
                            "steps": [
                                {
                                    "key": st.key,
                                    "title": st.title,
                                    "completed": st.completed,
                                    "action_path": st.action_path,
                                }
                                for st in rd.steps
                            ],
                        },
                    },
                }
            if tool_name == "search_business_records":
                q_str = str(args.get("query") or "").strip()
                if len(q_str) < 2:
                    return {
                        "jsonrpc": "2.0",
                        "id": body.id,
                        "error": {
                            "code": -32602,
                            "message": "query must be at least 2 characters",
                        },
                    }
                lim_kind = max(1, min(int(args.get("limit_per_kind") or 5), 10))
                hits = await search_business_records(
                    conn, tenant_id=tenant_id, query=q_str, limit_per_kind=lim_kind
                )
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Found {len(hits)} matching record(s) for '{q_str}'.",
                            }
                        ],
                        "structuredContent": {
                            "query": q_str,
                            "hits": [h.model_dump() for h in hits],
                        },
                    },
                }
            if tool_name == "draft_payment_proposal":
                amt_cents = int(args.get("amount_cents") or 0)
                desc = str(args.get("description") or "").strip()[:300]
                ref_id = str(args.get("reference_id") or "").strip()[:120] or None
                if not (50 <= amt_cents <= 99_999_999) or len(desc) < 2:
                    return {
                        "jsonrpc": "2.0",
                        "id": body.id,
                        "error": {
                            "code": -32602,
                            "message": "Provide amount_cents (50..99999999) and description",
                        },
                    }
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Prepared Human-in-the-Loop payment proposal for "
                                    f"USD ${amt_cents / 100:,.2f} ({desc}). "
                                    "Requires explicit owner approval in AMARKAL App Hub "
                                    "(/integrations/) before any payment link is created."
                                ),
                            }
                        ],
                        "structuredContent": {
                            "status": "awaiting_human_approval",
                            "executed": False,
                            "approval_path": "/integrations/",
                            "proposal": {
                                "kind": "create_stripe_payment_link",
                                "amount_cents": amt_cents,
                                "currency": "USD",
                                "description": desc,
                                "reference_id": ref_id,
                                "platform_commission_bps": 0,
                            },
                        },
                    },
                }
            if tool_name == "ask_business_copilot":
                copilot_question = str(args.get("question") or "")[:500]
                copilot_ctx = await gather_owner_copilot_context(conn, tenant_id=tenant_id)
                # Break out of DB transaction before external Cloudflare/Gemini call
                break_for_copilot = True
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": body.id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
                }
        else:
            return {
                "jsonrpc": "2.0",
                "id": body.id,
                "error": {"code": -32601, "message": f"Method not found: {body.method}"},
            }

    if break_for_copilot and copilot_ctx is not None:
        cp = await synthesize_owner_copilot(copilot_ctx, question=copilot_question or None)
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
        "error": {"code": -32601, "message": f"Method not found: {body.method}"},
    }
