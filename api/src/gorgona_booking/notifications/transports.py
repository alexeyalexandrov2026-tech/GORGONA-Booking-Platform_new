"""Notification transports: Sandbox, ACS Email (HMAC-SHA256), and Twilio SMS."""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import os
import smtplib
import ssl
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Protocol


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


def _https_post(
    *,
    host: str,
    path_and_query: str,
    body_bytes: bytes,
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[int, bytes, dict[str, str]]:
    """Perform a strict TLS HTTPS POST using stdlib http.client (zero extra runtime deps)."""
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, 443, timeout=timeout_s, context=ctx)
    try:
        conn.request("POST", path_and_query, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        resp_headers = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, raw, resp_headers
    finally:
        conn.close()


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
        parsed = urllib.parse.urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("ACS Email endpoint must use https://")
        self._endpoint = endpoint.rstrip("/")
        self._host = parsed.netloc
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
            code, raw, resp_headers = _https_post(
                host=self._host,
                path_and_query=path_and_query,
                body_bytes=body_bytes,
                headers=headers,
                timeout_s=self._timeout_s,
            )
            if code >= 400:
                retryable = code >= 500 or code == 429
                raise TransportDeliveryError(f"ACS Email HTTP {code}", retryable=retryable)
            data = json.loads(raw.decode()) if raw else {}
            msg_id = str(data.get("id") or resp_headers.get("x-ms-request-id") or uuid.uuid4())
            return DeliveryReceipt(
                provider_name=self.name, provider_message_id=msg_id, sandbox=False
            )
        except (OSError, http.client.HTTPException) as exc:
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
        path_and_query = f"/2010-04-01/Accounts/{self._account_sid}/Messages.json"
        form = urllib.parse.urlencode(
            {"To": recipient, "From": self._from_number, "Body": body}
        ).encode()
        basic = base64.b64encode(f"{self._account_sid}:{self._auth_token}".encode()).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            code, raw, _ = _https_post(
                host="api.twilio.com",
                path_and_query=path_and_query,
                body_bytes=form,
                headers=headers,
                timeout_s=self._timeout_s,
            )
            if code >= 400:
                retryable = code >= 500 or code == 429
                raise TransportDeliveryError(f"Twilio SMS HTTP {code}", retryable=retryable)
            data = json.loads(raw.decode()) if raw else {}
            return DeliveryReceipt(
                provider_name=self.name,
                provider_message_id=str(data.get("sid") or uuid.uuid4()),
                sandbox=False,
            )
        except (OSError, http.client.HTTPException) as exc:
            raise TransportDeliveryError(
                f"Twilio SMS network error: {exc}", retryable=True
            ) from exc


class SmtpEmailTransport:
    """Cloud-agnostic TLS SMTP transport (SendGrid, Postmark, Mailgun, Google Workspace)."""

    name = "smtp_email"
    sandbox = False

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender_address: str,
        timeout_s: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
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
            raise TransportDeliveryError("SMTP transport only supports email", retryable=False)
        msg = EmailMessage()
        msg["From"] = self._sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg["X-Idempotency-Key"] = idempotency_key
        msg.set_content(body)
        ctx = ssl.create_default_context()
        try:
            if self._port == 465:
                with smtplib.SMTP_SSL(
                    self._host, self._port, timeout=self._timeout_s, context=ctx
                ) as client:
                    client.login(self._username, self._password)
                    client.send_message(msg)
            else:
                with smtplib.SMTP(self._host, self._port, timeout=self._timeout_s) as client:
                    client.starttls(context=ctx)
                    client.login(self._username, self._password)
                    client.send_message(msg)
            msg_id = f"smtp-{uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:16]}"
            return DeliveryReceipt(
                provider_name=self.name, provider_message_id=msg_id, sandbox=False
            )
        except smtplib.SMTPResponseException as exc:
            retryable = 400 <= exc.smtp_code < 500
            raise TransportDeliveryError(
                f"SMTP error {exc.smtp_code}", retryable=retryable
            ) from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise TransportDeliveryError(f"SMTP network error: {exc}", retryable=True) from exc


def resolve_notification_transports(
    env: dict[str, str] | None = None,
) -> tuple[dict[str, NotificationTransport], dict[str, dict[str, object]]]:
    """Return active transports per channel plus truthful readiness diagnostics."""
    source = env if env is not None else dict(os.environ)
    mode = (source.get("GBA_NOTIFICATIONS_MODE") or "sandbox").strip().lower()
    sandbox = SandboxNotificationTransport()

    email_provider = (source.get("GBA_EMAIL_PROVIDER") or "acs").strip().lower()
    acs_missing = [
        k
        for k in ("GBA_ACS_EMAIL_ENDPOINT", "GBA_ACS_EMAIL_ACCESS_KEY", "GBA_ACS_EMAIL_SENDER")
        if not source.get(k, "").strip()
    ]
    smtp_missing = [
        k
        for k in (
            "GBA_SMTP_HOST",
            "GBA_SMTP_PORT",
            "GBA_SMTP_USERNAME",
            "GBA_SMTP_PASSWORD",
            "GBA_SMTP_SENDER",
        )
        if not source.get(k, "").strip()
    ]
    email_missing = smtp_missing if email_provider == "smtp" else acs_missing
    twilio_missing = [
        k
        for k in ("GBA_TWILIO_ACCOUNT_SID", "GBA_TWILIO_AUTH_TOKEN", "GBA_TWILIO_FROM_NUMBER")
        if not source.get(k, "").strip()
    ]

    email_transport: NotificationTransport = sandbox
    if mode == "live" and email_provider == "smtp" and not smtp_missing:
        email_transport = SmtpEmailTransport(
            host=source["GBA_SMTP_HOST"].strip(),
            port=int(source["GBA_SMTP_PORT"].strip()),
            username=source["GBA_SMTP_USERNAME"].strip(),
            password=source["GBA_SMTP_PASSWORD"].strip(),
            sender_address=source["GBA_SMTP_SENDER"].strip(),
        )
    elif mode == "live" and email_provider != "smtp" and not acs_missing:
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
            "production_credentials_configured": len(email_missing) == 0,
            "missing_production_env_vars": email_missing,
        },
        "sms": {
            "mode": "live" if not sms_transport.sandbox else "sandbox",
            "provider": sms_transport.name,
            "production_credentials_configured": len(twilio_missing) == 0,
            "missing_production_env_vars": twilio_missing,
        },
    }
    return {"email": email_transport, "sms": sms_transport}, readiness
