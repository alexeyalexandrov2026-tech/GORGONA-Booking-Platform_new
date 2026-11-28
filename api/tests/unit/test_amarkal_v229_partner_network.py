"""Unit tests for AMARKAL v2.29.0 Public Partner & Certified Integrator Network API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gorgona_booking.api.partner_network import (
    PARTNER_DIRECTORY_LISTINGS,
    filter_partner_listings,
    router,
)


def test_filter_partner_listings_by_track_and_query() -> None:
    assert len(PARTNER_DIRECTORY_LISTINGS) == 4
    cpa_only = filter_partner_listings(track="cpa_finance_holding")
    assert len(cpa_only) == 1
    assert "Holding" in cpa_only[0].practice_name

    freight_hits = filter_partner_listings(query="484")
    assert len(freight_hits) == 1
    assert freight_hits[0].slug == "amarkal-direct-midwest-freight"


def test_public_partner_directory_and_application_honeypot() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r_dir = client.get("/v1/public/partners?q=NetSuite")
    assert r_dir.status_code == 200
    body = r_dir.json()
    assert len(body["listings"]) >= 1
    assert len(body["certification_tiers"]) == 3

    # Valid application
    r_ok = client.post(
        "/v1/public/partners/apply",
        json={
            "company_name": "Midwest ERP Advisory LLC",
            "contact_name": "Dana Mercer",
            "work_email": "dana@midwesterp.example",
            "us_state": "IL",
            "partner_track": "cpa_finance_holding",
            "naics_focus": "484 Freight & Multi-Entity CPA",
            "team_size": "10-25",
            "experience_summary": "10 years NetSuite & QuickBooks migrations.",
        },
    )
    assert r_ok.status_code == 201
    assert r_ok.json()["received"] is True
    assert r_ok.json()["reference_id"].startswith("PARTNER-")

    # Honeypot bot trapped cleanly
    r_bot = client.post(
        "/v1/public/partners/apply",
        json={
            "company_name": "SpamBot Inc",
            "contact_name": "Bot",
            "work_email": "not-even-checked",
            "us_state": "TX",
            "naics_focus": "Spam",
            "website": "https://spam.example",
        },
    )
    assert r_bot.status_code == 201
    assert r_bot.json()["received"] is True

    # Invalid email rejected when honeypot is empty
    r_bad = client.post(
        "/v1/public/partners/apply",
        json={
            "company_name": "Valid Firm",
            "contact_name": "Alex",
            "work_email": "invalid-email",
            "us_state": "NY",
            "naics_focus": "Manufacturing",
        },
    )
    assert r_bad.status_code == 422
