"""Event-driven outbound HMAC-SHA256 webhook dispatcher (strictly outside DB transactions)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from gorgona_booking.connectors.service import (
    ALLOWED_WEBHOOK_EVENTS,
    PreparedWebhookTest,
    WebhookProbeOutcome,
    record_webhook_test_delivery,
    send_webhook_http_probe,
)
from gorgona_booking.db.pool import RuntimePool, tenant_transaction

_LOG = logging.getLogger(__name__)


async def dispatch_business_event(
    pool: RuntimePool,
    *,
    tenant_id: UUID,
    event_type: str,
    data: dict[str, Any],
    environment: str,
) -> list[dict[str, Any]]:
    """Deliver a real business event to all active tenant webhooks subscribed to `event_type`."""
    if event_type not in ALLOWED_WEBHOOK_EVENTS:
        raise ValueError(f"Unsupported webhook event type: {event_type}")

    targets: list[tuple[UUID, PreparedWebhookTest]] = []
    async with tenant_transaction(pool, tenant_id) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, url, signing_secret_hash
                FROM gba.webhook_endpoints
                WHERE tenant_id = %s
                  AND is_active = true
                  AND %s = ANY(events)
                ORDER BY created_at ASC
                LIMIT 20
                """,
                (tenant_id, event_type),
            )
            endpoints = await cur.fetchall()

        for ep in endpoints:
            ep_id = UUID(str(ep["id"]))
            payload: dict[str, Any] = {
                "event": event_type,
                "tenant_id": str(tenant_id),
                "endpoint_id": str(ep_id),
                "platform": "AMARKAL Platform",
                "data": data,
            }
            sig = hmac.new(
                str(ep["signing_secret_hash"]).encode("utf-8"),
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            targets.append(
                (
                    ep_id,
                    PreparedWebhookTest(
                        url=str(ep["url"]),
                        payload=payload,
                        signature_header=f"v1={sig}",
                    ),
                )
            )

    if not targets:
        return []

    outcomes: list[tuple[UUID, PreparedWebhookTest, WebhookProbeOutcome]] = []
    for ep_id, prepared in targets:
        if environment in ("staging", "production"):
            outcome = await send_webhook_http_probe(prepared)
        else:
            outcome = WebhookProbeOutcome(
                status="queued",
                http_status=None,
                last_error="Outbound webhook HTTP delivery is disabled in local/test environment.",
            )
        outcomes.append((ep_id, prepared, outcome))

    recorded: list[dict[str, Any]] = []
    async with tenant_transaction(pool, tenant_id) as conn:
        for ep_id, prepared, outcome in outcomes:
            row = await record_webhook_test_delivery(
                conn,
                tenant_id=tenant_id,
                endpoint_id=ep_id,
                prepared=prepared,
                outcome=outcome,
                event_type=event_type,
            )
            recorded.append(row)
    return recorded


async def dispatch_business_event_nonblocking(
    pool: RuntimePool,
    *,
    tenant_id: UUID,
    event_type: str,
    data: dict[str, Any],
    environment: str,
) -> None:
    """Fire-and-log helper so customer webhook outages never fail core business writes."""
    try:
        await dispatch_business_event(
            pool,
            tenant_id=tenant_id,
            event_type=event_type,
            data=data,
            environment=environment,
        )
    except Exception as exc:
        _LOG.warning(
            "Non-blocking webhook event dispatch failed for %s: %s",
            event_type,
            type(exc).__name__,
        )
