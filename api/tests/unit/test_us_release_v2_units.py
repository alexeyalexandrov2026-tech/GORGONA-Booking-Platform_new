"""Unit tests for US Release v2.0: AI Business Architect, Connectors, R2 SigV4 & Media."""

from __future__ import annotations

import http.client
import json
from typing import Any

import pytest

from gorgona_booking.connectors.service import (
    ALLOWED_SCOPES,
    ALLOWED_WEBHOOK_EVENTS,
    CONNECTOR_CATALOG,
    _mask_config,
)
from gorgona_booking.media.service import _detect_image_type, _sigv4_headers
from gorgona_booking.onboarding.ai_architect import (
    AiBlueprintRequest,
    generate_business_blueprint,
)

pytestmark = pytest.mark.anyio


async def test_ai_business_architect_grounded_us_blueprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GBA_CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("GBA_CF_API_TOKEN", raising=False)
    bp = await generate_business_blueprint(
        AiBlueprintRequest(
            description=(
                "Apex Auto Detailing & PPF in Austin, TX. 4 bays, ceramic coating, tint, "
                "and full detailing open Tue-Sun."
            )
        )
    )
    assert bp.engine == "grounded"
    assert bp.timezone == "America/Chicago"
    assert 21 in bp.industry_ids
    assert len(bp.services) >= 3
    assert all(s.currency == "USD" for s in bp.services)
    assert "native_mcp" in bp.recommended_connectors
    assert "reserve_with_google" in bp.recommended_connectors


async def test_ai_business_architect_cloudflare_json_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResp:
        status = 200

        def read(self) -> bytes:
            content = json.dumps(
                {
                    "business_name": "Harbor Legal Group",
                    "location_name": "Miami Office",
                    "timezone": "America/New_York",
                    "industry_ids": [6],
                    "business_formats": ["b2b"],
                    "services": [
                        {
                            "name": "Corporate Strategy Review",
                            "duration_minutes": 60,
                            "price_usd": 350,
                        }
                    ],
                    "resources": [{"display_name": "Managing Partner", "kind": "artist"}],
                    "business_hours": [{"weekday": 1, "opens_hour": 9, "closes_hour": 17}],
                    "cancellation_summary": "24-hour notice required.",
                    "rationale": "Configured for US corporate legal practice.",
                }
            )
            return json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")

    class FakeConn:
        def __init__(self, host: str, port: int, timeout: float = 22.0) -> None:
            assert host == "api.cloudflare.com"

        def request(self, *args: Any, **kwargs: Any) -> None:
            return None

        def getresponse(self) -> FakeResp:
            return FakeResp()

        def close(self) -> None:
            return None

    monkeypatch.setenv("GBA_CF_ACCOUNT_ID", "acc-test")
    monkeypatch.setenv("GBA_CF_API_TOKEN", "tok-test")
    monkeypatch.setattr(http.client, "HTTPSConnection", FakeConn)

    bp = await generate_business_blueprint(
        AiBlueprintRequest(description="Boutique corporate law firm in Miami FL")
    )
    assert bp.engine == "cloudflare"
    assert bp.business_name == "Harbor Legal Group"
    assert bp.timezone == "America/New_York"
    assert bp.industry_ids == (6,)
    assert bp.services[0].price_cents == 35000
    assert "projects" in bp.enableable_module_ids


def test_connectors_catalog_and_masking() -> None:
    assert len(CONNECTOR_CATALOG) >= 8
    assert "mcp:read" in ALLOWED_SCOPES
    assert "booking.created" in ALLOWED_WEBHOOK_EVENTS
    masked = _mask_config({"realm_id": "123456", "api_secret": "supersecretvalue123"})
    assert masked["realm_id"] == "123456"
    assert "supersecretvalue123" not in masked["api_secret"]
    assert "***" in masked["api_secret"]


def test_r2_image_magic_validation_and_sigv4() -> None:
    assert _detect_image_type(b"\x89PNG\r\n\x1a\nxxxx") == ("image/png", "png")
    assert _detect_image_type(b"\xff\xd8\xff\xe0xxxx") == ("image/jpeg", "jpg")
    assert _detect_image_type(b"RIFF\x00\x00\x00\x00WEBPxxxx") == ("image/webp", "webp")
    with pytest.raises(ValueError, match="PNG, JPEG, or WEBP only"):
        _detect_image_type(b"<svg><script>alert(1)</script></svg>")

    hdrs = _sigv4_headers(
        method="PUT",
        host="acc.r2.cloudflarestorage.com",
        canonical_uri="/gorgona-media/tenants/t1/logo/a.png",
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        access_key="AKIA_TEST",
        secret_key="SECRET_TEST",
        content_type="image/png",
    )
    assert hdrs["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIA_TEST/")
    assert "x-amz-date" in hdrs
