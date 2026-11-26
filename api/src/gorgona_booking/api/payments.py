"""HTTP routes for Stripe US Live/Test Checkout, session sync, refunds, and webhooks."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.payments.stripe_service import (
    PaymentProvider,
    PaymentReferenceKind,
    PaymentSessionRecord,
    PaymentSessionStatus,
    StripePaymentError,
    StripeRuntimeConfig,
    apply_stripe_webhook_event,
    create_stripe_checkout_session,
    list_payment_sessions,
    refund_stripe_payment_session,
    sync_stripe_payment_session,
    verify_and_parse_stripe_webhook,
)
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["payments"])


class PaymentsConfigResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    stripe_configured: bool
    stripe_livemode: bool
    stripe_publishable_key: str | None
    webhook_configured: bool
    paypal_configured: bool
    currency: Literal["USD"]
    payment_methods: list[str]


class CreateCheckoutSessionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    amount_cents: int = Field(ge=50, le=99_999_999)
    description: str = Field(min_length=1, max_length=300)
    reference_kind: PaymentReferenceKind = "invoice"
    reference_id: str | None = Field(default=None, max_length=120)
    customer_name: str = Field(default="", max_length=160)
    customer_email: str | None = Field(default=None, max_length=160)
    allow_ach: bool = True
    connected_account_id: str | None = Field(default=None, max_length=80)
    success_url: str | None = Field(default=None, max_length=1000)
    cancel_url: str | None = Field(default=None, max_length=1000)


class RefundSessionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["duplicate", "fraudulent", "requested_by_customer"] | None = None


class PaymentSessionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    provider: PaymentProvider
    livemode: bool
    provider_session_id: str
    provider_payment_intent_id: str | None
    connected_account_id: str | None
    reference_kind: PaymentReferenceKind
    reference_id: str | None
    customer_name: str
    customer_email: str | None
    description: str
    amount_cents: int
    currency: Literal["USD"]
    status: PaymentSessionStatus
    checkout_url: str
    paid_at: datetime | None
    refunded_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StripeWebhookAckResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    received: bool
    event_type: str
    applied: bool


def _to_response(rec: PaymentSessionRecord) -> PaymentSessionResponse:
    return PaymentSessionResponse(
        id=rec.id,
        provider=rec.provider,
        livemode=rec.livemode,
        provider_session_id=rec.provider_session_id,
        provider_payment_intent_id=rec.provider_payment_intent_id,
        connected_account_id=rec.connected_account_id,
        reference_kind=rec.reference_kind,
        reference_id=rec.reference_id,
        customer_name=rec.customer_name,
        customer_email=rec.customer_email,
        description=rec.description,
        amount_cents=rec.amount_cents,
        currency=rec.currency,
        status=rec.status,
        checkout_url=rec.checkout_url,
        paid_at=rec.paid_at,
        refunded_at=rec.refunded_at,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _default_return_base(request: Request) -> str:
    host = request.headers.get("host") or request.url.netloc
    hostname = host.split(":", 1)[0].lower()
    raw_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    scheme = raw_scheme if hostname in ("127.0.0.1", "localhost") else "https"
    return f"{scheme}://{host}"


@router.get("/v1/payments/config", response_model=PaymentsConfigResponse)
async def get_payments_config(response: Response) -> PaymentsConfigResponse:
    response.headers["Cache-Control"] = "no-store"
    cfg = StripeRuntimeConfig.from_env()
    return PaymentsConfigResponse(
        stripe_configured=cfg.configured,
        stripe_livemode=cfg.livemode,
        stripe_publishable_key=cfg.publishable_key,
        webhook_configured=cfg.webhook_configured,
        paypal_configured=cfg.paypal_configured,
        currency="USD",
        payment_methods=["card", "us_bank_account", "apple_pay", "google_pay"],
    )


@router.get(
    "/v1/businesses/{business_id}/payments/sessions",
    response_model=list[PaymentSessionResponse],
)
async def get_business_payment_sessions(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: int = 50,
) -> list[PaymentSessionResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_payment_sessions(session.conn, tenant_id=business_id, limit=limit)
    return [_to_response(r) for r in rows]


@router.post(
    "/v1/businesses/{business_id}/payments/checkout-sessions",
    response_model=PaymentSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_business_checkout_session(
    business_id: UUID,
    body: CreateCheckoutSessionRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PaymentSessionResponse:
    cfg = StripeRuntimeConfig.from_env()
    base = _default_return_base(request)
    success_url = body.success_url or f"{base}/integrations/?payment=success"
    cancel_url = body.cancel_url or f"{base}/integrations/?payment=cancelled"
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec = await create_stripe_checkout_session(
                session.conn,
                config=cfg,
                tenant_id=business_id,
                amount_cents=body.amount_cents,
                description=body.description,
                reference_kind=body.reference_kind,
                reference_id=body.reference_id,
                customer_name=body.customer_name,
                customer_email=body.customer_email,
                success_url=success_url,
                cancel_url=cancel_url,
                allow_ach=body.allow_ach,
                connected_account_id=body.connected_account_id,
                created_by_user_id=principal.user_id,
            )
    except StripePaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _to_response(rec)


@router.post(
    "/v1/businesses/{business_id}/payments/sessions/{session_id}/sync",
    response_model=PaymentSessionResponse,
)
async def post_sync_business_payment_session(
    business_id: UUID,
    session_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> PaymentSessionResponse:
    cfg = StripeRuntimeConfig.from_env()
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec = await sync_stripe_payment_session(
                session.conn,
                config=cfg,
                tenant_id=business_id,
                session_record_id=session_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StripePaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _to_response(rec)


@router.post(
    "/v1/businesses/{business_id}/payments/sessions/{session_id}/refund",
    response_model=PaymentSessionResponse,
)
async def post_refund_business_payment_session(
    business_id: UUID,
    session_id: UUID,
    body: RefundSessionRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PaymentSessionResponse:
    cfg = StripeRuntimeConfig.from_env()
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec = await refund_stripe_payment_session(
                session.conn,
                config=cfg,
                tenant_id=business_id,
                session_record_id=session_id,
                reason=body.reason,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except StripePaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return _to_response(rec)


@router.post("/v1/webhooks/stripe", response_model=StripeWebhookAckResponse)
async def post_stripe_webhook(request: Request) -> StripeWebhookAckResponse:
    cfg = StripeRuntimeConfig.from_env()
    if not cfg.webhook_configured or not cfg.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe webhook secret is not configured.",
        )
    payload = await request.body()
    if len(payload) > 262_144:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Webhook payload exceeds maximum allowed size.",
        )
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = verify_and_parse_stripe_webhook(payload, sig_header, cfg.webhook_secret)
    except StripePaymentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    if event.tenant_id is None:
        return StripeWebhookAckResponse(received=True, event_type=event.event_type, applied=False)

    async with tenant_transaction(runtime_pool(request), event.tenant_id) as conn:
        applied = await apply_stripe_webhook_event(conn, event=event)
    return StripeWebhookAckResponse(received=True, event_type=event.event_type, applied=applied)
