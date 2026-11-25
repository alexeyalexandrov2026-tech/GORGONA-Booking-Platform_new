"""Unit tests for Google Cloud Load Balancer trusted proxy and SMTP email portability."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request

from gorgona_booking.api.trusted_proxy import GoogleCloudLoadBalancerMiddleware
from gorgona_booking.config import Settings, UnsafeEnvironmentError, assert_environment_allowed
from gorgona_booking.notifications.transports import (
    SmtpEmailTransport,
    resolve_notification_transports,
)

_SECRET = "gorgona-gcp-edge-secret-32-chars-minimum-0123456789"


def test_gcp_settings_validation_and_environment_gate() -> None:
    jwks = (
        "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
    )
    base = {
        "GBA_ENV": "staging",
        "GBA_TRUSTED_PROXY": "google_cloud_lb",
        "GBA_EDGE_SECRET": _SECRET,
        "GBA_AUTH_ISSUER": "https://securetoken.google.com/gorgona-prod",
        "GBA_AUTH_AUDIENCE": "gorgona-prod",
        "GBA_AUTH_JWKS_URL": jwks,
    }
    s = Settings.from_env(base)
    assert s.trusted_proxy == "google_cloud_lb"
    assert_environment_allowed(s)

    with pytest.raises(ValueError, match="GBA_EDGE_SECRET"):
        Settings.from_env({**base, "GBA_EDGE_SECRET": "too-short"})

    prod = Settings.from_env({**base, "GBA_ENV": "production"})
    with pytest.raises(UnsafeEnvironmentError, match="GBA_PRODUCTION_AUTHORIZATION"):
        assert_environment_allowed(prod)

    prod_ok = Settings.from_env(
        {
            **base,
            "GBA_ENV": "production",
            "GBA_PRODUCTION_AUTHORIZATION": "PA-20261125-gcp-launch",
        }
    )
    assert_environment_allowed(prod_ok)


@pytest.mark.anyio
async def test_google_cloud_lb_middleware_fail_closed_and_host_rewrite() -> None:
    app = FastAPI()

    @app.get("/health/ready")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/whoami")
    async def whoami(request: Request) -> dict[str, str]:
        return {
            "host": request.headers.get("host", ""),
            "scheme": request.url.scheme,
            "secret_leaked": str("x-gorgona-edge-secret" in request.headers),
        }

    app.add_middleware(GoogleCloudLoadBalancerMiddleware, edge_secret=_SECRET)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal.run.app") as client:
        r_health = await client.get("/health/ready")
        assert r_health.status_code == 200

        r_missing = await client.get("/whoami")
        assert r_missing.status_code == 404
        r_bad = await client.get("/whoami", headers={"X-Gorgona-Edge-Secret": "wrong"})
        assert r_bad.status_code == 404

        r_ok = await client.get(
            "/whoami",
            headers={
                "X-Gorgona-Edge-Secret": _SECRET,
                "X-Forwarded-Host": "salon-a.gorgona.app",
                "X-Forwarded-Proto": "https",
            },
        )
        assert r_ok.status_code == 200
        body = r_ok.json()
        assert body["host"] == "salon-a.gorgona.app"
        assert body["scheme"] == "https"
        assert body["secret_leaked"] == "False"


def test_smtp_cloud_agnostic_email_transport_resolution() -> None:
    transports, readiness = resolve_notification_transports(
        {
            "GBA_NOTIFICATIONS_MODE": "live",
            "GBA_EMAIL_PROVIDER": "smtp",
            "GBA_SMTP_HOST": "smtp.sendgrid.net",
            "GBA_SMTP_PORT": "587",
            "GBA_SMTP_USERNAME": "apikey",
            "GBA_SMTP_PASSWORD": "sg-test-password",
            "GBA_SMTP_SENDER": "noreply@gorgona.app",
        }
    )
    assert isinstance(transports["email"], SmtpEmailTransport)
    assert readiness["email"]["mode"] == "live"
    assert readiness["email"]["provider"] == "smtp_email"
    assert readiness["email"]["production_credentials_configured"] is True
