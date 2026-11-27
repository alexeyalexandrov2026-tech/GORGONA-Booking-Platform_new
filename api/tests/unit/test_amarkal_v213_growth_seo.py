"""Unit tests for AMARKAL v2.13.0 public B2B demo lead intake & SEO framing cache."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from gorgona_booking.api import framing, public_demo

pytestmark = pytest.mark.anyio


async def test_public_demo_request_dispatches_and_traps_honeypot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GBA_NOTIFICATIONS_MODE", "sandbox")
    app = FastAPI()
    app.include_router(public_demo.router)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/v1/public/demo-requests",
            json={
                "full_name": "Jordan Rivera",
                "company_name": "Midwest Freight Logistics LLC",
                "work_email": "jordan@midwestfreight.us",
                "industry": "Transport & Logistics",
                "team_size": "25-100",
                "notes": "Looking to consolidate dispatch, CPQ quotes, and FIN-03 billing.",
                "source_path": "/industries/freight-logistics/",
            },
        )
        assert res.status_code == 201
        body = res.json()
        assert body["received"] is True
        assert body["reference_id"].startswith("DEMO-")

        # Invalid email refused
        bad = await client.post(
            "/v1/public/demo-requests",
            json={
                "full_name": "Jordan Rivera",
                "company_name": "Midwest Freight LLC",
                "work_email": "not-an-email",
                "industry": "Transport & Logistics",
            },
        )
        assert bad.status_code == 422

        # Honeypot filled -> synthetic 201 without error
        bot = await client.post(
            "/v1/public/demo-requests",
            json={
                "full_name": "Bot Name",
                "company_name": "Bot LLC",
                "work_email": "bot@invalid",
                "industry": "Other",
                "website": "https://spam.example",
            },
        )
        assert bot.status_code == 201


def test_industry_seo_pages_are_edge_cacheable() -> None:
    for path in (
        "/industries/freight-logistics/",
        "/industries/construction/",
        "/industries/commercial-property/",
        "/industries/equipment-rental/",
        "/status/",
    ):
        assert path in framing._PUBLIC_CACHEABLE_HTML_PATHS
