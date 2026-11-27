"""Open Plugin Engine (Custom Plugin Manifests) for AMARKAL App Hub.

Allows any tenant organization to register external HTTPS APIs, Remote MCP servers,
Webhook Bridges, or Custom OAuth2 apps without running untrusted code inside AMARKAL's
multi-tenant runtime. Credentials are encrypted with AES-256-GCM in `tenant_connector_secrets`
and outbound probes enforce HTTPS + anti-SSRF public IP validation outside DB transactions.
"""

from __future__ import annotations

import asyncio
import http.client
import re
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from gorgona_booking.connectors.service import (
    ALLOWED_SCOPES,
    ALLOWED_WEBHOOK_EVENTS,
    validate_public_webhook_url,
)
from gorgona_booking.connectors.vault import (
    delete_tenant_secret,
    get_tenant_secret_decrypted,
    upsert_tenant_secret,
)
from gorgona_booking.db.pool import RuntimeConnection

PluginProtocol = Literal["https_api", "mcp_remote", "webhook_bridge", "oauth2_custom"]
PluginAuthScheme = Literal["Bearer", "ApiKey", "None"]
PluginStatus = Literal["active", "paused"]

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_HEADER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{1,63}$")
_FORBIDDEN_HEADER_NAMES = frozenset(
    {"host", "content-length", "transfer-encoding", "connection", "cookie", "x-forwarded-for"}
)


@dataclass(frozen=True)
class CustomPluginView:
    id: UUID
    slug: str
    display_name: str
    category: str
    protocol: PluginProtocol
    endpoint_url: str
    auth_header_name: str
    auth_scheme: PluginAuthScheme
    scopes: list[str]
    subscribed_events: list[str]
    description: str
    has_secret: bool
    secret_hint: str | None
    status: PluginStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PreparedPluginProbe:
    plugin_id: UUID
    slug: str
    display_name: str
    endpoint_url: str
    protocol: PluginProtocol
    auth_header_name: str
    auth_scheme: PluginAuthScheme
    credential: str | None


@dataclass(frozen=True)
class PluginProbeOutcome:
    ok: bool
    status: Literal["reachable", "unreachable", "local_validated"]
    http_status: int | None
    latency_ms: int
    message: str


def _plugin_connector_key(slug: str) -> str:
    return f"plugin_{slug}"


def _clean_slug(raw: str) -> str:
    clean = raw.strip().lower()
    if not _SLUG_RE.match(clean):
        raise ValueError(
            "Plugin slug must be 2-63 lowercase chars (a-z, 0-9, _ or -) starting with a-z/0-9."
        )
    return clean


def _clean_header_name(raw: str) -> str:
    clean = raw.strip()
    if not _HEADER_NAME_RE.match(clean) or clean.lower() in _FORBIDDEN_HEADER_NAMES:
        raise ValueError("Invalid authentication header name.")
    return clean


def _clean_scopes(scopes: list[str]) -> list[str]:
    clean = sorted({s.strip() for s in scopes if s.strip()})
    if not set(clean).issubset(ALLOWED_SCOPES):
        raise ValueError(f"Scopes must be a subset of {sorted(ALLOWED_SCOPES)}")
    return clean


def _clean_events(events: list[str]) -> list[str]:
    clean = sorted({e.strip() for e in events if e.strip()})
    if not set(clean).issubset(ALLOWED_WEBHOOK_EVENTS):
        raise ValueError(f"Subscribed events must be a subset of {sorted(ALLOWED_WEBHOOK_EVENTS)}")
    return clean


def _row_to_view(r: dict[str, Any]) -> CustomPluginView:
    return CustomPluginView(
        id=UUID(str(r["id"])),
        slug=str(r["slug"]),
        display_name=str(r["display_name"]),
        category=str(r["category"]),
        protocol=r["protocol"],
        endpoint_url=str(r["endpoint_url"]),
        auth_header_name=str(r["auth_header_name"]),
        auth_scheme=r["auth_scheme"],
        scopes=list(r["scopes"] or []),
        subscribed_events=list(r["subscribed_events"] or []),
        description=str(r["description"] or ""),
        has_secret=bool(r["has_secret"]),
        secret_hint=str(r["secret_hint"]) if r["secret_hint"] else None,
        status=r["status"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def list_custom_plugins(
    conn: RuntimeConnection, *, tenant_id: UUID
) -> list[CustomPluginView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, slug, display_name, category, protocol, endpoint_url,
                   auth_header_name, auth_scheme, scopes, subscribed_events,
                   description, has_secret, secret_hint, status, created_at, updated_at
            FROM gba.custom_plugins
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_view(dict(r)) for r in rows]


async def create_custom_plugin(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    slug: str,
    display_name: str,
    category: str,
    protocol: PluginProtocol,
    endpoint_url: str,
    auth_header_name: str,
    auth_scheme: PluginAuthScheme,
    auth_credential: str | None,
    scopes: list[str],
    subscribed_events: list[str],
    description: str,
    user_id: UUID | None,
    environment: str,
) -> CustomPluginView:
    clean_slug = _clean_slug(slug)
    clean_name = display_name.strip()[:120]
    if len(clean_name) < 2:
        raise ValueError("Display name must be at least 2 characters.")
    clean_cat = (category.strip() or "Custom Integration")[:64]
    clean_url = validate_public_webhook_url(endpoint_url, resolve_dns=False)
    clean_header = _clean_header_name(auth_header_name or "Authorization")
    clean_scopes = _clean_scopes(scopes)
    clean_events = _clean_events(subscribed_events)
    clean_desc = description.strip()[:400]

    secret_hint: str | None = None
    has_secret = False
    clean_cred = (auth_credential or "").strip()
    if auth_scheme != "None" and clean_cred:
        meta = await upsert_tenant_secret(
            conn,
            tenant_id=tenant_id,
            connector_id=_plugin_connector_key(clean_slug),
            kind="plugin_credential",
            plaintext=clean_cred,
            metadata_public={"slug": clean_slug, "protocol": protocol},
            user_id=user_id,
            environment=environment,
        )
        has_secret = True
        secret_hint = meta.key_hint

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO gba.custom_plugins
                    (tenant_id, slug, display_name, category, protocol, endpoint_url,
                     auth_header_name, auth_scheme, scopes, subscribed_events, description,
                     has_secret, secret_hint, status, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', %s)
                RETURNING id, slug, display_name, category, protocol, endpoint_url,
                          auth_header_name, auth_scheme, scopes, subscribed_events,
                          description, has_secret, secret_hint, status, created_at, updated_at
                """,
                (
                    tenant_id,
                    clean_slug,
                    clean_name,
                    clean_cat,
                    protocol,
                    clean_url,
                    clean_header,
                    auth_scheme,
                    clean_scopes,
                    clean_events,
                    clean_desc,
                    has_secret,
                    secret_hint,
                    user_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as exc:
        raise ValueError(f"Custom plugin with slug '{clean_slug}' already exists.") from exc
    if row is None:
        raise RuntimeError("Failed to create custom plugin.")
    return _row_to_view(dict(row))


async def update_custom_plugin(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    plugin_id: UUID,
    status: PluginStatus | None,
    endpoint_url: str | None,
    description: str | None,
    auth_credential: str | None,
    clear_secret: bool,
    user_id: UUID | None,
    environment: str,
) -> CustomPluginView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, slug, display_name, category, protocol, endpoint_url,
                   auth_header_name, auth_scheme, scopes, subscribed_events,
                   description, has_secret, secret_hint, status, created_at, updated_at
            FROM gba.custom_plugins
            WHERE tenant_id = %s AND id = %s
            """,
            (tenant_id, plugin_id),
        )
        existing = await cur.fetchone()
    if existing is None:
        raise LookupError("Custom plugin not found.")

    slug = str(existing["slug"])
    next_status = status if status is not None else existing["status"]
    next_url = (
        validate_public_webhook_url(endpoint_url, resolve_dns=False)
        if endpoint_url is not None
        else str(existing["endpoint_url"])
    )
    next_desc = (
        description.strip()[:400] if description is not None else str(existing["description"] or "")
    )
    next_has_secret = bool(existing["has_secret"])
    next_hint = str(existing["secret_hint"]) if existing["secret_hint"] else None

    if clear_secret:
        await delete_tenant_secret(
            conn,
            tenant_id=tenant_id,
            connector_id=_plugin_connector_key(slug),
            kind="plugin_credential",
        )
        next_has_secret = False
        next_hint = None
    elif auth_credential is not None and auth_credential.strip():
        meta = await upsert_tenant_secret(
            conn,
            tenant_id=tenant_id,
            connector_id=_plugin_connector_key(slug),
            kind="plugin_credential",
            plaintext=auth_credential.strip(),
            metadata_public={"slug": slug, "protocol": existing["protocol"]},
            user_id=user_id,
            environment=environment,
        )
        next_has_secret = True
        next_hint = meta.key_hint

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.custom_plugins
            SET status = %s,
                endpoint_url = %s,
                description = %s,
                has_secret = %s,
                secret_hint = %s,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, slug, display_name, category, protocol, endpoint_url,
                      auth_header_name, auth_scheme, scopes, subscribed_events,
                      description, has_secret, secret_hint, status, created_at, updated_at
            """,
            (
                next_status,
                next_url,
                next_desc,
                next_has_secret,
                next_hint,
                tenant_id,
                plugin_id,
            ),
        )
        updated = await cur.fetchone()
    if updated is None:
        raise LookupError("Custom plugin not found.")
    return _row_to_view(dict(updated))


async def delete_custom_plugin(
    conn: RuntimeConnection, *, tenant_id: UUID, plugin_id: UUID
) -> bool:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "DELETE FROM gba.custom_plugins WHERE tenant_id = %s AND id = %s RETURNING slug",
            (tenant_id, plugin_id),
        )
        row = await cur.fetchone()
    if row is None:
        return False
    await delete_tenant_secret(
        conn,
        tenant_id=tenant_id,
        connector_id=_plugin_connector_key(str(row["slug"])),
        kind="plugin_credential",
    )
    return True


async def prepare_custom_plugin_probe(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    plugin_id: UUID,
    environment: str,
) -> PreparedPluginProbe:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, slug, display_name, endpoint_url, protocol,
                   auth_header_name, auth_scheme, has_secret
            FROM gba.custom_plugins
            WHERE tenant_id = %s AND id = %s
            """,
            (tenant_id, plugin_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise LookupError("Custom plugin not found.")
    credential: str | None = None
    if bool(row["has_secret"]):
        loaded = await get_tenant_secret_decrypted(
            conn,
            tenant_id=tenant_id,
            connector_id=_plugin_connector_key(str(row["slug"])),
            kind="plugin_credential",
            environment=environment,
        )
        if loaded is not None:
            credential = loaded[0]
    return PreparedPluginProbe(
        plugin_id=UUID(str(row["id"])),
        slug=str(row["slug"]),
        display_name=str(row["display_name"]),
        endpoint_url=str(row["endpoint_url"]),
        protocol=row["protocol"],
        auth_header_name=str(row["auth_header_name"]),
        auth_scheme=row["auth_scheme"],
        credential=credential,
    )


def _probe_plugin_sync(prepared: PreparedPluginProbe) -> PluginProbeOutcome:
    start = time.monotonic()
    try:
        safe_url = validate_public_webhook_url(prepared.endpoint_url, resolve_dns=True)
    except ValueError as exc:
        return PluginProbeOutcome(
            ok=False,
            status="unreachable",
            http_status=None,
            latency_ms=int((time.monotonic() - start) * 1000),
            message=str(exc),
        )
    parsed = urlparse(safe_url)
    host = parsed.hostname or ""
    port = parsed.port or 443
    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"
    headers: dict[str, str] = {
        "User-Agent": "AMARKAL-Plugin-Probe/1.0",
        "Accept": "application/json",
    }
    if prepared.credential and prepared.auth_scheme != "None":
        if prepared.auth_scheme == "Bearer":
            headers[prepared.auth_header_name] = f"Bearer {prepared.credential}"
        else:
            headers[prepared.auth_header_name] = prepared.credential

    conn = http.client.HTTPSConnection(
        host, port, timeout=6.0, context=ssl.create_default_context()
    )
    try:
        if prepared.protocol == "mcp_remote":
            headers["Content-Type"] = "application/json"
            body = b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
            conn.request("POST", target, body=body, headers=headers)
        else:
            conn.request("HEAD", target, headers=headers)
        resp = conn.getresponse()
        resp.read(1024)
        code = int(resp.status)
    except (OSError, http.client.HTTPException) as exc:
        return PluginProbeOutcome(
            ok=False,
            status="unreachable",
            http_status=None,
            latency_ms=int((time.monotonic() - start) * 1000),
            message=f"Connection error: {type(exc).__name__}",
        )
    finally:
        conn.close()

    elapsed_ms = int((time.monotonic() - start) * 1000)
    if 200 <= code < 400:
        return PluginProbeOutcome(
            ok=True,
            status="reachable",
            http_status=code,
            latency_ms=elapsed_ms,
            message=f"Endpoint responded with HTTP {code} in {elapsed_ms} ms.",
        )
    return PluginProbeOutcome(
        ok=False,
        status="unreachable",
        http_status=code,
        latency_ms=elapsed_ms,
        message=f"Endpoint responded with HTTP {code}.",
    )


async def execute_custom_plugin_probe(
    prepared: PreparedPluginProbe, *, environment: str
) -> PluginProbeOutcome:
    """Run bounded SSRF-safe HTTPS probe strictly outside any DB transaction."""
    if environment not in ("staging", "production"):
        return PluginProbeOutcome(
            ok=True,
            status="local_validated",
            http_status=None,
            latency_ms=0,
            message=(
                f"Manifest and HTTPS endpoint validated locally for '{prepared.display_name}'. "
                "Outbound probe runs in staging/production."
            ),
        )
    return await asyncio.to_thread(_probe_plugin_sync, prepared)
