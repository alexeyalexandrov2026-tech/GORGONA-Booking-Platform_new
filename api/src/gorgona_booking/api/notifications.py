"""Management HTTP endpoints for transactional Email/SMS notification readiness and outbox."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.notifications.service import (
    TEMPLATES,
    NotificationRecord,
    dispatch_notification,
    enqueue_notification,
    list_outbox,
)
from gorgona_booking.notifications.transports import resolve_notification_transports
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["notifications"])


class EnqueueNotificationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    channel: Literal["email", "sms"]
    template_code: str = Field(min_length=2, max_length=80)
    recipient: str = Field(min_length=3, max_length=160)
    variables: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=4, max_length=128)
    dispatch_now: bool = True


class DispatchNotificationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    recipient: str = Field(min_length=3, max_length=160)


class NotificationOutboxResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    channel: str
    template_code: str
    recipient_masked: str
    subject: str
    body_preview: str
    idempotency_key: str
    status: str
    attempt_count: int
    max_attempts: int
    provider_name: str
    provider_message_id: str | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


def _to_response(rec: NotificationRecord) -> NotificationOutboxResponse:
    return NotificationOutboxResponse(
        id=rec.id,
        channel=rec.channel,
        template_code=rec.template_code,
        recipient_masked=rec.recipient_masked,
        subject=rec.subject,
        body_preview=rec.body_preview,
        idempotency_key=rec.idempotency_key,
        status=rec.status,
        attempt_count=rec.attempt_count,
        max_attempts=rec.max_attempts,
        provider_name=rec.provider_name,
        provider_message_id=rec.provider_message_id,
        last_error=rec.last_error,
        created_at=rec.created_at,
        sent_at=rec.sent_at,
    )


@router.get("/v1/salons/{salon_id}/notifications/readiness")
@router.get("/v1/businesses/{salon_id}/notifications/readiness")
async def get_notification_readiness(
    salon_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> dict[str, object]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ):
        _, readiness = resolve_notification_transports()
        return {
            "salon_id": str(salon_id),
            "templates": sorted(TEMPLATES.keys()),
            "channels": readiness,
        }


@router.get(
    "/v1/salons/{salon_id}/notifications/outbox",
    response_model=list[NotificationOutboxResponse],
)
@router.get(
    "/v1/businesses/{salon_id}/notifications/outbox",
    response_model=list[NotificationOutboxResponse],
)
async def get_notification_outbox(
    salon_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: int = 50,
) -> list[NotificationOutboxResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        salon_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_outbox(session.conn, tenant_id=salon_id, limit=limit)
    return [_to_response(r) for r in rows]


@router.post(
    "/v1/salons/{salon_id}/notifications/enqueue",
    response_model=NotificationOutboxResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/businesses/{salon_id}/notifications/enqueue",
    response_model=NotificationOutboxResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_enqueue_notification(
    salon_id: UUID,
    body: EnqueueNotificationRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> NotificationOutboxResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            salon_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec = await enqueue_notification(
                session.conn,
                tenant_id=salon_id,
                channel=body.channel,
                template_code=body.template_code,
                recipient=body.recipient,
                variables=body.variables,
                idempotency_key=body.idempotency_key,
                created_by_user_id=principal.user_id,
            )
            if body.dispatch_now:
                rec = await dispatch_notification(
                    session.conn,
                    tenant_id=salon_id,
                    notification_id=rec.id,
                    recipient=body.recipient,
                )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_response(rec)


@router.post(
    "/v1/salons/{salon_id}/notifications/{notification_id}/dispatch",
    response_model=NotificationOutboxResponse,
)
@router.post(
    "/v1/businesses/{salon_id}/notifications/{notification_id}/dispatch",
    response_model=NotificationOutboxResponse,
)
async def post_dispatch_notification(
    salon_id: UUID,
    notification_id: UUID,
    body: DispatchNotificationRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> NotificationOutboxResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            salon_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            rec = await dispatch_notification(
                session.conn,
                tenant_id=salon_id,
                notification_id=notification_id,
                recipient=body.recipient,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_response(rec)
