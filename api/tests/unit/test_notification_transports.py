"""Unit tests for Email/SMS transports, ACS HMAC signing, validation, and PII masking."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest

from gorgona_booking.notifications.service import render_template, validate_and_mask_recipient
from gorgona_booking.notifications.transports import (
    AzureCommunicationEmailTransport,
    SandboxNotificationTransport,
    TransportDeliveryError,
    TwilioSmsTransport,
    build_acs_hmac_headers,
    resolve_notification_transports,
)


def test_recipient_validation_and_pii_masking() -> None:
    masked_email, hash_email = validate_and_mask_recipient("email", "Owner.One@Example.COM")
    assert masked_email == "O***@example.com"
    assert len(hash_email) == 64
    assert "Owner.One" not in masked_email

    masked_sms, hash_sms = validate_and_mask_recipient("sms", "+14155551234")
    assert masked_sms == "+14***1234"
    assert len(hash_sms) == 64

    with pytest.raises(ValueError, match="email"):
        validate_and_mask_recipient("email", "not-an-email")
    with pytest.raises(ValueError, match=r"E\.164"):
        validate_and_mask_recipient("sms", "415-555-1234")


def test_acs_hmac_headers_deterministic_signing() -> None:
    key_b64 = base64.b64encode(b"test-secret-key-32-bytes-minimum").decode("ascii")
    headers = build_acs_hmac_headers(
        endpoint="https://acs-gorgona.unitedstates.communication.azure.com",
        access_key_b64=key_b64,
        method="POST",
        path_and_query="/emails:send?api-version=2023-03-31",
        body_bytes=b'{"hello":"world"}',
        now=datetime(2026, 11, 24, 12, 0, 0, tzinfo=UTC),
    )
    assert headers["x-ms-date"] == "Tue, 24 Nov 2026 12:00:00 GMT"
    assert headers["Authorization"].startswith(
        "HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature="
    )
    assert len(headers["x-ms-content-sha256"]) == 44


def test_transport_resolution_sandbox_vs_live() -> None:
    transports, readiness = resolve_notification_transports({})
    assert isinstance(transports["email"], SandboxNotificationTransport)
    assert isinstance(transports["sms"], SandboxNotificationTransport)
    assert readiness["email"]["mode"] == "sandbox"
    assert readiness["sms"]["mode"] == "sandbox"

    live_env = {
        "GBA_NOTIFICATIONS_MODE": "live",
        "GBA_ACS_EMAIL_ENDPOINT": "https://acs.example.com",
        "GBA_ACS_EMAIL_ACCESS_KEY": base64.b64encode(b"secret").decode("ascii"),
        "GBA_ACS_EMAIL_SENDER": "DoNotReply@gorgona.example",
        "GBA_TWILIO_ACCOUNT_SID": "AC00000000000000000000000000000001",
        "GBA_TWILIO_AUTH_TOKEN": "tok_test",
        "GBA_TWILIO_FROM_NUMBER": "+14155550100",
    }
    live_transports, live_readiness = resolve_notification_transports(live_env)
    assert isinstance(live_transports["email"], AzureCommunicationEmailTransport)
    assert isinstance(live_transports["sms"], TwilioSmsTransport)
    assert live_readiness["email"]["mode"] == "live"
    assert live_readiness["sms"]["mode"] == "live"


def test_templates_and_sandbox_failure_simulation() -> None:
    subj, body = render_template(
        "booking_confirmation",
        {"business_name": "Atelier North", "reference": "BK-101", "starts_at": "2026-12-01 10:00"},
    )
    assert "Atelier North" in subj
    assert "BK-101" in body

    sbx = SandboxNotificationTransport()
    with pytest.raises(TransportDeliveryError) as transient:
        sbx.send(
            channel="email", recipient="u@fail.invalid", subject="s", body="b", idempotency_key="k1"
        )
    assert transient.value.retryable is True

    with pytest.raises(TransportDeliveryError) as permanent:
        sbx.send(
            channel="email",
            recipient="u@reject.invalid",
            subject="s",
            body="b",
            idempotency_key="k2",
        )
    assert permanent.value.retryable is False
