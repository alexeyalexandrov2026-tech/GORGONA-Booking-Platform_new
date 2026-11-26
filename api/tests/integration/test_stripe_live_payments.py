"""Integration tests for Stripe Live/Test Checkout sessions, signed webhooks, and FORCE RLS."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership
from gorgona_booking.payments import stripe_service
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_user
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


def _sign(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    signed = f"{ts}.{payload.decode('utf-8')}".encode()
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


def _owner(owner_conn: psycopg.Connection, tenant_id: UUID, label: str) -> FakeUser:
    user = seed_user(owner_conn, f"stripe-live-{label}-{uuid7()}")
    add_membership(owner_conn, tenant_id=tenant_id, user_id=user.user_id, role="owner")
    return user


async def test_stripe_checkout_webhook_sync_refund_and_tenant_isolation(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    webhook_secret = "whsec_live_integration_test_secret_123"
    monkeypatch.setenv("GBA_STRIPE_SECRET_KEY", "rk_live_integration_test_key_123")
    monkeypatch.setenv("GBA_STRIPE_PUBLISHABLE_KEY", "pk_live_integration_test_key_123")
    monkeypatch.setenv("GBA_STRIPE_WEBHOOK_SECRET", webhook_secret)

    owner_a = _owner(owner_conn, world.a.tenant_id, "owner-a")
    owner_b = _owner(owner_conn, world.b.tenant_id, "owner-b")
    h_a = idp.bearer(owner_a.subject, email=owner_a.email)
    h_b = idp.bearer(owner_b.subject, email=owner_b.email)

    cfg = await client.get("/v1/payments/config")
    assert cfg.status_code == 200
    cfg_json = cfg.json()
    assert cfg_json["stripe_configured"] is True
    assert cfg_json["stripe_livemode"] is True
    assert cfg_json["webhook_configured"] is True
    assert cfg_json["currency"] == "USD"

    def fake_create(**kwargs: Any) -> dict[str, Any]:
        return {
            "id": "cs_live_test_001",
            "url": "https://checkout.stripe.com/c/pay/cs_live_test_001",
            "livemode": True,
            "payment_intent": None,
        }

    def fake_refund(**kwargs: Any) -> str:
        return "re_live_test_001"

    monkeypatch.setattr(stripe_service, "_create_stripe_session_sync", fake_create)
    monkeypatch.setattr(stripe_service, "_create_stripe_refund_sync", fake_refund)

    created = await client.post(
        f"/v1/businesses/{world.a.tenant_id}/payments/checkout-sessions",
        headers=h_a,
        json={
            "amount_cents": 25000,
            "description": "Freight dispatch invoice #401",
            "reference_kind": "invoice",
            "reference_id": "INV-401",
            "customer_name": "Acme Corp",
            "customer_email": "ap@acme.test",
            "allow_ach": True,
            "success_url": "https://gorgona.example.test/integrations/?payment=success",
            "cancel_url": "https://gorgona.example.test/integrations/?payment=cancelled",
        },
    )
    assert created.status_code == 201, created.text
    rec = created.json()
    assert rec["status"] == "open"
    assert rec["livemode"] is True
    assert rec["amount_cents"] == 25000
    assert rec["currency"] == "USD"

    # Cross-tenant isolation: tenant B sees zero sessions from tenant A.
    list_b = await client.get(
        f"/v1/businesses/{world.b.tenant_id}/payments/sessions",
        headers=h_b,
    )
    assert list_b.status_code == 200
    assert list_b.json() == []

    # Signed Stripe webhook marks session paid idempotently.
    event_body = json.dumps(
        {
            "id": "evt_live_checkout_001",
            "type": "checkout.session.completed",
            "livemode": True,
            "data": {
                "object": {
                    "id": "cs_live_test_001",
                    "payment_intent": "pi_live_001",
                    "payment_status": "paid",
                    "metadata": {"gorgona_tenant_id": str(world.a.tenant_id)},
                }
            },
        }
    ).encode("utf-8")

    bad_sig = await client.post(
        "/v1/webhooks/stripe",
        content=event_body,
        headers={"stripe-signature": _sign(event_body, "whsec_wrong")},
    )
    assert bad_sig.status_code == 400

    first_wh = await client.post(
        "/v1/webhooks/stripe",
        content=event_body,
        headers={"stripe-signature": _sign(event_body, webhook_secret)},
    )
    assert first_wh.status_code == 200, first_wh.text
    assert first_wh.json() == {
        "received": True,
        "event_type": "checkout.session.completed",
        "applied": True,
    }

    replay_wh = await client.post(
        "/v1/webhooks/stripe",
        content=event_body,
        headers={"stripe-signature": _sign(event_body, webhook_secret)},
    )
    assert replay_wh.status_code == 200
    assert replay_wh.json()["applied"] is False

    listed_a = await client.get(
        f"/v1/businesses/{world.a.tenant_id}/payments/sessions",
        headers=h_a,
    )
    assert listed_a.status_code == 200
    items = listed_a.json()
    assert len(items) == 1
    assert items[0]["status"] == "paid"
    assert items[0]["provider_payment_intent_id"] == "pi_live_001"

    # Refund transitions paid -> refunded.
    refunded = await client.post(
        f"/v1/businesses/{world.a.tenant_id}/payments/sessions/{rec['id']}/refund",
        headers=h_a,
        json={"reason": "requested_by_customer"},
    )
    assert refunded.status_code == 200, refunded.text
    assert refunded.json()["status"] == "refunded"
