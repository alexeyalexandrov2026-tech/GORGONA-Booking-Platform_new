"""HTTP routes for the tenant-isolated Customer AI Concierge and Owner AI Business Copilot."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.ai_concierge.service import ask_customer_concierge, ask_owner_copilot
from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.holds import get_tenant_id
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["ai-concierge"])
type HostTenant = Annotated[UUID, Depends(get_tenant_id)]


class CustomerConciergeRequest(BaseModel):
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


class CustomerConciergeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: Literal[1] = 1
    engine: Literal["gemini", "grounded"]
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


class OwnerCopilotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    version: Literal[1] = 1
    engine: Literal["gemini", "grounded"]
    business_name: str
    reply: str
    metrics: dict[str, Any]
    insights: list[CopilotInsightResponse]


@router.post("/v1/customer/concierge", response_model=CustomerConciergeResponse)
async def post_customer_concierge(
    body: CustomerConciergeRequest,
    request: Request,
    response: Response,
    tenant_id: HostTenant,
) -> CustomerConciergeResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        async with tenant_transaction(runtime_pool(request), tenant_id) as conn:
            res = await ask_customer_concierge(
                conn,
                tenant_id=tenant_id,
                message=body.message,
                location_id=body.location_id,
                preferred_day=body.preferred_day,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return CustomerConciergeResponse(
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
        res = await ask_owner_copilot(
            session.conn,
            tenant_id=salon_id,
            question=body.question,
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
    )
