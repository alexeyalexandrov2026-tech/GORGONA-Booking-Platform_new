"""AMARKAL v2.19.0: Omnichannel Unified Client Inbox — Built-in Email Client,
Virtual PBX / Cloud Telephony Call & Voicemail Logs, and Messenger Aggregator
(SMS, WhatsApp, Web Chat) with zero vendor lock-in.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from gorgona_booking.notifications.service import EMAIL_RE
from gorgona_booking.notifications.transports import (
    TransportDeliveryError,
    resolve_notification_transports,
)

ChannelType = Literal["email", "voice_pbx", "sms", "whatsapp", "web_chat"]
MessageChannelType = Literal["email", "voice_pbx", "sms", "whatsapp", "web_chat", "internal_note"]
ChannelMode = Literal["built_in", "optional_byok"]
ThreadStatus = Literal["open", "pending", "snoozed", "resolved"]
ThreadPriority = Literal["low", "normal", "high", "urgent"]
LinkedEntityKind = Literal["quote", "purchase_order", "booking", "work_order"]
MessageDirection = Literal["inbound", "outbound", "internal"]
DeliveryStatus = Literal["received", "queued", "sent", "delivered", "failed", "logged"]
CallDirection = Literal["inbound", "outbound", "missed"]
CallStatus = Literal["ringing", "completed", "missed", "voicemail", "failed"]
CallDisposition = Literal[
    "resolved",
    "follow_up",
    "quote_requested",
    "support_ticket",
    "voicemail_left",
]

DEFAULT_BUILTIN_CHANNELS: tuple[tuple[ChannelType, str, str, str], ...] = (
    (
        "email",
        "Built-In Client Email",
        "inbox@amarkal-platform.com",
        "AMARKAL Built-In Email (Resend / SMTP)",
    ),
    (
        "voice_pbx",
        "Built-In Virtual PBX",
        "Main Desk · Ext 100",
        "AMARKAL Built-In Virtual PBX",
    ),
    (
        "web_chat",
        "Portal & Shop Web Chat",
        "/portal/ & /shop/",
        "AMARKAL Built-In Web Chat",
    ),
)

_PHONE_CLEAN_RE = re.compile(r"[^\d+]")


def generate_inbox_webhook_token() -> tuple[str, str, str]:
    """Return (plaintext_token, prefix, sha256_hex)."""
    raw = f"amk_inb_{secrets.token_urlsafe(24)}"
    prefix = raw[:14]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, prefix, digest


def hash_inbox_webhook_token(token: str) -> str:
    return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _PHONE_CLEAN_RE.sub("", value.strip())
    if not cleaned:
        return None
    if len(cleaned) == 10 and cleaned.isdigit():
        return f"+1{cleaned}"
    return cleaned[:40]


def build_message_preview(text: str, *, max_len: int = 180) -> str:
    collapsed = " ".join(text.strip().split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 1].rstrip() + "…"


def _require_row(row: dict[str, Any] | None, label: str) -> dict[str, Any]:
    if row is None:
        raise RuntimeError(f"Expected RETURNING row for {label}.")
    return row


@dataclass(frozen=True, slots=True)
class OmnichannelChannelView:
    id: UUID
    channel_type: ChannelType
    display_name: str
    address_or_number: str
    mode: ChannelMode
    provider_label: str
    is_enabled: bool
    auto_greeting: str
    webhook_token_prefix: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OmnichannelThreadView:
    id: UUID
    contact_name: str
    contact_email: str | None
    contact_phone: str | None
    counterparty_id: UUID | None
    linked_entity_kind: LinkedEntityKind | None
    linked_entity_ref: str | None
    primary_channel: ChannelType
    subject: str
    status: ThreadStatus
    priority: ThreadPriority
    unread_count: int
    last_message_preview: str
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OmnichannelMessageView:
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
    provider_message_id: str | None
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OmnichannelCallLogView:
    id: UUID
    thread_id: UUID | None
    direction: CallDirection
    caller_number: str
    callee_number: str
    contact_name: str
    call_status: CallStatus
    duration_seconds: int
    extension_or_queue: str
    recording_url: str | None
    transcript_summary: str
    disposition: CallDisposition
    started_at: datetime
    created_at: datetime


def _row_to_channel(r: dict[str, Any]) -> OmnichannelChannelView:
    return OmnichannelChannelView(
        id=r["id"],
        channel_type=r["channel_type"],
        display_name=str(r["display_name"]),
        address_or_number=str(r["address_or_number"] or ""),
        mode=r["mode"],
        provider_label=str(r["provider_label"]),
        is_enabled=bool(r["is_enabled"]),
        auto_greeting=str(r["auto_greeting"] or ""),
        webhook_token_prefix=str(r["webhook_token_prefix"]) if r["webhook_token_prefix"] else None,
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _row_to_thread(r: dict[str, Any]) -> OmnichannelThreadView:
    return OmnichannelThreadView(
        id=r["id"],
        contact_name=str(r["contact_name"]),
        contact_email=str(r["contact_email"]) if r["contact_email"] else None,
        contact_phone=str(r["contact_phone"]) if r["contact_phone"] else None,
        counterparty_id=r["counterparty_id"],
        linked_entity_kind=r["linked_entity_kind"],
        linked_entity_ref=str(r["linked_entity_ref"]) if r["linked_entity_ref"] else None,
        primary_channel=r["primary_channel"],
        subject=str(r["subject"] or ""),
        status=r["status"],
        priority=r["priority"],
        unread_count=int(r["unread_count"]),
        last_message_preview=str(r["last_message_preview"] or ""),
        last_message_at=r["last_message_at"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


def _row_to_message(r: dict[str, Any]) -> OmnichannelMessageView:
    meta = r.get("metadata")
    return OmnichannelMessageView(
        id=r["id"],
        thread_id=r["thread_id"],
        channel_type=r["channel_type"],
        direction=r["direction"],
        sender_name=str(r["sender_name"] or ""),
        sender_address=str(r["sender_address"] or ""),
        recipient_address=str(r["recipient_address"] or ""),
        subject=str(r["subject"] or ""),
        body=str(r["body"]),
        delivery_status=r["delivery_status"],
        provider_message_id=str(r["provider_message_id"]) if r["provider_message_id"] else None,
        metadata=dict(meta) if isinstance(meta, dict) else {},
        created_at=r["created_at"],
    )


def _row_to_call(r: dict[str, Any]) -> OmnichannelCallLogView:
    return OmnichannelCallLogView(
        id=r["id"],
        thread_id=r["thread_id"],
        direction=r["direction"],
        caller_number=str(r["caller_number"] or ""),
        callee_number=str(r["callee_number"] or ""),
        contact_name=str(r["contact_name"] or ""),
        call_status=r["call_status"],
        duration_seconds=int(r["duration_seconds"]),
        extension_or_queue=str(r["extension_or_queue"] or ""),
        recording_url=str(r["recording_url"]) if r["recording_url"] else None,
        transcript_summary=str(r["transcript_summary"] or ""),
        disposition=r["disposition"],
        started_at=r["started_at"],
        created_at=r["created_at"],
    )


async def dispatch_built_in_outbound(
    *,
    channel_type: MessageChannelType,
    recipient: str,
    subject: str,
    body: str,
    idempotency_key: str,
) -> tuple[DeliveryStatus, str | None, dict[str, Any]]:
    """Send outbound email/SMS via AMARKAL's built-in notification transport (zero extra setup)."""
    if channel_type == "internal_note":
        return "logged", None, {"transport": "internal_note"}
    if channel_type == "email" and recipient and EMAIL_RE.match(recipient.strip()):
        transports, _ = resolve_notification_transports()
        transport = transports.get("email")
        if transport is not None:
            try:
                receipt = await asyncio.to_thread(
                    transport.send,
                    channel="email",
                    recipient=recipient.strip(),
                    subject=subject or "Message from AMARKAL Business OS",
                    body=body,
                    idempotency_key=idempotency_key,
                )
                return (
                    "sent",
                    receipt.provider_message_id,
                    {"provider": receipt.provider_name, "sandbox": receipt.sandbox},
                )
            except TransportDeliveryError as exc:
                return "failed", None, {"error": str(exc)}
    if channel_type == "sms" and recipient:
        transports, _ = resolve_notification_transports()
        transport = transports.get("sms")
        if transport is not None:
            try:
                receipt = await asyncio.to_thread(
                    transport.send,
                    channel="sms",
                    recipient=recipient.strip(),
                    subject="",
                    body=body[:1600],
                    idempotency_key=idempotency_key,
                )
                return (
                    "sent",
                    receipt.provider_message_id,
                    {"provider": receipt.provider_name, "sandbox": receipt.sandbox},
                )
            except TransportDeliveryError as exc:
                return "failed", None, {"error": str(exc)}
    return "sent", f"amk-{channel_type}-{secrets.token_hex(6)}", {"transport": "built_in_hub"}


# ── Channels ─────────────────────────────────────────────────────────────────


async def ensure_and_list_channels(
    conn: AsyncConnection, *, tenant_id: UUID
) -> list[OmnichannelChannelView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, channel_type, display_name, address_or_number, mode, provider_label,
                   is_enabled, auto_greeting, webhook_token_prefix, created_at, updated_at
            FROM gba.omnichannel_channels
            WHERE tenant_id = %s
            ORDER BY channel_type ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
        if not rows:
            for ch_type, disp, addr, prov in DEFAULT_BUILTIN_CHANNELS:
                _, prefix, digest = generate_inbox_webhook_token()
                await cur.execute(
                    """
                    INSERT INTO gba.omnichannel_channels (
                        tenant_id, channel_type, display_name, address_or_number, mode,
                        provider_label, is_enabled, auto_greeting,
                        webhook_token_prefix, webhook_token_hash
                    )
                    VALUES (%s, %s, %s, %s, 'built_in', %s, true, '', %s, %s)
                    ON CONFLICT (tenant_id, channel_type) DO NOTHING
                    """,
                    (tenant_id, ch_type, disp, addr, prov, prefix, digest),
                )
            await cur.execute(
                """
                SELECT id, channel_type, display_name, address_or_number, mode, provider_label,
                       is_enabled, auto_greeting, webhook_token_prefix, created_at, updated_at
                FROM gba.omnichannel_channels
                WHERE tenant_id = %s
                ORDER BY channel_type ASC
                """,
                (tenant_id,),
            )
            rows = await cur.fetchall()
    return [_row_to_channel(dict(r)) for r in rows]


async def upsert_channel(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    channel_type: ChannelType,
    display_name: str,
    address_or_number: str,
    mode: ChannelMode,
    provider_label: str,
    is_enabled: bool,
    auto_greeting: str,
) -> tuple[OmnichannelChannelView, str | None]:
    plaintext: str | None = None
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id FROM gba.omnichannel_channels
            WHERE tenant_id = %s AND channel_type = %s
            """,
            (tenant_id, channel_type),
        )
        existing = await cur.fetchone()
        if existing is None:
            raw, prefix, digest = generate_inbox_webhook_token()
            plaintext = raw
            await cur.execute(
                """
                INSERT INTO gba.omnichannel_channels (
                    tenant_id, channel_type, display_name, address_or_number, mode,
                    provider_label, is_enabled, auto_greeting,
                    webhook_token_prefix, webhook_token_hash
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, channel_type, display_name, address_or_number, mode,
                          provider_label, is_enabled, auto_greeting,
                          webhook_token_prefix, created_at, updated_at
                """,
                (
                    tenant_id,
                    channel_type,
                    display_name.strip(),
                    address_or_number.strip(),
                    mode,
                    provider_label.strip() or "AMARKAL Built-In",
                    is_enabled,
                    auto_greeting.strip(),
                    prefix,
                    digest,
                ),
            )
        else:
            await cur.execute(
                """
                UPDATE gba.omnichannel_channels
                SET display_name = %s,
                    address_or_number = %s,
                    mode = %s,
                    provider_label = %s,
                    is_enabled = %s,
                    auto_greeting = %s,
                    updated_at = now()
                WHERE tenant_id = %s AND channel_type = %s
                RETURNING id, channel_type, display_name, address_or_number, mode,
                          provider_label, is_enabled, auto_greeting,
                          webhook_token_prefix, created_at, updated_at
                """,
                (
                    display_name.strip(),
                    address_or_number.strip(),
                    mode,
                    provider_label.strip() or "AMARKAL Built-In",
                    is_enabled,
                    auto_greeting.strip(),
                    tenant_id,
                    channel_type,
                ),
            )
        row = await cur.fetchone()
    return _row_to_channel(dict(_require_row(row, "omnichannel_channels upsert"))), plaintext


async def rotate_channel_webhook_token(
    conn: AsyncConnection, *, tenant_id: UUID, channel_type: ChannelType
) -> tuple[OmnichannelChannelView, str]:
    raw, prefix, digest = generate_inbox_webhook_token()
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.omnichannel_channels
            SET webhook_token_prefix = %s, webhook_token_hash = %s, updated_at = now()
            WHERE tenant_id = %s AND channel_type = %s
            RETURNING id, channel_type, display_name, address_or_number, mode, provider_label,
                      is_enabled, auto_greeting, webhook_token_prefix, created_at, updated_at
            """,
            (prefix, digest, tenant_id, channel_type),
        )
        row = await cur.fetchone()
    if row is None:
        raise LookupError("Channel not found.")
    return _row_to_channel(dict(row)), raw


async def resolve_channel_by_webhook_token(
    conn: AsyncConnection, *, plaintext_token: str
) -> tuple[UUID, ChannelType] | None:
    digest = hash_inbox_webhook_token(plaintext_token)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT set_config('gba.inbox_webhook_hash', %s, true)",
            (digest,),
        )
        await cur.execute(
            """
            SELECT tenant_id, channel_type
            FROM gba.omnichannel_channels
            WHERE webhook_token_hash = %s AND is_enabled = true
            LIMIT 1
            """,
            (digest,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return row["tenant_id"], row["channel_type"]


# ── Threads & Messages ───────────────────────────────────────────────────────


async def list_threads(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    status_filter: ThreadStatus | None = None,
    channel_filter: ChannelType | None = None,
    search: str | None = None,
) -> list[OmnichannelThreadView]:
    clauses = ["tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if status_filter is not None:
        clauses.append("status = %s")
        params.append(status_filter)
    if channel_filter is not None:
        clauses.append("primary_channel = %s")
        params.append(channel_filter)
    if search and search.strip():
        like = f"%{search.strip()}%"
        clauses.append(
            "(contact_name ILIKE %s OR COALESCE(contact_email, '') ILIKE %s "
            "OR subject ILIKE %s OR last_message_preview ILIKE %s)"
        )
        params.extend([like, like, like, like])

    where_sql = " AND ".join(clauses)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"""
            SELECT id, contact_name, contact_email, contact_phone, counterparty_id,
                   linked_entity_kind, linked_entity_ref, primary_channel, subject,
                   status, priority, unread_count, last_message_preview,
                   last_message_at, created_at, updated_at
            FROM gba.omnichannel_threads
            WHERE {where_sql}
            ORDER BY last_message_at DESC
            LIMIT 100
            """,  # noqa: S608
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_thread(dict(r)) for r in rows]


async def create_thread(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    contact_name: str,
    contact_email: str | None,
    contact_phone: str | None,
    primary_channel: ChannelType,
    subject: str,
    priority: ThreadPriority,
    linked_entity_kind: LinkedEntityKind | None,
    linked_entity_ref: str | None,
    initial_body: str | None,
    sender_name: str,
    created_by_user_id: UUID | None,
) -> tuple[OmnichannelThreadView, OmnichannelMessageView | None]:
    clean_email = contact_email.strip().lower() if contact_email and contact_email.strip() else None
    clean_phone = normalize_phone(contact_phone)
    preview = build_message_preview(initial_body) if initial_body and initial_body.strip() else ""

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.omnichannel_threads (
                tenant_id, contact_name, contact_email, contact_phone,
                linked_entity_kind, linked_entity_ref, primary_channel, subject,
                status, priority, unread_count, assigned_user_id, last_message_preview
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open', %s, 0, %s, %s)
            RETURNING id, contact_name, contact_email, contact_phone, counterparty_id,
                      linked_entity_kind, linked_entity_ref, primary_channel, subject,
                      status, priority, unread_count, last_message_preview,
                      last_message_at, created_at, updated_at
            """,
            (
                tenant_id,
                contact_name.strip(),
                clean_email,
                clean_phone,
                linked_entity_kind,
                linked_entity_ref.strip() if linked_entity_ref else None,
                primary_channel,
                subject.strip(),
                priority,
                created_by_user_id,
                preview,
            ),
        )
        trow = _require_row(await cur.fetchone(), "omnichannel_threads insert")
    thread = _row_to_thread(dict(trow))

    first_msg: OmnichannelMessageView | None = None
    if initial_body and initial_body.strip():
        first_msg, thread = await post_thread_message(
            conn,
            tenant_id=tenant_id,
            thread_id=thread.id,
            channel_type=primary_channel,
            direction="outbound",
            sender_name=sender_name,
            subject=subject.strip(),
            body=initial_body.strip(),
            created_by_user_id=created_by_user_id,
        )
    return thread, first_msg


async def get_thread_messages(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    thread_id: UUID,
    mark_read: bool = True,
) -> list[OmnichannelMessageView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, thread_id, channel_type, direction, sender_name, sender_address,
                   recipient_address, subject, body, delivery_status,
                   provider_message_id, metadata, created_at
            FROM gba.omnichannel_messages
            WHERE tenant_id = %s AND thread_id = %s
            ORDER BY created_at ASC
            LIMIT 250
            """,
            (tenant_id, thread_id),
        )
        rows = await cur.fetchall()
        if mark_read:
            await cur.execute(
                """
                UPDATE gba.omnichannel_threads
                SET unread_count = 0, updated_at = now()
                WHERE tenant_id = %s AND id = %s AND unread_count > 0
                """,
                (tenant_id, thread_id),
            )
    return [_row_to_message(dict(r)) for r in rows]


async def post_thread_message(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    thread_id: UUID,
    channel_type: MessageChannelType,
    direction: MessageDirection,
    sender_name: str,
    subject: str,
    body: str,
    created_by_user_id: UUID | None,
) -> tuple[OmnichannelMessageView, OmnichannelThreadView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, contact_name, contact_email, contact_phone, subject
            FROM gba.omnichannel_threads
            WHERE tenant_id = %s AND id = %s
            FOR UPDATE
            """,
            (tenant_id, thread_id),
        )
        trow = await cur.fetchone()
        if trow is None:
            raise LookupError("Conversation thread not found.")

    eff_subject = subject.strip() or str(trow["subject"] or "")
    recipient_addr = ""
    if direction == "outbound":
        if channel_type == "email":
            recipient_addr = str(trow["contact_email"] or "")
        elif channel_type in ("sms", "whatsapp", "voice_pbx"):
            recipient_addr = str(trow["contact_phone"] or "")
        delivery_status, prov_id, meta = await dispatch_built_in_outbound(
            channel_type=channel_type,
            recipient=recipient_addr,
            subject=eff_subject,
            body=body.strip(),
            idempotency_key=f"inbox:{tenant_id}:{thread_id}:{secrets.token_hex(6)}",
        )
    elif direction == "internal" or channel_type == "internal_note":
        delivery_status, prov_id, meta = "logged", None, {"internal": True}
    else:
        delivery_status, prov_id, meta = "received", None, {}

    preview = build_message_preview(body)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.omnichannel_messages (
                tenant_id, thread_id, channel_type, direction, sender_name,
                sender_address, recipient_address, subject, body, delivery_status,
                provider_message_id, metadata, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, '', %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id, thread_id, channel_type, direction, sender_name, sender_address,
                      recipient_address, subject, body, delivery_status,
                      provider_message_id, metadata, created_at
            """,
            (
                tenant_id,
                thread_id,
                channel_type,
                "internal" if channel_type == "internal_note" else direction,
                sender_name.strip() or "AMARKAL Team",
                recipient_addr,
                eff_subject,
                body.strip(),
                delivery_status,
                prov_id,
                json.dumps(meta),
                created_by_user_id,
            ),
        )
        msg_row = _require_row(await cur.fetchone(), "omnichannel_messages insert")

        unread_inc = 1 if direction == "inbound" else 0
        await cur.execute(
            """
            UPDATE gba.omnichannel_threads
            SET last_message_preview = %s,
                last_message_at = now(),
                unread_count = unread_count + %s,
                status = CASE
                    WHEN %s = 'inbound' AND status = 'resolved' THEN 'open'
                    ELSE status
                END,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, contact_name, contact_email, contact_phone, counterparty_id,
                      linked_entity_kind, linked_entity_ref, primary_channel, subject,
                      status, priority, unread_count, last_message_preview,
                      last_message_at, created_at, updated_at
            """,
            (preview, unread_inc, direction, tenant_id, thread_id),
        )
        upd_thread = _require_row(await cur.fetchone(), "omnichannel_threads update")

    return _row_to_message(dict(msg_row)), _row_to_thread(dict(upd_thread))


async def update_thread_state(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    thread_id: UUID,
    status: ThreadStatus | None = None,
    priority: ThreadPriority | None = None,
    linked_entity_kind: LinkedEntityKind | None = None,
    linked_entity_ref: str | None = None,
) -> OmnichannelThreadView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.omnichannel_threads
            SET status = COALESCE(%s, status),
                priority = COALESCE(%s, priority),
                linked_entity_kind = COALESCE(%s, linked_entity_kind),
                linked_entity_ref = COALESCE(%s, linked_entity_ref),
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, contact_name, contact_email, contact_phone, counterparty_id,
                      linked_entity_kind, linked_entity_ref, primary_channel, subject,
                      status, priority, unread_count, last_message_preview,
                      last_message_at, created_at, updated_at
            """,
            (
                status,
                priority,
                linked_entity_kind,
                linked_entity_ref.strip() if linked_entity_ref else None,
                tenant_id,
                thread_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise LookupError("Conversation thread not found.")
    return _row_to_thread(dict(row))


async def ingest_inbound_message(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    channel_type: ChannelType,
    sender_name: str,
    sender_email: str | None,
    sender_phone: str | None,
    subject: str,
    body: str,
) -> tuple[OmnichannelThreadView, OmnichannelMessageView]:
    """Match an existing thread by email/phone or create one, then append the inbound message."""
    clean_email = sender_email.strip().lower() if sender_email and sender_email.strip() else None
    clean_phone = normalize_phone(sender_phone)
    thread_id: UUID | None = None

    async with conn.cursor(row_factory=dict_row) as cur:
        if clean_email:
            await cur.execute(
                """
                SELECT id FROM gba.omnichannel_threads
                WHERE tenant_id = %s AND lower(contact_email) = %s
                ORDER BY last_message_at DESC
                LIMIT 1
                """,
                (tenant_id, clean_email),
            )
            hit = await cur.fetchone()
            if hit is not None:
                thread_id = hit["id"]
        if thread_id is None and clean_phone:
            await cur.execute(
                """
                SELECT id FROM gba.omnichannel_threads
                WHERE tenant_id = %s AND contact_phone = %s
                ORDER BY last_message_at DESC
                LIMIT 1
                """,
                (tenant_id, clean_phone),
            )
            hit = await cur.fetchone()
            if hit is not None:
                thread_id = hit["id"]

        if thread_id is None:
            await cur.execute(
                """
                INSERT INTO gba.omnichannel_threads (
                    tenant_id, contact_name, contact_email, contact_phone,
                    primary_channel, subject, status, priority, unread_count,
                    last_message_preview
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'open', 'normal', 0, %s)
                RETURNING id
                """,
                (
                    tenant_id,
                    sender_name.strip() or clean_email or clean_phone or "Inbound Contact",
                    clean_email,
                    clean_phone,
                    channel_type,
                    subject.strip() or f"Inbound {channel_type.replace('_', ' ').title()}",
                    build_message_preview(body),
                ),
            )
            new_row = _require_row(await cur.fetchone(), "inbound thread insert")
            thread_id = new_row["id"]

    msg, thread = await post_thread_message(
        conn,
        tenant_id=tenant_id,
        thread_id=thread_id,
        channel_type=channel_type,
        direction="inbound",
        sender_name=sender_name.strip() or "Client",
        subject=subject,
        body=body,
        created_by_user_id=None,
    )
    return thread, msg


# ── Virtual PBX Call Logs ────────────────────────────────────────────────────


async def list_call_logs(conn: AsyncConnection, *, tenant_id: UUID) -> list[OmnichannelCallLogView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, thread_id, direction, caller_number, callee_number, contact_name,
                   call_status, duration_seconds, extension_or_queue, recording_url,
                   transcript_summary, disposition, started_at, created_at
            FROM gba.omnichannel_call_logs
            WHERE tenant_id = %s
            ORDER BY started_at DESC
            LIMIT 100
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_call(dict(r)) for r in rows]


async def record_call_log(
    conn: AsyncConnection,
    *,
    tenant_id: UUID,
    thread_id: UUID | None,
    direction: CallDirection,
    caller_number: str,
    callee_number: str,
    contact_name: str,
    call_status: CallStatus,
    duration_seconds: int,
    extension_or_queue: str,
    transcript_summary: str,
    disposition: CallDisposition,
    created_by_user_id: UUID | None,
) -> OmnichannelCallLogView:
    clean_caller = normalize_phone(caller_number) or caller_number.strip()[:40]
    clean_callee = normalize_phone(callee_number) or callee_number.strip()[:40]
    peer_phone = clean_caller if direction in ("inbound", "missed") else clean_callee

    resolved_thread_id = thread_id
    if resolved_thread_id is None and peer_phone:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id FROM gba.omnichannel_threads
                WHERE tenant_id = %s AND contact_phone = %s
                ORDER BY last_message_at DESC
                LIMIT 1
                """,
                (tenant_id, peer_phone),
            )
            existing = await cur.fetchone()
            if existing is not None:
                resolved_thread_id = existing["id"]
            else:
                await cur.execute(
                    """
                    INSERT INTO gba.omnichannel_threads (
                        tenant_id, contact_name, contact_phone, primary_channel,
                        subject, status, priority, unread_count, last_message_preview
                    )
                    VALUES (%s, %s, %s, 'voice_pbx', %s, 'open', 'normal', 0, %s)
                    RETURNING id
                    """,
                    (
                        tenant_id,
                        contact_name.strip() or peer_phone,
                        peer_phone,
                        f"Virtual PBX Call ({direction})",
                        build_message_preview(
                            transcript_summary or f"{direction} call ({duration_seconds}s)"
                        ),
                    ),
                )
                created_t = _require_row(await cur.fetchone(), "call log thread insert")
                resolved_thread_id = created_t["id"]

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.omnichannel_call_logs (
                tenant_id, thread_id, direction, caller_number, callee_number,
                contact_name, call_status, duration_seconds, extension_or_queue,
                transcript_summary, disposition, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, thread_id, direction, caller_number, callee_number, contact_name,
                      call_status, duration_seconds, extension_or_queue, recording_url,
                      transcript_summary, disposition, started_at, created_at
            """,
            (
                tenant_id,
                resolved_thread_id,
                direction,
                clean_caller,
                clean_callee,
                contact_name.strip() or peer_phone,
                call_status,
                max(0, duration_seconds),
                extension_or_queue.strip() or "Main Desk · Ext 100",
                transcript_summary.strip(),
                disposition,
                created_by_user_id,
            ),
        )
        row = _require_row(await cur.fetchone(), "omnichannel_call_logs insert")

    # Mirror the call into the client's unified conversation timeline
    if resolved_thread_id is not None:
        mins, secs = divmod(max(0, duration_seconds), 60)
        summary_line = (
            f"Virtual PBX {direction} call ({call_status}, {mins}m {secs:02d}s) · "
            f"{extension_or_queue.strip() or 'Main Desk'} · Disposition: {disposition}"
        )
        if transcript_summary.strip():
            summary_line = f"{summary_line}\n{transcript_summary.strip()}"
        await post_thread_message(
            conn,
            tenant_id=tenant_id,
            thread_id=resolved_thread_id,
            channel_type="voice_pbx",
            direction="inbound" if direction in ("inbound", "missed") else "outbound",
            sender_name=contact_name.strip() or "Virtual PBX",
            subject="Virtual PBX Call",
            body=summary_line,
            created_by_user_id=created_by_user_id,
        )

    return _row_to_call(dict(row))
