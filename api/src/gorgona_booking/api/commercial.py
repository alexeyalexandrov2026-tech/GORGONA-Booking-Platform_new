"""HTTP routes for AMARKAL v2.10.0 Deal-to-Cash B2B Engine:
CPQ Commercial Quotes, Purchase Orders & 3-Way Match, Approval Policies,
1-click Quote-to-Stripe Payment Link, and External B2B Client/Vendor Portal.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid7

from fastapi import APIRouter, HTTPException, Request, Response, status
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import commercial as service
from gorgona_booking.business import recurring_aging as ra_service
from gorgona_booking.business.commercial import (
    ApprovalPolicyView,
    CommercialError,
    CommercialSummaryView,
    CreatePurchaseOrderRequest,
    CreateQuoteRequest,
    MatchVendorBillRequest,
    PolicyEntityKind,
    PortalPublicDocument,
    PortalRespondRequest,
    PortalShareResponse,
    PurchaseOrderView,
    QuoteView,
    RecordReceiptRequest,
    UpdateApprovalPolicyRequest,
)
from gorgona_booking.business.recurring_aging import (
    AgingReportView,
    CreateRecurringScheduleRequest,
    RecurringRunResult,
    RecurringScheduleView,
    render_cpa_aging_csv,
)
from gorgona_booking.connectors.dispatcher import dispatch_business_event_nonblocking
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.notifications.service import dispatch_notification, enqueue_notification
from gorgona_booking.payments.stripe_service import (
    StripePaymentError,
    StripeRuntimeConfig,
    create_stripe_checkout_session,
    load_tenant_stripe_account_id,
)
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["commercial"])


def _return_base(request: Request) -> str:
    host = request.headers.get("host") or request.url.netloc
    hostname = host.split(":", 1)[0].lower()
    raw_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    scheme = raw_scheme if hostname in ("127.0.0.1", "localhost") else "https"
    return f"{scheme}://{host}"


def _env_name(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    return settings.environment if settings is not None else "local"


class ConvertQuotePaymentResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    quote: QuoteView
    payment_session_id: UUID
    checkout_url: str


@router.get(
    "/v1/businesses/{business_id}/commercial/summary",
    response_model=CommercialSummaryView,
)
async def get_commercial_summary(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> CommercialSummaryView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        return await service.get_commercial_summary(session.conn, tenant_id=business_id)


@router.get(
    "/v1/businesses/{business_id}/commercial/policies",
    response_model=list[ApprovalPolicyView],
)
async def get_approval_policies(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[ApprovalPolicyView]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        return await service.list_approval_policies(session.conn, tenant_id=business_id)


@router.put(
    "/v1/businesses/{business_id}/commercial/policies/{entity_kind}",
    response_model=ApprovalPolicyView,
)
async def put_approval_policy(
    business_id: UUID,
    entity_kind: PolicyEntityKind,
    body: UpdateApprovalPolicyRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> ApprovalPolicyView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        return await service.upsert_approval_policy(
            session.conn,
            tenant_id=business_id,
            entity_kind=entity_kind,
            body=body,
            user_id=principal.user_id,
        )


@router.get(
    "/v1/businesses/{business_id}/commercial/quotes",
    response_model=list[QuoteView],
)
async def get_commercial_quotes(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: int = 50,
) -> list[QuoteView]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        return await service.list_quotes(session.conn, tenant_id=business_id, limit=limit)


@router.post(
    "/v1/businesses/{business_id}/commercial/quotes",
    response_model=QuoteView,
    status_code=status.HTTP_201_CREATED,
)
async def post_commercial_quote(
    business_id: UUID,
    body: CreateQuoteRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> QuoteView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        quote = await service.create_quote(
            session.conn, tenant_id=business_id, body=body, user_id=principal.user_id
        )
    await dispatch_business_event_nonblocking(
        runtime_pool(request),
        tenant_id=business_id,
        event_type="quote.created",
        data={
            "quote_id": str(quote.id),
            "quote_number": quote.quote_number,
            "counterparty_name": quote.counterparty_name,
            "total_cents": quote.total_cents,
            "status": quote.status,
        },
        environment=_env_name(request),
    )
    return quote


@router.post(
    "/v1/businesses/{business_id}/commercial/quotes/{quote_id}/approve",
    response_model=QuoteView,
)
async def post_approve_quote(
    business_id: UUID,
    quote_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> QuoteView:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            return await service.approve_quote(
                session.conn,
                tenant_id=business_id,
                quote_id=quote_id,
                user_id=principal.user_id,
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/v1/businesses/{business_id}/commercial/quotes/{quote_id}/share",
    response_model=PortalShareResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_share_quote_portal(
    business_id: UUID,
    quote_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> PortalShareResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            return await service.create_portal_share_link(
                session.conn,
                tenant_id=business_id,
                entity_kind="quote",
                entity_id=quote_id,
                base_url=_return_base(request),
                user_id=principal.user_id,
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/v1/businesses/{business_id}/commercial/quotes/{quote_id}/convert-payment",
    response_model=ConvertQuotePaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_convert_quote_to_payment(
    business_id: UUID,
    quote_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> ConvertQuotePaymentResponse:
    """Convert an approved or accepted quote into a live USD Stripe Checkout payment link."""
    cfg = StripeRuntimeConfig.from_env()
    if not cfg.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Stripe payments are not configured for this environment.",
        )

    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        async with session.conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT * FROM gba.commercial_quotes WHERE tenant_id = %s AND id = %s",
                (business_id, quote_id),
            )
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found.")
        quote = service._parse_quote_row(row)
        if quote.status not in ("approved", "sent", "accepted"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approve or accept this quote before creating a Stripe payment link.",
            )
        if quote.total_cents < 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quote total must be at least $0.50 USD to create a Stripe payment link.",
            )
        acct_id, _ = await load_tenant_stripe_account_id(session.conn, tenant_id=business_id)

    base = _return_base(request)
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            pay_rec = await create_stripe_checkout_session(
                session.conn,
                config=cfg,
                tenant_id=business_id,
                created_by_user_id=principal.user_id,
                amount_cents=quote.total_cents,
                description=f"{quote.quote_number}: {quote.title}"[:300],
                reference_kind="invoice",
                reference_id=quote.quote_number,
                customer_name=quote.counterparty_name,
                customer_email=quote.counterparty_email,
                success_url=f"{base}/commercial/?paid={quote.quote_number}",
                cancel_url=f"{base}/commercial/?cancelled={quote.quote_number}",
                allow_ach=True,
                connected_account_id=acct_id,
            )
            async with session.conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE gba.commercial_quotes
                    SET status = 'converted',
                        payment_session_id = %s,
                        converted_invoice_ref = %s,
                        updated_at = now()
                    WHERE tenant_id = %s AND id = %s
                    RETURNING *
                    """,
                    (pay_rec.id, quote.quote_number, business_id, quote_id),
                )
                updated_row = await cur.fetchone()
    except StripePaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if updated_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found.")
    return ConvertQuotePaymentResponse(
        quote=service._parse_quote_row(updated_row),
        payment_session_id=pay_rec.id,
        checkout_url=pay_rec.checkout_url,
    )


@router.get(
    "/v1/businesses/{business_id}/commercial/purchase-orders",
    response_model=list[PurchaseOrderView],
)
async def get_purchase_orders(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: int = 50,
) -> list[PurchaseOrderView]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        return await service.list_purchase_orders(session.conn, tenant_id=business_id, limit=limit)


@router.post(
    "/v1/businesses/{business_id}/commercial/purchase-orders",
    response_model=PurchaseOrderView,
    status_code=status.HTTP_201_CREATED,
)
async def post_purchase_order(
    business_id: UUID,
    body: CreatePurchaseOrderRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PurchaseOrderView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        return await service.create_purchase_order(
            session.conn, tenant_id=business_id, body=body, user_id=principal.user_id
        )


@router.post(
    "/v1/businesses/{business_id}/commercial/purchase-orders/{po_id}/approve",
    response_model=PurchaseOrderView,
)
async def post_approve_purchase_order(
    business_id: UUID,
    po_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> PurchaseOrderView:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            return await service.approve_purchase_order(
                session.conn,
                tenant_id=business_id,
                po_id=po_id,
                user_id=principal.user_id,
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/v1/businesses/{business_id}/commercial/purchase-orders/{po_id}/share",
    response_model=PortalShareResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_share_po_portal(
    business_id: UUID,
    po_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> PortalShareResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            share = await service.create_portal_share_link(
                session.conn,
                tenant_id=business_id,
                entity_kind="purchase_order",
                entity_id=po_id,
                base_url=_return_base(request),
                user_id=principal.user_id,
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    await dispatch_business_event_nonblocking(
        runtime_pool(request),
        tenant_id=business_id,
        event_type="purchase_order.issued",
        data={"po_id": str(po_id), "token_prefix": share.token_prefix},
        environment=_env_name(request),
    )
    return share


@router.post(
    "/v1/businesses/{business_id}/commercial/purchase-orders/{po_id}/receive",
    response_model=PurchaseOrderView,
)
async def post_receive_purchase_order(
    business_id: UUID,
    po_id: UUID,
    body: RecordReceiptRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PurchaseOrderView:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            return await service.record_po_receipt(
                session.conn, tenant_id=business_id, po_id=po_id, body=body
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/v1/businesses/{business_id}/commercial/purchase-orders/{po_id}/match-bill",
    response_model=PurchaseOrderView,
)
async def post_match_po_vendor_bill(
    business_id: UUID,
    po_id: UUID,
    body: MatchVendorBillRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PurchaseOrderView:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            po = await service.match_po_vendor_bill(
                session.conn, tenant_id=business_id, po_id=po_id, body=body
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    if po.three_way_match_status == "matched":
        await dispatch_business_event_nonblocking(
            runtime_pool(request),
            tenant_id=business_id,
            event_type="purchase_order.matched",
            data={
                "po_id": str(po.id),
                "po_number": po.po_number,
                "vendor_bill_number": po.vendor_bill_number,
                "total_cents": po.total_cents,
            },
            environment=_env_name(request),
        )
    return po


# ---------------------------------------------------------------------------
# v2.12.0: 1-Click Email Dispatch (SMTP/Resend), Recurring Billing & AR/AP Aging
# ---------------------------------------------------------------------------


class EmailPortalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recipient_email: str | None = Field(default=None, max_length=160)


class EmailDispatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    portal_url: str
    recipient_email: str
    delivery_status: str
    provider_name: str


@router.post(
    "/v1/businesses/{business_id}/commercial/quotes/{quote_id}/email",
    response_model=EmailDispatchResponse,
)
async def post_email_quote_portal(
    business_id: UUID,
    quote_id: UUID,
    body: EmailPortalRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> EmailDispatchResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            async with session.conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM gba.commercial_quotes WHERE tenant_id = %s AND id = %s",
                    (business_id, quote_id),
                )
                q_row = await cur.fetchone()
                if q_row is None:
                    raise HTTPException(status_code=404, detail="Quote not found.")
                await cur.execute(
                    "SELECT display_name FROM gba.tenants WHERE id = %s", (business_id,)
                )
                t_row = await cur.fetchone()
            biz_name = str(t_row["display_name"]) if t_row else "AMARKAL Business"
            quote = service._parse_quote_row(q_row)
            target_email = (body.recipient_email or quote.counterparty_email or "").strip()
            if not target_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Provide a client email address on the quote or request.",
                )
            share = await service.create_portal_share_link(
                session.conn,
                tenant_id=business_id,
                entity_kind="quote",
                entity_id=quote_id,
                base_url=_return_base(request),
                user_id=principal.user_id,
            )
            note = await enqueue_notification(
                session.conn,
                tenant_id=business_id,
                channel="email",
                template_code="commercial_quote_shared",
                recipient=target_email,
                variables={
                    "business_name": biz_name,
                    "reference": quote.quote_number,
                    "amount": f"${quote.total_cents / 100:,.2f} USD",
                    "action_url": share.portal_url,
                },
                idempotency_key=f"quote-email-{quote_id}-{uuid7().hex[:12]}",
                created_by_user_id=principal.user_id,
            )
            sent = await dispatch_notification(
                session.conn,
                tenant_id=business_id,
                notification_id=note.id,
                recipient=target_email,
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return EmailDispatchResponse(
        portal_url=share.portal_url,
        recipient_email=target_email,
        delivery_status=sent.status,
        provider_name=sent.provider_name,
    )


@router.post(
    "/v1/businesses/{business_id}/commercial/purchase-orders/{po_id}/email",
    response_model=EmailDispatchResponse,
)
async def post_email_po_portal(
    business_id: UUID,
    po_id: UUID,
    body: EmailPortalRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> EmailDispatchResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            async with session.conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM gba.purchase_orders WHERE tenant_id = %s AND id = %s",
                    (business_id, po_id),
                )
                p_row = await cur.fetchone()
                if p_row is None:
                    raise HTTPException(status_code=404, detail="Purchase order not found.")
                await cur.execute(
                    "SELECT display_name FROM gba.tenants WHERE id = %s", (business_id,)
                )
                t_row = await cur.fetchone()
            biz_name = str(t_row["display_name"]) if t_row else "AMARKAL Business"
            po = service._parse_po_row(p_row)
            target_email = (body.recipient_email or po.vendor_email or "").strip()
            if not target_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Provide a vendor email address on the purchase order or request.",
                )
            share = await service.create_portal_share_link(
                session.conn,
                tenant_id=business_id,
                entity_kind="purchase_order",
                entity_id=po_id,
                base_url=_return_base(request),
                user_id=principal.user_id,
            )
            note = await enqueue_notification(
                session.conn,
                tenant_id=business_id,
                channel="email",
                template_code="purchase_order_issued",
                recipient=target_email,
                variables={
                    "business_name": biz_name,
                    "reference": po.po_number,
                    "amount": f"${po.total_cents / 100:,.2f} USD",
                    "action_url": share.portal_url,
                },
                idempotency_key=f"po-email-{po_id}-{uuid7().hex[:12]}",
                created_by_user_id=principal.user_id,
            )
            sent = await dispatch_notification(
                session.conn,
                tenant_id=business_id,
                notification_id=note.id,
                recipient=target_email,
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return EmailDispatchResponse(
        portal_url=share.portal_url,
        recipient_email=target_email,
        delivery_status=sent.status,
        provider_name=sent.provider_name,
    )


@router.get(
    "/v1/businesses/{business_id}/commercial/recurring",
    response_model=list[RecurringScheduleView],
)
async def get_recurring_schedules(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: int = 50,
) -> list[RecurringScheduleView]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        return await ra_service.list_recurring_schedules(
            session.conn, tenant_id=business_id, limit=limit
        )


@router.post(
    "/v1/businesses/{business_id}/commercial/recurring",
    response_model=RecurringScheduleView,
    status_code=status.HTTP_201_CREATED,
)
async def post_recurring_schedule(
    business_id: UUID,
    body: CreateRecurringScheduleRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> RecurringScheduleView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        return await ra_service.create_recurring_schedule(
            session.conn, tenant_id=business_id, body=body, user_id=principal.user_id
        )


@router.post(
    "/v1/businesses/{business_id}/commercial/recurring/{schedule_id}/toggle",
    response_model=RecurringScheduleView,
)
async def post_toggle_recurring_schedule(
    business_id: UUID,
    schedule_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> RecurringScheduleView:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            return await ra_service.toggle_recurring_schedule(
                session.conn, tenant_id=business_id, schedule_id=schedule_id
            )
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/v1/businesses/{business_id}/commercial/recurring/{schedule_id}/run-now",
    response_model=RecurringRunResult,
)
async def post_run_recurring_schedule(
    business_id: UUID,
    schedule_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> RecurringRunResult:
    email_status: str | None = None
    portal_url: str | None = None
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.FINANCE_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            sched, quote = await ra_service.execute_recurring_cycle(
                session.conn,
                tenant_id=business_id,
                schedule_id=schedule_id,
                user_id=principal.user_id,
            )
            if sched.auto_email_client and sched.counterparty_email and quote.status == "approved":
                async with session.conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        "SELECT display_name FROM gba.tenants WHERE id = %s", (business_id,)
                    )
                    t_row = await cur.fetchone()
                biz_name = str(t_row["display_name"]) if t_row else "AMARKAL Business"
                share = await service.create_portal_share_link(
                    session.conn,
                    tenant_id=business_id,
                    entity_kind="quote",
                    entity_id=quote.id,
                    base_url=_return_base(request),
                    user_id=principal.user_id,
                )
                portal_url = share.portal_url
                note = await enqueue_notification(
                    session.conn,
                    tenant_id=business_id,
                    channel="email",
                    template_code="recurring_billing_notice",
                    recipient=sched.counterparty_email,
                    variables={
                        "business_name": biz_name,
                        "reference": quote.quote_number,
                        "amount": f"${quote.total_cents / 100:,.2f} USD",
                        "action_url": share.portal_url,
                    },
                    idempotency_key=f"rec-run-{schedule_id}-{sched.runs_count}",
                    created_by_user_id=principal.user_id,
                )
                sent = await dispatch_notification(
                    session.conn,
                    tenant_id=business_id,
                    notification_id=note.id,
                    recipient=sched.counterparty_email,
                )
                email_status = f"{sent.status} ({sent.provider_name})"
    except CommercialError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    return RecurringRunResult(
        schedule=sched,
        generated_quote=quote,
        email_status=email_status,
        portal_url=portal_url,
    )


@router.get(
    "/v1/businesses/{business_id}/commercial/aging",
    response_model=AgingReportView,
)
async def get_commercial_aging(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> AgingReportView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        return await ra_service.build_tenant_aging_report(session.conn, tenant_id=business_id)


@router.get("/v1/businesses/{business_id}/commercial/cpa-export.csv")
async def get_commercial_cpa_csv_export(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.FINANCE_READ,
        request_id=get_request_id(request),
    ) as session:
        report = await ra_service.build_tenant_aging_report(session.conn, tenant_id=business_id)
    csv_body = render_cpa_aging_csv(report.items)
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="amarkal-cpa-ar-ap-export.csv"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------------------
# Public Tokenized B2B Client & Vendor Portal (strict FORCE RLS, no login)
# ---------------------------------------------------------------------------


@router.get("/v1/portal/{raw_token}", response_model=PortalPublicDocument)
async def get_public_b2b_portal_document(
    raw_token: str,
    request: Request,
    response: Response,
) -> PortalPublicDocument:
    response.headers["Cache-Control"] = "no-store"
    if len(raw_token) < 16 or len(raw_token) > 128:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found.")
    pool = runtime_pool(request)
    async with pool.connection() as conn, conn.transaction():
        link = await service.resolve_portal_token(conn, raw_token=raw_token)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portal link is invalid, revoked, or expired.",
        )

    tenant_id = UUID(str(link["tenant_id"]))
    entity_kind: Literal["quote", "purchase_order"] = link["entity_kind"]
    entity_id = UUID(str(link["entity_id"]))

    async with (
        tenant_transaction(pool, tenant_id) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute(
            "UPDATE gba.b2b_portal_links SET last_viewed_at = now() "
            "WHERE tenant_id = %s AND id = %s",
            (tenant_id, link["id"]),
        )
        await cur.execute("SELECT display_name FROM gba.tenants WHERE id = %s", (tenant_id,))
        tenant_row = await cur.fetchone()
        biz_name = str(tenant_row["display_name"]) if tenant_row else "AMARKAL Business"

        if entity_kind == "quote":
            await cur.execute(
                "SELECT * FROM gba.commercial_quotes WHERE tenant_id = %s AND id = %s",
                (tenant_id, entity_id),
            )
            q_row = await cur.fetchone()
            if q_row is None:
                raise HTTPException(status_code=404, detail="Quote not found.")
            quote = service._parse_quote_row(q_row)
            checkout_url: str | None = None
            if quote.payment_session_id:
                await cur.execute(
                    "SELECT checkout_url FROM gba.payment_sessions "
                    "WHERE tenant_id = %s AND id = %s",
                    (tenant_id, quote.payment_session_id),
                )
                ps = await cur.fetchone()
                if ps:
                    checkout_url = str(ps["checkout_url"])
            return PortalPublicDocument(
                entity_kind="quote",
                business_name=biz_name,
                expires_at=link["expires_at"],
                responded_at=link["responded_at"],
                quote=quote,
                checkout_url=checkout_url,
            )

        await cur.execute(
            "SELECT * FROM gba.purchase_orders WHERE tenant_id = %s AND id = %s",
            (tenant_id, entity_id),
        )
        p_row = await cur.fetchone()
        if p_row is None:
            raise HTTPException(status_code=404, detail="Purchase order not found.")
        return PortalPublicDocument(
            entity_kind="purchase_order",
            business_name=biz_name,
            expires_at=link["expires_at"],
            responded_at=link["responded_at"],
            purchase_order=service._parse_po_row(p_row),
        )


@router.post("/v1/portal/{raw_token}/respond", response_model=PortalPublicDocument)
async def post_public_b2b_portal_respond(
    raw_token: str,
    body: PortalRespondRequest,
    request: Request,
    response: Response,
) -> PortalPublicDocument:
    response.headers["Cache-Control"] = "no-store"
    if len(raw_token) < 16 or len(raw_token) > 128:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found.")
    pool = runtime_pool(request)
    async with pool.connection() as conn, conn.transaction():
        link = await service.resolve_portal_token(conn, raw_token=raw_token)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portal link is invalid, revoked, or expired.",
        )

    tenant_id = UUID(str(link["tenant_id"]))
    entity_kind: Literal["quote", "purchase_order"] = link["entity_kind"]
    entity_id = UUID(str(link["entity_id"]))
    actor_name = body.actor_name.strip()

    event_type: str | None = None
    event_data: dict[str, object] = {}

    async with (
        tenant_transaction(pool, tenant_id) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        await cur.execute("SELECT display_name FROM gba.tenants WHERE id = %s", (tenant_id,))
        tenant_row = await cur.fetchone()
        biz_name = str(tenant_row["display_name"]) if tenant_row else "AMARKAL Business"

        if entity_kind == "quote":
            if body.action == "accept":
                await cur.execute(
                    """
                    UPDATE gba.commercial_quotes
                    SET status = 'accepted',
                        accepted_by_name = %s,
                        accepted_at = now(),
                        updated_at = now()
                    WHERE tenant_id = %s AND id = %s AND status IN ('approved', 'sent')
                    RETURNING *
                    """,
                    (actor_name, tenant_id, entity_id),
                )
                q_row = await cur.fetchone()
                if q_row is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This quote has already been responded to or closed.",
                    )
                event_type = "quote.accepted"
                event_data = {
                    "quote_id": str(entity_id),
                    "quote_number": str(q_row["quote_number"]),
                    "accepted_by_name": actor_name,
                    "total_cents": int(q_row["total_cents"]),
                }
            elif body.action == "decline":
                await cur.execute(
                    """
                    UPDATE gba.commercial_quotes
                    SET status = 'declined',
                        declined_reason = %s,
                        updated_at = now()
                    WHERE tenant_id = %s AND id = %s AND status IN ('approved', 'sent')
                    RETURNING *
                    """,
                    ((body.reason or "").strip() or None, tenant_id, entity_id),
                )
                q_row = await cur.fetchone()
                if q_row is None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This quote has already been responded to or closed.",
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Quotes only support 'accept' or 'decline'.",
                )

            await cur.execute(
                "UPDATE gba.b2b_portal_links SET responded_at = now() "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, link["id"]),
            )
            result = PortalPublicDocument(
                entity_kind="quote",
                business_name=biz_name,
                expires_at=link["expires_at"],
                responded_at=q_row["updated_at"],
                quote=service._parse_quote_row(q_row),
            )
        else:
            if body.action != "acknowledge":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Purchase orders support 'acknowledge' on the vendor portal.",
                )
            await cur.execute(
                """
                UPDATE gba.purchase_orders
                SET status = 'acknowledged',
                    vendor_acknowledged_by = %s,
                    vendor_acknowledged_at = now(),
                    updated_at = now()
                WHERE tenant_id = %s AND id = %s AND status IN ('approved', 'issued')
                RETURNING *
                """,
                (actor_name, tenant_id, entity_id),
            )
            p_row = await cur.fetchone()
            if p_row is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This purchase order has already been acknowledged or closed.",
                )
            await cur.execute(
                "UPDATE gba.b2b_portal_links SET responded_at = now() "
                "WHERE tenant_id = %s AND id = %s",
                (tenant_id, link["id"]),
            )
            result = PortalPublicDocument(
                entity_kind="purchase_order",
                business_name=biz_name,
                expires_at=link["expires_at"],
                responded_at=p_row["updated_at"],
                purchase_order=service._parse_po_row(p_row),
            )

    if event_type:
        await dispatch_business_event_nonblocking(
            pool,
            tenant_id=tenant_id,
            event_type=event_type,
            data=event_data,
            environment=_env_name(request),
        )
    return result
