"""Unit tests for Stripe US Live/Test Checkout, webhook signatures, and status mapping."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from uuid import uuid7

import pytest

from gorgona_booking.payments.stripe_service import (
    StripePaymentError,
    StripeRuntimeConfig,
    map_stripe_session_status,
    validate_connected_account,
    validate_return_url,
    verify_and_parse_stripe_webhook,
)


def _sign(payload: bytes, secret: str, *, ts: int | None = None) -> str:
    stamp = int(time.time()) if ts is None else ts
    signed = f"{stamp}.{payload.decode('utf-8')}".encode()
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={stamp},v1={digest}"


def test_runtime_config_detects_live_and_test_keys() -> None:
    live = StripeRuntimeConfig.from_env(
        {
            "GBA_STRIPE_SECRET_KEY": "rk_live_example_123456",
            "GBA_STRIPE_PUBLISHABLE_KEY": "pk_live_example_123456",
            "GBA_STRIPE_WEBHOOK_SECRET": "whsec_example_123456",
        }
    )
    assert live.configured is True
    assert live.livemode is True
    assert live.webhook_configured is True
    assert live.publishable_key == "pk_live_example_123456"

    test_cfg = StripeRuntimeConfig.from_env(
        {
            "GBA_STRIPE_SECRET_KEY": "sk_test_example_123456",
            "GBA_STRIPE_PUBLISHABLE_KEY": "pk_test_example_123456",
        }
    )
    assert test_cfg.configured is True
    assert test_cfg.livemode is False
    assert test_cfg.webhook_configured is False

    empty = StripeRuntimeConfig.from_env({})
    assert empty.configured is False
    assert empty.livemode is False
    assert empty.webhook_configured is False


def test_validate_return_url_and_connected_account() -> None:
    assert validate_return_url("https://app.gorgona.ai/integrations/?payment=success").startswith(
        "https://"
    )
    assert validate_return_url("http://127.0.0.1:8000/integrations/").startswith("http://127.0.0.1")
    with pytest.raises(StripePaymentError):
        validate_return_url("http://example.com/insecure")
    with pytest.raises(StripePaymentError):
        validate_return_url("javascript:alert(1)")

    assert validate_connected_account("acct_1UJtGO0mkpVWlKYX") == "acct_1UJtGO0mkpVWlKYX"
    assert validate_connected_account("  ") is None
    with pytest.raises(StripePaymentError):
        validate_connected_account("bad_account")


def test_verify_and_parse_checkout_completed_webhook() -> None:
    tenant_id = uuid7()
    secret = "whsec_test_unit_secret_0123456789"
    body = json.dumps(
        {
            "id": "evt_live_001",
            "type": "checkout.session.completed",
            "livemode": True,
            "data": {
                "object": {
                    "id": "cs_live_abc123",
                    "payment_intent": "pi_live_xyz789",
                    "payment_status": "paid",
                    "metadata": {"gorgona_tenant_id": str(tenant_id)},
                }
            },
        }
    ).encode("utf-8")
    sig = _sign(body, secret)

    parsed = verify_and_parse_stripe_webhook(body, sig, secret)
    assert parsed.event_id == "evt_live_001"
    assert parsed.event_type == "checkout.session.completed"
    assert parsed.livemode is True
    assert parsed.tenant_id == tenant_id
    assert parsed.provider_session_id == "cs_live_abc123"
    assert parsed.provider_payment_intent_id == "pi_live_xyz789"
    assert parsed.target_status == "paid"

    with pytest.raises(StripePaymentError) as exc:
        verify_and_parse_stripe_webhook(body, _sign(body, "whsec_wrong_secret"), secret)
    assert exc.value.code == "INVALID_SIGNATURE"


def test_verify_and_parse_charge_refunded_webhook() -> None:
    tenant_id = uuid7()
    secret = "whsec_test_unit_secret_0123456789"
    body = json.dumps(
        {
            "id": "evt_live_ref_002",
            "type": "charge.refunded",
            "livemode": True,
            "data": {
                "object": {
                    "id": "ch_live_123",
                    "payment_intent": "pi_live_xyz789",
                    "refunded": True,
                    "metadata": {"gorgona_tenant_id": str(tenant_id)},
                }
            },
        }
    ).encode("utf-8")
    parsed = verify_and_parse_stripe_webhook(body, _sign(body, secret), secret)
    assert parsed.tenant_id == tenant_id
    assert parsed.provider_payment_intent_id == "pi_live_xyz789"
    assert parsed.target_status == "refunded"


def test_map_stripe_session_status_preserves_refunded() -> None:
    assert (
        map_stripe_session_status(
            stripe_status="complete", payment_status="paid", current_status="open"
        )
        == "paid"
    )
    assert (
        map_stripe_session_status(
            stripe_status="expired", payment_status="unpaid", current_status="open"
        )
        == "expired"
    )
    assert (
        map_stripe_session_status(
            stripe_status="complete", payment_status="paid", current_status="refunded"
        )
        == "refunded"
    )
