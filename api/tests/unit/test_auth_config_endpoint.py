"""Unit tests for public runtime /auth-config.json endpoint (fail-closed when unset)."""

import httpx
import pytest
from fastapi.responses import JSONResponse

from gorgona_booking.api.app import create_app
from gorgona_booking.config import Settings

pytestmark = pytest.mark.anyio


async def test_auth_config_returns_404_when_client_id_not_configured() -> None:
    app = create_app(Settings(environment="test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/auth-config.json")
    assert res.status_code == 404


async def test_auth_config_returns_public_oidc_settings_when_configured() -> None:
    app = create_app(
        Settings(
            environment="test",
            auth_issuer="https://login.microsoftonline.com/example/v2.0",
            auth_audience="00000000-0000-0000-0000-000000000001",
            auth_jwks_url="https://login.microsoftonline.com/example/discovery/v2.0/keys",
            auth_client_id="00000000-0000-0000-0000-000000000001",
            auth_scope="openid profile email api://00000000-0000-0000-0000-000000000001/access_as_user",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/auth-config.json")
    assert res.status_code == 200
    assert res.headers.get("cache-control") == "no-store"
    assert res.json() == {
        "authority": "https://login.microsoftonline.com/example/v2.0",
        "client_id": "00000000-0000-0000-0000-000000000001",
        "scope": "openid profile email api://00000000-0000-0000-0000-000000000001/access_as_user",
    }


async def test_auth_config_allows_test_override_when_unset() -> None:
    app = create_app(Settings(environment="test"))

    @app.get("/auth-config.json")
    async def test_override() -> JSONResponse:
        return JSONResponse({"authority": "http://127.0.0.1:1234", "client_id": "test"})

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/auth-config.json")
    assert res.status_code == 200
    assert res.json()["client_id"] == "test"
