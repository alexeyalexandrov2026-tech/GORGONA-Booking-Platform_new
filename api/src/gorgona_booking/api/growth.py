"""HTTP routes for universal growth settings and smart waitlist (customer + management)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.holds import get_tenant_id
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.growth.service import (
    AssistantTone,
    GrowthSettingsRecord,
    LaunchReadinessRecord,
    PreferredWindow,
    UnitEconomicsRecord,
    WaitlistEntryRecord,
    WaitlistStatus,
    export_business_snapshot,
    get_growth_settings,
    get_launch_readiness,
    get_unit_economics,
    join_waitlist,
    list_waitlist,
    offer_waitlist_slot,
    update_waitlist_status,
    upsert_growth_settings,
)
from gorgona_booking.payments.stripe_service import StripeRuntimeConfig
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["growth"])
type HostTenant = Annotated[UUID, Depends(get_tenant_id)]


class GrowthSettingsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    tenant_id: UUID
    google_review_url: str | None
    reminder_hours_before: int
    review_delay_hours: int
    rebooking_days_after: int
    waitlist_auto_offer: bool
    ai_assistant_enabled: bool
    ai_assistant_tone: str
    updated_at: datetime | None


class GrowthSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    google_review_url: str | None = Field(default=None, max_length=500)
    reminder_hours_before: int = Field(default=24, ge=1, le=168)
    review_delay_hours: int = Field(default=2, ge=0, le=168)
    rebooking_days_after: int = Field(default=28, ge=7, le=365)
    waitlist_auto_offer: bool = True
    ai_assistant_enabled: bool = True
    ai_assistant_tone: AssistantTone = "warm_professional"


class CustomerWaitlistRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    location_id: UUID
    variant_id: UUID
    preferred_resource_id: UUID | None = None
    preferred_day: date
    preferred_window: PreferredWindow = "any"
    customer_name: str = Field(min_length=1, max_length=160)
    contact_channel: Literal["email", "sms"]
    contact_value: str = Field(min_length=3, max_length=160)
    notes: str = Field(default="", max_length=400)


class WaitlistEntryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    location_id: UUID
    location_name: str
    variant_id: UUID
    variant_name: str
    service_name: str
    price_cents: int
    currency: str
    preferred_resource_id: UUID | None
    preferred_day: date
    preferred_window: str
    customer_name: str
    contact_channel: str
    contact_masked: str
    notes: str
    status: str
    offered_at: datetime | None
    offer_notification_id: UUID | None
    created_at: datetime


class OfferWaitlistSlotRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recipient: str = Field(min_length=3, max_length=160)
    starts_at: str = Field(min_length=4, max_length=80)
    business_name: str = Field(default="AMARKAL Business", min_length=1, max_length=160)
    action_url: str = Field(default="", max_length=500)


class UpdateWaitlistStatusRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: WaitlistStatus


class UnitEconomicsResponse(BaseModel):
    """Trailing-window unit economics in whole US cents (the platform is USD-only)."""

    model_config = ConfigDict(frozen=True)
    window_days: int
    currency: Literal["USD"]
    bookings_count_30d: int
    gross_revenue_cents: int
    average_ticket_cents: int
    material_cogs_cents: int
    net_margin_cents: int
    margin_percent: float


def _to_settings_response(rec: GrowthSettingsRecord) -> GrowthSettingsResponse:
    return GrowthSettingsResponse(
        tenant_id=rec.tenant_id,
        google_review_url=rec.google_review_url,
        reminder_hours_before=rec.reminder_hours_before,
        review_delay_hours=rec.review_delay_hours,
        rebooking_days_after=rec.rebooking_days_after,
        waitlist_auto_offer=rec.waitlist_auto_offer,
        ai_assistant_enabled=rec.ai_assistant_enabled,
        ai_assistant_tone=rec.ai_assistant_tone,
        updated_at=rec.updated_at,
    )


def _to_waitlist_response(rec: WaitlistEntryRecord) -> WaitlistEntryResponse:
    return WaitlistEntryResponse(
        id=rec.id,
        location_id=rec.location_id,
        location_name=rec.location_name,
        variant_id=rec.variant_id,
        variant_name=rec.variant_name,
        service_name=rec.service_name,
        price_cents=rec.price_cents,
        currency=rec.currency,
        preferred_resource_id=rec.preferred_resource_id,
        preferred_day=rec.preferred_day,
        preferred_window=rec.preferred_window,
        customer_name=rec.customer_name,
        contact_channel=rec.contact_channel,
        contact_masked=rec.contact_masked,
        notes=rec.notes,
        status=rec.status,
        offered_at=rec.offered_at,
        offer_notification_id=rec.offer_notification_id,
        created_at=rec.created_at,
    )


def _to_unit_economics_response(rec: UnitEconomicsRecord) -> UnitEconomicsResponse:
    return UnitEconomicsResponse(
        window_days=rec.window_days,
        currency=rec.currency,
        bookings_count_30d=rec.bookings_count_30d,
        gross_revenue_cents=rec.gross_revenue_cents,
        average_ticket_cents=rec.average_ticket_cents,
        material_cogs_cents=rec.material_cogs_cents,
        net_margin_cents=rec.net_margin_cents,
        margin_percent=rec.margin_percent,
    )


@router.post(
    "/v1/customer/waitlist",
    response_model=WaitlistEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_customer_waitlist(
    body: CustomerWaitlistRequest,
    request: Request,
    response: Response,
    tenant_id: HostTenant,
) -> WaitlistEntryResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        async with tenant_transaction(runtime_pool(request), tenant_id) as conn:
            rec = await join_waitlist(
                conn,
                tenant_id=tenant_id,
                location_id=body.location_id,
                variant_id=body.variant_id,
                preferred_resource_id=body.preferred_resource_id,
                preferred_day=body.preferred_day,
                preferred_window=body.preferred_window,
                customer_name=body.customer_name,
                contact_channel=body.contact_channel,
                contact_value=body.contact_value,
                notes=body.notes,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_waitlist_response(rec)


@router.get("/v1/salons/{salon_id}/growth/settings", response_model=GrowthSettingsResponse)
@router.get("/v1/businesses/{salon_id}/growth/settings", response_model=GrowthSettingsResponse)
async def get_business_growth_settings(
    salon_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> GrowthSettingsResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rec = await get_growth_settings(session.conn, tenant_id=salon_id)
    return _to_settings_response(rec)


@router.put("/v1/salons/{salon_id}/growth/settings", response_model=GrowthSettingsResponse)
@router.put("/v1/businesses/{salon_id}/growth/settings", response_model=GrowthSettingsResponse)
async def put_business_growth_settings(
    salon_id: UUID,
    body: GrowthSettingsUpdateRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> GrowthSettingsResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            salon_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec = await upsert_growth_settings(
                session.conn,
                tenant_id=salon_id,
                google_review_url=body.google_review_url,
                reminder_hours_before=body.reminder_hours_before,
                review_delay_hours=body.review_delay_hours,
                rebooking_days_after=body.rebooking_days_after,
                waitlist_auto_offer=body.waitlist_auto_offer,
                ai_assistant_enabled=body.ai_assistant_enabled,
                ai_assistant_tone=body.ai_assistant_tone,
                updated_by_user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_settings_response(rec)


@router.get("/v1/salons/{salon_id}/growth/unit-economics", response_model=UnitEconomicsResponse)
@router.get("/v1/businesses/{salon_id}/growth/unit-economics", response_model=UnitEconomicsResponse)
async def get_business_unit_economics(
    salon_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> UnitEconomicsResponse:
    # Material cost comes from stock valuations, whose amounts only company-wide members with
    # finance access may see (the stock API gates the same money at FINANCE_READ).
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        rec = await get_unit_economics(session.conn, tenant_id=salon_id)
    return _to_unit_economics_response(rec)


@router.get("/v1/salons/{salon_id}/growth/waitlist", response_model=list[WaitlistEntryResponse])
@router.get("/v1/businesses/{salon_id}/growth/waitlist", response_model=list[WaitlistEntryResponse])
async def get_business_waitlist(
    salon_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[WaitlistEntryResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_waitlist(
            session.conn, tenant_id=salon_id, status_filter=status_filter, limit=limit
        )
    return [_to_waitlist_response(r) for r in rows]


@router.post(
    "/v1/salons/{salon_id}/growth/waitlist/{entry_id}/offer",
    response_model=WaitlistEntryResponse,
)
@router.post(
    "/v1/businesses/{salon_id}/growth/waitlist/{entry_id}/offer",
    response_model=WaitlistEntryResponse,
)
async def post_offer_waitlist_slot(
    salon_id: UUID,
    entry_id: UUID,
    body: OfferWaitlistSlotRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> WaitlistEntryResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            salon_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec, _ = await offer_waitlist_slot(
                session.conn,
                tenant_id=salon_id,
                entry_id=entry_id,
                recipient=body.recipient,
                starts_at=body.starts_at,
                business_name=body.business_name,
                action_url=body.action_url,
                created_by_user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_waitlist_response(rec)


class ReadinessStepResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    key: str
    title: str
    detail: str
    completed: bool
    action_path: str
    action_label: str


class LaunchReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    business_name: str
    slug: str
    booking_state: str
    score_percent: int
    completed_steps: int
    total_steps: int
    stripe_live_ready: bool
    trailing_30d_volume_cents: int
    commission_saved_vs_5pct_cents: int
    steps: list[ReadinessStepResponse]


def _to_readiness_response(rec: LaunchReadinessRecord) -> LaunchReadinessResponse:
    return LaunchReadinessResponse(
        business_name=rec.business_name,
        slug=rec.slug,
        booking_state=rec.booking_state,
        score_percent=rec.score_percent,
        completed_steps=rec.completed_steps,
        total_steps=rec.total_steps,
        stripe_live_ready=rec.stripe_live_ready,
        trailing_30d_volume_cents=rec.trailing_30d_volume_cents,
        commission_saved_vs_5pct_cents=rec.commission_saved_vs_5pct_cents,
        steps=[
            ReadinessStepResponse(
                key=s.key,
                title=s.title,
                detail=s.detail,
                completed=s.completed,
                action_path=s.action_path,
                action_label=s.action_label,
            )
            for s in rec.steps
        ],
    )


@router.get("/v1/salons/{salon_id}/launch-readiness", response_model=LaunchReadinessResponse)
@router.get("/v1/businesses/{salon_id}/launch-readiness", response_model=LaunchReadinessResponse)
async def get_business_launch_readiness(
    salon_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> LaunchReadinessResponse:
    stripe_cfg = StripeRuntimeConfig.from_env()
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rec = await get_launch_readiness(
            session.conn,
            tenant_id=salon_id,
            stripe_configured=stripe_cfg.configured,
            stripe_livemode=stripe_cfg.livemode,
        )
    return _to_readiness_response(rec)


@router.get("/v1/salons/{salon_id}/export/snapshot")
@router.get("/v1/businesses/{salon_id}/export/snapshot")
async def get_business_portable_snapshot(
    salon_id: UUID,
    request: Request,
    response: Response,
    principal: CurrentPrincipal,
) -> dict[str, Any]:
    """Zero-lock-in portable JSON export of the tenant's business data."""
    response.headers["Cache-Control"] = "private, no-store"
    stripe_cfg = StripeRuntimeConfig.from_env()
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        return await export_business_snapshot(
            session.conn,
            tenant_id=salon_id,
            stripe_configured=stripe_cfg.configured,
            stripe_livemode=stripe_cfg.livemode,
        )


@router.post(
    "/v1/salons/{salon_id}/growth/waitlist/{entry_id}/status",
    response_model=WaitlistEntryResponse,
)
@router.post(
    "/v1/businesses/{salon_id}/growth/waitlist/{entry_id}/status",
    response_model=WaitlistEntryResponse,
)
async def post_update_waitlist_status(
    salon_id: UUID,
    entry_id: UUID,
    body: UpdateWaitlistStatusRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> WaitlistEntryResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            salon_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec = await update_waitlist_status(
                session.conn,
                tenant_id=salon_id,
                entry_id=entry_id,
                new_status=body.status,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_waitlist_response(rec)
