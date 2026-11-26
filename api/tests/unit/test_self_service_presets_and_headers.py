"""Unit tests for 39-industry onboarding presets and HTTP security headers."""

import httpx
import pytest
from fastapi import FastAPI

from gorgona_booking.api.framing import FramingPolicyMiddleware
from gorgona_booking.business.catalog import INDUSTRIES
from gorgona_booking.business.modules import MODULES_BY_ID
from gorgona_booking.business.onboarding_presets import (
    INDUSTRY_RECOMMENDED_MODULES,
    all_industry_presets,
    resolve_onboarding_modules,
)

pytestmark = pytest.mark.anyio


def test_every_one_of_39_industries_has_valid_preset_and_never_auto_enables_unverified() -> None:
    assert set(INDUSTRY_RECOMMENDED_MODULES.keys()) == {i.id for i in INDUSTRIES}
    presets = all_industry_presets()
    assert len(presets) == 39
    for preset in presets:
        assert len(preset.enableable_module_ids) >= 1
        for mid in preset.enableable_module_ids:
            mod = MODULES_BY_ID[mid]
            assert mod.enableable, f"{mid} must be enableable"
        for mid in preset.pending_module_ids:
            mod = MODULES_BY_ID[mid]
            assert not mod.enableable, f"{mid} must not be enableable"

    multi = resolve_onboarding_modules((1, 19, 24))
    assert "booking_resources" in multi.enableable_module_ids
    assert "finance_documents" in multi.enableable_module_ids
    assert "finance" in multi.enableable_module_ids
    assert "counterparties" in multi.enableable_module_ids
    for mid in multi.enableable_module_ids:
        assert MODULES_BY_ID[mid].enableable


async def test_framing_middleware_adds_nosniff_and_referrer_policy() -> None:
    app = FastAPI()
    app.add_middleware(FramingPolicyMiddleware, allow_loopback=True)

    @app.get("/v1/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/v1/ping")
    assert res.status_code == 200
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert res.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert res.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"
    assert res.headers.get("strict-transport-security") is None
    assert "frame-ancestors 'none'" in res.headers.get("content-security-policy", "")


async def test_framing_middleware_sets_hsts_on_https_or_production() -> None:
    app = FastAPI()
    app.add_middleware(FramingPolicyMiddleware, allow_loopback=False)

    @app.get("/v1/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/v1/ping")
    assert res.status_code == 200
    assert res.headers.get("strict-transport-security") == "max-age=31536000; includeSubDomains"
    assert res.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"
