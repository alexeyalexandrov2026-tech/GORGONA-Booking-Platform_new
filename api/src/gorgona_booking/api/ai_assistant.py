"""HTTP routes for the tenant-isolated Customer AI Assistant and Owner AI Business Copilot."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.ai_assistant.actions import (
    ActionKind,
    build_action_proposals,
    execute_governed_action,
)
from gorgona_booking.ai_assistant.evidence_bridge import emit_evidence_nonblocking
from gorgona_booking.ai_assistant.service import (
    ask_customer_assistant,
    gather_owner_copilot_context,
    synthesize_owner_copilot,
)
from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.holds import get_tenant_id
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.payments.stripe_service import StripePaymentError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["ai-assistant"])
type HostTenant = Annotated[UUID, Depends(get_tenant_id)]


class CustomerAssistantRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    message: str = Field(min_length=2, max_length=500)
    location_id: UUID | None = None
    preferred_day: date | None = None


class RecommendedSlotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    location_id: UUID
    location_name: str
    variant_id: UUID
    service_name: str
    variant_name: str
    resource_id: UUID
    resource_name: str
    day: date
    start_at: datetime
    end_at: datetime
    timezone: str
    price_cents: int
    currency: str
    duration_minutes: int


class CustomerAssistantResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: Literal[1] = 1
    engine: Literal["cloudflare", "gemini", "grounded"]
    business_name: str
    reply: str
    recommended_slots: list[RecommendedSlotResponse]
    waitlist_suggested: bool
    cancellation_summary: str


class OwnerCopilotRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    question: str | None = Field(default=None, max_length=500)


class CopilotInsightResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    priority: Literal["high", "medium", "low"]
    category: str
    title: str
    detail: str
    action_path: str


class ActionProposalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    kind: ActionKind
    title: str
    description: str
    impact_summary: str
    requires_permission: str
    params: dict[str, Any]


class ExecuteCopilotActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: ActionKind
    params: dict[str, Any] = Field(default_factory=dict)


class ExecuteCopilotActionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: ActionKind
    executed: bool
    summary: str
    result: dict[str, Any]


class OwnerCopilotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: Literal[1] = 1
    engine: Literal["cloudflare", "gemini", "grounded"]
    business_name: str
    reply: str
    metrics: dict[str, Any]
    insights: list[CopilotInsightResponse]
    action_proposals: list[ActionProposalResponse] = Field(default_factory=list)


@router.post("/v1/customer/assistant", response_model=CustomerAssistantResponse)
async def post_customer_assistant(
    body: CustomerAssistantRequest,
    request: Request,
    response: Response,
    tenant_id: HostTenant,
) -> CustomerAssistantResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        async with tenant_transaction(runtime_pool(request), tenant_id) as conn:
            res = await ask_customer_assistant(
                conn,
                tenant_id=tenant_id,
                message=body.message,
                location_id=body.location_id,
                preferred_day=body.preferred_day,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return CustomerAssistantResponse(
        engine=res.engine,
        business_name=res.business_name,
        reply=res.reply,
        recommended_slots=[
            RecommendedSlotResponse(
                location_id=s.location_id,
                location_name=s.location_name,
                variant_id=s.variant_id,
                service_name=s.service_name,
                variant_name=s.variant_name,
                resource_id=s.resource_id,
                resource_name=s.resource_name,
                day=s.day,
                start_at=s.start_at,
                end_at=s.end_at,
                timezone=s.timezone,
                price_cents=s.price_cents,
                currency=s.currency,
                duration_minutes=s.duration_minutes,
            )
            for s in res.recommended_slots
        ],
        waitlist_suggested=res.waitlist_suggested,
        cancellation_summary=res.cancellation_summary,
    )


@router.post("/v1/salons/{salon_id}/copilot", response_model=OwnerCopilotResponse)
@router.post("/v1/businesses/{salon_id}/copilot", response_model=OwnerCopilotResponse)
async def post_owner_copilot(
    salon_id: UUID,
    body: OwnerCopilotRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> OwnerCopilotResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        ctx = await gather_owner_copilot_context(
            session.conn,
            tenant_id=salon_id,
        )
    res = await synthesize_owner_copilot(ctx, question=body.question)
    proposals = build_action_proposals(ctx)
    await emit_evidence_nonblocking(
        tenant_id=salon_id,
        kind="owner_copilot_query",
        summary=body.question or "executive_brief",
        metadata={"engine": res.engine, "insights_count": len(res.insights)},
    )
    return OwnerCopilotResponse(
        engine=res.engine,
        business_name=res.business_name,
        reply=res.reply,
        metrics=res.metrics,
        insights=[
            CopilotInsightResponse(
                priority=i.priority,
                category=i.category,
                title=i.title,
                detail=i.detail,
                action_path=i.action_path,
            )
            for i in res.insights
        ],
        action_proposals=[
            ActionProposalResponse(
                id=p.id,
                kind=p.kind,
                title=p.title,
                description=p.description,
                impact_summary=p.impact_summary,
                requires_permission=p.requires_permission,
                params=p.params,
            )
            for p in proposals
        ],
    )


def _return_base_url(request: Request) -> str:
    host = request.headers.get("host") or request.url.netloc
    hostname = host.split(":", 1)[0].lower()
    raw_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    scheme = raw_scheme if hostname in ("127.0.0.1", "localhost") else "https"
    return f"{scheme}://{host}"


@router.post(
    "/v1/salons/{salon_id}/copilot/execute-action",
    response_model=ExecuteCopilotActionResponse,
)
@router.post(
    "/v1/businesses/{salon_id}/copilot/execute-action",
    response_model=ExecuteCopilotActionResponse,
)
async def post_execute_copilot_action(
    salon_id: UUID,
    body: ExecuteCopilotActionRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> ExecuteCopilotActionResponse:
    """Execute a human-approved AI Copilot action proposal under FORCE RLS."""
    required_perm = (
        Permission.FINANCE_MANAGE
        if body.kind == "create_stripe_payment_link"
        else Permission.BUSINESS_MANAGE
    )
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            salon_id,
            required_perm,
            request_id=get_request_id(request),
        ) as session:
            outcome = await execute_governed_action(
                session.conn,
                tenant_id=salon_id,
                user_id=principal.user_id,
                kind=body.kind,
                params=body.params,
                return_base_url=_return_base_url(request),
            )
    except StripePaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    await emit_evidence_nonblocking(
        tenant_id=salon_id,
        kind="copilot_action_executed",
        summary=outcome.summary,
        metadata={"action_kind": outcome.kind, "executed": outcome.executed},
    )
    return ExecuteCopilotActionResponse(
        kind=outcome.kind,
        executed=outcome.executed,
        summary=outcome.summary,
        result=outcome.result,
    )
