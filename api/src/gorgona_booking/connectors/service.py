"""AMARKAL App Hub & Connector Engine (Scoped API Keys, Signed Webhooks, Native MCP)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import http.client
import ipaddress
import json
import secrets
import socket
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gorgona_booking.db.pool import RuntimeConnection

ALLOWED_SCOPES = frozenset(
    {
        "mcp:read",
        "bookings:read",
        "bookings:write",
        "catalog:read",
        "finance:read",
        "webhooks:manage",
    }
)

ALLOWED_WEBHOOK_EVENTS = frozenset(
    {
        "booking.created",
        "booking.cancelled",
        "waitlist.joined",
        "invoice.issued",
        "payment.recorded",
        "quote.created",
        "quote.accepted",
        "purchase_order.issued",
        "purchase_order.matched",
        "connector.test",
    }
)


@dataclass(frozen=True)
class ConnectorCatalogItem:
    id: str
    name: str
    category: str
    summary: str
    auth_mode: Literal["mcp_api_key", "webhook", "byok", "oauth_ready"]
    fields: tuple[str, ...]
    us_highlight: str


CONNECTOR_CATALOG: tuple[ConnectorCatalogItem, ...] = (
    ConnectorCatalogItem(
        id="native_mcp",
        name="AMARKAL Native MCP Server",
        category="AI & Agents",
        summary=(
            "Connect ChatGPT, Claude, Gemini, Vapi, Retell, or custom AI agents directly to your "
            "live slots, services, and business metrics via /v1/mcp with strict tenant isolation."
        ),
        auth_mode="mcp_api_key",
        fields=("agent_label",),
        us_highlight="2027 Agentic Standard — works with any MCP-compatible AI or Voice agent",
    ),
    ConnectorCatalogItem(
        id="zapier_make",
        name="Zapier / Make / n8n",
        category="Automation",
        summary=(
            "Connect 7,000+ US apps using HMAC-SHA256 signed webhooks and scoped API keys "
            "without cluttering your AMARKAL core."
        ),
        auth_mode="webhook",
        fields=("workflow_label",),
        us_highlight="Instant no-code bridge to CRM, Slack, Google Sheets, and email marketing",
    ),
    ConnectorCatalogItem(
        id="quickbooks_online",
        name="QuickBooks Online (US)",
        category="Accounting & Tax",
        summary=(
            "Optional accounting connector: sync AMARKAL FIN-03 double-entry invoices, payments, "
            "and 1099-ready summaries with your US CPA's QuickBooks Online company file."
        ),
        auth_mode="oauth_ready",
        fields=("realm_id", "sync_mode"),
        us_highlight="Optional OAuth2 / BYOK connector — built on real double-entry ledger",
    ),
    ConnectorCatalogItem(
        id="xero_accounting",
        name="Xero Accounting (Optional)",
        category="Accounting & Tax",
        summary=(
            "Optional OAuth2 connector for organizations using Xero for US GAAP general ledger "
            "and vendor bill synchronization."
        ),
        auth_mode="oauth_ready",
        fields=("tenant_org_id", "sync_mode"),
        us_highlight="Self-service OAuth2 connection — zero accounting vendor lock-in",
    ),
    ConnectorCatalogItem(
        id="slack_workspace",
        name="Slack Workspace Alerts (Optional)",
        category="Communications",
        summary=(
            "Optional team notifications for quote approvals, 3-way match variances, "
            "and Stripe settlement events."
        ),
        auth_mode="oauth_ready",
        fields=("channel_name",),
        us_highlight="Instant operational alerts without cluttering your AMARKAL core",
    ),
    ConnectorCatalogItem(
        id="email_marketing_byok",
        name="Email Marketing Bridge (Mailchimp / Klaviyo / Resend)",
        category="Marketing (Optional)",
        summary=(
            "Optional email campaign plugin: connect your own Mailchimp, Klaviyo, or Resend "
            "audience via webhooks without forcing marketing bloat into the Business OS core."
        ),
        auth_mode="byok",
        fields=("provider_name", "audience_id"),
        us_highlight="Strictly optional plugin — businesses keep full ownership of client lists",
    ),
    ConnectorCatalogItem(
        id="google_calendar",
        name="Google Calendar",
        category="Scheduling",
        summary=(
            "Connect Google Workspace staff calendars so personal blocks and external events stay "
            "aligned with live AMARKAL availability."
        ),
        auth_mode="oauth_ready",
        fields=("calendar_email",),
        us_highlight="Eliminates double-bookings across field & service teams",
    ),
    ConnectorCatalogItem(
        id="microsoft_365",
        name="Microsoft 365 (Outlook, Calendar & Teams)",
        category="Productivity (Optional)",
        summary=(
            "Optional OAuth2 connector for organizations running Microsoft 365: sync Outlook "
            "calendars, send quote/PO emails through Outlook Mail, and route Teams alerts."
        ),
        auth_mode="oauth_ready",
        fields=("mailbox_email", "teams_channel"),
        us_highlight="Optional customer-chosen Microsoft Graph bridge — zero core lock-in",
    ),
    ConnectorCatalogItem(
        id="reserve_with_google",
        name="Reserve with Google & Maps",
        category="Discovery",
        summary=(
            "Publish verified live slots and Schema.org ReserveAction directly into Google Search "
            "and Maps with 0% marketplace commission."
        ),
        auth_mode="byok",
        fields=("google_place_id",),
        us_highlight="Zero-commission US local organic demand",
    ),
    ConnectorCatalogItem(
        id="twilio_voice_sms",
        name="Twilio SMS & AI Voice (BYOK)",
        category="Communications",
        summary=(
            "Bring your own US A2P 10DLC number or external AI Voice receptionist (Vapi/Retell) "
            "with zero platform telecom markup."
        ),
        auth_mode="byok",
        fields=("from_number", "voice_provider"),
        us_highlight="You own your US phone number and pay wholesale carrier rates",
    ),
    ConnectorCatalogItem(
        id="meta_messaging",
        name="WhatsApp & Instagram DM (BYOK)",
        category="Communications",
        summary=(
            "Optional social messaging bridge using your own Meta Business credentials and "
            "webhook routing."
        ),
        auth_mode="byok",
        fields=("meta_page_id",),
        us_highlight="Optional plugin — never forced on B2B or enterprise teams",
    ),
    ConnectorCatalogItem(
        id="stripe_ach_pos",
        name="Stripe US (Cards, Apple Pay, ACH)",
        category="Payments",
        summary=(
            "Accept US cards, Apple/Google Pay, Tap to Pay, and $5-cap US ACH bank transfers "
            "for high-ticket construction, legal, and rental invoices."
        ),
        auth_mode="oauth_ready",
        fields=("stripe_account_id", "ach_enabled"),
        us_highlight="Save thousands on large US B2B invoices via ACH",
    ),
)
CONNECTORS_BY_ID = {c.id: c for c in CONNECTOR_CATALOG}


def _sha256_hex(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def _mask_config(raw_config: dict[str, Any]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for k, v in raw_config.items():
        clean_k = str(k).strip()[:64]
        clean_v = str(v).strip()[:240]
        if not clean_k:
            continue
        low_k = clean_k.lower()
        if any(s in low_k for s in ("secret", "token", "key", "password")):
            masked[clean_k] = f"{clean_v[:4]}***{clean_v[-2:]}" if len(clean_v) > 8 else "***"
        else:
            masked[clean_k] = clean_v
    return masked


async def list_connector_installations(
    conn: RuntimeConnection, *, tenant_id: UUID
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT connector_id, display_name, category, status, config_masked,
                   created_at, updated_at
            FROM gba.connector_installations
            WHERE tenant_id = %s
            ORDER BY connector_id
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def upsert_connector_installation(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    connector_id: str,
    status: Literal["installed", "paused"],
    config: dict[str, Any],
    user_id: UUID | None,
) -> dict[str, Any]:
    spec = CONNECTORS_BY_ID.get(connector_id)
    if spec is None:
        raise ValueError(f"Unknown connector: {connector_id}")
    masked = _mask_config(config)
    cfg_hash = _sha256_hex(json.dumps(config, sort_keys=True, ensure_ascii=False))
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.connector_installations
                (tenant_id, connector_id, display_name, category, status,
                 config_masked, config_hash, installed_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, connector_id) DO UPDATE SET
                status = EXCLUDED.status,
                config_masked = EXCLUDED.config_masked,
                config_hash = EXCLUDED.config_hash,
                installed_by_user_id = EXCLUDED.installed_by_user_id,
                updated_at = now()
            RETURNING connector_id, display_name, category, status, config_masked,
                      created_at, updated_at
            """,
            (
                tenant_id,
                spec.id,
                spec.name,
                spec.category,
                status,
                Jsonb(masked),
                cfg_hash,
                user_id,
            ),
        )
        row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return dict(row)


async def delete_connector_installation(
    conn: RuntimeConnection, *, tenant_id: UUID, connector_id: str
) -> bool:
    cur = await conn.execute(
        "DELETE FROM gba.connector_installations WHERE tenant_id = %s AND connector_id = %s",
        (tenant_id, connector_id),
    )
    return cur.rowcount > 0


async def list_api_keys(conn: RuntimeConnection, *, tenant_id: UUID) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, name, key_prefix, scopes, status, last_used_at, created_at, revoked_at
            FROM gba.api_keys
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def create_api_key(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    name: str,
    scopes: list[str],
    user_id: UUID | None,
) -> tuple[dict[str, Any], str]:
    clean_scopes = sorted({s.strip() for s in scopes if s.strip()})
    if not clean_scopes or not set(clean_scopes).issubset(ALLOWED_SCOPES):
        raise ValueError(f"Scopes must be a non-empty subset of {sorted(ALLOWED_SCOPES)}")
    raw_secret = f"gorg_live_{secrets.token_urlsafe(32)}"
    prefix = raw_secret[:18]
    digest = _sha256_hex(raw_secret)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.api_keys
                (tenant_id, name, key_prefix, key_hash, scopes, status, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, 'active', %s)
            RETURNING id, name, key_prefix, scopes, status, last_used_at, created_at, revoked_at
            """,
            (tenant_id, name.strip(), prefix, digest, clean_scopes, user_id),
        )
        row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return dict(row), raw_secret


async def revoke_api_key(conn: RuntimeConnection, *, tenant_id: UUID, key_id: UUID) -> bool:
    cur = await conn.execute(
        """
        UPDATE gba.api_keys
        SET status = 'revoked', revoked_at = now()
        WHERE tenant_id = %s AND id = %s AND status = 'active'
        """,
        (tenant_id, key_id),
    )
    return cur.rowcount > 0


async def resolve_api_key(
    conn: RuntimeConnection, raw_token: str
) -> tuple[UUID, UUID, tuple[str, ...]] | None:
    """Resolve an active Scoped API Key via invoker-only RLS setting `gba.api_key_hash`."""
    clean = raw_token.strip()
    if not clean.startswith("gorg_live_") or len(clean) < 24:
        return None
    digest = _sha256_hex(clean)
    await conn.execute(
        "SELECT pg_catalog.set_config('gba.api_key_hash', %s, true)",
        (digest,),
    )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, tenant_id, scopes
            FROM gba.api_keys
            WHERE key_hash = %s AND status = 'active'
            """,
            (digest,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return (UUID(str(row["id"])), UUID(str(row["tenant_id"])), tuple(row["scopes"] or ()))


async def list_webhooks(conn: RuntimeConnection, *, tenant_id: UUID) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, url, description, events, signing_secret_prefix, is_active,
                   created_at, updated_at
            FROM gba.webhook_endpoints
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def create_webhook(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    url: str,
    description: str,
    events: list[str],
    user_id: UUID | None,
) -> tuple[dict[str, Any], str]:
    clean_url = url.strip()
    if not clean_url.startswith("https://") or len(clean_url) < 12:
        raise ValueError("Webhook URL must use https://")
    clean_events = sorted({e.strip() for e in events if e.strip()})
    if not clean_events or not set(clean_events).issubset(ALLOWED_WEBHOOK_EVENTS):
        raise ValueError(f"Events must be a non-empty subset of {sorted(ALLOWED_WEBHOOK_EVENTS)}")
    signing_secret = f"whsec_{secrets.token_urlsafe(28)}"
    prefix = signing_secret[:14]
    digest = _sha256_hex(signing_secret)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.webhook_endpoints
                (tenant_id, url, description, events, signing_secret_prefix,
                 signing_secret_hash, is_active, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, true, %s)
            RETURNING id, url, description, events, signing_secret_prefix, is_active,
                      created_at, updated_at
            """,
            (tenant_id, clean_url, description.strip(), clean_events, prefix, digest, user_id),
        )
        row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return dict(row), signing_secret


async def delete_webhook(conn: RuntimeConnection, *, tenant_id: UUID, endpoint_id: UUID) -> bool:
    cur = await conn.execute(
        "DELETE FROM gba.webhook_endpoints WHERE tenant_id = %s AND id = %s",
        (tenant_id, endpoint_id),
    )
    return cur.rowcount > 0


def validate_public_webhook_url(url: str, *, resolve_dns: bool = True) -> str:
    """Ensure webhook target is HTTPS and does not resolve to private/loopback/metadata IPs."""
    clean = url.strip()
    parsed = urlparse(clean)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Webhook URL must use https:// with a valid hostname")
    host = parsed.hostname.lower().rstrip(".")
    if host in ("localhost", "ip6-localhost") or host.endswith(
        (".local", ".internal", ".localhost")
    ):
        raise ValueError("Webhook URL cannot target localhost or internal hostnames")

    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not literal_ip.is_global:
            raise ValueError("Webhook URL cannot target private, loopback, or link-local IPs")
        return clean

    if not resolve_dns:
        return clean

    try:
        infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Webhook hostname could not be resolved: {host}") from exc
    if not infos:
        raise ValueError(f"Webhook hostname resolved to no addresses: {host}")
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if not addr.is_global:
            raise ValueError("Webhook URL resolves to a non-public IP address")
    return clean


@dataclass(frozen=True)
class PreparedWebhookTest:
    url: str
    payload: dict[str, Any]
    signature_header: str


@dataclass(frozen=True)
class WebhookProbeOutcome:
    status: Literal["delivered", "failed", "queued"]
    http_status: int | None
    last_error: str | None


async def prepare_webhook_test_delivery(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    endpoint_id: UUID,
) -> PreparedWebhookTest:
    """Load active webhook endpoint and compute HMAC-SHA256 signature inside a short TX."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, url, signing_secret_hash
            FROM gba.webhook_endpoints
            WHERE tenant_id = %s AND id = %s AND is_active = true
            """,
            (tenant_id, endpoint_id),
        )
        ep = await cur.fetchone()
    if ep is None:
        raise LookupError("Active webhook endpoint not found")
    payload = {
        "event": "connector.test",
        "tenant_id": str(tenant_id),
        "endpoint_id": str(endpoint_id),
        "platform": "AMARKAL Platform",
    }
    sig = hmac.new(
        str(ep["signing_secret_hash"]).encode("utf-8"),
        json.dumps(payload, sort_keys=True).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return PreparedWebhookTest(
        url=str(ep["url"]),
        payload=payload,
        signature_header=f"v1={sig}",
    )


def _post_webhook_https_sync(
    safe_url: str, body: bytes, signature_header: str
) -> WebhookProbeOutcome:
    """Bounded stdlib HTTPS POST (no redirects, zero extra runtime dependencies)."""
    parsed = urlparse(safe_url)
    host = parsed.hostname or ""
    port = parsed.port or 443
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    conn = http.client.HTTPSConnection(
        host,
        port,
        timeout=6.0,
        context=ssl.create_default_context(),
    )
    try:
        conn.request(
            "POST",
            target,
            body=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AMARKAL-Webhooks/1.0",
                "X-AMARKAL-Event": "connector.test",
                "X-AMARKAL-Signature": signature_header,
            },
        )
        resp = conn.getresponse()
        resp.read(1024)
        code = int(resp.status)
    except (OSError, http.client.HTTPException) as exc:
        return WebhookProbeOutcome(
            status="failed",
            http_status=None,
            last_error=f"Outbound delivery error: {type(exc).__name__}",
        )
    finally:
        conn.close()

    if 200 <= code < 300:
        return WebhookProbeOutcome(status="delivered", http_status=code, last_error=None)
    return WebhookProbeOutcome(
        status="failed",
        http_status=code,
        last_error=f"Endpoint responded with HTTP {code}",
    )


async def send_webhook_http_probe(prepared: PreparedWebhookTest) -> WebhookProbeOutcome:
    """Perform a real bounded HTTPS POST strictly outside the DB transaction with SSRF guard."""
    try:
        safe_url = await asyncio.to_thread(
            validate_public_webhook_url, prepared.url, resolve_dns=True
        )
    except ValueError as exc:
        return WebhookProbeOutcome(status="failed", http_status=None, last_error=str(exc))

    body = json.dumps(prepared.payload, sort_keys=True).encode("utf-8")
    return await asyncio.to_thread(
        _post_webhook_https_sync, safe_url, body, prepared.signature_header
    )


async def record_webhook_test_delivery(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    endpoint_id: UUID,
    prepared: PreparedWebhookTest,
    outcome: WebhookProbeOutcome,
    event_type: str = "connector.test",
) -> dict[str, Any]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.webhook_deliveries
                (tenant_id, endpoint_id, event_type, payload, signature_header,
                 status, http_status, attempts, last_error, delivered_at)
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, 1, %s,
                CASE WHEN %s = 'delivered' THEN now() ELSE NULL END
            )
            RETURNING id, endpoint_id, event_type, signature_header, status, http_status,
                      attempts, last_error, created_at, delivered_at
            """,
            (
                tenant_id,
                endpoint_id,
                event_type,
                Jsonb(prepared.payload),
                prepared.signature_header,
                outcome.status,
                outcome.http_status,
                outcome.last_error,
                outcome.status,
            ),
        )
        row = await cur.fetchone()
    assert row is not None  # noqa: S101
    return dict(row)


async def enqueue_webhook_test_delivery(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    endpoint_id: UUID,
) -> dict[str, Any]:
    """Queue a signed webhook test record without fabricating an HTTP 200 delivery."""
    prepared = await prepare_webhook_test_delivery(
        conn, tenant_id=tenant_id, endpoint_id=endpoint_id
    )
    outcome = WebhookProbeOutcome(
        status="queued",
        http_status=None,
        last_error="Outbound webhook HTTP delivery is disabled in local/test environment.",
    )
    return await record_webhook_test_delivery(
        conn,
        tenant_id=tenant_id,
        endpoint_id=endpoint_id,
        prepared=prepared,
        outcome=outcome,
    )


async def list_webhook_deliveries(
    conn: RuntimeConnection, *, tenant_id: UUID, limit: int = 20
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, endpoint_id, event_type, signature_header, status, http_status,
                   attempts, last_error, created_at, delivered_at
            FROM gba.webhook_deliveries
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, max(1, min(limit, 100))),
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


def _iso_or_none(val: Any) -> str | None:
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val) if val is not None else None
