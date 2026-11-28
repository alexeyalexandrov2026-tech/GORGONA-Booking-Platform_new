"""HTTP routes for AMARKAL v2.19.0 Omnichannel Unified Client Inbox & Virtual PBX."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.api.self_service import (
    enforce_sliding_window_rate_limit,
    extract_client_ip,
)
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.omnichannel_inbox import (
    CallDirection,
    CallDisposition,
    CallStatus,
    ChannelMode,
    ChannelType,
    DeliveryStatus,
    LinkedEntityKind,
    MessageChannelType,
    MessageDirection,
    OmnichannelCallLogView,
    OmnichannelChannelView,
    OmnichannelMessageView,
    OmnichannelThreadView,
    ThreadPriority,
    ThreadStatus,
    create_thread,
    ensure_and_list_channels,
    get_thread_messages,
    ingest_inbound_message,
    list_call_logs,
    list_threads,
    post_thread_message,
    record_call_log,
    resolve_channel_by_webhook_token,
    rotate_channel_webhook_token,
    update_thread_state,
    upsert_channel,
)
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["omnichannel-inbox"])

_INBOUND_WEBHOOK_HITS: dict[str, deque[float]] = {}


# ── Pydantic Models ──────────────────────────────────────────────────────────


class ChannelResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    channel_type: ChannelType
    display_name: str
    address_or_number: str
    mode: ChannelMode
    provider_label: str
    is_enabled: bool
    auto_greeting: str
    webhook_token_prefix: str | None = None
    created_at: datetime
    updated_at: datetime


class ChannelUpsertResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    channel: ChannelResponse
    webhook_token: str | None = None


class UpsertChannelRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    channel_type: ChannelType
    display_name: str = Field(min_length=2, max_length=120)
    address_or_number: str = Field(default="", max_length=160)
    mode: ChannelMode = "built_in"
    provider_label: str = Field(default="AMARKAL Built-In", max_length=120)
    is_enabled: bool = True
    auto_greeting: str = Field(default="", max_length=500)


class ThreadResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    contact_name: str
    contact_email: str | None = None
    contact_phone: str | None = None
    counterparty_id: UUID | None = None
    linked_entity_kind: LinkedEntityKind | None = None
    linked_entity_ref: str | None = None
    primary_channel: ChannelType
    subject: str
    status: ThreadStatus
    priority: ThreadPriority
    unread_count: int
    last_message_preview: str
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    thread_id: UUID
    channel_type: MessageChannelType
    direction: MessageDirection
    sender_name: str
    sender_address: str
    recipient_address: str
    subject: str
    body: str
    delivery_status: DeliveryStatus
    provider_message_id: str | None = None
    metadata: dict[str, Any]
    created_at: datetime


class ThreadCreatedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    thread: ThreadResponse
    initial_message: MessageResponse | None = None


class CreateThreadRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    contact_name: str = Field(min_length=1, max_length=160)
    contact_email: str | None = Field(default=None, max_length=160)
    contact_phone: str | None = Field(default=None, max_length=40)
    primary_channel: ChannelType = "email"
    subject: str = Field(default="", max_length=240)
    priority: ThreadPriority = "normal"
    linked_entity_kind: LinkedEntityKind | None = None
    linked_entity_ref: str | None = Field(default=None, max_length=80)
    initial_body: str | None = Field(default=None, max_length=8000)


class PostMessageRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    channel_type: MessageChannelType = "email"
    direction: MessageDirection = "outbound"
    subject: str = Field(default="", max_length=240)
    body: str = Field(min_length=1, max_length=8000)


class PostMessageResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    message: MessageResponse
    thread: ThreadResponse


class PatchThreadRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: ThreadStatus | None = None
    priority: ThreadPriority | None = None
    linked_entity_kind: LinkedEntityKind | None = None
    linked_entity_ref: str | None = Field(default=None, max_length=80)


class CallLogResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    thread_id: UUID | None = None
    direction: CallDirection
    caller_number: str
    callee_number: str
    contact_name: str
    call_status: CallStatus
    duration_seconds: int
    extension_or_queue: str
    recording_url: str | None = None
    transcript_summary: str
    disposition: CallDisposition
    started_at: datetime
    created_at: datetime


class RecordCallLogRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    thread_id: UUID | None = None
    direction: CallDirection = "outbound"
    caller_number: str = Field(default="", max_length=40)
    callee_number: str = Field(default="", max_length=40)
    contact_name: str = Field(min_length=1, max_length=160)
    call_status: CallStatus = "completed"
    duration_seconds: int = Field(default=0, ge=0, le=86400)
    extension_or_queue: str = Field(default="Main Desk · Ext 100", max_length=120)
    transcript_summary: str = Field(default="", max_length=4000)
    disposition: CallDisposition = "resolved"


class PublicInboundWebhookRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sender_name: str = Field(min_length=1, max_length=160)
    sender_email: str | None = Field(default=None, max_length=160)
    sender_phone: str | None = Field(default=None, max_length=40)
    subject: str = Field(default="", max_length=240)
    body: str = Field(min_length=1, max_length=8000)


# ── Serializers ──────────────────────────────────────────────────────────────


def _ch_resp(v: OmnichannelChannelView) -> ChannelResponse:
    return ChannelResponse(
        id=v.id,
        channel_type=v.channel_type,
        display_name=v.display_name,
        address_or_number=v.address_or_number,
        mode=v.mode,
        provider_label=v.provider_label,
        is_enabled=v.is_enabled,
        auto_greeting=v.auto_greeting,
        webhook_token_prefix=v.webhook_token_prefix,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _thread_resp(v: OmnichannelThreadView) -> ThreadResponse:
    return ThreadResponse(
        id=v.id,
        contact_name=v.contact_name,
        contact_email=v.contact_email,
        contact_phone=v.contact_phone,
        counterparty_id=v.counterparty_id,
        linked_entity_kind=v.linked_entity_kind,
        linked_entity_ref=v.linked_entity_ref,
        primary_channel=v.primary_channel,
        subject=v.subject,
        status=v.status,
        priority=v.priority,
        unread_count=v.unread_count,
        last_message_preview=v.last_message_preview,
        last_message_at=v.last_message_at,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


def _msg_resp(v: OmnichannelMessageView) -> MessageResponse:
    return MessageResponse(
        id=v.id,
        thread_id=v.thread_id,
        channel_type=v.channel_type,
        direction=v.direction,
        sender_name=v.sender_name,
        sender_address=v.sender_address,
        recipient_address=v.recipient_address,
        subject=v.subject,
        body=v.body,
        delivery_status=v.delivery_status,
        provider_message_id=v.provider_message_id,
        metadata=v.metadata,
        created_at=v.created_at,
    )


def _call_resp(v: OmnichannelCallLogView) -> CallLogResponse:
    return CallLogResponse(
        id=v.id,
        thread_id=v.thread_id,
        direction=v.direction,
        caller_number=v.caller_number,
        callee_number=v.callee_number,
        contact_name=v.contact_name,
        call_status=v.call_status,
        duration_seconds=v.duration_seconds,
        extension_or_queue=v.extension_or_queue,
        recording_url=v.recording_url,
        transcript_summary=v.transcript_summary,
        disposition=v.disposition,
        started_at=v.started_at,
        created_at=v.created_at,
    )


# ── Tenant Routes ────────────────────────────────────────────────────────────


@router.get(
    "/v1/businesses/{business_id}/inbox/channels",
    response_model=list[ChannelResponse],
)
async def get_inbox_channels(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[ChannelResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await ensure_and_list_channels(session.conn, tenant_id=business_id)
    return [_ch_resp(c) for c in items]


@router.put(
    "/v1/businesses/{business_id}/inbox/channels",
    response_model=ChannelUpsertResponse,
)
async def put_inbox_channel(
    business_id: UUID,
    body: UpsertChannelRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> ChannelUpsertResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        ch, tok = await upsert_channel(
            session.conn,
            tenant_id=business_id,
            channel_type=body.channel_type,
            display_name=body.display_name,
            address_or_number=body.address_or_number,
            mode=body.mode,
            provider_label=body.provider_label,
            is_enabled=body.is_enabled,
            auto_greeting=body.auto_greeting,
        )
    return ChannelUpsertResponse(channel=_ch_resp(ch), webhook_token=tok)


@router.post(
    "/v1/businesses/{business_id}/inbox/channels/{channel_type}/rotate-token",
    response_model=ChannelUpsertResponse,
)
async def post_rotate_channel_token(
    business_id: UUID,
    channel_type: ChannelType,
    principal: CurrentPrincipal,
    request: Request,
) -> ChannelUpsertResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            ch, tok = await rotate_channel_webhook_token(
                session.conn, tenant_id=business_id, channel_type=channel_type
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChannelUpsertResponse(channel=_ch_resp(ch), webhook_token=tok)


@router.get(
    "/v1/businesses/{business_id}/inbox/threads",
    response_model=list[ThreadResponse],
)
async def get_inbox_threads(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
    status_filter: Annotated[ThreadStatus | None, Query(alias="status")] = None,
    channel: Annotated[ChannelType | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
) -> list[ThreadResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        items = await list_threads(
            session.conn,
            tenant_id=business_id,
            status_filter=status_filter,
            channel_filter=channel,
            search=q,
        )
    return [_thread_resp(t) for t in items]


@router.post(
    "/v1/businesses/{business_id}/inbox/threads",
    response_model=ThreadCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_inbox_thread(
    business_id: UUID,
    body: CreateThreadRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> ThreadCreatedResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        thread, first_msg = await create_thread(
            session.conn,
            tenant_id=business_id,
            contact_name=body.contact_name,
            contact_email=body.contact_email,
            contact_phone=body.contact_phone,
            primary_channel=body.primary_channel,
            subject=body.subject,
            priority=body.priority,
            linked_entity_kind=body.linked_entity_kind,
            linked_entity_ref=body.linked_entity_ref,
            initial_body=body.initial_body,
            sender_name=principal.display_name or "AMARKAL Team",
            created_by_user_id=principal.user_id,
        )
    return ThreadCreatedResponse(
        thread=_thread_resp(thread),
        initial_message=_msg_resp(first_msg) if first_msg is not None else None,
    )


@router.get(
    "/v1/businesses/{business_id}/inbox/threads/{thread_id}/messages",
    response_model=list[MessageResponse],
)
async def get_inbox_thread_messages(
    business_id: UUID,
    thread_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[MessageResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        msgs = await get_thread_messages(
            session.conn, tenant_id=business_id, thread_id=thread_id, mark_read=True
        )
    return [_msg_resp(m) for m in msgs]


@router.post(
    "/v1/businesses/{business_id}/inbox/threads/{thread_id}/messages",
    response_model=PostMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_inbox_thread_message(
    business_id: UUID,
    thread_id: UUID,
    body: PostMessageRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> PostMessageResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            msg, thread = await post_thread_message(
                session.conn,
                tenant_id=business_id,
                thread_id=thread_id,
                channel_type=body.channel_type,
                direction=body.direction,
                sender_name=principal.display_name or "AMARKAL Team",
                subject=body.subject,
                body=body.body,
                created_by_user_id=principal.user_id,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PostMessageResponse(message=_msg_resp(msg), thread=_thread_resp(thread))


@router.patch(
    "/v1/businesses/{business_id}/inbox/threads/{thread_id}",
    response_model=ThreadResponse,
)
async def patch_inbox_thread(
    business_id: UUID,
    thread_id: UUID,
    body: PatchThreadRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> ThreadResponse:
    pool = runtime_pool(request)
    try:
        async with authorized_tenant(
            pool,
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            thread = await update_thread_state(
                session.conn,
                tenant_id=business_id,
                thread_id=thread_id,
                status=body.status,
                priority=body.priority,
                linked_entity_kind=body.linked_entity_kind,
                linked_entity_ref=body.linked_entity_ref,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _thread_resp(thread)


@router.get(
    "/v1/businesses/{business_id}/inbox/calls",
    response_model=list[CallLogResponse],
)
async def get_inbox_calls(
    business_id: UUID,
    principal: CurrentPrincipal,
    request: Request,
) -> list[CallLogResponse]:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        calls = await list_call_logs(session.conn, tenant_id=business_id)
    return [_call_resp(c) for c in calls]


@router.post(
    "/v1/businesses/{business_id}/inbox/calls",
    response_model=CallLogResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_inbox_call(
    business_id: UUID,
    body: RecordCallLogRequest,
    principal: CurrentPrincipal,
    request: Request,
) -> CallLogResponse:
    pool = runtime_pool(request)
    async with authorized_tenant(
        pool,
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        call = await record_call_log(
            session.conn,
            tenant_id=business_id,
            thread_id=body.thread_id,
            direction=body.direction,
            caller_number=body.caller_number,
            callee_number=body.callee_number,
            contact_name=body.contact_name,
            call_status=body.call_status,
            duration_seconds=body.duration_seconds,
            extension_or_queue=body.extension_or_queue,
            transcript_summary=body.transcript_summary,
            disposition=body.disposition,
            created_by_user_id=principal.user_id,
        )
    return _call_resp(call)


# ── Public Rate-Limited Inbound Omnichannel Webhook ──────────────────────────


@router.post(
    "/v1/public/inbox/inbound",
    response_model=PostMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_public_inbox_inbound(
    body: PublicInboundWebhookRequest,
    request: Request,
    inbox_token: Annotated[str | None, Header(alias="X-AMARKAL-Inbox-Token")] = None,
) -> PostMessageResponse:
    """Inbound Email/SMS/WhatsApp/Web-Chat/PBX webhook authenticated via X-AMARKAL-Inbox-Token."""
    client_ip = extract_client_ip(request)
    enforce_sliding_window_rate_limit(
        _INBOUND_WEBHOOK_HITS,
        key=f"inb:{client_ip}",
        window_seconds=60.0,
        max_requests=120,
        detail="Inbound inbox webhook rate limit exceeded. Please retry shortly.",
    )
    if not inbox_token or len(inbox_token.strip()) < 16:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-AMARKAL-Inbox-Token header.",
        )

    pool = runtime_pool(request)
    async with pool.connection() as conn, conn.transaction():
        resolved = await resolve_channel_by_webhook_token(conn, plaintext_token=inbox_token)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or disabled inbox webhook token.",
        )

    tenant_id, channel_type = resolved
    async with tenant_transaction(pool, tenant_id) as conn:
        thread, msg = await ingest_inbound_message(
            conn,
            tenant_id=tenant_id,
            channel_type=channel_type,
            sender_name=body.sender_name,
            sender_email=body.sender_email,
            sender_phone=body.sender_phone,
            subject=body.subject,
            body=body.body,
        )
    return PostMessageResponse(message=_msg_resp(msg), thread=_thread_resp(thread))
