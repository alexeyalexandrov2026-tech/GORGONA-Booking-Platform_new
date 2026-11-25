"""Async Email & SMS outbox service with templates, masking, retries, and dead-lettering."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from gorgona_booking.notifications.transports import (
    NotificationTransport,
    TransportDeliveryError,
    resolve_notification_transports,
)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
E164_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")

TEMPLATES: dict[str, tuple[str, str]] = {
    "booking_confirmation": (
        "Booking confirmed: {business_name}",
        "Your booking {reference} with {business_name} is confirmed for {starts_at}.",
    ),
    "booking_reminder": (
        "Upcoming appointment reminder: {business_name}",
        "Reminder: booking {reference} with {business_name} starts at {starts_at}.",
    ),
    "staff_invitation": (
        "Invitation to join {business_name} on GORGONA",
        "You have been invited as {role} to {business_name}. Open your invitation link to accept.",
    ),
    "invoice_issued": (
        "Invoice {reference} from {business_name}",
        "Invoice {reference} for {amount} has been issued by {business_name}.",
    ),
}


@dataclass(frozen=True)
class NotificationRecord:
    id: UUID
    tenant_id: UUID
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


def validate_and_mask_recipient(channel: str, recipient: str) -> tuple[str, str]:
    clean = recipient.strip()
    if channel == "email":
        if not EMAIL_RE.match(clean):
            raise ValueError("Invalid email recipient address")
        local, domain = clean.split("@", 1)
        masked = f"{local[:1]}***@{domain.lower()}"
        canonical = clean.lower()
    elif channel == "sms":
        if not E164_RE.match(clean):
            raise ValueError("Invalid E.164 SMS phone number (expected +1...)")
        masked = f"{clean[:3]}***{clean[-4:]}"
        canonical = clean
    else:
        raise ValueError(f"Unsupported notification channel: {channel}")
    digest = hashlib.sha256(f"{channel}:{canonical}".encode()).hexdigest()
    return masked, digest


def render_template(template_code: str, variables: dict[str, str]) -> tuple[str, str]:
    if template_code not in TEMPLATES:
        raise ValueError(f"Unknown notification template: {template_code}")
    subj_tmpl, body_tmpl = TEMPLATES[template_code]
    safe_vars = {
        "business_name": variables.get("business_name", "GORGONA Business"),
        "reference": variables.get("reference", "N/A"),
        "starts_at": variables.get("starts_at", "scheduled time"),
        "role": variables.get("role", "team member"),
        "amount": variables.get("amount", "0.00"),
    }
    return subj_tmpl.format(**safe_vars)[:240], body_tmpl.format(**safe_vars)[:2000]


def _row_to_record(row: dict[str, Any]) -> NotificationRecord:
    return NotificationRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        channel=row["channel"],
        template_code=row["template_code"],
        recipient_masked=row["recipient_masked"],
        subject=row["subject"],
        body_preview=row["body_preview"],
        idempotency_key=row["idempotency_key"],
        status=row["status"],
        attempt_count=row["attempt_count"],
        max_attempts=row["max_attempts"],
        provider_name=row["provider_name"],
        provider_message_id=row["provider_message_id"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        sent_at=row["sent_at"],
    )


async def enqueue_notification(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    channel: str,
    template_code: str,
    recipient: str,
    variables: dict[str, str],
    idempotency_key: str,
    created_by_user_id: UUID | None = None,
    max_attempts: int = 3,
) -> NotificationRecord:
    masked, recipient_hash = validate_and_mask_recipient(channel, recipient)
    subject, body = render_template(template_code, variables)
    key = idempotency_key.strip()
    if len(key) < 4 or len(key) > 128:
        raise ValueError("idempotency_key must be 4..128 characters")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.notification_outbox (
                tenant_id, channel, template_code, recipient_masked, recipient_hash,
                subject, body_preview, idempotency_key, max_attempts, created_by_user_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING *
            """,
            (
                tenant_id,
                channel,
                template_code,
                masked,
                recipient_hash,
                subject,
                body,
                key,
                max_attempts,
                created_by_user_id,
                json.dumps({"template": template_code}),
            ),
        )
        row = await cur.fetchone()
        if row is None:
            await cur.execute(
                (
                    "SELECT * FROM gba.notification_outbox "
                    "WHERE tenant_id = %s AND idempotency_key = %s"
                ),
                (tenant_id, key),
            )
            row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Notification outbox row missing")
    return _row_to_record(row)


async def list_outbox(
    conn: AsyncConnection[Any], *, tenant_id: UUID, limit: int = 50
) -> list[NotificationRecord]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT * FROM gba.notification_outbox
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, max(1, min(limit, 200))),
        )
        rows = await cur.fetchall()
    return [_row_to_record(r) for r in rows]


async def dispatch_notification(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    notification_id: UUID,
    recipient: str,
    transports: dict[str, NotificationTransport] | None = None,
) -> NotificationRecord:
    active_transports, _ = resolve_notification_transports()
    if transports is not None:
        active_transports.update(transports)

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT * FROM gba.notification_outbox
            WHERE tenant_id = %s AND id = %s
            FOR UPDATE
            """,
            (tenant_id, notification_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise LookupError("Notification not found")
        if row["status"] in ("sent", "dead_lettered"):
            return _row_to_record(row)

        _, expected_hash = validate_and_mask_recipient(row["channel"], recipient)
        if expected_hash != row["recipient_hash"]:
            raise ValueError("Recipient does not match queued notification hash")

        transport = active_transports[row["channel"]]
        attempts = int(row["attempt_count"]) + 1
        max_attempts = int(row["max_attempts"])
        try:
            receipt = await asyncio.to_thread(
                transport.send,
                channel=row["channel"],
                recipient=recipient.strip(),
                subject=row["subject"],
                body=row["body_preview"],
                idempotency_key=row["idempotency_key"],
            )
            await cur.execute(
                """
                UPDATE gba.notification_outbox
                SET status = 'sent',
                    attempt_count = %s,
                    provider_name = %s,
                    provider_message_id = %s,
                    last_error = NULL,
                    sent_at = now(),
                    updated_at = now()
                WHERE tenant_id = %s AND id = %s
                RETURNING *
                """,
                (
                    attempts,
                    receipt.provider_name,
                    receipt.provider_message_id,
                    tenant_id,
                    notification_id,
                ),
            )
            updated = await cur.fetchone()
        except TransportDeliveryError as exc:
            next_status = (
                "dead_lettered" if (not exc.retryable or attempts >= max_attempts) else "failed"
            )
            backoff_sec = min(3600, 30 * (2 ** max(0, attempts - 1)))
            next_at = datetime.now(UTC) + timedelta(seconds=backoff_sec)
            await cur.execute(
                """
                UPDATE gba.notification_outbox
                SET status = %s,
                    attempt_count = %s,
                    provider_name = %s,
                    last_error = %s,
                    next_attempt_at = %s,
                    updated_at = now()
                WHERE tenant_id = %s AND id = %s
                RETURNING *
                """,
                (
                    next_status,
                    attempts,
                    transport.name,
                    str(exc)[:500],
                    next_at,
                    tenant_id,
                    notification_id,
                ),
            )
            updated = await cur.fetchone()
    if updated is None:
        raise RuntimeError("Updated notification row missing")
    return _row_to_record(updated)
