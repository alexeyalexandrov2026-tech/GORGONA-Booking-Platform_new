"""Unit tests for AMARKAL v2.9.0 B2B SaaS engine (CSV, search, scanner, Connect, A2A)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid7

import httpx
import pytest
from fastapi import FastAPI

from gorgona_booking.api import connectors as connectors_api
from gorgona_booking.api.search import escape_like_pattern
from gorgona_booking.business.counterparty_import import parse_counterparty_csv
from gorgona_booking.business.file_errors import (
    FileMalwareDetectedError,
    FileScanningNotConfiguredError,
)
from gorgona_booking.business.malware_scanner import (
    is_file_uploads_enabled,
    scan_upload_if_required,
)
from gorgona_booking.payments.stripe_service import (
    StripeRuntimeConfig,
    create_stripe_connect_onboarding_link,
    fetch_stripe_connect_status,
)

pytestmark = pytest.mark.anyio


def test_parse_counterparty_csv_maps_aliases_and_validates_rows() -> None:
    sample = (
        "Company Name,E-mail,Phone Number,Type,Role,EIN\n"
        "Apex Freight LLC,billing@apexfreight.us,+1 214-555-0188,business,vendor,12-3456789\n"
        "Elena Vance,elena@vance.io,+1 305-555-0192,individual,client,\n"
        "Broken Email Corp,not-an-email,+1 555-010-1111,organization,customer,\n"
        ",empty@name.io,,,\n"
    )
    rows = parse_counterparty_csv(sample)
    assert len(rows) == 4

    r1 = rows[0]
    assert r1[1] is not None
    assert r1[1].display_name == "Apex Freight LLC"
    assert r1[1].kind == "organization"
    assert r1[1].roles == ("supplier",)
    assert r1[1].tax_id == "12-3456789"

    r2 = rows[1]
    assert r2[1] is not None
    assert r2[1].kind == "person"
    assert r2[1].roles == ("customer",)

    # Invalid email and missing name are surfaced as row errors without aborting the batch
    assert rows[2][1] is None
    assert "e-mail" in rows[2][6].lower()
    assert rows[3][1] is None
    assert "missing" in rows[3][6].lower()


def test_escape_like_pattern_escapes_sql_wildcards() -> None:
    assert escape_like_pattern("100%_test\\x") == "%100\\%\\_test\\\\x%"


async def test_malware_scanner_fail_closed_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GBA_MALWARE_SCANNER_URL", raising=False)
    assert is_file_uploads_enabled("local") is True
    assert is_file_uploads_enabled("production") is False
    with pytest.raises(FileScanningNotConfiguredError):
        await scan_upload_if_required(
            b"%PDF-1.7", environment="production", media_type="application/pdf"
        )

    monkeypatch.setenv("GBA_MALWARE_SCANNER_URL", "https://scanner.internal/scan")
    assert is_file_uploads_enabled("production") is True

    monkeypatch.setattr(
        "gorgona_booking.business.malware_scanner._scan_bytes_sync",
        lambda _url, _content, *, media_type: None,
    )
    await scan_upload_if_required(
        b"%PDF-1.7", environment="production", media_type="application/pdf"
    )

    def _flag(_url: str, _content: bytes, *, media_type: str) -> None:
        raise FileMalwareDetectedError("flagged")

    monkeypatch.setattr("gorgona_booking.business.malware_scanner._scan_bytes_sync", _flag)
    with pytest.raises(FileMalwareDetectedError):
        await scan_upload_if_required(
            b"EICAR", environment="production", media_type="application/pdf"
        )


async def test_a2a_agent_card_exposes_governance_and_mcp_endpoint() -> None:
    app = FastAPI()
    app.include_router(connectors_api.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/.well-known/agent.json")
    assert res.status_code == 200
    body = res.json()
    assert body["governance"]["human_in_the_loop"] is True
    assert body["governance"]["zero_unapproved_writes"] is True
    assert body["governance"]["platform_transaction_commission_bps"] == 0
    assert "search_business_records" in body["capabilities"]
    assert "draft_payment_proposal" in body["capabilities"]


async def test_stripe_connect_onboarding_and_status_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = StripeRuntimeConfig(
        secret_key="sk_test_123456",
        publishable_key="pk_test_123456",
        webhook_secret=None,
        paypal_configured=False,
    )
    monkeypatch.setattr(
        "stripe.Account.create",
        lambda **_kwargs: SimpleNamespace(id="acct_1TestExpress12345"),
    )
    monkeypatch.setattr(
        "stripe.AccountLink.create",
        lambda **_kwargs: SimpleNamespace(url="https://connect.stripe.com/setup/e/test_123"),
    )
    monkeypatch.setattr(
        "stripe.Account.retrieve",
        lambda _acct_id, **_kwargs: SimpleNamespace(
            charges_enabled=True, payouts_enabled=True, details_submitted=True
        ),
    )

    acct_id, link_url = await create_stripe_connect_onboarding_link(
        config=cfg,
        tenant_id=uuid7(),
        business_name="Apex Freight LLC",
        existing_account_id=None,
        email="ops@apexfreight.us",
        return_url="https://www.amarkal-platform.com/integrations/?connect=return",
        refresh_url="https://www.amarkal-platform.com/integrations/?connect=refresh",
    )
    assert acct_id == "acct_1TestExpress12345"
    assert link_url.startswith("https://connect.stripe.com/")

    st = await fetch_stripe_connect_status(config=cfg, account_id=acct_id)
    assert st.connected is True
    assert st.charges_enabled is True
    assert st.payouts_enabled is True
    assert st.details_submitted is True

    empty_st = await fetch_stripe_connect_status(config=cfg, account_id=None)
    assert empty_st.connected is False
    assert empty_st.account_id is None
