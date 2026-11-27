"""Optional OAuth2 connector flow for AMARKAL App Hub (QuickBooks Online, Google Calendar,
Xero, Slack). Strict opt-in per organization, HMAC-SHA256 signed anti-CSRF state, and stdlib
HTTPS token exchange strictly outside database transactions (zero extra runtime dependencies).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import http.client
import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse
from uuid import UUID

OAUTH_STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class OAuthProviderSpec:
    connector_id: str
    display_name: str
    authorize_url: str
    exchange_url: str
    scopes: tuple[str, ...]
    client_id_env: str
    credential_env: str
    sandbox_authorize_url: str | None = None
    sandbox_env_flag: str | None = None


OAUTH_PROVIDERS: dict[str, OAuthProviderSpec] = {
    "quickbooks_online": OAuthProviderSpec(
        connector_id="quickbooks_online",
        display_name="QuickBooks Online (US)",
        authorize_url="https://appcenter.intuit.com/connect/oauth2",
        exchange_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
        scopes=("com.intuit.quickbooks.accounting",),
        client_id_env="GBA_QBO_CLIENT_ID",
        credential_env="GBA_QBO_CLIENT_SECRET",
        sandbox_env_flag="GBA_QBO_SANDBOX",
    ),
    "google_calendar": OAuthProviderSpec(
        connector_id="google_calendar",
        display_name="Google Calendar",
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        exchange_url="https://oauth2.googleapis.com/token",
        scopes=(
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/calendar.readonly",
        ),
        client_id_env="GBA_GOOGLE_OAUTH_CLIENT_ID",
        credential_env="GBA_GOOGLE_OAUTH_CLIENT_SECRET",
    ),
    "xero_accounting": OAuthProviderSpec(
        connector_id="xero_accounting",
        display_name="Xero Accounting",
        authorize_url="https://login.xero.com/identity/connect/authorize",
        exchange_url="https://identity.xero.com/connect/token",
        scopes=("offline_access", "accounting.transactions", "accounting.contacts"),
        client_id_env="GBA_XERO_CLIENT_ID",
        credential_env="GBA_XERO_CLIENT_SECRET",
    ),
    "slack_workspace": OAuthProviderSpec(
        connector_id="slack_workspace",
        display_name="Slack Workspace",
        authorize_url="https://slack.com/oauth/v2/authorize",
        exchange_url="https://slack.com/api/oauth.v2.access",
        scopes=("chat:write", "incoming-webhook"),
        client_id_env="GBA_SLACK_CLIENT_ID",
        credential_env="GBA_SLACK_CLIENT_SECRET",
    ),
}


def provider_credentials(connector_id: str) -> tuple[str | None, str | None]:
    spec = OAUTH_PROVIDERS.get(connector_id)
    if spec is None:
        return None, None
    cid = os.environ.get(spec.client_id_env, "").strip() or None
    csec = os.environ.get(spec.credential_env, "").strip() or None
    return cid, csec


def is_oauth_provider_configured(connector_id: str) -> bool:
    cid, csec = provider_credentials(connector_id)
    return bool(cid and csec)


def _state_signing_secret(*, environment: str) -> bytes:
    raw = (
        os.environ.get("GBA_OAUTH_STATE_SECRET", "").strip()
        or os.environ.get("GBA_EDGE_SECRET", "").strip()
    )
    if raw:
        return raw.encode("utf-8")
    if environment in ("staging", "production"):
        raise RuntimeError("OAuth state signing secret is not configured in production.")
    return b"amarkal-local-dev-oauth-state-secret"


def create_oauth_state(
    *,
    tenant_id: UUID,
    connector_id: str,
    user_id: UUID | None,
    environment: str,
    now_ts: int | None = None,
) -> str:
    """Return an HMAC-SHA256 signed URL-safe OAuth2 state token with a 10-minute TTL."""
    issued = int(now_ts if now_ts is not None else time.time())
    payload = {
        "tid": str(tenant_id),
        "cid": connector_id,
        "uid": str(user_id) if user_id else None,
        "iat": issued,
        "exp": issued + OAUTH_STATE_TTL_SECONDS,
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    sig = hmac.new(
        _state_signing_secret(environment=environment),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{sig}"


def verify_oauth_state(
    state: str,
    *,
    expected_connector_id: str,
    environment: str,
    now_ts: int | None = None,
) -> tuple[UUID, UUID | None]:
    """Validate signature, expiry, and connector binding; returns (tenant_id, user_id)."""
    parts = state.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("Malformed OAuth state.")
    encoded, sig = parts
    expected_sig = hmac.new(
        _state_signing_secret(environment=environment),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid OAuth state signature.")
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Corrupt OAuth state payload.") from exc
    if payload.get("cid") != expected_connector_id:
        raise ValueError("OAuth state connector mismatch.")
    now_val = int(now_ts if now_ts is not None else time.time())
    if int(payload.get("exp") or 0) < now_val:
        raise ValueError("OAuth state expired. Please start the connection again.")
    tid = UUID(str(payload["tid"]))
    uid = UUID(str(payload["uid"])) if payload.get("uid") else None
    return tid, uid


def build_oauth_authorization_url(
    *,
    connector_id: str,
    redirect_uri: str,
    state: str,
) -> str:
    spec = OAUTH_PROVIDERS.get(connector_id)
    if spec is None:
        raise ValueError(f"Unsupported OAuth connector: {connector_id}")
    cid, _ = provider_credentials(connector_id)
    if not cid:
        raise ValueError(f"OAuth credentials are not configured for {spec.display_name}.")
    params: dict[str, str] = {
        "client_id": cid,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(spec.scopes),
        "state": state,
    }
    if connector_id == "google_calendar":
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    return f"{spec.authorize_url}?{urlencode(params)}"


def _exchange_code_sync(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    use_basic_auth: bool,
) -> dict[str, Any]:
    parsed = urlparse(token_url)
    host = parsed.hostname or ""
    path = parsed.path or "/"
    form: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    if use_basic_auth:
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {basic}"
    else:
        form["client_id"] = client_id
        form["client_secret"] = client_secret

    conn = http.client.HTTPSConnection(host, parsed.port or 443, timeout=12.0)
    try:
        conn.request("POST", path, body=urlencode(form).encode("utf-8"), headers=headers)
        resp = conn.getresponse()
        raw = resp.read(65536).decode("utf-8", errors="replace")
        if resp.status >= 400:
            raise RuntimeError(f"OAuth token exchange rejected with HTTP {resp.status}.")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("OAuth token endpoint returned unexpected response.")
        return data
    finally:
        conn.close()


async def exchange_oauth_code(
    *,
    connector_id: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    spec = OAUTH_PROVIDERS.get(connector_id)
    if spec is None:
        raise ValueError(f"Unsupported OAuth connector: {connector_id}")
    cid, csec = provider_credentials(connector_id)
    if not cid or not csec:
        raise RuntimeError(f"OAuth credentials are not configured for {spec.display_name}.")
    return await asyncio.to_thread(
        _exchange_code_sync,
        token_url=spec.exchange_url,
        client_id=cid,
        client_secret=csec,
        code=code,
        redirect_uri=redirect_uri,
        use_basic_auth=connector_id in ("quickbooks_online", "xero_accounting"),
    )
