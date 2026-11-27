"""Unit tests for AMARKAL v2.8.0 Sprint A security, reliability, and honesty fixes."""

from __future__ import annotations

from collections import deque
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid7

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse

from gorgona_booking.ai_assistant.service import (
    CustomerAssistantContext,
    RecommendedSlot,
    synthesize_customer_assistant,
)
from gorgona_booking.api.framing import FramingPolicyMiddleware
from gorgona_booking.api.self_service import (
    enforce_sliding_window_rate_limit,
    extract_client_ip,
)
from gorgona_booking.connectors.service import validate_public_webhook_url
from gorgona_booking.customer.contracts import (
    BookingRules,
    BootstrapView,
    BrandingView,
    CancellationPolicy,
)
from gorgona_booking.payments.stripe_service import (
    StripePaymentError,
    _create_stripe_session_sync,
    verify_tenant_connected_account,
)

pytestmark = pytest.mark.anyio


def _fake_request(*, xff: str | None = None, client_host: str = "198.51.100.9") -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("ascii")))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/v1/onboarding/ai-blueprint",
        "headers": headers,
        "client": (client_host, 44321),
    }
    return Request(scope)


def test_extract_client_ip_blocks_left_side_xff_spoofing() -> None:
    # Behind GCP LB (1 trusted proxy hop): <spoofed>, <real_client>, <gclb_ip>
    req = _fake_request(xff="1.1.1.1, 203.0.113.42, 34.49.10.5")
    assert extract_client_ip(req) == "203.0.113.42"

    # Malformed spoofed prefix ignored cleanly
    req_bad = _fake_request(xff="not-an-ip, 203.0.113.77, 34.49.10.5")
    assert extract_client_ip(req_bad) == "203.0.113.77"

    # No XFF falls back to peer address
    req_direct = _fake_request(xff=None, client_host="198.51.100.9")
    assert extract_client_ip(req_direct) == "198.51.100.9"


def test_sliding_window_rate_limit_enforces_and_bounds_memory() -> None:
    store: dict[str, deque[float]] = {}
    # Seed 1,050 stale IPs to verify bounded eviction
    for idx in range(1050):
        store[f"198.51.{idx // 256}.{idx % 256}"] = deque([10.0])

    enforce_sliding_window_rate_limit(
        store,
        key="203.0.113.10",
        window_seconds=300.0,
        max_requests=2,
        detail="Too many requests",
        now=500.0,
    )
    assert len(store) == 1
    enforce_sliding_window_rate_limit(
        store,
        key="203.0.113.10",
        window_seconds=300.0,
        max_requests=2,
        detail="Too many requests",
        now=501.0,
    )
    with pytest.raises(HTTPException) as exc:
        enforce_sliding_window_rate_limit(
            store,
            key="203.0.113.10",
            window_seconds=300.0,
            max_requests=2,
            detail="Too many requests",
            now=502.0,
        )
    assert exc.value.status_code == 429


async def test_framing_middleware_caches_public_html_and_protects_app_html() -> None:
    app = FastAPI()
    app.add_middleware(FramingPolicyMiddleware, allow_loopback=True)

    @app.get("/")
    async def home() -> HTMLResponse:
        return HTMLResponse("<h1>AMARKAL</h1>")

    @app.get("/legal/privacy/")
    async def privacy() -> HTMLResponse:
        return HTMLResponse("<h1>Privacy</h1>")

    @app.get("/overview/")
    async def overview() -> HTMLResponse:
        return HTMLResponse("<h1>Overview</h1>")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r_home = await client.get("/")
        r_priv = await client.get("/legal/privacy/")
        r_app = await client.get("/overview/")

    assert r_home.headers["cache-control"] == "public, max-age=300, stale-while-revalidate=600"
    assert r_priv.headers["cache-control"] == "public, max-age=300, stale-while-revalidate=600"
    assert r_app.headers["cache-control"] == "private, no-store"
    assert r_home.headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://hooks.example.com/test",
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://169.254.169.254/latest/meta-data/",
        "https://10.0.0.12/internal",
        "https://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_webhook_ssrf_guard_rejects_private_and_non_https_urls(bad_url: str) -> None:
    with pytest.raises(ValueError, match="Webhook URL"):
        validate_public_webhook_url(bad_url, resolve_dns=False)


def test_webhook_ssrf_guard_allows_public_https_url() -> None:
    assert (
        validate_public_webhook_url("https://hooks.zapier.com/hooks/catch/1/a/", resolve_dns=False)
        == "https://hooks.zapier.com/hooks/catch/1/a/"
    )


class _FakeCursor:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _sql: str, _params: tuple[Any, ...]) -> None:
        return None

    async def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _FakeConn:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def cursor(self, **_kwargs: Any) -> _FakeCursor:
        return _FakeCursor(self._row)


async def test_verify_tenant_connected_account_blocks_cross_tenant_spoofing() -> None:
    tenant_id = uuid7()
    conn_missing: Any = _FakeConn(None)
    assert (
        await verify_tenant_connected_account(
            conn_missing, tenant_id=tenant_id, connected_account_id=None
        )
        is None
    )
    with pytest.raises(StripePaymentError) as exc_missing:
        await verify_tenant_connected_account(
            conn_missing, tenant_id=tenant_id, connected_account_id="acct_1SpoofedAccount99"
        )
    assert exc_missing.value.status_code == 403
    assert exc_missing.value.code == "CONNECTED_ACCOUNT_NOT_AUTHORIZED"

    conn_other: Any = _FakeConn({"config_masked": {"stripe_account_id": "acct_1TenantOwned123"}})
    with pytest.raises(StripePaymentError) as exc_mismatch:
        await verify_tenant_connected_account(
            conn_other, tenant_id=tenant_id, connected_account_id="acct_1OtherTenant999"
        )
    assert exc_mismatch.value.status_code == 403

    assert (
        await verify_tenant_connected_account(
            conn_other, tenant_id=tenant_id, connected_account_id="acct_1TenantOwned123"
        )
        == "acct_1TenantOwned123"
    )


def test_create_stripe_session_passes_automatic_tax_only_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict[str, Any]] = []

    def _fake_create(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return SimpleNamespace(
            id="cs_test_123",
            url="https://checkout.stripe.com/c/pay/cs_test_123",
            livemode=False,
            payment_intent="pi_test_123",
        )

    monkeypatch.setattr("stripe.checkout.Session.create", _fake_create)
    base_kwargs: dict[str, Any] = {
        "api_key": "sk_test_123",
        "record_id": uuid7(),
        "tenant_id": uuid7(),
        "amount_cents": 10000,
        "description": "Charter deposit",
        "reference_kind": "invoice",
        "reference_id": "INV-1",
        "customer_email": "guest@example.com",
        "success_url": "https://www.amarkal-platform.com/integrations/?payment=success",
        "cancel_url": "https://www.amarkal-platform.com/integrations/?payment=cancelled",
        "allow_ach": True,
        "connected_account_id": None,
    }
    _create_stripe_session_sync(**base_kwargs, automatic_tax=False)
    _create_stripe_session_sync(**base_kwargs, automatic_tax=True)
    assert "automatic_tax" not in captured[0]
    assert captured[1]["automatic_tax"] == {"enabled": True}


async def test_synthesize_customer_assistant_runs_outside_db(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GBA_AI_PROVIDER", "grounded")
    boot = BootstrapView(
        name="Harbor Yacht Co.",
        branding=BrandingView(),
        locations=[],
        variants=[],
        add_ons=[],
        artists=[],
        rules=BookingRules(
            version=1,
            slot_interval_minutes=30,
            advance_notice_minutes=60,
            max_days_ahead=60,
        ),
        cancellation=CancellationPolicy(
            version=1,
            summary="Free cancellation up to 24h before departure.",
        ),
    )
    slot = RecommendedSlot(
        location_id=uuid7(),
        location_name="Miami Marina",
        variant_id=uuid7(),
        service_name="Sunset Charter",
        variant_name="3 Hours",
        resource_id=uuid7(),
        resource_name="Capt. Reyes",
        day=date(2026, 11, 28),
        start_at=datetime(2026, 11, 28, 22, 0, tzinfo=UTC),
        end_at=datetime(2026, 11, 29, 1, 0, tzinfo=UTC),
        timezone="America/New_York",
        price_cents=145000,
        currency="USD",
        duration_minutes=180,
    )
    ctx = CustomerAssistantContext(
        boot=boot,
        ai_assistant_tone="friendly",
        message="Sunset charter tomorrow",
        language="en",
        ranked_variants=[],
        recommended_slots=[slot],
        waitlist_suggested=False,
    )
    res = await synthesize_customer_assistant(ctx)
    assert res.engine == "grounded"
    assert res.business_name == "Harbor Yacht Co."
    assert len(res.recommended_slots) == 1
    assert "Sunset Charter" in res.reply
