"""Notification transports: Sandbox, ACS Email (HMAC-SHA256), and Twilio SMS."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Protocol

import httpx


class TransportDeliveryError(RuntimeError):
    """Raised when an external notification provider rejects or fails delivery."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class DeliveryReceipt:
    provider_name: str
    provider_message_id: str
    sandbox: bool


class NotificationTransport(Protocol):
    name: str
    sandbox: bool

    def send(
        self,
        *,
        channel: str,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> DeliveryReceipt: ...


class SandboxNotificationTransport:
    """Zero-spend deterministic delivery sink for CI, staging, and sandbox tests."""

    name = "sandbox"
    sandbox = True

    def send(
        self,
        *,
        channel: str,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> DeliveryReceipt:
        if recipient.endswith("@fail.invalid") or recipient.endswith("0000"):
            raise TransportDeliveryError("Simulated transient provider error", retryable=True)
        if recipient.endswith("@reject.invalid"):
            raise TransportDeliveryError("Simulated permanent bounce", retryable=False)
        raw = f"{channel}:{idempotency_key}:{subject}:{len(body)}".encode()
        digest = hashlib.sha256(raw).hexdigest()[:16]
        return DeliveryReceipt(
            provider_name=self.name,
            provider_message_id=f"sbx-{channel}-{digest}-{uuid.uuid4().hex[:8]}",
            sandbox=True,
        )


def build_acs_hmac_headers(
    *,
    endpoint: str,
    access_key_b64: str,
    method: str,
    path_and_query: str,
    body_bytes: bytes,
    now: datetime | None = None,
) -> dict[str, str]:
    """Build Azure Communication Services REST HMAC-SHA256 authentication headers."""
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("ACS endpoint must use https://")
    host = parsed.netloc
    utc_now = (now or datetime.now(UTC)).astimezone(UTC)
    date_header = format_datetime(utc_now, usegmt=True)
    content_hash = base64.b64encode(hashlib.sha256(body_bytes).digest()).decode("ascii")
    string_to_sign = f"{method.upper()}\n{path_and_query}\n{date_header};{host};{content_hash}"
    secret = base64.b64decode(access_key_b64)
    signature = base64.b64encode(
        hmac.new(secret, string_to_sign.encode(), hashlib.sha256).digest()
    ).decode("ascii")
    signed = "x-ms-date;host;x-ms-content-sha256"
    return {
        "Content-Type": "application/json",
        "x-ms-date": date_header,
        "x-ms-content-sha256": content_hash,
        "Authorization": f"HMAC-SHA256 SignedHeaders={signed}&Signature={signature}",
    }


class AzureCommunicationEmailTransport:
    """Azure Communication Services Email REST transport (API 2023-03-31)."""

    name = "azure_communication_email"
    sandbox = False

    def __init__(
        self, *, endpoint: str, access_key: str, sender_address: str, timeout_s: float = 15.0
    ) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("ACS Email endpoint must use https://")
        self._endpoint = endpoint.rstrip("/")
        self._access_key = access_key
        self._sender = sender_address
        self._timeout_s = timeout_s

    def send(
        self,
        *,
        channel: str,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> DeliveryReceipt:
        if channel != "email":
            raise TransportDeliveryError("ACS Email transport only supports email", retryable=False)
        path_and_query = "/emails:send?api-version=2023-03-31"
        payload = {
            "senderAddress": self._sender,
            "content": {"subject": subject, "plainText": body},
            "recipients": {"to": [{"address": recipient}]},
        }
        body_bytes = json.dumps(payload, separators=(",", ":")).encode()
        headers = build_acs_hmac_headers(
            endpoint=self._endpoint,
            access_key_b64=self._access_key,
            method="POST",
            path_and_query=path_and_query,
            body_bytes=body_bytes,
        )
        headers["repeatability-request-id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key))
        try:
            resp = httpx.post(
                f"{self._endpoint}{path_and_query}",
                content=body_bytes,
                headers=headers,
                timeout=self._timeout_s,
            )
            if resp.status_code >= 400:
                retryable = resp.status_code >= 500 or resp.status_code == 429
                raise TransportDeliveryError(
                    f"ACS Email HTTP {resp.status_code}", retryable=retryable
                )
            data = resp.json() if resp.content else {}
            msg_id = str(data.get("id") or resp.headers.get("x-ms-request-id") or uuid.uuid4())
            return DeliveryReceipt(
                provider_name=self.name, provider_message_id=msg_id, sandbox=False
            )
        except httpx.HTTPError as exc:
            raise TransportDeliveryError(f"ACS Email network error: {exc}", retryable=True) from exc


class TwilioSmsTransport:
    """Twilio Programmable SMS REST transport (2010-04-01)."""

    name = "twilio_sms"
    sandbox = False

    def __init__(
        self, *, account_sid: str, auth_token: str, from_number: str, timeout_s: float = 15.0
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._timeout_s = timeout_s

    def send(
        self,
        *,
        channel: str,
        recipient: str,
        subject: str,
        body: str,
        idempotency_key: str,
    ) -> DeliveryReceipt:
        if channel != "sms":
            raise TransportDeliveryError("Twilio SMS transport only supports sms", retryable=False)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        try:
            resp = httpx.post(
                url,
                data={"To": recipient, "From": self._from_number, "Body": body},
                auth=(self._account_sid, self._auth_token),
                timeout=self._timeout_s,
            )
            if resp.status_code >= 400:
                retryable = resp.status_code >= 500 or resp.status_code == 429
                raise TransportDeliveryError(
                    f"Twilio SMS HTTP {resp.status_code}", retryable=retryable
                )
            data = resp.json() if resp.content else {}
            return DeliveryReceipt(
                provider_name=self.name,
                provider_message_id=str(data.get("sid") or uuid.uuid4()),
                sandbox=False,
            )
        except httpx.HTTPError as exc:
            raise TransportDeliveryError(
                f"Twilio SMS network error: {exc}", retryable=True
            ) from exc


def resolve_notification_transports(
    env: dict[str, str] | None = None,
) -> tuple[dict[str, NotificationTransport], dict[str, dict[str, object]]]:
    """Return active transports per channel plus truthful readiness diagnostics."""
    source = env if env is not None else dict(os.environ)
    mode = (source.get("GBA_NOTIFICATIONS_MODE") or "sandbox").strip().lower()
    sandbox = SandboxNotificationTransport()

    acs_missing = [
        k
        for k in ("GBA_ACS_EMAIL_ENDPOINT", "GBA_ACS_EMAIL_ACCESS_KEY", "GBA_ACS_EMAIL_SENDER")
        if not source.get(k, "").strip()
    ]
    twilio_missing = [
        k
        for k in ("GBA_TWILIO_ACCOUNT_SID", "GBA_TWILIO_AUTH_TOKEN", "GBA_TWILIO_FROM_NUMBER")
        if not source.get(k, "").strip()
    ]

    email_transport: NotificationTransport = sandbox
    if mode == "live" and not acs_missing:
        email_transport = AzureCommunicationEmailTransport(
            endpoint=source["GBA_ACS_EMAIL_ENDPOINT"].strip(),
            access_key=source["GBA_ACS_EMAIL_ACCESS_KEY"].strip(),
            sender_address=source["GBA_ACS_EMAIL_SENDER"].strip(),
        )

    sms_transport: NotificationTransport = sandbox
    if mode == "live" and not twilio_missing:
        sms_transport = TwilioSmsTransport(
            account_sid=source["GBA_TWILIO_ACCOUNT_SID"].strip(),
            auth_token=source["GBA_TWILIO_AUTH_TOKEN"].strip(),
            from_number=source["GBA_TWILIO_FROM_NUMBER"].strip(),
        )

    readiness: dict[str, dict[str, object]] = {
        "email": {
            "mode": "live" if not email_transport.sandbox else "sandbox",
            "provider": email_transport.name,
            "production_credentials_configured": len(acs_missing) == 0,
            "missing_production_env_vars": acs_missing,
        },
        "sms": {
            "mode": "live" if not sms_transport.sandbox else "sandbox",
            "provider": sms_transport.name,
            "production_credentials_configured": len(twilio_missing) == 0,
            "missing_production_env_vars": twilio_missing,
        },
    }
    return {"email": email_transport, "sms": sms_transport}, readiness
