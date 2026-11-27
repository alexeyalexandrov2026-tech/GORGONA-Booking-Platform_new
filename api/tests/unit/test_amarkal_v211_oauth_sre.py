"""Unit tests for AMARKAL v2.11.0 optional OAuth2 connectors and SRE /v1/status."""

from __future__ import annotations

from uuid import uuid7

import httpx
import pytest
from fastapi import FastAPI

from gorgona_booking.api import health as health_api
from gorgona_booking.connectors.oauth import (
    OAUTH_PROVIDERS,
    build_oauth_authorization_url,
    create_oauth_state,
    is_oauth_provider_configured,
    verify_oauth_state,
)
from gorgona_booking.connectors.service import CONNECTORS_BY_ID

pytestmark = pytest.mark.anyio


def test_oauth_state_signing_verification_and_tamper_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GBA_OAUTH_STATE_SECRET", "test-secret-0123456789abcdef0123456789")
    tid = uuid7()
    uid = uuid7()
    state = create_oauth_state(
        tenant_id=tid,
        connector_id="quickbooks_online",
        user_id=uid,
        environment="production",
        now_ts=1_700_000_000,
    )
    got_tid, got_uid = verify_oauth_state(
        state,
        expected_connector_id="quickbooks_online",
        environment="production",
        now_ts=1_700_000_120,
    )
    assert got_tid == tid
    assert got_uid == uid

    # Connector mismatch rejected
    with pytest.raises(ValueError, match="connector mismatch"):
        verify_oauth_state(
            state,
            expected_connector_id="google_calendar",
            environment="production",
            now_ts=1_700_000_120,
        )

    # Expired state rejected
    with pytest.raises(ValueError, match="expired"):
        verify_oauth_state(
            state,
            expected_connector_id="quickbooks_online",
            environment="production",
            now_ts=1_700_001_000,
        )

    # Tampered signature rejected
    with pytest.raises(ValueError, match="signature"):
        verify_oauth_state(
            state[:-1] + ("0" if state[-1] != "0" else "1"),
            expected_connector_id="quickbooks_online",
            environment="production",
            now_ts=1_700_000_120,
        )


def test_optional_oauth_providers_and_authorization_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert {"quickbooks_online", "google_calendar", "xero_accounting", "slack_workspace"} <= set(
        OAUTH_PROVIDERS
    )
    assert "email_marketing_byok" in CONNECTORS_BY_ID
    monkeypatch.delenv("GBA_QBO_CLIENT_ID", raising=False)
    monkeypatch.delenv("GBA_QBO_CLIENT_SECRET", raising=False)
    assert is_oauth_provider_configured("quickbooks_online") is False

    monkeypatch.setenv("GBA_QBO_CLIENT_ID", "qbo-client-123")
    monkeypatch.setenv("GBA_QBO_CLIENT_SECRET", "qbo-secret-456")
    assert is_oauth_provider_configured("quickbooks_online") is True
    url = build_oauth_authorization_url(
        connector_id="quickbooks_online",
        redirect_uri="https://www.amarkal-platform.com/v1/connectors/oauth/quickbooks_online/callback",
        state="signed.state",
    )
    assert url.startswith("https://appcenter.intuit.com/connect/oauth2?")
    assert "client_id=qbo-client-123" in url
    assert "state=signed.state" in url


async def test_public_sre_status_reports_operational_and_degraded() -> None:
    app = FastAPI()
    app.include_router(health_api.router)

    async def ok_probe() -> None:
        return None

    app.state.readiness_probe = ok_probe
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res_ok = await client.get("/v1/status")
    assert res_ok.status_code == 200
    body = res_ok.json()
    assert body["overall"] == "operational"
    assert body["operator"] == "Alexey AAA Logistics LLC"
    assert len(body["components"]) == 5

    async def fail_probe() -> None:
        raise RuntimeError("db connection lost")

    app.state.readiness_probe = fail_probe
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res_deg = await client.get("/v1/status")
    assert res_deg.status_code == 503
    assert res_deg.json()["overall"] == "degraded"
    assert "db connection lost" not in res_deg.text
